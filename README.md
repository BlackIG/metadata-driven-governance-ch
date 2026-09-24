# Chilaka Data Security Demo

A tenant-aware ClickHouse data platform demonstrating:

- ClickHouse Cloud as the warehouse
- dbt seed, staging, and mart transformations
- Tenant-specific users and role-based access
- Row-level tenant isolation
- Column-level masking for subscriber data
- Direct Claude Desktop MCP connections for three tenant users
- Automated terminal tests for tenant access

## Model Approach
![model approach image](model-approach.jpg)

## Architecture

```text
CSV seeds
  -> dbt raw tables in ClickHouse Cloud
  -> dbt staging models
  -> subscriber order summary mart
  -> tenant roles and row policies
  -> Claude Desktop via mcp-clickhouse
```

The repository has two data product layers:

```text
data_products/
  ingestion_data_products/
    Orders/
    Subscribers/
  mart_data_products/
    subscriber_order_summary/
```

ClickHouse Cloud contains these logical databases:

- `raw`: seeded source tables
- `staging`: tenant-aware staging models
- `mart`: subscriber order aggregates
- `test_failures`: optional dbt failure storage

## Prerequisites

Install or create the following before starting:

1. Docker Desktop with Docker Compose support.
2. A ClickHouse Cloud account and an active service. A trial service is sufficient.
3. ClickHouse Cloud MCP enabled for the service if you want to use the managed MCP endpoint.
4. A ClickHouse Cloud SQL username and password with permission to create databases, tables, users, roles, and policies. The initial setup uses the `default` user.
5. `uv` installed and available on your PATH for Claude Desktop MCP. Verify it with:

   ```powershell
   uv --version
   ```

6. Claude Desktop installed if you want to query ClickHouse through MCP.

## 1. Clone and open the repository

Open PowerShell and move to the repository root:

```powershell
Set-Location "C:\path\to\data_security_demo"
```

All commands in this README should be run from this directory unless stated otherwise.

## 2. Get the ClickHouse Cloud connection details

In ClickHouse Cloud:

1. Open the service.
2. Select **Connect**.
3. Choose the SQL or HTTPS connection details.
4. Copy the hostname. It should look similar to:

   ```text
   abc123.eu-west-2.aws.clickhouse.cloud
   ```

Use the database connection hostname, not the ClickHouse Cloud console URL.

The normal Cloud connection settings are:

```text
Port: 8443
Secure: true
Database: default
```

## 3. Create the local environment file

Copy the example file:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and replace the placeholders:

```env
CLICKHOUSE_CLOUD_HOST=your-real-service-host.region.aws.clickhouse.cloud
CLICKHOUSE_CLOUD_PORT=8443
CLICKHOUSE_CLOUD_SECURE=true
CLICKHOUSE_CLOUD_USER=default
CLICKHOUSE_CLOUD_PASSWORD=your-clickhouse-cloud-password
CLICKHOUSE_CLOUD_MCP_URL=https://mcp.clickhouse.cloud/mcp
CLICKHOUSE_MCP_PASSWORD_TENANT_1=Tenant1McpPassword1!
CLICKHOUSE_MCP_PASSWORD_TENANT_2=Tenant2McpPassword2!
CLICKHOUSE_MCP_PASSWORD_TENANT_3=Tenant3McpPassword3!
```

Tenant passwords must satisfy the password policy configured by ClickHouse Cloud. Use at least one uppercase character, one number, and one special character.

Never commit `.env`. It is ignored by Git.

## 4. Build the dbt Docker image

Build the project image and install its Python dependencies:

```powershell
docker compose build dbt
```

The image contains dbt, the ClickHouse adapter, `clickhouse-connect`, and PyYAML. The image does not contain ClickHouse itself; the warehouse is ClickHouse Cloud.

## 5. Test the Cloud connection

Run dbt debug for the Subscribers product:

