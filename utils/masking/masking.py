from pathlib import Path
from typing import Any, Iterable

import yaml

from ..constants import MASKING_TAG_LIST
from ..schema_reader import read_asset_schema


MASKING_FORMATS_PATH = Path(__file__).parent / "formats.yml"


def _load_masking_formats() -> dict[str, Any]:
    """Load masking formats and default expressions from the YAML configuration.

    Returns:
        The parsed masking configuration, or an empty mapping when the YAML file
        contains no values.
    """
    with MASKING_FORMATS_PATH.open("r", encoding="utf-8") as formats_file:
        return yaml.safe_load(formats_file) or {}


def get_masking_expression(data_type: str, masking_format: str | None) -> str:
    """Resolve a ClickHouse masking expression for a column.

    Args:
        data_type: ClickHouse data type of the column.
        masking_format: Optional named format from the masking configuration.

    Returns:
        A ClickHouse masking expression using ``$column_name`` as its placeholder.
    """
    formats = _load_masking_formats()
    named_formats = formats.get("formats", {})

    if masking_format and masking_format in named_formats:
        return named_formats[masking_format]

    for default in formats.get("defaults", {}).values():
        if data_type in default.get("data_types", []):
            return default["expression"]

    return "'******'"


def is_maskable(column: dict[str, Any]) -> bool:
    """Return whether a dbt column is tagged as PII or sensitive.

    Args:
        column: dbt column metadata containing optional masking tags.

    Returns:
        True when the column has a ``pii`` or ``sensitive`` tag; otherwise False.
    """
    meta = column.get("meta", {}) or {}
    masking = meta.get("masking", {}) or {}
    tags = masking.get("tags", meta.get("tags", [])) or []

    if isinstance(tags, str):
        tags = [tags]

    return any(str(tag).lower() in MASKING_TAG_LIST for tag in tags)


def _schema_nodes(schema_reader: dict[str, Any]) -> Iterable[dict[str, Any]]:
    """Collect model and snapshot nodes from a loaded dbt schema mapping.

    Args:
        schema_reader: Parsed dbt schema containing models and snapshots.

    Returns:
        An iterable containing model and snapshot node mappings.
    """
    nodes = []
    for node_group in (schema_reader.get("models", []), schema_reader.get("snapshots", [])):
        nodes.extend(node_group.values() if isinstance(node_group, dict) else node_group)
    return nodes


def get_maskable_columns(schema_reader: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract tagged columns and resolved masks from models and snapshots.

    Args:
        schema_reader: Parsed dbt schema containing models and snapshots.

    Returns:
        A list of metadata dictionaries for columns tagged as PII or sensitive.
    """
    maskable_columns = []

    for node in _schema_nodes(schema_reader):
        node_name = node.get("name")
        columns = node.get("columns", []) or []
        if isinstance(columns, dict):
            columns = [dict(column, name=column_name) for column_name, column in columns.items()]

        for column in columns:
            column_name = column.get("name")
            if not is_maskable(column):
                continue

            data_type = column.get("data_type", "String")
            meta = column.get("meta", {}) or {}
            masking = meta.get("masking", {}) or {}
            masking_format = masking.get("format", meta.get("masking_format"))
            maskable_columns.append(
                {
                    "node_name": node_name,
                    "column_name": column_name,
                    "data_type": data_type,
                    "masking_format": masking_format,
                    "masking_expression": get_masking_expression(data_type, masking_format),
                }
            )

    return maskable_columns


def masking_policy_name(
    product_id: str, asset_name: str, tenant_code: int, column_name: str
) -> str:
    """Build a unique ClickHouse masking-policy name.

    Args:
        product_id: Identifier of the data product.
        asset_name: Name of the data asset.
        tenant_code: Numeric tenant code.
        column_name: Column protected by the policy.

    Returns:
        The generated masking-policy name.
    """
    return f"{product_id}_{asset_name}_tenant_{tenant_code}_{column_name}_masking_policy"


def create_masking_policy_ddl(
    product_id: str,
    database: str,
    asset_name: str,
    tenant_code: int,
    role_name: str,
    column: dict[str, Any],
) -> str:
    """Generate a ClickHouse masking policy for a masked tenant role.

    Args:
        product_id: Identifier of the data product.
        database: ClickHouse database containing the asset.
        asset_name: Name of the data asset.
        tenant_code: Numeric tenant code.
        role_name: Masked role receiving the policy.
        column: Column and resolved expression to mask.

    Returns:
        A ClickHouse CREATE MASKING POLICY statement.
    """
    column_name = column["column_name"]
    expression = column["masking_expression"].replace("$column_name", column_name)

    return (
        f"CREATE MASKING POLICY IF NOT EXISTS "
        f"{masking_policy_name(product_id, asset_name, tenant_code, column_name)} "
        f"ON {database}.{asset_name} "
        f"UPDATE {column_name} = {expression} "
        f"TO {role_name}; "
    )


def generate_masking_policy_ddls(
    data_products_dir: str | Path, contract: dict[str, Any]
) -> list[str]:
    """Generate masking policies separately from warehouse access DDL.

    Args:
        data_products_dir: Root directory containing data product directories.
        contract: Parsed data contract containing assets and tenant access rules.

    Returns:
        An ordered list of masking-policy DDL statements for masked roles.
    """
    product = contract["data_product"]
    product_id = product["id"]
    ddls = []

    for asset in product["data_assets"]:
        schema = read_asset_schema(data_products_dir, contract, asset)
        maskable_columns = [
            column
            for column in get_maskable_columns(schema)
            if column["node_name"] == asset["name"]
        ]
        if not maskable_columns:
            continue

        tenant_codes = {
            tenant_access["tenant_code"]
            for tenant_access in asset.get("access", [])
            if any(
                user.get("is_masked", False)
                for user in tenant_access.get("users", [])
            )
        }
        for tenant_code in sorted(tenant_codes):
            role_name = (
                f"{product_id}_{asset['name']}_tenant_{tenant_code}_masked_reader"
            )
            for column in maskable_columns:
                ddls.append(
                    create_masking_policy_ddl(
                        product_id,
                        asset["database"],
                        asset["name"],
                        tenant_code,
                        role_name,
                        column,
                    )
                )

    return ddls
