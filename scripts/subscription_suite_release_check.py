import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    "subscription_suite",
    "subscription_suite_billing",
    "subscription_suite_dunning",
    "subscription_suite_portal",
    "subscription_suite_reports",
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run repeatable Odoo 19 Subscription Suite release checks."
    )
    parser.add_argument(
        "-d",
        "--database",
        default="odoo19_subscription_demo",
        help="Database used for install, upgrade, and tagged tests.",
    )
    parser.add_argument(
        "--static-only",
        action="store_true",
        help="Run compile and diff checks without connecting to PostgreSQL.",
    )
    parser.add_argument(
        "--fresh-install",
        action="store_true",
        help="Recreate the database and install the complete suite.",
    )
    parser.add_argument(
        "--confirm-recreate",
        action="store_true",
        help="Required confirmation for destructive --fresh-install database recreation.",
    )
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="Run all five addon test tags after install or upgrade.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing them.",
    )
    return parser.parse_args()


def run(command, dry_run=False):
    print("\n>", subprocess.list2cmdline([str(part) for part in command]))
    if not dry_run:
        subprocess.run(command, cwd=ROOT, check=True)


def odoo_command(database, operation, modules, log_level="info"):
    return [
        sys.executable,
        "scripts/dev_odoo.py",
        "--odoo-version",
        "19.0",
        "-d",
        database,
        operation,
        ",".join(modules),
        "--stop-after-init",
        "--no-browser",
        "--no-cron",
        "--no-dev",
        f"--log-level={log_level}",
    ]


def main():
    args = parse_args()
    if args.fresh_install and not args.confirm_recreate:
        raise SystemExit(
            "--fresh-install drops and recreates the selected database. "
            "Pass --confirm-recreate to continue."
        )

    addon_paths = [
        ROOT / "versions" / "19.0" / "custom_addons" / module
        for module in MODULES
    ]
    run([sys.executable, "-m", "compileall", "scripts", *addon_paths], args.dry_run)
    run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "diff", "--check"],
        args.dry_run,
    )

    if args.static_only:
        print("\nRelease static checks completed.")
        return

    if args.fresh_install:
        run(
            [sys.executable, "scripts/recreate_odoo_database.py", args.database],
            args.dry_run,
        )
        run(odoo_command(args.database, "-i", MODULES), args.dry_run)
    else:
        run(odoo_command(args.database, "-u", MODULES), args.dry_run)

    if args.run_tests:
        for module in MODULES:
            command = odoo_command(args.database, "-u", (module,), "test")
            command.extend(["--", "--test-enable", "--test-tags", f"/{module}"])
            run(command, args.dry_run)

    print("\nSubscription Suite release checks completed.")


if __name__ == "__main__":
    main()
