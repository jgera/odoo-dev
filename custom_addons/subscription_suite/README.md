# Subscription Suite

Subscription Suite is an Odoo 19 Community Edition addon suite for subscription plans, recurring subscription orders, portal visibility, dunning, billing extensions, and subscription reporting.

## Odoo Version

This suite is maintained for Odoo 19 only.

## Addons

- `subscription_suite`: Core subscription plans, lifecycle fields, recurring invoice cron, cancellation wizard, demo data, and menus.
- `subscription_suite_billing`: Proration records, plan-change support, billing runs, and billing attempt tracking.
- `subscription_suite_dunning`: Dunning policies, failed-payment follow-up fields, and recovery cron hooks.
- `subscription_suite_portal`: Customer portal subscription list and detail pages.
- `subscription_suite_reports`: SQL-backed subscription reporting views.

## Documentation

- [Documentation index](docs/README.md)
- [Enterprise phased development plan](docs/ENTERPRISE_PHASED_DEVELOPMENT_PLAN.md)
- [Phase validation checklist](docs/PHASE_VALIDATION_CHECKLIST.md)
- [Demo data inventory](docs/DEMO_DATA_INVENTORY.md)
- [Testing guide](docs/TESTING_GUIDE.md)
- [Portal demo guide](docs/PORTAL_DEMO_GUIDE.md)

## Install

From the workspace root:

```powershell
python scripts\dev_odoo.py --odoo-version 19.0 -d odoo19_subscription_demo -i base,subscription_suite,subscription_suite_billing,subscription_suite_dunning,subscription_suite_portal,subscription_suite_reports --stop-after-init --no-browser --no-cron --no-dev --log-level=info -- --with-demo
```

To run the demo database:

```powershell
python scripts\dev_odoo.py --odoo-version 19.0 -d odoo19_subscription_demo
```

Open `http://localhost:8069/web?debug=1`.

## Demo Data

The core demo file creates:

- Basic Monthly and Pro Annual plans.
- Demo subscription products.
- Active, trial, paused, and cancelled subscription sale orders.
- Cancellation reasons.
- Demo MRR movement records for new, expansion, and churn examples.

See [Demo Data Inventory](docs/DEMO_DATA_INVENTORY.md) for the current demo coverage and the required demo expansion path for each phase.

## Testing And Validation

Use the [Testing Guide](docs/TESTING_GUIDE.md) after every code, XML, security, demo-data, or manifest change.

Minimum Phase 0 checks:

```powershell
python -m compileall custom_addons\subscription_suite
python scripts\dev_odoo.py --odoo-version 19.0 -d odoo19_subscription_demo -u subscription_suite,subscription_suite_billing,subscription_suite_dunning,subscription_suite_portal,subscription_suite_reports --stop-after-init --no-browser --no-cron --no-dev --log-level=info
```

## Portal Testing

See [Portal Demo Guide](docs/PORTAL_DEMO_GUIDE.md).

Short version:

1. Start Odoo with `odoo19_subscription_demo`.
2. Grant portal access to a customer attached to a demo subscription.
3. Log in as that portal user.
4. Open `/my/subscriptions`.
5. Open a subscription detail page from the list.

Portal users should only see their own subscription records.

## Known Limitations

- Billing runs, billing attempts, failed-billing queue, repeated-failure reporting, manual retry, automated retry scheduling, retry exhaustion activities, subscription processing locks, and retry policy settings are implemented for recurring invoice cron visibility and idempotency.
- Recurring invoice generation still needs broader cross-period billing analytics.
- Portal self-service actions such as cancel, pause, resume, change plan, and payment-method changes are not implemented yet.
- Stored-token payment collection still needs production-grade handling.
- Provider-level payment transaction capture and dunning attempt ledgers are not implemented yet.
- Renewal and upsell quotation workflows now have linked quotation foundations; remaining work is proration-depth and advanced sales policy controls.
- Dunning cron behavior needs broader automated test coverage.
- Revenue recognition is not implemented yet.
