import argparse
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = ROOT / "venv" / "Scripts" / "python.exe"
ODOO_BIN = ROOT / "odoo-server" / "odoo-bin"
CONFIG = ROOT / "odoo.conf"
ODOO_ADDONS = ROOT / "odoo-server" / "addons"
CUSTOM_ADDONS = ROOT / "custom_addons"
DEFAULT_POSTGRES_SERVICE = "postgresql-x64-18"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Development-oriented launcher for the local Odoo checkout.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("-c", "--config", default=str(CONFIG), help="Odoo config file")
    parser.add_argument("-d", "--database", help="Database name to use")
    parser.add_argument("-u", "--update", help="Comma-separated module list to update")
    parser.add_argument("-i", "--init", help="Comma-separated module list to install")
    parser.add_argument(
        "--dev",
        default="all",
        help="Odoo developer mode options, for example all, reload, qweb, xml",
    )
    parser.add_argument("--no-dev", action="store_true", help="Do not pass --dev")
    parser.add_argument("--log-level", default="debug", help="Odoo log level")
    parser.add_argument("--port", default="8069", help="HTTP port")
    parser.add_argument("--url", help="Browser URL. Defaults to localhost using --port")
    parser.add_argument("--browser-delay", type=int, default=8, help="Browser open delay")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser")
    parser.add_argument(
        "--postgres-service",
        default=DEFAULT_POSTGRES_SERVICE,
        help="Windows PostgreSQL service name",
    )
    parser.add_argument("--no-postgres", action="store_true", help="Do not start PostgreSQL")
    parser.add_argument("--no-cron", action="store_true", help="Disable cron workers")
    parser.add_argument("--stop-after-init", action="store_true", help="Stop after init/update")
    parser.add_argument("--dry-run", action="store_true", help="Print command and exit")
    parser.add_argument(
        "odoo_args",
        nargs=argparse.REMAINDER,
        help="Extra arguments passed to odoo-bin. Prefix with -- when needed.",
    )
    return parser.parse_args()


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def ensure_paths():
    required = [
        (VENV_PYTHON, "virtualenv Python"),
        (ODOO_BIN, "Odoo entry point"),
        (CONFIG, "Odoo config"),
        (ODOO_ADDONS, "Odoo addons path"),
        (CUSTOM_ADDONS, "custom addons path"),
    ]
    missing = [f"{label}: {path}" for path, label in required if not path.exists()]
    if missing:
        return fail("Missing required paths:\n  " + "\n  ".join(missing))
    return 0


def service_is_running(service_name):
    result = subprocess.run(
        ["sc.exe", "query", service_name],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        print(result.stdout.strip() or result.stderr.strip())
        return False
    return "RUNNING" in result.stdout.upper()


def start_postgres(service_name):
    print(f"PostgreSQL service: {service_name}")
    if service_is_running(service_name):
        print("PostgreSQL is already running.")
        return 0

    print("Starting PostgreSQL...")
    result = subprocess.run(["net.exe", "start", service_name], text=True)
    if result.returncode != 0:
        return fail(
            f'Could not start PostgreSQL service "{service_name}". '
            "Run the launcher as Administrator if Windows denies service control."
        )
    return 0


def open_browser_later(url, delay):
    def worker():
        time.sleep(delay)
        webbrowser.open(url)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()


def clean_remainder(args):
    if args and args[0] == "--":
        return args[1:]
    return args


def build_odoo_command(args):
    command = [
        str(VENV_PYTHON),
        str(ODOO_BIN),
        "-c",
        args.config,
        "--addons-path",
        f"{ODOO_ADDONS},{CUSTOM_ADDONS}",
        "--http-port",
        str(args.port),
        "--log-level",
        args.log_level,
    ]

    if args.database:
        command.extend(["-d", args.database])
    if args.update:
        command.extend(["-u", args.update])
    if args.init:
        command.extend(["-i", args.init])
    if args.dev and not args.no_dev:
        command.append(f"--dev={args.dev}")
    if args.no_cron:
        command.append("--max-cron-threads=0")
    if args.stop_after_init:
        command.append("--stop-after-init")

    command.extend(clean_remainder(args.odoo_args))
    return command


def should_open_browser(args):
    extra_args = set(clean_remainder(args.odoo_args))
    return (
        not args.no_browser
        and not args.stop_after_init
        and "--stop-after-init" not in extra_args
        and "--no-http" not in extra_args
    )


def main():
    args = parse_args()

    path_status = ensure_paths()
    if path_status:
        return path_status

    if not args.no_postgres:
        postgres_status = start_postgres(args.postgres_service)
        if postgres_status:
            return postgres_status

    command = build_odoo_command(args)
    url = args.url or f"http://localhost:{args.port}"

    print()
    print("Odoo development launcher")
    print(f"Project:       {ROOT}")
    print(f"Config:        {args.config}")
    print(f"Addons:        {ODOO_ADDONS}")
    print(f"Custom addons: {CUSTOM_ADDONS}")
    print(f"URL:           {url}")
    print(f"Command:       {subprocess.list2cmdline(command)}")
    print()

    if args.dry_run:
        return 0

    if should_open_browser(args):
        open_browser_later(url, args.browser_delay)

    try:
        return subprocess.call(command, cwd=str(ROOT))
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
