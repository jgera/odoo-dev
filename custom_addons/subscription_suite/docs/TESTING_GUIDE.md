# Testing Guide

This guide defines the standard validation commands for Subscription Suite on Odoo 19.

Run commands from the workspace root:

```text
D:\Projects\Odoo dev
```

## 1. Compile Python

```powershell
python -m compileall custom_addons\subscription_suite
```

Use this after every Python edit.

## 2. Install With Demo Data

Use this for a fresh demo database or when validating demo setup:

```powershell
python scripts\dev_odoo.py --odoo-version 19.0 -d odoo19_subscription_demo -i base,subscription_suite,subscription_suite_billing,subscription_suite_dunning,subscription_suite_portal,subscription_suite_reports --stop-after-init --no-browser --no-cron --no-dev --log-level=info -- --with-demo
```

## 3. Upgrade All Suite Modules

Use this after code, XML, security, demo, or manifest edits:

```powershell
python scripts\dev_odoo.py --odoo-version 19.0 -d odoo19_subscription_demo -u subscription_suite,subscription_suite_billing,subscription_suite_dunning,subscription_suite_portal,subscription_suite_reports --stop-after-init --no-browser --no-cron --no-dev --log-level=info
```

## 4. Start Demo Server

```powershell
python scripts\dev_odoo.py --odoo-version 19.0 -d odoo19_subscription_demo --no-browser --no-cron --no-dev --log-level=info
```

Open:

```text
http://localhost:8069/web?debug=1
```

## 5. Run Module Tests

Run tests per addon when touching that addon.

Core lifecycle:

```powershell
python scripts\dev_odoo.py --odoo-version 19.0 -d odoo19_subscription_demo -u subscription_suite --stop-after-init --no-browser --no-cron --no-dev --log-level=test -- --test-enable --test-tags /subscription_suite
```

Billing and proration:

```powershell
python scripts\dev_odoo.py --odoo-version 19.0 -d odoo19_subscription_demo -u subscription_suite_billing --stop-after-init --no-browser --no-cron --no-dev --log-level=test -- --test-enable --test-tags /subscription_suite_billing
```

Dunning:

```powershell
python scripts\dev_odoo.py --odoo-version 19.0 -d odoo19_subscription_demo -u subscription_suite_dunning --stop-after-init --no-browser --no-cron --no-dev --log-level=test -- --test-enable --test-tags /subscription_suite_dunning
```

Portal:

```powershell
python scripts\dev_odoo.py --odoo-version 19.0 -d odoo19_subscription_demo -u subscription_suite_portal --stop-after-init --no-browser --no-cron --no-dev --log-level=test -- --test-enable --test-tags /subscription_suite_portal
```

Reports:

```powershell
python scripts\dev_odoo.py --odoo-version 19.0 -d odoo19_subscription_demo -u subscription_suite_reports --stop-after-init --no-browser --no-cron --no-dev --log-level=test -- --test-enable --test-tags /subscription_suite_reports
```

## 6. Manual Smoke Test

After an upgrade, validate:

- Subscriptions app opens.
- Plans open in kanban/list/form.
- Demo subscriptions open in kanban/list/form.
- Subscription statusbar renders.
- Recurring values and MRR show correctly.
- Reporting menus open.
- MRR movement report opens.
- Dunning policies open when dunning is installed.
- Billing Runs, Billing Attempts, Failed Billing, and Repeated Failures menus open when billing is installed.
- Failed Billing list has Retryable, Needs Manual Fix, Recovery Required, Retry Exhausted, and Repeated Failures filters.
- Portal `/my/subscriptions` redirects to login when unauthenticated.

## 7. Phase 1 Billing Demo

After installing demo data and upgrading `subscription_suite_billing`, use `demo_subscription_due_billing` to validate billing attempts. The billing cron intentionally processes confirmed sales orders only, so confirm the demo subscription before running the cron.

