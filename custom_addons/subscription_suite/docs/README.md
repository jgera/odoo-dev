# Subscription Suite Documentation

This folder is the execution and validation hub for Subscription Suite.

The suite targets **Odoo 19 only**. Every phase should update demo data, tests, and documentation before it is considered complete.

## Documents

| Document | Purpose |
| --- | --- |
| [Enterprise Phased Development Plan](ENTERPRISE_PHASED_DEVELOPMENT_PLAN.md) | Enterprise roadmap, competitor benchmark, phase order, acceptance gates |
| [Phase Validation Checklist](PHASE_VALIDATION_CHECKLIST.md) | Repeatable checklist for every phase before moving forward |
| [Demo Data Inventory](DEMO_DATA_INVENTORY.md) | Current demo records and the required demo expansion path |
| [Testing Guide](TESTING_GUIDE.md) | Compile, install, upgrade, and Odoo test commands |
| [Portal Demo Guide](PORTAL_DEMO_GUIDE.md) | How to validate customer portal subscription visibility |
| [10K Benchmark Report](10K_BENCHMARK_REPORT.md) | Dedicated 10K benchmark evidence and current performance budget |
| [Installation And Configuration Guide](INSTALLATION_AND_CONFIGURATION_GUIDE.md) | Deployment, setup, upgrade, and post-install checks |
| [User Guide](USER_GUIDE.md) | Daily subscription, billing, dunning, analytics, portal-support, operations, and migration workflows |
| [Admin Guide](ADMIN_GUIDE.md) | Users, companies, scheduled actions, observability, backups, and release validation |
| [Finance Guide](FINANCE_GUIDE.md) | Deferred revenue setup, schedules, preview, posting, adjustments, reconciliation, and finance limits |
| [Portal Guide](PORTAL_GUIDE.md) | Customer portal access, subscription visibility, lifecycle requests, payment recovery, and ownership checks |
| [Troubleshooting Guide](TROUBLESHOOTING_GUIDE.md) | Install, upgrade, portal, payment, dunning, analytics, finance, migration, and operations troubleshooting |
| [Release Checklist](RELEASE_CHECKLIST.md) | Release-candidate acceptance and sign-off gates |
| [Known Limitations](KNOWN_LIMITATIONS.md) | Explicit functional and operational product boundaries |
| [Changelog](CHANGELOG.md) | Release-facing change history |
| [Migration And Data Operations Runbook](MIGRATION_RUNBOOK.md) | CSV preparation, validation, apply, backfill, correction, and recovery workflow |
| [Odoo Apps Listing](ODOO_APPS_LISTING.md) | App-store listing copy, support statement, limitations summary, and screenshot plan |
| [Screenshots Checklist](SCREENSHOTS_CHECKLIST.md) | Required release-candidate screenshot coverage |
| [Release Notes Template](RELEASE_NOTES_TEMPLATE.md) | Versioned release notes structure |

## Phase 0 Baseline

Phase 0 is complete only when:

- The suite can be installed fresh with demo data.
- All current modules can be upgraded.
- Existing tests can be run.
- Demo records are inventoried.
- Portal validation steps are documented.
- Known limitations are current and visible.

## Standard Demo Database

Use `odoo19_subscription_demo` as the working demo database unless a phase explicitly needs a fresh disposable database.

Start Odoo:

```powershell
python scripts\dev_odoo.py --odoo-version 19.0 -d odoo19_subscription_demo --no-browser --no-cron --no-dev --log-level=info
```

Open:

```text
http://localhost:8069/web?debug=1
```
