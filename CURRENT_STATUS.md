# Current Status - Subscription Suite

Last updated: 2026-06-05

## Branch

`subscription-suite-odoo19-enterprise`

## Source Of Truth

Runnable Odoo 19 addon source:

`versions/19.0/custom_addons`

Launcher/config no longer include root `custom_addons` in the Odoo 19 addons path.

## Latest Checkpoints

- `456111f Add subscription operations dashboard metrics`
- `fc2450b Add Codex continuation context`
- `b038ff7 Add subscription manager operations dashboard`

## Recently Completed

- Manager request workflows for plan changes, lifecycle pause/resume, and cancellations.
- Manager review activities and subscription stat buttons.
- Portal request flows for plan change, lifecycle, and cancellation.
- Billing retry/recovery hardening.
- Manager Operations queue combining pending requests and failed billing recovery.
- Operations Dashboard with manager KPIs and drilldowns.
- Removed stale one-off migration helper scripts from the active Odoo 19 addons root.

## Latest Validation

- `python -m compileall versions\19.0\custom_addons` passed.
- `/subscription_suite_billing` tests passed with 0 failed, 0 errors.
- Full suite upgrade passed for `subscription_suite,subscription_suite_billing,subscription_suite_dunning,subscription_suite_portal,subscription_suite_reports`.

## Next Careful Slice

Payment recovery portal flow, designed carefully because it touches payment and customer self-service.
