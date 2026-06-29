# Subscription Suite User Guide

## Daily Workflow

Subscription Suite is operated from the **Subscriptions** app. Sales and
subscription users work mainly with subscriptions, plans, invoices, dunning,
payment recovery, customer requests, and generated reports.

Use the backend with Odoo developer mode only when troubleshooting views or
technical configuration. Normal subscription work does not require developer
mode.

## Subscriptions

Open **Subscriptions -> Subscriptions** to review active customer contracts.

Common actions:

- Create a subscription from a configured plan.
- Confirm the quotation to start the subscription.
- Review state, plan, recurring amount, MRR, next invoice date, payment method,
  seat quantity, pending changes, and sales history.
- Use renewal and upsell quotation actions when plan policy allows them.
- Pause, resume, cancel, or schedule cancellation through the provided
  subscription actions and request records.

Subscriptions should be managed through their buttons and wizards. Do not edit
technical state fields directly unless you are correcting test data in a
controlled development database.

## Plans And Pricing

Open **Subscriptions -> Plans** to manage plan products, recurring lines,
upgrade or downgrade paths, renewal and upsell policies, pricing models,
usage rules, discount metadata, and cancellation or pause policy.

Plan lines can represent:

- Base subscription charges.
- Seat-based recurring charges.
- Add-ons.
- Tiered or volume-priced recurring lines.
- Usage overage rules through configured usage meters.

When a plan is applied, recurring line configuration is copied onto the
subscription. Later changes to the plan do not silently rewrite active
subscriptions.

## Billing

Use **Subscriptions -> Billing** for recurring invoice generation, billing
attempts, payment attempts, usage summaries, deferred revenue, and finance
operations.

Recommended billing review:

1. Check due subscriptions by next invoice date.
2. Run recurring billing in a staging or controlled batch first.
3. Review billing attempts and generated invoices.
4. Re-run the same batch to confirm idempotency when testing.
5. Review failed payment attempts and recovery-required records.

Billing reruns are designed to avoid duplicate subscription-period invoices,
but users should still review exceptions before enabling scheduled jobs in a
new database.

## Payment Recovery

Payment recovery uses Odoo payment tokens and transactions. Managers can review
payment attempts, failed recoveries, pending provider confirmations, backup
payment fallback, and manual-action-required items.

Portal customers can see recovery guidance for eligible unpaid subscription
invoices, select an existing saved token, validate a new saved method through
Odoo payment validation, and retry payment when policy and ownership checks
allow it.

Provider-specific webhook behavior is not part of this suite. Odoo payment
transaction state remains the integration boundary.

## Dunning

Open **Subscriptions -> Dunning** to review dunning attempts, escalations, and
final-action conditions.

Dunning should be tested with controlled past-due subscriptions before enabling
automated scheduled actions. Retry-exhausted and final-action records should be
reviewed through Manager Operations and recovery analytics.

## Customer Requests

Portal lifecycle requests appear in backend request menus. Managers review and
approve or reject:

- Plan change requests.
- Pause and resume requests.
- Cancellation requests.

Approvals apply existing subscription policy. Rejections should include a clear
reason so the customer-facing history remains understandable.

## Analytics

Generated analytics are operational reports, not accounting revenue recognition.
They remain separated by company, currency, and plan where applicable.

Generate analytics in this order:

1. MRR snapshots.
2. MRR reconciliation.
3. Movement anomalies when needed.
4. KPI summaries.
5. KPI dashboard.
6. MRR waterfall.
7. Retention cohorts.
8. Revenue forecast.
9. ARPU summary.
10. LTV summary.
11. Churn reasons.
12. Top plans.
13. At-risk subscriptions.
14. Payment recovery.
15. Trial conversion.

Use generated statuses and drilldowns to review missing upstream inputs before
treating a report as ready.

## Manager Operations

Manager Operations gives a consolidated view of billing, dunning, payment
recovery, recognition, analytics, and operational run issues.

Review:

- Failed and partial operation runs.
- Retry-exhausted dunning.
- Payment recovery work.
- Failed or skipped recognition runs.
- Source drilldowns before taking corrective action.

Generic replay is not supported. Use the specific safe retry actions provided
by the related billing, dunning, payment, or finance workflow.

## Data Operations

Migration and backfill tools are manager-only. Always validate CSV files before
apply mode, and apply only the exact file hash that was validated.

Use [Migration And Data Operations Runbook](MIGRATION_RUNBOOK.md) for supported
CSV schemas, validation, apply, rerun, and correction workflows.

