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
- `0852b3d Add portal payment recovery entry point`

## Recently Completed

- Manager request workflows for plan changes, lifecycle pause/resume, and cancellations.
- Manager review activities and subscription stat buttons.
- Portal request flows for plan change, lifecycle, and cancellation.
- Billing retry/recovery hardening.
- Manager Operations queue combining pending requests and failed billing recovery.
- Operations Dashboard with manager KPIs and drilldowns.
- Removed stale one-off migration helper scripts from the active Odoo 19 addons root.
- Portal payment recovery banner for open subscription invoices.
- Portal saved-payment retry route with no-token safety guard.
- Dedicated payment-attempt ledger for portal and cron payment collection.
- Manager-facing payment attempt views and failed-payment recovery queue entries.

## Latest Validation

- `python -m compileall versions\19.0\custom_addons` passed.
- `/subscription_suite_portal` tests passed with 0 failed, 0 errors.
- `/subscription_suite_billing` tests passed with 0 failed, 0 errors across 33 tests.
- Full suite upgrade passed for `subscription_suite,subscription_suite_billing,subscription_suite_dunning,subscription_suite_portal,subscription_suite_reports`.

## Next Careful Slice

Payment-method onboarding and customer update-payment flow. The payment-attempt ledger now records provider outcomes, but customers still need a clean way to add or replace saved payment methods from the subscription portal.
