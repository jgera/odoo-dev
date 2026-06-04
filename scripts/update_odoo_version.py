import argparse
import subprocess
import sys

from odoo_env import DEFAULT_VERSION, addons_path, get_paths


def parse_args():
    parser = argparse.ArgumentParser(
        description="Update one local Odoo version checkout and its venv.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--odoo-version",
        "--version",
        default=DEFAULT_VERSION,
        help="Odoo version folder under versions/",
    )
    parser.add_argument(
        "--database",
        "-d",
        help="Database to update when --update-modules is provided",
    )
    parser.add_argument(
        "--update-modules",
        "-u",
        help="Comma-separated modules to update after pulling, for example all",
    )
    parser.add_argument(
        "--no-pull",
        action="store_true",
        help="Skip git pull",
    )
    parser.add_argument(
        "--no-requirements",
        action="store_true",
        help="Skip pip requirements install",
    )
    parser.add_argument(
        "--no-watchdog",
        action="store_true",
        help="Skip installing watchdog for developer autoreload",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without running them",
    )
    return parser.parse_args()


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def command_text(command):
    return subprocess.list2cmdline([str(part) for part in command])


def run_command(command, cwd=None, dry_run=False):
    print(command_text(command))
    if dry_run:
        return 0
    return subprocess.call([str(part) for part in command], cwd=str(cwd) if cwd else None)


def ensure_paths(paths):
    required = [
        (paths.odoo_server, "Odoo source checkout"),
        (paths.venv_python, "version Python"),
        (paths.config, "version config"),
    ]
    missing = [f"{label}: {path}" for path, label in required if not path.exists()]
    if missing:
        return fail("Missing required paths:\n  " + "\n  ".join(missing))
    return 0


def main():
    args = parse_args()
    paths = get_paths(args.odoo_version)
    status = ensure_paths(paths)
    if status:
        return status

    requirements = paths.odoo_server / "requirements.txt"

    print(f"Odoo update: {paths.version}")
    print(f"Source:      {paths.odoo_server}")
    print(f"Python:      {paths.venv_python}")
    print()

    if not args.no_pull:
        status = run_command(["git", "-C", paths.odoo_server, "pull", "--ff-only"], dry_run=args.dry_run)
        if status:
            return status

    if not args.no_requirements:
        if not requirements.exists():
            return fail(f"Requirements file not found: {requirements}")
        status = run_command(
            [paths.venv_python, "-m", "pip", "install", "-r", requirements],
            dry_run=args.dry_run,
        )
        if status:
            return status

    if not args.no_watchdog:
        status = run_command(
            [paths.venv_python, "-m", "pip", "install", "watchdog"],
            dry_run=args.dry_run,
        )
        if status:
            return status

    if args.update_modules:
        if not args.database:
            return fail("--database is required when --update-modules is provided.")
        status = run_command(
            [
                paths.venv_python,
                paths.odoo_bin,
                "-c",
                paths.config,
                "--addons-path",
                addons_path(paths),
                "--data-dir",
                paths.data_dir,
                "-d",
                args.database,
                "-u",
                args.update_modules,
                "--stop-after-init",
            ],
            cwd=paths.root,
            dry_run=args.dry_run,
        )
        if status:
            return status

    print()
    print(f"Update completed for Odoo {paths.version}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
