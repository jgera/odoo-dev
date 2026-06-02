import argparse
import getpass
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ODOO_SERVER = ROOT / "odoo-server"
DEFAULT_CONFIG = ROOT / "odoo.conf"

sys.path.insert(0, str(ODOO_SERVER))

import odoo  # noqa: E402
from odoo import api, SUPERUSER_ID  # noqa: E402
from odoo.modules.registry import Registry  # noqa: E402
from odoo.tools import config  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(
        description="Interactively change an Odoo user's password using odoo.conf."
    )
    parser.add_argument(
        "-c",
        "--config",
        default=str(DEFAULT_CONFIG),
        help=f"Path to odoo.conf. Defaults to {DEFAULT_CONFIG}",
    )
    parser.add_argument(
        "-d",
        "--database",
        help="Odoo database name. If omitted, the script prompts when needed.",
    )
    return parser.parse_args()


def load_odoo_config(config_path):
    if not Path(config_path).is_file():
        raise SystemExit(f"Config file not found: {config_path}")
    config.parse_config(["-c", config_path])


def config_value(name, default=None):
    value = config.get(name)
    return default if value in (None, False, "") else value


def list_databases():
    import psycopg2

    host = config_value("db_host", "localhost")
    port = config_value("db_port", 5432)
    user = config_value("db_user")
    password = config_value("db_password")

    conn = psycopg2.connect(
        dbname="postgres",
        host=host,
        port=port,
        user=user,
        password=password,
    )
    try:
        with conn.cursor() as cr:
            cr.execute(
                """
                SELECT datname
                  FROM pg_database
                 WHERE datistemplate = false
                   AND datallowconn = true
                 ORDER BY datname
                """
            )
            return [row[0] for row in cr.fetchall()]
    finally:
        conn.close()


def choose_database(cli_database):
    if cli_database:
        return cli_database

    configured = config_value("db_name")
    if configured:
        if isinstance(configured, str):
            names = [name.strip() for name in configured.split(",") if name.strip()]
        else:
            names = list(configured)
        if len(names) == 1:
            return names[0]

    databases = list_databases()
    if not databases:
        raise SystemExit("No PostgreSQL databases found.")
    if len(databases) == 1:
        return databases[0]

    print("\nAvailable databases:")
    for index, database in enumerate(databases, start=1):
        print(f"{index}. {database}")

    while True:
        choice = input("Select database number: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(databases):
            return databases[int(choice) - 1]
        print("Invalid database selection.")


def list_users(database):
    registry = Registry(database)
    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {"active_test": False})
        users = env["res.users"].sudo().with_context(active_test=False).search(
            [], order="id"
        )
        return [
            {
                "id": user.id,
                "name": user.name or "",
                "login": user.login or "",
                "active": user.active,
            }
            for user in users
        ]


def choose_user(users):
    if not users:
        raise SystemExit("No users found in this database.")

    print("\nUsers:")
    for index, user in enumerate(users, start=1):
        status = "active" if user["active"] else "inactive"
        print(f"{index}. [{user['id']}] {user['name']} <{user['login']}> ({status})")

    while True:
        choice = input("Select user number: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(users):
            return users[int(choice) - 1]
        print("Invalid user selection.")


def prompt_password():
    while True:
        password = getpass.getpass("New password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords do not match.")
            continue
        if not password:
            print("Password cannot be empty.")
            continue
        return password


def update_password(database, user_id, password):
    registry = Registry(database)
    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        user = env["res.users"].sudo().browse(user_id)
        if not user.exists():
            raise SystemExit(f"User no longer exists: {user_id}")
        user.password = password
        cr.commit()


def main():
    args = parse_args()
    load_odoo_config(args.config)

    database = choose_database(args.database)
    users = list_users(database)
    selected_user = choose_user(users)
    password = prompt_password()

    update_password(database, selected_user["id"], password)
    print(
        f"Password updated for {selected_user['login']} "
        f"in database {database}."
    )


if __name__ == "__main__":
    main()
