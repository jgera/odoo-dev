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
