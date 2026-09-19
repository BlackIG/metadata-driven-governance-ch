import glob
import os
import argparse
import re

from .warehouse_access_builder import (
    execute_ddls,
    generate_warehouse_access_ddls,
    load_contract,
)
from .masking.masking import generate_masking_policy_ddls


def display_ddl(ddl):
    """Print DDL without exposing passwords embedded in CREATE USER statements."""
    return re.sub(
        r"(IDENTIFIED WITH sha256_password BY ')[^']*(';)",
        r"\1<redacted>\2",
        ddl,
    )


def find_contracts(data_products_dir):
    """Find data contract files in each data product directory.

    Args:
        data_products_dir: Root directory containing data product directories.

    Returns:
        A list of paths to discovered data contract files.
    """
    pattern = os.path.join(data_products_dir, "**", "data_contract.yml")
    return glob.glob(pattern, recursive=True)


def main(execute=False):
    """Generate and print access-control DDL for all configured data products.

    Returns:
        A list of generated DDL statements, or None when no contracts are found.
    """
    data_products_dir = "/usr/app/data_products"
    contract_paths = find_contracts(data_products_dir)

    if not contract_paths:
        print(f"No data contracts found under {data_products_dir}")
        return

    all_warehouse_access_ddls = []
    all_masking_policy_ddls = []
    default_roles = {}
    for path in contract_paths:
        contract = load_contract(path)
        product_id = contract["data_product"]["id"]
        print(f"-- {product_id} ({path})")
        warehouse_access_ddls = generate_warehouse_access_ddls(contract, default_roles)
        masking_policy_ddls = generate_masking_policy_ddls(data_products_dir, contract)

        print("-- warehouse access DDL")
        all_warehouse_access_ddls.extend(warehouse_access_ddls)
        for ddl in warehouse_access_ddls:
            print(display_ddl(ddl))

        print("-- masking policy DDL")
        all_masking_policy_ddls.extend(masking_policy_ddls)
        for ddl in masking_policy_ddls:
            print(display_ddl(ddl))

    for user_name, role_names in default_roles.items():
        default_role_ddl = f"ALTER USER {user_name} DEFAULT ROLE {', '.join(role_names)}; "
        all_warehouse_access_ddls.append(default_role_ddl)
        print(display_ddl(default_role_ddl))

    all_ddls = all_warehouse_access_ddls + all_masking_policy_ddls
    if execute:
        execute_ddls(
            all_ddls,
            host=os.environ["CLICKHOUSE_CLOUD_HOST"],
            user=os.environ.get("CLICKHOUSE_CLOUD_USER", "default"),
            password=os.environ["CLICKHOUSE_CLOUD_PASSWORD"],
        )
        print(f"Executed {len(all_ddls)} DDL statements successfully.")

    return {
        "warehouse_access_ddls": all_warehouse_access_ddls,
        "masking_policy_ddls": all_masking_policy_ddls,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate ClickHouse access-control DDL.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the generated DDL against ClickHouse after printing it.",
    )
    main(execute=parser.parse_args().execute)
