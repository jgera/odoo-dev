import argparse
import subprocess
import sys
import threading
import time
import webbrowser
from urllib.parse import urlparse, urlunparse

from odoo_env import (
    DEFAULT_CHROME,
    DEFAULT_POSTGRES_SERVICE,
    DEFAULT_VERSION,
    ROOT,
    addons_path,
    addons_paths,
    available_versions,
    get_paths,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Development-oriented launcher for the local Odoo checkout.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--odoo-version",
        "--version",
        default=DEFAULT_VERSION,
        help="Odoo version folder under versions/",
    )
    parser.add_argument(
        "--list-versions",
        action="store_true",
        help="List configured Odoo versions and exit",
    )
    parser.add_argument("-c", "--config", help="Odoo config file")
    parser.add_argument("-d", "--database", help="Database name to use")
    parser.add_argument("-u", "--update", help="Comma-separated module list to update")
    parser.add_argument("-i", "--init", help="Comma-separated module list to install")
    parser.add_argument(
        "--dev",
        default=None,
        help="Odoo server dev options, for example all, reload, qweb, xml. Browser developer mode still uses ?debug=1 by default.",
    )
    parser.add_argument("--no-dev", action="store_true", help="Do not pass --dev")
    parser.add_argument("--log-level", default="info", help="Odoo log level")
    parser.add_argument("--port", default="8069", help="HTTP port")
    parser.add_argument("--url", help="Browser URL. Defaults to localhost using --port")
    parser.add_argument("--browser-delay", type=int, default=8, help="Browser open delay")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser")
    developer_mode_group = parser.add_mutually_exclusive_group()
    developer_mode_group.add_argument(
        "--developer-mode",
        dest="browser_developer_mode",
        action="store_true",
        help="Open Odoo web client with ?debug=1",
    )
    developer_mode_group.add_argument(
        "--no-developer-mode",
        dest="browser_developer_mode",
        action="store_false",
        help="Open Odoo web client without ?debug=1",
    )
    browser_debug_group = parser.add_mutually_exclusive_group()
    browser_debug_group.add_argument(
        "--debug-browser",
        dest="debug_browser",
        action="store_true",
        help="Open Chrome with remote debugging enabled",
    )
    browser_debug_group.add_argument(
        "--no-debug-browser",
        dest="debug_browser",
        action="store_false",
        help="Open the default browser without Chrome remote debugging",
    )
    parser.add_argument(
        "--browser-debug-port",
        default="9222",
        help="Chrome remote debugging port used with --debug-browser",
    )
    parser.add_argument(
        "--browser-profile",
        default=None,
        help="Dedicated Chrome profile directory for debug browser sessions",
    )
    parser.add_argument(
        "--browser-exe",
        default=str(DEFAULT_CHROME),
        help="Chrome executable used for debug browser sessions",
    )
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
    parser.set_defaults(browser_developer_mode=None, debug_browser=None)
    return parser.parse_args()


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def ensure_paths(paths, config_path):
    required = [
        (paths.venv_python, "virtualenv Python"),
        (paths.odoo_bin, "Odoo entry point"),
        (config_path, "Odoo config"),
        (paths.core_addons, "Odoo addons path"),
        (paths.shared_addons, "shared custom addons path"),
        (paths.data_dir, "Odoo data directory"),
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


def ask_yes_no(question, default):
    suffix = "Y/n" if default else "y/N"
    answer = input(f"{question} [{suffix}]: ").strip().lower()
    if not answer:
        return default
    return answer in {"y", "yes"}


def resolve_prompted_options(args):
    if args.no_browser or args.dry_run or not sys.stdin.isatty():
        if args.browser_developer_mode is None:
            args.browser_developer_mode = True
        if args.debug_browser is None:
            args.debug_browser = False
        return args

    if args.browser_developer_mode is None:
        args.browser_developer_mode = ask_yes_no(
            "Open Odoo in developer mode (?debug=1)?", True
        )
    if args.debug_browser is None:
        args.debug_browser = ask_yes_no(
            "Open browser in Chrome remote debugging mode?", False
        )
    return args


def with_odoo_debug_query(url):
    parsed = urlparse(url)
    path = parsed.path or "/web"
    query_parts = [part for part in parsed.query.split("&") if part]
    query_parts = [part for part in query_parts if part.split("=", 1)[0] != "debug"]
    query_parts.append("debug=1")
    return urlunparse(
        parsed._replace(path=path, query="&".join(query_parts))
    )


def open_chrome_debug_browser(url, args):
    from pathlib import Path

    chrome = Path(args.browser_exe)
    if not chrome.exists():
        print(f"Chrome not found at {chrome}; opening default browser.")
        webbrowser.open(url)
        return

    profile = Path(args.browser_profile)
    profile.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [
            str(chrome),
            f"--remote-debugging-port={args.browser_debug_port}",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def open_browser_later(url, delay, args):
    def worker():
        time.sleep(delay)
        if args.debug_browser:
            open_chrome_debug_browser(url, args)
        else:
            webbrowser.open(url)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()


def clean_remainder(args):
    if args and args[0] == "--":
        return args[1:]
    return args


def build_odoo_command(args, paths, config_path):
    command = [
        str(paths.venv_python),
        paths.odoo_bin.name,
        "-c",
        str(config_path),
        "--addons-path",
        addons_path(paths),
        "--http-port",
        str(args.port),
        "--data-dir",
        str(paths.data_dir),
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


def build_browser_url(args):
    url = args.url or f"http://localhost:{args.port}/web"
    if args.browser_developer_mode:
        return with_odoo_debug_query(url)
    return url


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
    args = resolve_prompted_options(args)
    paths = get_paths(args.odoo_version)
    config_path = args.config or paths.config
    if args.browser_profile is None:
        args.browser_profile = str(paths.browser_profile)

    if args.list_versions:
        versions = available_versions()
        print("\n".join(versions) if versions else "No configured Odoo versions found.")
        return 0

    path_status = ensure_paths(paths, config_path)
    if path_status:
        return path_status

    if not args.no_postgres:
        postgres_status = start_postgres(args.postgres_service)
        if postgres_status:
            return postgres_status

    command = build_odoo_command(args, paths, config_path)
    url = build_browser_url(args)

    print()
    print("Odoo development launcher")
    print(f"Project:        {ROOT}")
    print(f"Odoo version:   {paths.version}")
    print(f"Version root:   {paths.root}")
    print(f"Config:         {config_path}")
    print(f"Addons paths:   {addons_path(paths)}")
    print(f"Data dir:       {paths.data_dir}")
    print(f"URL:            {url}")
    print(f"Developer URL: {'yes' if args.browser_developer_mode else 'no'}")
    print(
        "Browser debug: "
        + (
            f"yes, Chrome remote debugging port {args.browser_debug_port}"
            if args.debug_browser
            else "no"
        )
    )
    print(f"Command:       {subprocess.list2cmdline(command)}")
    print()

    if args.dry_run:
        return 0

    if should_open_browser(args):
        open_browser_later(url, args.browser_delay, args)

    try:
        return subprocess.call(command, cwd=str(paths.odoo_server))
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
