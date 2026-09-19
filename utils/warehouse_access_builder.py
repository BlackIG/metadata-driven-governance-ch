import os

import yaml
import clickhouse_connect

from .helpers import get_mcp_password_env_name


def load_contract(path):
    """Load a YAML data contract from disk.

    Args:
        path: Path to the YAML data contract.

    Returns:
        The parsed contract mapping.
    """
    with open(path, "r") as f:
        return yaml.safe_load(f)


def masked_role_name(product_id, asset_name, tenant_code):
    """Build the masked-reader role name for a tenant data asset.

    Args:
        product_id: Identifier of the data product.
        asset_name: Name of the data asset.
        tenant_code: Numeric tenant code.

    Returns:
        The generated masked role name.
    """
    return f"{product_id}_{asset_name}_tenant_{tenant_code}_masked_reader"


def full_role_name(product_id, asset_name, tenant_code):
    """Build the full-reader role name for a tenant data asset.

    Args:
        product_id: Identifier of the data product.
        asset_name: Name of the data asset.
        tenant_code: Numeric tenant code.

    Returns:
        The generated full role name.
    """
    return f"{product_id}_{asset_name}_tenant_{tenant_code}_full_reader"


def policy_name(product_id, asset_name, tenant_code):
    """Build the row-policy name for a tenant data asset.

    Args:
        product_id: Identifier of the data product.
        asset_name: Name of the data asset.
        tenant_code: Numeric tenant code.

    Returns:
        The generated row-policy name.
    """
    return f"{product_id}_{asset_name}_tenant_{tenant_code}_scope_policy"


def create_role_ddl(role_name):
    """Generate DDL that creates a role when it does not already exist.

    Args:
        role_name: Name of the role to create.

    Returns:
        A ClickHouse CREATE ROLE statement.
    """
    return f"CREATE ROLE IF NOT EXISTS {role_name}; "


def create_user_ddl(user_name):
    """Generate DDL for a password-protected dummy user.

    Args:
        user_name: Username and dummy password for the ClickHouse user.

    Returns:
        A ClickHouse CREATE USER statement.
    """
    password_env_name = get_mcp_password_env_name(user_name)
    password = os.environ.get(password_env_name)
    if not password:
        raise RuntimeError(
            f"Missing {password_env_name}; set a ClickHouse-compliant password "
            f"before generating DDL for {user_name}."
        )
    escaped_password = password.replace("\\", "\\\\").replace("'", "\\'")
    return f"CREATE USER IF NOT EXISTS {user_name} IDENTIFIED WITH sha256_password BY '{escaped_password}'; "


def create_row_policy_ddl(product_id, database, asset_name, tenant_code, masked_role, full_role):
    """Generate a tenant-scoped ClickHouse row-policy statement.

    Args:
        product_id: Identifier of the data product.
        database: ClickHouse database containing the asset.
        asset_name: Name of the data asset.
        tenant_code: Numeric tenant code used by the row filter.
        masked_role: Role receiving the masked tenant policy.
        full_role: Role receiving the full tenant policy.

    Returns:
        A ClickHouse CREATE ROW POLICY statement.
    """
    return (
        f"CREATE ROW POLICY IF NOT EXISTS {policy_name(product_id, asset_name, tenant_code)} "
        f"ON {database}.{asset_name} "
        f"USING tenant_code = {tenant_code} "
        f"TO {masked_role}, {full_role}; "
    )


def grant_role_to_user_ddl(role_name, user_name):
    """Generate DDL that grants a role to a user.

    Args:
        role_name: Role to grant.
        user_name: User receiving the role.

    Returns:
        A ClickHouse GRANT statement.
    """
    return f"GRANT {role_name} TO {user_name}; "


