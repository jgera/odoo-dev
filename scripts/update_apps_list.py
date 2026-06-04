import argparse

from odoo_env import DEFAULT_VERSION, add_odoo_to_path, addons_path, get_paths


def parse_args():
    parser = argparse.ArgumentParser(description="Refresh Odoo's Apps list.")
    parser.add_argument(
        "--odoo-version",
        "--version",
        default=DEFAULT_VERSION,
        help="Odoo version folder under versions/",
    )
    parser.add_argument("-d", "--database", required=True, help="Odoo database name")
    parser.add_argument(
        "-c",
        "--config",
        help="Path to odoo.conf. Defaults to versions/<version>/odoo.conf",
    )
    parser.add_argument(
        "--module",
        default="subscription_package",
        help="Module name to report after refreshing the list",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    paths = get_paths(args.odoo_version)
    config_path = args.config or paths.config
    add_odoo_to_path(paths)

    import odoo
    import odoo.service.server
    from odoo import api, SUPERUSER_ID
    from odoo.modules.registry import Registry
    from odoo.tools import config

    config.parse_config([
        "-c",
        str(config_path),
        "--addons-path",
        addons_path(paths),
        "--data-dir",
        str(paths.data_dir),
    ])
    odoo.service.server.load_server_wide_modules()

    registry = Registry(args.database)
    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        env["ir.module.module"].sudo().update_list()
        module = env["ir.module.module"].sudo().search([("name", "=", args.module)], limit=1)
        cr.commit()

        if not module:
            print(f"Apps list refreshed. Module not found: {args.module}")
            return 1

        print("Apps list refreshed.")
        print(f"Module: {module.name}")
        print(f"Display name: {module.shortdesc}")
        print(f"State: {module.state}")
        print(f"Application: {module.application}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
