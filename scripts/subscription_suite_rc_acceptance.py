import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    "subscription_suite",
    "subscription_suite_billing",
    "subscription_suite_dunning",
    "subscription_suite_portal",
    "subscription_suite_reports",
)
DEFAULT_DATABASE = "odoo19_subscription_rc"
DEFAULT_OUTPUT_DIR = (
    ROOT
    / "custom_addons"
    / "subscription_suite"
    / "docs"
    / "release_evidence"
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run and record Subscription Suite release-candidate acceptance evidence.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("-d", "--database", default=DEFAULT_DATABASE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--fresh-install",
        action="store_true",
        help="Recreate the RC database and install the five-module suite.",
    )
    parser.add_argument(
        "--confirm-recreate",
        action="store_true",
        help="Required with --fresh-install because the target database is dropped.",
    )
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="Run all five addon test tags after the install/upgrade check.",
    )
    parser.add_argument(
        "--portal-smoke",
        action="store_true",
        help="Mark portal smoke as expected and leave a manual evidence gate in the report.",
    )
    parser.add_argument(
        "--screenshot-dir",
        type=Path,
        help="Directory containing reviewed RC screenshots for the report.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands and write evidence without executing shell commands.",
    )
    return parser.parse_args()


def git_value(*args):
    command = ["git", "-c", f"safe.directory={ROOT.as_posix()}", *args]
    try:
        return subprocess.check_output(command, cwd=ROOT, text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def command_text(command):
    return subprocess.list2cmdline([str(part) for part in command])


def run_step(name, command, dry_run=False):
    started = time.perf_counter()
    result = {
        "name": name,
        "command": command_text(command),
        "state": "dry_run" if dry_run else "running",
        "duration_seconds": 0.0,
        "returncode": None,
    }
    print(f"\n[{name}] {result['command']}")
    if dry_run:
        result["duration_seconds"] = round(time.perf_counter() - started, 3)
        return result
    completed = subprocess.run(command, cwd=ROOT)
    result["returncode"] = completed.returncode
    result["duration_seconds"] = round(time.perf_counter() - started, 3)
    result["state"] = "passed" if completed.returncode == 0 else "failed"
    if completed.returncode != 0:
        raise SystemExit(f"RC acceptance step failed: {name}")
    return result


def release_check_command(database, *extra):
    return [
        sys.executable,
        "scripts/subscription_suite_release_check.py",
        "-d",
        database,
        *extra,
    ]


def collect_screenshots(path):
    if not path:
        return []
    absolute = path if path.is_absolute() else ROOT / path
    if not absolute.exists():
        return []
    return sorted(
        str(item.relative_to(ROOT))
        for item in absolute.rglob("*")
        if item.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    )


def manual_gate(name, state, note):
    return {
        "name": name,
        "state": state,
        "note": note,
    }


def write_markdown(report, path):
    lines = [
        "# Subscription Suite RC Acceptance Report",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Database: `{report['database']}`",
        f"- Branch: `{report['git']['branch'] or 'unknown'}`",
        f"- Commit: `{report['git']['commit'] or 'unknown'}`",
        "",
        "## Automated Steps",
        "",
        "| Step | State | Duration | Command |",
        "| --- | --- | ---: | --- |",
    ]
    for step in report["steps"]:
        lines.append(
            "| {name} | {state} | {duration_seconds:.3f}s | `{command}` |".format(**step)
        )
    lines.extend(["", "## Manual Gates", ""])
    lines.extend(["| Gate | State | Note |", "| --- | --- | --- |"])
    for gate in report["manual_gates"]:
        lines.append("| {name} | {state} | {note} |".format(**gate))
    lines.extend(["", "## Screenshots", ""])
    if report["screenshots"]:
        for screenshot in report["screenshots"]:
            lines.append(f"- `{screenshot}`")
    else:
        lines.append("- No reviewed screenshots were supplied to this run.")
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "Set one final release decision after reviewing failed, blocked, or manual gates:",
            "",
            "- `release`",
            "- `release with limitations`",
            "- `blocked`",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    args = parse_args()
    if args.fresh_install and not args.confirm_recreate:
        raise SystemExit(
            "--fresh-install drops and recreates the selected database. "
            "Pass --confirm-recreate to continue."
        )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    steps = [
        run_step(
            "static",
            release_check_command(args.database, "--static-only"),
            args.dry_run,
        )
    ]
    if args.fresh_install:
        steps.append(
            run_step(
                "fresh_install",
                release_check_command(
                    args.database,
                    "--fresh-install",
                    "--confirm-recreate",
                ),
                args.dry_run,
            )
        )
    else:
        steps.append(
            run_step(
                "upgrade",
                release_check_command(args.database),
                args.dry_run,
            )
        )
    if args.run_tests:
        steps.append(
            run_step(
                "tagged_tests",
                release_check_command(args.database, "--run-tests"),
                args.dry_run,
            )
        )

    screenshots = collect_screenshots(args.screenshot_dir)
    manual_gates = [
        manual_gate(
            "portal_smoke",
            "pending" if args.portal_smoke else "not_requested",
            "Validate two portal customers and denied cross-customer access in the RC database.",
        ),
        manual_gate(
            "screenshot_review",
            "pending" if not screenshots else "ready_for_review",
            "Complete SCREENSHOTS_CHECKLIST.md and verify no credentials, local paths, or debug artifacts are visible.",
        ),
        manual_gate(
            "commercial_metadata",
            "blocked",
            "Author, website, support, pricing, and listing ownership require owner sign-off before publication.",
        ),
    ]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "database": args.database,
        "modules": MODULES,
        "git": {
            "branch": git_value("branch", "--show-current"),
            "commit": git_value("rev-parse", "--short", "HEAD"),
            "status": git_value("status", "--short"),
        },
        "steps": steps,
        "manual_gates": manual_gates,
        "screenshots": screenshots,
    }

    json_path = output_dir / f"subscription_suite_rc_acceptance_{timestamp}.json"
    md_path = output_dir / f"subscription_suite_rc_acceptance_{timestamp}.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report, md_path)
    print(f"\nWrote {json_path.relative_to(ROOT)}")
    print(f"Wrote {md_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
