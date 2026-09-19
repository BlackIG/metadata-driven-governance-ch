import os
from pathlib import Path
from typing import Any

import yaml

from .constants import SCHEMA_TAG_LIST


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML document from disk.

    Args:
        path: Path to the YAML document.

    Returns:
        The parsed YAML mapping, or an empty mapping when the document is empty.
    """
    with path.open("r", encoding="utf-8") as yaml_file:
        return yaml.safe_load(yaml_file) or {}


def find_product_directory(data_products_dir: Path, product_name: str) -> Path:
    """Find a data product directory using a case-insensitive name match.

    Args:
        data_products_dir: Root directory containing data product directories.
        product_name: Name of the product directory to find.

    Returns:
        The matching product directory.

    Raises:
        FileNotFoundError: If no matching product directory exists.
    """
    product_name = product_name.casefold()
    for root, directories, _ in os.walk(data_products_dir, followlinks=False):
        for directory in directories:
            if directory.casefold() == product_name:
                return Path(root) / directory
    raise FileNotFoundError(f"Data product directory not found: {product_name}")


def find_product_schema(product_directory: Path, product_name: str) -> Path:
    """Find a product schema YAML under its dbt model schema directories.

    Args:
        product_directory: Root directory of the data product.
        product_name: Name used for the schema filename, without ``.yml``.

    Returns:
        The matching schema path.

    Raises:
        FileNotFoundError: If no matching schema file exists.
    """
    expected_name = Path(product_name).stem.casefold()
    models_directory = product_directory / "dbt" / "models"

    for schema_tag in SCHEMA_TAG_LIST:
        schema_directory = models_directory / schema_tag
        if not schema_directory.is_dir():
            continue
        for schema_path in schema_directory.glob("*.yml"):
            if schema_path.stem.casefold() == expected_name:
                return schema_path

    raise FileNotFoundError(
        f"Schema file not found for product '{product_name}' under {models_directory}"
    )


def find_asset_schema(product_directory: Path, asset: dict[str, Any]) -> Path:
    """Resolve the schema file declared by a data-contract asset.

    The declared path is used first and must exist. The resolved schema is then
    checked against the asset name and the corresponding dbt model or snapshot.

    Args:
        product_directory: Root directory of the data product.
        asset: Data-contract asset containing ``name`` and ``schema`` fields.

    Returns:
        The resolved schema path.

    Raises:
        FileNotFoundError: If the declared schema does not exist.
        ValueError: If the schema filename or dbt node does not match the asset.
    """
    declared_path = product_directory / asset["schema"]
    schema_path = declared_path.resolve()
    if not schema_path.is_file():
        raise FileNotFoundError(f"Asset schema not found: {schema_path}")

    product_name = product_directory.name
    if schema_path.stem.casefold() != Path(product_name).stem.casefold():
        raise ValueError(
            f"Schema filename '{schema_path.name}' does not match product '{product_name}'"
        )

    schema = load_yaml(schema_path)
    node_names = [
        node.get("name")
        for group in (schema.get("models", []), schema.get("snapshots", []))
        for node in (group.values() if isinstance(group, dict) else group)
    ]
    if asset["name"] not in node_names:
        raise ValueError(
            f"Asset '{asset['name']}' was not found in schema '{schema_path.name}'"
        )

    return schema_path


def read_asset_schema(data_products_dir: str | Path, contract: dict[str, Any], asset: dict[str, Any]) -> dict[str, Any]:
    """Load the dbt schema for a contract asset.

    Args:
        data_products_dir: Root directory containing data product directories.
        contract: Parsed data contract containing the product identifier.
        asset: Contract asset whose dbt schema should be loaded.

    Returns:
        The parsed schema mapping for the matching model or snapshot.
    """
    root = Path(data_products_dir)
    product_id = contract["data_product"]["id"]
    product_directory = find_product_directory(root, product_id)
    schema_path = find_asset_schema(product_directory, asset)
    return load_yaml(schema_path)