1. Open `demo_subscription_due_billing` from **Subscriptions -> Subscriptions**.
2. Confirm the sale order if it is still a quotation.
3. Open **Subscriptions -> Billing -> Billing Runs** and note the current records.
4. Run the subscription invoice cron manually from scheduled actions, or run it from an Odoo shell/test context with `sale.order._cron_generate_subscription_invoices()`.
5. Open **Subscriptions -> Billing -> Billing Runs**.
6. Open the latest run.
7. Confirm it has a successful attempt for `demo_subscription_due_billing`.
8. Open the generated invoice from the attempt.
9. Run the cron again and confirm no duplicate invoice is created for the same billing period.

Failed billing operator flow:

1. Open **Subscriptions -> Billing -> Failed Billing**.
2. Use **Retryable** for temporary/system failures.
3. Use **Needs Manual Fix** for configuration or invoice validation failures.
4. Open a retryable failed attempt and click **Retry** after the root cause is resolved.
5. Confirm the attempt changes to Success and links to the generated invoice.
6. Open **Subscriptions -> Billing -> Repeated Failures** to review attempts with more than one recorded failure.
7. On a failed attempt, confirm **Failure Count**, **First Failure At**, **Last Failure At**, **Last Failure Message**, and **Recovery Note** are populated.
8. Confirm the attempt chatter includes billing failure log messages.

Retry policy settings are available from **Subscriptions -> Configuration -> Settings**:

- **Max Billing Retry Attempts** controls the maximum total attempts before a manual recovery activity is created.
- **Billing Retry Batch Size** controls how many failed attempts are processed per retry cron run.
- **Billing Retry Delay** controls the delay before retryable failures are retried.

The settings persist to these system parameters:

- `subscription_suite.billing_retry_max_attempts`: maximum total attempts before manual recovery activity, default `3`.
- `subscription_suite.billing_retry_batch_size`: maximum failed attempts retried per cron run, default `50`.
- `subscription_suite.billing_retry_delay_hours`: delay before the next retry for retryable failures, default `1`.

Scheduled action:

- **Subscription: Retry Failed Billing** runs `subscription.billing.attempt._cron_retry_failed_billing_attempts()`.

## 8. Phase 2 Lifecycle Demo

Pause/resume:

1. Open an active subscription with a future **Next Invoice Date**.
2. Click **Pause**.
3. Adjust only in a test database if you need to simulate elapsed paused days.
4. Click **Resume**.
5. Confirm **Next Invoice Date** moved forward by the paused duration.

Scheduled cancellation:

1. Open a subscription whose plan uses **End of Billing Period** cancellation.
2. Click **Cancel Subscription**.
3. Confirm the wizard.
4. Confirm the subscription remains active with **Pending Cancellation** enabled.
5. Confirm **Cancellation Effective Date** is the current period end or later.
6. Use **Reverse Cancellation** to clear the scheduled cancellation when needed.
7. Scheduled action **Subscription: Process Scheduled Cancellations** finalizes due scheduled cancellations.

Immediate cancellation:

1. Open a subscription whose plan uses **Immediate** cancellation.
2. Click **Cancel Subscription** and confirm.
3. Confirm the subscription moves to Cancelled immediately.

Renewal quotation:

1. Open `demo_subscription_active`.
2. Click **Renew**.
3. Confirm a draft quotation opens with **Subscription Quote Type** set to Renewal and **Origin Subscription** set to the active subscription.
4. Confirm recurring lines were copied to the renewal quotation.
5. Confirm the quotation.
6. Return to the original subscription and confirm **Sales History** includes the renewal quotation.
7. Confirm the subscription log includes a **Renewed** event.

Upsell quotation:

1. Open `demo_subscription_active`.
2. Click **Upsell**.
3. Add a recurring product line, or open demo quotation `demo_subscription_upsell_quote`.
4. Set **Quote Effective Date** to a date inside the current billing period when validating proration.
5. Confirm the quotation.
6. Return to the original subscription and confirm the upsell line was added to the subscription.
7. Confirm MRR increased and the subscription log includes an **Upsold** event.
8. When `subscription_suite_billing` is installed, confirm a related proration record exists under the subscription proration smart button.
9. Confirm **Sales History** includes the upsell quotation.

## 9. Phase Result Log

Record phase results in the phase notes or pull request description:

```text
Phase:
Database:
Commands run:
Modules upgraded:
Tests passed:
Manual smoke test:
Demo data updated:
Documentation updated:
Known limitations:
```
