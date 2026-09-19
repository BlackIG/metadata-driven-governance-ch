import argparse
import os

import clickhouse_connect


MASKED_COLUMNS = (
    "phone",
    "company_email",
    "name",
    "national_id",
    "address",
    "date_of_birth",
    "age",
    "salary",
)
UNMASKED_COLUMNS = ("tenant_code", "user_id", "username", "timezone", "loaded_at")


def get_connection():
    """Create a ClickHouse Cloud connection from environment settings."""
    return clickhouse_connect.get_client(
        host=os.environ["CLICKHOUSE_CLOUD_HOST"],
        port=int(os.environ.get("CLICKHOUSE_CLOUD_PORT", "8443")),
        username=os.environ["CLICKHOUSE_TEST_USER"],
        password=os.environ["CLICKHOUSE_TEST_PASSWORD"],
        secure=os.environ.get("CLICKHOUSE_CLOUD_SECURE", "true").lower() == "true",
    )


def run_test(tenant_number):
    """Query Subscribers and verify tenant isolation for one tenant user."""
    user_name = f"tenant_{tenant_number}_mcp_user"
    password_name = f"CLICKHOUSE_MCP_PASSWORD_TENANT_{tenant_number}"
    os.environ["CLICKHOUSE_TEST_USER"] = user_name
    os.environ["CLICKHOUSE_TEST_PASSWORD"] = os.environ[password_name]
    columns = UNMASKED_COLUMNS + MASKED_COLUMNS
    query = (
        f"SELECT {', '.join(columns)} "
        "FROM staging.stg_subscribers "
        "ORDER BY user_id"
    )

    with get_connection() as client:
        rows = client.query(query).result_rows

    if not rows:
        raise AssertionError(f"No rows returned for {user_name}")

    tenant_index = columns.index("tenant_code")
    unexpected_tenants = {row[tenant_index] for row in rows if row[tenant_index] != tenant_number}
    if unexpected_tenants:
        raise AssertionError(f"Unexpected tenant rows returned: {unexpected_tenants}")

    print(f"PASS: {user_name} returned {len(rows)} row(s) for tenant {tenant_number}")
    print(f"Unmasked columns: {', '.join(UNMASKED_COLUMNS)}")
    print(f"Masked columns: {', '.join(MASKED_COLUMNS)}")
    for row in rows:
        print(row)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test tenant access to Subscribers.")
    parser.add_argument("--tenant", type=int, choices=(1, 2, 3), required=True)
    args = parser.parse_args()
    run_test(args.tenant)
