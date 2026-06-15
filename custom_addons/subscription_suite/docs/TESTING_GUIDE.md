# Testing Guide

This guide defines the standard validation commands for Subscription Suite on Odoo 19.

## Float And Monetary Comparison Standard

Use Odoo precision helpers for subscription quantities and money-sensitive comparisons:

- Use `float_compare` or `float_is_zero` with the relevant UoM rounding for seat, usage, or quantity comparisons.
- Use `currency_id.compare_amounts()` and `currency_id.is_zero()` for MRR, proration, invoice, payment, discount, credit, and recovery amount comparisons.
- Avoid raw `==`, `!=`, `>`, or `<` for float business decisions unless the value is a counter/date/state, or the comparison intentionally does not depend on precision.
- Add tests for near-equal values when changing quantity, pricing, MRR movement, proration, discounts, usage metering, or payment recovery logic.

Run commands from the workspace root:

```text
D:\Projects\Odoo dev
```

## 1. Compile Python

```powershell
python -m compileall versions\19.0\custom_addons
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
- Operations Dashboard and Manager Operations open under **Subscriptions -> Operations** when billing is installed.
- Failed Billing list has Retryable, Needs Manual Fix, Recovery Required, Retry Exhausted, and Repeated Failures filters.
- Plan Change Requests, Lifecycle Requests, and Cancellation Requests open in list/form/activity views with pending filters, request age, activity assignment, and Open Subscription actions.
- Subscription forms show manager stat buttons for lifecycle, cancellation, and plan-change request history when those modules are installed.
- Portal `/my/subscriptions` redirects to login when unauthenticated.
- Portal subscription list shows plan change status when a subscription has a scheduled plan change.
- Portal subscription detail shows the current plan, scheduled plan change banner, plan change request statuses, recurring items, and invoice history.
- Portal subscription detail shows **Request Plan Change** when the subscription is active and its current plan has configured upgrade or downgrade paths.
- Portal subscription detail shows scheduled cancellation status, cancellation request history, and **Request Cancellation** when cancellation is allowed.
- Portal subscription detail shows lifecycle request history and **Request Pause** or **Request Resume** when the subscription state allows it.
- Portal subscription detail shows a payment recovery banner when a posted subscription invoice is unpaid or partially paid.
- Portal subscription detail shows a read-only **Seats** summary when recurring seat lines exist, and omits it when no seat lines exist.

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

Manager operations queue:

1. Open **Subscriptions -> Operations -> Operations Dashboard**.
2. Confirm the dashboard shows counts for open items, pending requests, critical items, and oldest pending age.
3. Confirm the dashboard shows separate counts for plan changes, lifecycle requests, cancellations, and failed billing.
4. Click each dashboard KPI and confirm it opens the Manager Operations queue with the expected filtered records.
5. Open **Subscriptions -> Operations -> Manager Operations**.
6. Confirm pending plan-change, lifecycle, and cancellation requests appear in the same queue.
7. Confirm failed billing attempts needing retry or manual recovery appear as **Billing Recovery** items.
8. Use the Plan Changes, Lifecycle, Cancellations, Billing Recovery, and Critical filters.
9. Group by **Type** and confirm managers can scan by request/recovery category.
10. Open a row and use **Open Source** to navigate to the underlying request or billing attempt.
11. Use **Open Subscription** to navigate back to the customer subscription.

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

Minimum commitment:

1. Configure a plan with **Minimum Commitment Periods** greater than zero.
2. Open a subscription whose start date is still inside that commitment window.
3. Attempt to cancel the subscription.
4. Confirm Odoo blocks the cancellation and shows the commitment end date.
5. With `subscription_suite_billing` installed, attempt a downgrade before the commitment end date.
6. Confirm Odoo blocks the downgrade.
7. Move the subscription start date outside the commitment window in a test database and confirm cancellation is allowed.

Next-period plan change:

1. Open an active subscription with a future **Next Invoice Date**, or use demo record `demo_subscription_pending_plan_change`.
2. Click **Change Plan**.
3. Select a different plan and set **Apply** to **Next Billing Period**.
4. Confirm the change.
5. Confirm the subscription still shows the current plan and also shows the pending plan, date, and type.
6. Run the subscription invoice cron on or after the pending date.
7. Confirm the pending plan is now the active plan, no proration record was created, and the renewal invoice uses the new plan line.
8. Repeat the setup and click **Cancel Plan Change** to confirm the pending fields are cleared.

Plan change approval:

1. Open `Basic Monthly` or `Enterprise Monthly` and confirm **Require Approval for Upgrades** or **Require Approval for Downgrades** is enabled.
2. Open an active subscription on that plan.
3. Click **Change Plan** and choose a plan that matches the restricted direction.
4. Confirm the change.
5. Confirm a **Plan Change Request** opens in Pending state and the subscription plan has not changed.
6. As a subscription manager, approve the request.
7. For immediate changes, confirm the plan change and proration document were created.
8. For next-period changes, confirm the subscription now shows the pending plan change and the renewal cron later applies it.
9. Repeat with **Reject** and **Cancel** to confirm rejected/cancelled requests do not change the subscription.

Demo approval records:

- `demo_plan_change_request_pending`: pending upgrade request from Basic Monthly to Enterprise Monthly.
- `demo_plan_change_request_rejected`: rejected downgrade request from Enterprise Monthly to Basic Monthly.
- `demo_plan_change_request_cancelled`: cancelled upgrade request.
- `demo_subscription_pending_plan_change`: active subscription with an already scheduled next-period upgrade.
- `demo_cancellation_request_pending`: pending customer cancellation request for the paused demo subscription.
- `demo_lifecycle_request_resume_pending`: pending customer resume request for the pause/resume demo subscription.

Portal read-only plan change visibility:

1. Log in as a portal customer that can access the demo subscription, or create portal access for the customer on `demo_subscription_pending_plan_change`.
2. Open `/my/subscriptions`.
3. Confirm the list shows the subscription and its scheduled target plan in the **Plan Change** column.
4. Open the subscription detail page.
5. Confirm the scheduled plan change banner shows the target plan, change type, and effective date.
6. Confirm **Plan Change Requests** shows pending, rejected, or cancelled request statuses when the subscription has matching request records.
7. Confirm portal users cannot access another customer's subscription detail URL.

Renewal quotation:

1. Open `demo_subscription_active`.
2. Click **Renew**.
3. Confirm a draft quotation opens with **Subscription Quote Type** set to Renewal and **Origin Subscription** set to the active subscription.
4. Confirm recurring lines were copied to the renewal quotation.
5. Confirm the quotation.
6. Return to the original subscription and confirm **Sales History** includes the renewal quotation.
7. Confirm the subscription log includes a **Renewed** event.
8. On the subscription plan, disable **Allow Renewal Quotes** and confirm **Renew** is blocked.
9. Set the subscription to past due, disable **Allow Past-Due Renewal Quotes**, and confirm **Renew** is blocked.
10. Set the subscription to expired and confirm **Renew** can still create a renewal quotation.

Upsell quotation:

1. Open `demo_subscription_active`.
2. Click **Upsell**.
3. Add a recurring product line, or open demo quotation `demo_subscription_upsell_quote`.
4. Set **Quote Effective Date** to a date inside the current billing period when validating proration.
5. Confirm the quotation.
6. Return to the original subscription and confirm the upsell line was added to the subscription.
7. Confirm MRR increased and the subscription log includes an **Upsold** event.
8. When `subscription_suite_billing` is installed, confirm a related proration record exists under the subscription proration smart button.
9. Open the proration record and confirm **Adjustment Invoice** is set for a positive net amount or **Credit Note** is set for a negative net amount.
10. Confirm **Sales History** includes the upsell quotation.
11. On the subscription plan, disable **Allow Upsell Quotes** and confirm **Upsell** is blocked.
12. Set the subscription to past due, disable **Allow Past-Due Upsell Quotes**, and confirm **Upsell** is blocked.
13. Set the subscription to expired and confirm **Upsell** is blocked while **Renew** remains available.
14. Open the Sales search view and confirm **Renewal Quotes**, **Upsell Quotes**, and **Origin Subscription** grouping are available for quote visibility.

## 9. Phase 3 Portal Demo

Read-only portal:

1. Log in as a portal customer that can access a subscription.
2. Open `/my/subscriptions`.
3. Confirm each subscription row shows reference, current plan, plan-change status, next invoice, status, and MRR.
4. Open a subscription detail page.
5. Confirm current plan, billing period, payment method, auto-pay status, recurring items, invoice history, scheduled plan change, and plan change request history render correctly.

Portal plan change request:

1. Configure the current plan with at least one **Upgrade Plans** or **Downgrade Plans** option.
2. Open an active subscription for a portal customer on that plan.
3. Log in as that portal customer and open the subscription detail page.
4. In **Request Plan Change**, select an allowed target plan and click **Request Change**.
5. Confirm the portal shows **Plan change request submitted**.
6. In the backend, open **Subscriptions -> Subscriptions -> Plan Change Requests**.
7. Confirm a pending request exists with **Apply** set to **Next Billing Period**.
8. Confirm the subscription itself has not changed plan and has no scheduled plan change yet.
9. Approve the request as a subscription manager.
10. Confirm the subscription now shows the scheduled next-period plan change.

Automated coverage:

- `subscription_suite_billing` tests cover the shared portal request helper, including success, inactive subscriptions, unconfigured paths, duplicate pending requests, and already scheduled plan changes.
- `subscription_suite_billing` tests cover the manager operations queue across pending requests and failed billing recovery items.
- `subscription_suite_portal` tests cover portal subscription filtering and plan-change visibility context.
- `subscription_suite_portal` tests cover payment recovery ownership for invoice retry, saved-token selection, and validation-return handling.
- Live `HttpCase` route tests are not part of the passing checkpoint yet. A local route-test attempt hung after portal login, so route-level browser coverage remains a Phase 8 hardening task instead of being treated as validated.

Portal pause/resume request:

1. Open an active subscription whose plan allows pausing.
2. Confirm the subscription does not already have a pending lifecycle, plan change, or cancellation request.
3. Log in as that portal customer and open the subscription detail page.
4. In **Request Pause**, optionally enter feedback and submit.
5. Confirm the portal shows **Lifecycle request submitted**.
6. In the backend, open **Subscriptions -> Subscriptions -> Lifecycle Requests**.
7. Approve the request as a subscription manager.
8. Confirm the subscription moves to Paused.
9. Open the paused subscription in the portal and submit **Request Resume**.
10. Approve the resume request and confirm the subscription moves back to Active.

Automated coverage:

- `subscription_suite` lifecycle tests cover portal pause/resume request creation, approval, duplicate blocking, and plan pause-policy enforcement.
- `subscription_suite` lifecycle tests cover manager request queues, automatic review activities, request age, and subscription stat-button actions.
- `subscription_suite_portal` tests cover portal lifecycle request status data.

Portal cancellation request:

1. Open an active, trial, paused, or past-due subscription for a portal customer.
2. Confirm the subscription does not already have **Pending Cancellation** or a pending cancellation request.
3. Log in as that portal customer and open the subscription detail page.
4. In **Request Cancellation**, select a reason and optionally enter feedback.
5. Confirm the portal shows **Cancellation request submitted**.
6. In the backend, open **Subscriptions -> Subscriptions -> Cancellation Requests**.
7. Confirm a pending request exists with the selected reason and the plan cancellation policy.
8. Confirm the subscription itself is not immediately cancelled by the portal request.
9. Approve the request as a subscription manager.
10. Confirm immediate policies cancel immediately and end-of-period policies schedule cancellation.

Automated coverage:

- `subscription_suite` lifecycle tests cover the shared portal cancellation helper, duplicate blocking, scheduled-cancellation blocking, minimum commitment enforcement, and manager approval.
- `subscription_suite_portal` tests cover portal cancellation request status data.
- `subscription_suite` lifecycle tests cover cancellation request review activities and subscription stat-button actions.

Security checks:

1. Log in as a different portal customer.
2. Try to open another customer's subscription detail URL.
3. Confirm Odoo redirects away from the record.
4. Try to POST a plan-change request for another customer's subscription.
5. Try to POST a lifecycle request for another customer's subscription.
6. Try to POST a cancellation request for another customer's subscription.
7. Confirm no plan change, lifecycle, or cancellation request is created.
8. Try to POST payment retry for another customer's invoice.
9. Try to assign another customer's saved payment token.
10. Try to return from payment-method validation using another customer's transaction.
11. Confirm no payment attempt or payment-method update is created for rejected requests.

Current limitation:

- Portal plan changes are intentionally next-period approval requests only. Immediate prorated changes remain backend-only until payment recovery and customer payment-method flows are stronger.
- Portal pause/resume requests are approval-gated. The customer portal does not directly change lifecycle state.
- Portal cancellation requests are approval-gated. The customer portal does not directly cancel subscriptions.
- Portal route-level `HttpCase` coverage is deferred until the local HTTP test harness is stable. Current automated coverage focuses on deterministic controller-helper and model behavior for ownership, policy, blocked states, and audit records.

## 10. Phase Result Log

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

## 11. Portal Payment Recovery Demo

This slice intentionally reuses Odoo's invoice portal payment page instead of creating a separate card-management flow.

Demo portal users use password `portal`:

- `portal.recovery.saved@example.com`: `PORTAL-RECOVERY-SAVED`, past due with an unpaid invoice, saved primary method, and manager-configured backup method.
- `portal.recovery.nomethod@example.com`: `PORTAL-RECOVERY-NOMETHOD`, past due with an unpaid invoice and no saved payment method.
- `portal.recovery.clear@example.com`: `PORTAL-RECOVERY-CLEAR`, active subscription with no recovery banner.
- `portal.recovery.other@example.com`: `PORTAL-RECOVERY-OTHER`, second portal customer for access isolation checks.

1. Generate or open a posted customer invoice linked to a subscription.
2. Leave the invoice unpaid or partially paid.
3. Open the subscription as the portal customer.
4. Confirm the subscription detail page shows **Payment Recovery Needed**.
5. Confirm the banner shows invoice number, due date, payment status, and residual amount.
6. Click **Open Invoice** and confirm it opens the Odoo invoice portal payment page.
7. If the subscription has a saved payment token, confirm **Retry Saved Method** is available and submit it.
8. Confirm the page returns with a submitted/completed payment message.
9. If no saved payment method exists, confirm the page explains that a saved method is required and directs the customer to pay the invoice or add a method.
10. Confirm paid invoices do not appear as payment recovery work.
11. Log in as `portal.recovery.saved@example.com` and confirm the saved-method retry action is available.
12. Log in as `portal.recovery.nomethod@example.com` and confirm the banner blocks retry until a method is saved.
13. Log in as `portal.recovery.clear@example.com` and confirm no recovery banner appears.
14. Log in as `portal.recovery.other@example.com` and confirm this customer cannot access the other recovery subscriptions.

## 12. Payment Attempt Ledger Demo

1. Open **Subscriptions > Billing > Payment Attempts**.
2. Confirm successful, pending, failed, cancelled, and exception outcomes appear with provider state when generated by tests or manual retries.
3. Open a payment attempt and confirm it links to the subscription, invoice, transaction, token, provider, and requesting user.
4. Open **Subscriptions > Billing > Failed Payments** and confirm recovery-required rows are visible.
5. Open **Subscriptions > Operations > Manager Operations** and confirm failed payment attempts appear as payment recovery work.
6. From a subscription, use the **Payments** stat button and confirm it filters attempts for that subscription only.
7. For portal retries, confirm the attempt source is **Portal** and recovery notes distinguish pending provider confirmation, successful recovery, and failed customer retry.
8. If a primary-method attempt failed and the subscription has a backup payment method, confirm the next retry records **Payment Method Role** as **Backup**.

## 13. Portal Payment Method Demo

1. Open a subscription as the portal customer.
2. Confirm the **Payment Method** panel shows the currently assigned method or a no-method state.
3. If the customer already has saved tokens, select one and click **Use Method**.
4. Confirm the subscription returns with **Payment method updated** and auto-pay reflects the assigned token.
5. Click **Add Method** and confirm Odoo's native payment-method validation form opens.
6. Complete validation with a tokenizing provider and confirm the return page assigns the newly saved token to the subscription.
7. Try assigning a token owned by another customer through a crafted request and confirm the server rejects it.

Backend backup payment method:

1. Open a subscription in the backend.
2. In the **Subscription** tab, set **Payment Token** to the primary saved method.
3. Set **Backup Payment Token** to a different active token owned by the same customer.
4. Confirm the form rejects a backup token that equals the primary token.
5. Confirm the form rejects a backup token owned by another customer.
6. Create or locate a failed payment attempt for the same invoice that used the primary method.
7. Trigger the next portal, manual, or automated retry and confirm the new payment attempt uses **Payment Method Role: Backup**.

## 14. Dunning Attempt Ledger Demo

1. Configure a dunning policy with email templates for every email or email-and-retry step.
2. Put a subscription into **Past Due** with **Dunning Start Date** in the past and **Next Dunning Date** due today.
3. Run scheduled action **Subscription: Process Dunning** or execute `sale.order._cron_process_dunning()` from an Odoo shell/test context.
4. Open **Subscriptions > Billing > Dunning Attempts**.
5. Confirm a row exists for the subscription with the policy, step, action type, status, amount at risk, and recovery URL.
6. Open the attempt and confirm **Open Subscription**, **Open Invoice** when available, and **Open Payment Attempt** when a retry was attempted.
7. Open the subscription and confirm the **Dunning** stat button filters attempts for that subscription.
8. Confirm dunning emails contain a portal recovery link to `/my/subscription/<id>`.
9. Move the subscription beyond the final-action delay and rerun dunning.
10. Confirm a final-action attempt is created and the subscription is cancelled, paused, or skipped according to the policy.

Automated coverage:

- `subscription_suite_dunning` tests cover dunning attempt creation for email steps.
- `subscription_suite_dunning` tests cover final cancellation attempt creation.
- `subscription_suite_dunning` tests cover email template validation for email-and-retry steps.
- `subscription_suite_dunning` tests cover the payment override signature used by portal and cron payment recovery.

## 15. Recovery Dashboard Demo

1. Open **Subscriptions > Operations > Operations Dashboard**.
2. Confirm **Payment Recovery** shows Active Dunning, MRR at Risk, Failed Payments, Recovered, Portal Attempts, Portal Pending, Portal Failed, Portal Recovered, and Manual Action.
3. Confirm **Dunning Attempts** shows Pending, Failed, and Final Actions.
4. Click **Active Dunning** and confirm it opens past-due subscriptions.
5. Click **MRR at Risk** and confirm it opens the same past-due subscriptions behind the at-risk MRR total.
6. Click **Failed Payments** and confirm it opens recovery-required failed payment attempts.
7. Click **Portal Attempts**, **Portal Pending**, **Portal Failed**, **Portal Recovered**, and **Manual Action** and confirm each opens the matching portal-originated payment attempts.
8. Click **Pending** or **Failed** under Dunning Attempts and confirm each opens filtered dunning attempts.
9. Click **Final Actions** and confirm final pause/cancel/no-action dunning attempts are visible.
10. Click **Recovered** and confirm subscriptions with a dunning recovery log this month are listed.

Automated coverage:

- `subscription_suite_dunning` tests compare recovery dashboard KPIs against their source domains.
- `subscription_suite_dunning` tests verify the dashboard drilldown domains for active dunning, failed payments, portal recovery buckets, pending dunning attempts, and final actions.

## 16. Manual Dunning Retry Demo

1. Open **Subscriptions > Billing > Dunning Attempts**.
2. Open a non-final dunning attempt linked to an unpaid or partially paid invoice.
3. Confirm the subscription has a saved payment method.
4. Click **Retry Payment**.
5. Confirm the dunning attempt shows **Manual Retries**, **Last Manual Retry At**, and a linked **Payment Attempt**.
6. Open the linked payment attempt and confirm it records source **Manual**.
7. If the payment succeeds, confirm the subscription moves from **Past Due** back to **Active**.
8. Try **Retry Payment** on a final cancel/pause/no-action attempt and confirm it is blocked.

Automated coverage:

- `subscription_suite_dunning` tests cover manual retry from a dunning attempt.
- `subscription_suite_dunning` tests cover missing payment method and final-action retry guards.
- `subscription_suite_dunning` tests cover final dunning action idempotency.
- `subscription_suite_billing` tests cover backup payment method validation and next-retry fallback selection.

## 17. Automated Dunning Retry Demo

1. Open **Subscriptions > Configuration > Dunning Policies**.
2. Configure a dunning step with **Action** set to **Send Email & Retry Payment**.
3. Set **Retry Delay (Hours)** and **Max Auto Retries**.
4. Trigger the dunning step for a past-due subscription with a saved payment method and an unpaid posted invoice.
5. Open **Subscriptions > Billing > Dunning Attempts**.
6. Confirm the attempt shows **Auto Retry Enabled**, **Next Auto Retry At**, and **Max Auto Retries**.
7. Run scheduled action **Subscription: Retry Dunning Payments**.
8. Confirm the dunning attempt links a payment attempt and increments **Auto Retries**.
9. If the retry fails until the maximum is reached, confirm **Retry Exhausted** is enabled and **Next Auto Retry At** is cleared.
10. If the retry succeeds, confirm the subscription is recovered to **Active**.

Automated coverage:

- `subscription_suite_dunning` tests cover scheduled retry creation for email-and-retry steps.
- `subscription_suite_dunning` tests cover auto retry cron linking payment attempts.
- `subscription_suite_dunning` tests cover auto retry using the backup method after a primary-method failure.
- `subscription_suite_dunning` tests cover retry exhaustion.
- `subscription_suite_dunning` tests cover retry setting validation.

## 18. Seat Billing Foundation Demo

1. Open **Subscriptions -> Configuration -> Plans**.
2. Open **Team Seats Monthly** and confirm the plan has a base recurring line and a seat recurring line.
3. Confirm each plan line has the expected **Component Type**: **Base** for the platform line and **Seat** for the team-seat line.
4. Open the demo subscription **Team Seats Monthly**.
5. Confirm the subscription shows **Seats** with the expected quantity from recurring seat lines.
6. Create a renewal quote and confirm the copied seat line keeps its component type and quantity.
7. Generate an invoice for the subscription and confirm the seat line uses normal Odoo quantity times unit-price billing.
8. Open the same subscription in the customer portal and confirm **Seats** appears as read-only summary data.
9. Open a subscription without seat lines and confirm the portal does not show a seat summary.

Automated coverage:

- `subscription_suite` tests cover default component type, plan application, seat quantity computation, renewal preservation, and upsell component preservation.
- `subscription_suite_billing` tests cover seat invoice quantity and unit-price behavior plus existing MRR and billing recovery coverage.
- `subscription_suite_portal` tests cover read-only portal seat data and existing ownership/payment recovery flows.

## 19. Immediate Seat Change Demo

1. Open the demo subscription **Team Seats Monthly**.
2. Confirm the subscription is active or past due and has exactly one recurring line with **Component Type** set to **Seat**.
3. Click **Change Seats**.
4. Increase the seat quantity and confirm the wizard shows current seats, new seats, effective date, current MRR, new MRR, net amount, and a proration preview.
5. Confirm the change.
6. Open **Prorations** from the subscription and confirm a **Seat Change** proration exists with old seats, new seats, applied state, and an adjustment invoice for an increase.
7. Repeat with a lower seat quantity and confirm a credit note is created for a decrease.
8. Confirm the subscription **Seats**, recurring total, and MRR update after each change.
9. Confirm subscription logs and MRR movement history record the seat change.

Automated coverage:

- `subscription_suite_billing` tests cover immediate seat increase, decrease, wizard apply, proration audit fields, adjustment invoice, credit note, MRR movement, logs, and blocked states.

## 20. Scheduled Seat Change Demo

1. Open the demo subscription **Team Seats Monthly**.
2. Confirm the subscription is active, paused, or past due and has exactly one recurring line with **Component Type** set to **Seat**.
3. Click **Change Seats**.
4. Select **Next Billing Period** in the **Apply** field.
5. Enter a different seat quantity and confirm the effective date is the subscription's next invoice date.
6. Confirm the wizard shows a zero net amount and explains that no proration document is generated at the billing boundary.
7. Confirm the change and verify the subscription shows **Pending Seat Quantity** and **Pending Seat Change Date**.
8. Use **Cancel Seat Change** before billing and confirm the pending fields clear without changing current seats.
9. Schedule the change again, run recurring billing, and confirm the seat quantity updates before the invoice is created.
10. Confirm the generated invoice uses the new seat quantity, no seat-change proration document is created, and subscription logs plus MRR movement history record the scheduled change.

Automated coverage:

- `subscription_suite_billing` tests cover scheduled wizard submission, zero-proration preview, cancellation, no-op clearing, application before recurring invoice generation, invoice quantity, MRR movement, and shared blocked states.

## 21. Backend Add-on Operations Demo

1. Open the demo subscription **Team Seats Monthly**.
2. Confirm the subscription is active, paused, or past due.
3. Click **Change Add-ons**.
4. Select **Add**, choose the support add-on product, enter quantity, unit price, and discount, then confirm **Immediately with Proration**.
5. Confirm a recurring line with **Component Type** set to **Add-on** is added or updated, MRR increases, and an **Add-on Change** proration creates an adjustment invoice when inside the billing period.
6. Open **Change Add-ons** again, select **Remove**, choose the existing add-on line, enter the quantity to remove, and confirm immediately.
7. Confirm the add-on quantity decreases or reaches zero, MRR decreases, and an **Add-on Change** proration creates a credit note when applicable.
8. Repeat add/remove with **Next Billing Period** and confirm **Pending Add-on Operation**, product, quantity, and date appear on the subscription without a proration document.
9. Use **Cancel Add-on Change** and confirm pending fields clear without changing current add-on lines.
10. Schedule the change again, run recurring billing, and confirm the add-on change applies before invoice generation and the invoice reflects the new add-on quantity.

Automated coverage:

- `subscription_suite_billing` tests cover immediate add/remove, add-on proration invoices and credit notes, scheduled add/remove before billing, cancellation, wizard scheduling, MRR movement, and blocked states.

## 22. Tiered And Volume Pricing Demo

1. Open **Subscriptions -> Configuration -> Plans**.
2. Open **Volume Seats Monthly** and confirm the seat line uses **Pricing Model** set to **Volume** with two tiers: 1 to 10 at 12.00 and 10+ at 10.00.
3. Confirm the plan monthly equivalent uses the matched tier price for the full quantity.
4. Open **Graduated Seats Monthly** and confirm the seat line uses **Pricing Model** set to **Graduated** with the same tiers.
5. Confirm the graduated plan monthly equivalent totals the first bracket at 12.00, later units at 10.00, and stores the effective unit price when copied to a subscription line.
6. Create a subscription from a tiered plan and confirm the recurring line shows the copied pricing model while the invoice still contains one line with the effective unit price.
7. Create a renewal quote and confirm the recurring line keeps the pricing model and copied tiers.
8. On a tiered seat subscription, use **Change Seats** to cross a tier boundary and confirm the seat line's unit price, recurring total, MRR, proration, and generated invoice reflect the new effective unit price.
9. Confirm flat add-ons still use normal quantity times unit-price behavior.

Automated coverage:

- `subscription_suite` tests cover flat pricing compatibility, volume pricing, graduated pricing, plan MRR, renewal quote tier copying, and invalid tier validation for gaps, overlaps, non-positive quantities, non-positive prices, and missing open-ended final tiers.
- `subscription_suite_billing` tests cover plan application copying tier metadata, tiered invoice single-line presentation, and tier-aware seat change MRR/proration recomputation while existing flat add-on and payment recovery tests continue to run.

## 23. Usage Metering Foundation Demo

1. Open **Subscriptions -> Configuration -> Usage Meters**.
2. Confirm **API Calls** exists with code `API_CALLS` and unit of measure **Units**.
3. Open **Subscriptions -> Configuration -> Plans** and open **Team Seats Monthly**.
4. In **Usage Billing**, confirm the plan includes **API Calls** with an included quantity of `1000`, overage product **API Call Overage**, and overage unit price `0.02`.
5. Open **Subscriptions -> Billing -> Usage Events** and confirm the demo events for **Team Seats Monthly** are in **Ready** state and inside the current billing period.
6. Run recurring billing for the demo subscription or the billing cron.
7. Open **Subscriptions -> Billing -> Usage Summaries** and confirm one summary exists for **API Calls** with used quantity, included quantity, billable quantity, amount, and a linked invoice.
8. Open the generated invoice and confirm it includes the normal recurring lines plus one **Usage overage: API Calls** line when usage exceeds the allowance.
9. Run billing again for the same period and confirm no duplicate usage summary or duplicate usage invoice line is created.
10. For a plan with a usage rule but no events in the billing period, confirm billing creates no empty usage summary and no usage invoice line.

Automated coverage:

- `subscription_suite_billing` tests cover usage rule validation, one-summary aggregation by subscription/meter/period, no-event summary suppression, included usage with no invoice line, overage invoice line quantity/subtotal, event invoicing, and idempotent reruns.

## 24. Usage Metering Audit Hardening Demo

1. Open **Subscriptions -> Billing -> Usage Events**.
2. Create or open a **Ready** usage event that has not been invoiced.
3. Click **Cancel Event** and confirm the event moves to **Cancelled**.
4. Confirm cancelled events do not appear in the linked draft usage summary after recomputation.
5. Open an uninvoiced usage summary and click **Recompute Usage** after adding another ready event in the same period.
6. Confirm the summary used quantity, billable quantity, and amount update from ready events only.
7. Generate the recurring invoice for a subscription with usage.
8. Confirm invoiced events cannot be cancelled or edited and the linked usage summary cannot be recomputed.

Automated coverage:

- `subscription_suite_billing` tests cover cancelled usage exclusion, cancellation-driven summary recomputation/clearing, recomputing draft summaries with new events, and locked invoiced usage records.
