import argparse

import psycopg2


def parse_args():
    parser = argparse.ArgumentParser(description="Drop and recreate a local Odoo database.")
    parser.add_argument("database", help="Database name to recreate")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", default=5432, type=int)
    parser.add_argument("--user", default="odoo")
    parser.add_argument("--password", default="odoo")
    parser.add_argument("--owner", default="odoo")
    parser.add_argument("--template", default="template0")
    parser.add_argument("--lc-collate", default="English_India.1252")
    parser.add_argument("--lc-ctype", default="English_India.1252")
    return parser.parse_args()


def main():
    args = parse_args()
    conn = psycopg2.connect(
        dbname="postgres",
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
    )
    conn.autocommit = True
    try:
        with conn.cursor() as cr:
            cr.execute(
                "select pg_terminate_backend(pid) "
                "from pg_stat_activity where datname = %s",
                (args.database,),
            )
            cr.execute(f'drop database if exists "{args.database}"')
            cr.execute(
                f'create database "{args.database}" '
                f'with owner "{args.owner}" '
                f'template "{args.template}" '
                f"lc_collate '{args.lc_collate}' "
                f"lc_ctype '{args.lc_ctype}'"
            )
    finally:
        conn.close()

    print(f"Recreated database: {args.database}")


if __name__ == "__main__":
    main()