```powershell
docker compose run --rm dbt dbt debug `
  --project-dir /usr/app/data_products/ingestion_data_products/Subscribers/dbt `
  --profiles-dir /usr/app/data_products/ingestion_data_products/Subscribers/dbt
```

Because all profiles now default to the Cloud target, the output should show:

```text
target='cloud'
secure: True
Connection test: [OK connection ok]
```

## 6. Load and build the ingestion products

Run both ingestion products sequentially with a full refresh:

```powershell
docker compose run --rm dbt dbt build --full-refresh `
  --project-dir /usr/app/data_products/ingestion_data_products/Subscribers/dbt `
  --profiles-dir /usr/app/data_products/ingestion_data_products/Subscribers/dbt

docker compose run --rm dbt dbt build --full-refresh `
  --project-dir /usr/app/data_products/ingestion_data_products/Orders/dbt `
  --profiles-dir /usr/app/data_products/ingestion_data_products/Orders/dbt
```

This creates or refreshes:

```text
raw.raw_tenant_1_subscribers
raw.raw_tenant_2_subscribers
raw.raw_tenant_3_subscribers
raw.raw_tenant_1_orders
raw.raw_tenant_2_orders
raw.raw_tenant_3_orders
staging.stg_subscribers
staging.stg_orders
```

Each build runs its model and data tests.

## 7. Build the mart product

Build the subscriber order summary mart after the ingestion products succeed:

```powershell
docker compose run --rm dbt dbt build --full-refresh `
  --project-dir /usr/app/data_products/mart_data_products/subscriber_order_summary/dbt `
  --profiles-dir /usr/app/data_products/mart_data_products/subscriber_order_summary/dbt
```

The mart creates:

```text
mart.subscriber_order_summary
```

It contains one row per tenant subscriber with:

- Order counts
- Completed and cancelled order counts
- Total units
- Gross and average order values
- First and last order dates
- Latest order status
- Selected subscriber identity fields

The identity fields are documented as personal identifiable information in the schema descriptions and must not be divulged. They are intentionally not tagged for masking in this mart schema.

## 8. Generate and apply access control

The access builder discovers contracts across both data product layers. By default it only prints DDL:

```powershell
docker compose run --rm dbt python -m utils.main
```

Review the output before applying it.

To execute the generated DDL against ClickHouse Cloud:

```powershell
docker compose run --rm dbt python -m utils.main --execute
```

If you ran an earlier version of this project, remove the old policies by runing `DROP` commands on the sql console, before applying new ones. Then run the access builder command again.

The command creates or updates:

- Tenant roles
- Tenant users
- Role-based `SELECT` grants
- Tenant row policies
- Subscriber column masking policies
- Additive default roles for each tenant user

Permissions are assigned to roles. Users receive roles; users do not receive direct `SELECT` grants.

The tenant users are:

```text
tenant_1_mcp_user
tenant_2_mcp_user
tenant_3_mcp_user
```

## 9. Verify users and grants in ClickHouse Cloud

In the ClickHouse Cloud SQL Console, run:

```sql
SELECT name
FROM system.users
WHERE name LIKE 'tenant_%_mcp_user'
ORDER BY name;
```

Inspect a tenant user's roles:

```sql
SHOW GRANTS FOR tenant_1_mcp_user;
SHOW GRANTS FOR tenant_2_mcp_user;
SHOW GRANTS FOR tenant_3_mcp_user;
```

Inspect tenant row policies:

```sql
SELECT database, table, name, storage
FROM system.row_policies
WHERE database IN ('staging', 'mart')
ORDER BY database, table, name;
```

## 10. Run the terminal tenant access tests

The test script is located at:

```text
user_tests/test_tenant_access.py
```

Run it for each tenant:

```powershell
docker compose run --rm dbt python /usr/app/user_tests/test_tenant_access.py --tenant 1
docker compose run --rm dbt python /usr/app/user_tests/test_tenant_access.py --tenant 2
docker compose run --rm dbt python /usr/app/user_tests/test_tenant_access.py --tenant 3
```

