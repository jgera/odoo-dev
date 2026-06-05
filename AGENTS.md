# AGENTS.md

## Project Scope

- This workspace is for local Odoo development.
- Subscription Suite is being built exclusively for Odoo 19 Community.
- Odoo 19 runnable addon source is `versions/19.0/custom_addons`.
- The root `custom_addons` tree may contain mirrored files or docs, but Odoo 19 module loading should not depend on it.

## Development Rules

- Prefer small, validated enterprise slices over broad rewrites.
- Inspect the current repo state before changing architecture, workflows, or migration paths.
- Keep code, demo data, tests, and docs aligned for each phase.
- Do not revert user or prior-agent changes unless explicitly requested.
- Use `scripts/dev_odoo.py --odoo-version 19.0` for Odoo commands.
- Browser developer mode means Odoo `?debug=1`, not Chrome remote debugging, unless explicitly requested.

## Validation

- After Python/code changes, run `python -m compileall` on affected addon paths.
- For billing changes, run the `/subscription_suite_billing` test tag.
- For core lifecycle changes, run the `/subscription_suite` test tag.
- For portal changes, run the `/subscription_suite_portal` test tag.
- Before a checkpoint, run a full upgrade of installed suite modules:
  `subscription_suite,subscription_suite_billing,subscription_suite_dunning,subscription_suite_portal,subscription_suite_reports`.

## Current Module Direction

- Continue from `custom_addons/subscription_suite/docs/ENTERPRISE_PHASED_DEVELOPMENT_PLAN.md`.
- Current next careful area: operations dashboard metrics and drilldowns, then payment recovery portal flow.
