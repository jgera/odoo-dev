# Current Status - Subscription Suite

Last updated: 2026-06-05

## Branch

`subscription-suite-odoo19-enterprise`

## Source Of Truth

Runnable Odoo 19 addon source:

`versions/19.0/custom_addons`

Launcher/config no longer include root `custom_addons` in the Odoo 19 addons path.

## Latest Checkpoints

- `b038ff7 Add subscription manager operations dashboard`
- `a6053b6 Use Odoo 19 custom addons path for development`
- `a195a12 Polish subscription request manager workflows`

## Recently Completed

- Manager request workflows for plan changes, lifecycle pause/resume, and cancellations.
- Manager review activities and subscription stat buttons.
- Portal request flows for plan change, lifecycle, and cancellation.
- Billing retry/recovery hardening.
- Manager Operations queue combining pending requests and failed billing recovery.
- Operations Dashboard with manager KPIs and drilldowns.

## Latest Validation

- Compile billing addon passed.
- `/subscription_suite_billing` tests passed with 0 failed, 0 errors.
- Full suite upgrade passed.

## Next Careful Slice

Payment recovery portal flow, designed carefully because it touches payment and customer self-service.