Expected behavior:

- Tenant 1 receives only tenant 1 rows and masked subscriber columns.
- Tenant 2 receives only tenant 2 rows and masked subscriber columns.
- Tenant 3 receives only tenant 3 rows and unmasked subscriber columns because its contract sets `is_masked: false`.

## 11. Configure Claude Desktop

The repository includes a template at:

```text
user_tests/claude/claude_desktop_config.json
```

Copy the `mcpServers` entries into your local Claude Desktop configuration. On Windows, Claude Desktop usually opens the file through **Settings > Developer > Edit Config**. The file is commonly located at:

```text
%APPDATA%\Claude\claude_desktop_config.json
```

The configuration format is:

```json
{
  "mcpServers": {
    "clickhouse-tenant-1": {
      "command": "uv",
      "args": [
        "run",
        "--with",
        "mcp-clickhouse",
        "--python",
        "3.12",
        "mcp-clickhouse"
      ],
      "env": {
        "CLICKHOUSE_HOST": "your-real-service-host.region.aws.clickhouse.cloud",
        "CLICKHOUSE_PORT": "8443",
        "CLICKHOUSE_SECURE": "true",
        "CLICKHOUSE_VERIFY": "true",
        "CLICKHOUSE_CONNECT_TIMEOUT": "30",
        "CLICKHOUSE_USER": "tenant_1_mcp_user",
        "CLICKHOUSE_PASSWORD": "your-tenant-1-password"
      }
    }
  }
}
```

The repository template contains placeholders only. Replace them with the real Cloud host and the corresponding tenant password. Add the tenant 2 and tenant 3 entries from the same template if you want all three connections.

After saving the Claude config:

1. Fully restart Claude Desktop.
2. Open the MCP or Connectors section.
3. Confirm the ClickHouse tenant server is connected.
4. Select the desired tenant server.
5. Ask Claude to list databases or query `staging.stg_subscribers`.

Example prompt:

```text
Query staging.stg_subscribers and return the user_id, username, phone, company_email, and salary columns. Confirm that every row belongs to the connected tenant.
```

## 12. Direct tenant query examples

The same access model can be tested with SQL over HTTPS, without Claude:

```sql
SELECT
    tenant_code,
    user_id,
    username,
    phone,
    company_email,
    name,
    salary
FROM staging.stg_subscribers
ORDER BY user_id;
```

Run this using a tenant's database credentials. Row policies restrict the result to that tenant, and masking policies affect masked tenant roles.

## Troubleshooting

### dbt connects to the wrong target

Check the output for:

```text
target='cloud'
```

The profiles are configured to default to Cloud. Do not use `--target dev`; there is no local ClickHouse service in the cleaned Cloud-only Compose setup.

### `Database staging does not exist`

Run the Subscribers and Orders builds first. dbt creates the `raw`, `staging`, and `mart` databases as models and seeds are built.

### Password policy error

Tenant passwords must satisfy the ClickHouse Cloud password policy. Update the three `CLICKHOUSE_MCP_PASSWORD_TENANT_*` values in `.env`, then rerun:

```powershell
docker compose run --rm dbt python -m utils.main --execute
```

### Claude cannot find `uv`

Find the executable:

```powershell
where.exe uv
```

Replace `"uv"` in the Claude config with the full path if Claude Desktop does not inherit your PATH.

### Claude connects but shows the wrong tenant

Select the correct MCP server entry. Each entry is configured with a different ClickHouse database user.

## Security notes

- Do not commit `.env`.
- Do not put real passwords in the repository's Claude template.
- Use a dedicated ClickHouse administrative user for provisioning in production.
- Use least-privilege tenant users for normal MCP queries.
- Review every SQL tool call made by an AI assistant.
- The mart identity fields are documented as PII and must not be divulged.