def grant_select_to_role_ddl(database, asset_name, role_name):
    """Generate DDL granting SELECT access to a role on a data asset.

    Args:
        database: ClickHouse database containing the asset.
        asset_name: Name of the data asset.
        role_name: Role receiving SELECT access.

    Returns:
        A ClickHouse GRANT SELECT statement.
    """
    return f"GRANT SELECT ON {database}.{asset_name} TO {role_name}; "


def set_default_role_ddl(user_name, role_names):
    """Generate DDL that sets a user's default role.

    Args:
        user_name: User whose default role is being set.
        role_names: Roles activated by default for the user.

    Returns:
        A ClickHouse ALTER USER statement.
    """
    return f"ALTER USER {user_name} DEFAULT ROLE {', '.join(role_names)}; "


class ClickHouseDDLExecutor:
    """Execute generated DDL statements using one ClickHouse connection."""

    def __init__(self, host, user, password, port=None, secure=None):
        port = int(port or os.environ.get("CLICKHOUSE_CLOUD_PORT", "8443"))
        if secure is None:
            secure = os.environ.get("CLICKHOUSE_CLOUD_SECURE", "true").lower() == "true"
        self.client = clickhouse_connect.get_client(
            host=host,
            port=port,
            username=user,
            password=password,
            secure=secure,
        )

    def execute(self, ddls):
        """Execute DDL statements in order and stop at the first failure."""
        for index, ddl in enumerate(ddls, start=1):
            try:
                self.client.command(ddl)
            except Exception as error:
                raise RuntimeError(f"DDL statement {index} failed: {ddl}") from error

    def close(self):
        """Close the ClickHouse connection."""
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


def execute_ddls(ddls, host, user, password, port=None, secure=None):
    """Execute DDL statements against ClickHouse in order.

    Args:
        ddls: DDL statements to execute.
        host: ClickHouse hostname.
        user: ClickHouse username.
        password: ClickHouse password.
        port: ClickHouse HTTP(S) port.
        secure: Whether to use HTTPS.

    Raises:
        RuntimeError: If a DDL statement fails. Earlier statements remain applied.
    """
    with ClickHouseDDLExecutor(host, user, password, port, secure) as executor:
        executor.execute(ddls)


def generate_warehouse_access_ddls(contract, default_roles=None):
    """Generate users, roles, policies, and grants from a data contract.

    Args:
        contract: Parsed data contract containing assets and tenant access rules.

    Returns:
        An ordered list of ClickHouse DDL statements.
    """
    ddls = []
    product = contract["data_product"]
    product_id = product["id"]
    seen_users = set()
    collected_roles = {} if default_roles is None else default_roles

    for asset in product["data_assets"]:
        asset_name = asset["name"]
        database = asset["database"]
        seen_tenants = set()

        for tenant_access in asset.get("access", []):
            tenant_code = tenant_access["tenant_code"]
            masked_role = masked_role_name(product_id, asset_name, tenant_code)
            full_role = full_role_name(product_id, asset_name, tenant_code)

            if tenant_code not in seen_tenants:
                ddls.append(create_role_ddl(masked_role))
                ddls.append(create_role_ddl(full_role))
                ddls.append(create_row_policy_ddl(product_id, database, asset_name, tenant_code, masked_role, full_role))
                ddls.append(grant_select_to_role_ddl(database, asset_name, masked_role))
                ddls.append(grant_select_to_role_ddl(database, asset_name, full_role))
                seen_tenants.add(tenant_code)

            for user in tenant_access.get("users", []):
                user_name = user["name"]
                is_masked = user["is_masked"]

                if user_name not in seen_users:
                    ddls.append(create_user_ddl(user_name))
                    seen_users.add(user_name)

                target_role = masked_role if is_masked else full_role
                ddls.append(grant_role_to_user_ddl(target_role, user_name))
                collected_roles.setdefault(user_name, [])
                if target_role not in collected_roles[user_name]:
                    collected_roles[user_name].append(target_role)

    if default_roles is None:
        for user_name, role_names in collected_roles.items():
            ddls.append(set_default_role_ddl(user_name, role_names))

    return ddls
