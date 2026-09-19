def get_mcp_password_env_name(user_name):
    """Return the environment variable containing a tenant user password."""
    tenant_number = user_name.removeprefix("tenant_").removesuffix("_mcp_user")
    return f"CLICKHOUSE_MCP_PASSWORD_TENANT_{tenant_number}"
