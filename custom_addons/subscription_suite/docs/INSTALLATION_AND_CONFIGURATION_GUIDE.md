# Installation And Configuration Guide

## Supported Environment

- Odoo 19 Community only.
- All five addons must come from `versions/19.0/custom_addons`.
- Install the addons in one database and keep their versions aligned.

## Addons

1. `subscription_suite`
2. `subscription_suite_billing`
3. `subscription_suite_dunning`
4. `subscription_suite_portal`
5. `subscription_suite_reports`

## Fresh Installation

Use a disposable database:

```powershell
python scripts\subscription_suite_release_check.py -d odoo19_subscription_release --fresh-install --confirm-recreate
```

This command recreates the named database. Never point it at production.

For a normal installation into an existing empty database:

```powershell
python scripts\dev_odoo.py --odoo-version 19.0 -d DATABASE -i subscription_suite,subscription_suite_billing,subscription_suite_dunning,subscription_suite_portal,subscription_suite_reports --stop-after-init --no-browser --no-cron --no-dev --log-level=info
```

## Required Configuration

1. Review subscription user and manager assignments.
2. Configure plans, recurring products, taxes, journals, and payment providers.
3. Configure billing batch size and retry policy.
4. Configure dunning policies and test email delivery.
5. Configure company-specific deferred revenue journal and accounts.
6. Keep scheduled recognition disabled until preview, posting, and reconciliation pass.
7. Create portal users only for the intended commercial partner.
8. Review scheduled actions and enable only required jobs.

## Upgrade

Back up the database and filestore, then run:

```powershell
python scripts\subscription_suite_release_check.py -d DATABASE
```

For a release candidate:

```powershell
python scripts\subscription_suite_release_check.py -d DATABASE --run-tests
```

## Post-Installation Verification

- Confirm a subscription and generate a recurring invoice.
- Rerun billing and verify idempotency.
- Exercise payment recovery and dunning on a controlled invoice.
- Verify portal ownership with two separate customers.
- Generate analytics in the documented sequence.
- Generate, preview, post, and reconcile deferred revenue.
- Review restricted multi-company users.

Do not enable production crons until these checks pass in staging.
