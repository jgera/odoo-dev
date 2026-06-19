# Demo Data Inventory

This inventory tracks the demo records that make each phase visible and testable. Update it whenever demo XML, demo scripts, or manual demo setup changes.

## Current Demo Source

Primary demo XML:

```text
subscription_suite/demo/subscription_demo.xml
subscription_suite_billing/demo/plan_change_approval_demo.xml
```

The current demo data is loaded by the core `subscription_suite` manifest and billing demo additions from `subscription_suite_billing`.

## Current Demo Records

### Products

| XML ID | Model | Purpose |
| --- | --- | --- |
| `subscription_suite.demo_product_basic` | `product.product` | Basic subscription service product |
| `subscription_suite.demo_product_pro` | `product.product` | Pro subscription service product |
| `subscription_suite.demo_product_support_addon` | `product.product` | Priority support subscription add-on |
| `subscription_suite_billing.demo_product_api_call_overage` | `product.product` | API-call overage billing product |

### Plans

| XML ID | Billing | Trial | Purpose |
| --- | --- | --- | --- |
| `subscription_suite.demo_plan_basic` | Monthly | 14 days | Basic monthly plan |
| `subscription_suite.demo_plan_pro` | Annual | 30 days | Pro annual plan |
| `subscription_suite.demo_plan_team_seats` | Monthly | 0 days | Seat-based plan with API-call usage rule |
| `subscription_suite.demo_plan_discounted_monthly` | Monthly | 0 days | Promotional monthly plan with an active expiring discount |

### Plan Lines

| XML ID | Product | Price | Purpose |
| --- | --- | --- | --- |
| `subscription_suite.demo_plan_basic_line` | Basic Subscription Tier | 29.00 | Monthly recurring plan line |
| `subscription_suite.demo_plan_pro_line` | Pro Subscription Tier | 299.00 | Annual recurring plan line |
| `subscription_suite.demo_plan_discounted_monthly_line` | Basic Subscription Tier | 29.00 | Base plus active promotional discount metadata |
| `subscription_suite_billing.demo_plan_team_seats_usage_api_calls` | API Calls | 0.02 overage | Included API-call allowance and overage rule |

### Usage Metering

| XML ID | Model | Purpose |
| --- | --- | --- |
| `subscription_suite_billing.demo_usage_meter_api_calls` | `subscription.usage.meter` | API-call meter used by the Team Seats plan |
| `subscription_suite_billing.demo_usage_event_team_seats_api_calls_1` | `subscription.usage.event` | Ready demo API-call usage event |
| `subscription_suite_billing.demo_usage_event_team_seats_api_calls_2` | `subscription.usage.event` | Ready demo API-call usage event |

### Cancellation Reasons

| XML ID | Purpose |
| --- | --- |
| `subscription_suite.demo_cancel_reason_expensive` | Price-driven churn |
| `subscription_suite.demo_cancel_reason_switched` | Competitor churn |
| `subscription_suite.demo_cancel_reason_project_end` | End-of-project churn |

### Subscriptions

| XML ID | State | Partner | Purpose |
| --- | --- | --- | --- |
| `subscription_suite.demo_subscription_active` | Active | `base.res_partner_2` | Active annual subscription |
| `subscription_suite.demo_subscription_trial` | Trial | `base.res_partner_3` | Trial subscription with future trial end |
| `subscription_suite.demo_subscription_paused` | Paused | `base.res_partner_4` | Paused monthly subscription |
| `subscription_suite.demo_subscription_due_billing` | Active | `base.res_partner_2` | Active monthly subscription due for Phase 1 billing-run validation; confirm before running cron |
| `subscription_suite.demo_subscription_active_discount` | Active | `base.res_partner_2` | Active monthly subscription with an active expiring promotional discount |
| `subscription_suite.demo_subscription_expired_discount` | Active | `base.res_partner_3` | Due monthly subscription with expired promotional metadata for billing expiry validation |
| `subscription_suite.demo_subscription_future_discount` | Active | `base.res_partner_4` | Active monthly subscription with future-dated promotional metadata for manager refresh/search validation |
| `subscription_suite.demo_subscription_cancelled` | Cancelled | `base.res_partner_1` | Churned annual subscription |
| `subscription_suite.demo_subscription_pause_resume_example` | Paused | `base.res_partner_3` | Paused subscription with next invoice date for resume-date validation |
| `subscription_suite.demo_subscription_scheduled_cancellation` | Active | `base.res_partner_4` | Active subscription with end-of-period cancellation already scheduled |
| `subscription_suite.demo_subscription_renewal_quote` | Quotation | `base.res_partner_2` | Renewal quotation linked to the active annual subscription |
| `subscription_suite.demo_subscription_upsell_quote` | Quotation | `base.res_partner_2` | Upsell quotation linked to the active annual subscription |

### MRR Movements

| XML ID | Movement | Purpose |
| --- | --- | --- |
| `subscription_suite.demo_mrr_movement_active_new` | New | New MRR for active subscription |
| `subscription_suite.demo_mrr_movement_active_expansion` | Expansion | Expansion movement example |
| `subscription_suite.demo_mrr_movement_paused_new` | New | New MRR for paused subscription |
| `subscription_suite.demo_mrr_movement_cancelled_churn` | Churn | Churned MRR for cancelled subscription |

### Request Queues

| XML ID | Model | Purpose |
| --- | --- | --- |
| `subscription_suite.demo_cancellation_request_pending` | `subscription.cancellation.request` | Pending portal cancellation request |
| `subscription_suite.demo_lifecycle_request_resume_pending` | `subscription.lifecycle.request` | Pending portal resume request |

## Current Coverage

| Scenario | Covered today | Notes |
| --- | --- | --- |
| Monthly plan | Yes | Basic Monthly |
| Annual plan | Yes | Pro Annual |
| Active subscription | Yes | `demo_subscription_active` |
| Trial subscription | Yes | `demo_subscription_trial` |
| Paused subscription | Yes | `demo_subscription_paused` |
| Cancelled subscription | Yes | `demo_subscription_cancelled` |
| Pause/resume billing-date example | Yes | `demo_subscription_pause_resume_example` |
| Scheduled cancellation | Yes | `demo_subscription_scheduled_cancellation` |
| Portal cancellation request | Yes | `demo_cancellation_request_pending` |
| Portal lifecycle request | Yes | `demo_lifecycle_request_resume_pending` |
| Past-due subscription | No | Needed for dunning and portal recovery phases |
| Subscription due for billing | Yes | `demo_subscription_due_billing` can generate a billing attempt and invoice after confirmation |
| Open subscription invoice | No | Generated by running billing cron against due demo records |
| Paid subscription invoice | No | Needed for portal invoice-history demos |
| Billing run/attempt | Yes | Generated by running billing cron against confirmed due demo records |
| Payment attempt | No | Phase 4 |
| Dunning attempt | No | Phase 4 |
| Renewal quotation | Yes | `demo_subscription_renewal_quote` |
| Upsell quotation | Yes | `demo_subscription_upsell_quote` |
| Usage billing | Yes | API-call meter/rule/events support usage billing walkthroughs |
| Time-limited recurring discount | Yes | `demo_plan_discounted_monthly`, `demo_subscription_active_discount`, and `demo_subscription_expired_discount` |
| Backend discount operations | Yes | `demo_subscription_active_discount`, `demo_subscription_expired_discount`, and `demo_subscription_future_discount` |
| MRR snapshots | Generated | Generate from **Subscriptions -> Reporting -> Generate MRR Snapshot** after demo install/upgrade; static XML is intentionally avoided |
| MRR reconciliation | Generated | Generate from **Subscriptions -> Reporting -> Generate MRR Reconciliation** after creating opening/closing snapshots; static XML is intentionally avoided |
| MRR movement anomalies | Generated | Generate from **Subscriptions -> Reporting -> Generate MRR Movement Anomalies** for audit ranges; static XML is intentionally avoided |
| MRR KPI summaries | Generated | Generate from **Subscriptions -> Reporting -> Generate MRR KPI Summary** after snapshots and reconciliation; static XML is intentionally avoided |
| MRR KPI dashboards | Generated | Generate from **Subscriptions -> Reporting -> Generate MRR KPI Dashboard** after KPI summaries; static XML is intentionally avoided |
| MRR waterfalls | Generated | Generate from **Subscriptions -> Reporting -> Generate MRR Waterfall** after KPI summaries; static XML is intentionally avoided; verify expected closing, actual closing, and variance |
| Retention cohorts | Generated | Generate from **Subscriptions -> Reporting -> Generate Retention Cohorts** for a cohort month range; static XML is intentionally avoided |
| Revenue forecasts | Generated | Generate from **Subscriptions -> Reporting -> Generate Revenue Forecast** for a forecast month range; static XML is intentionally avoided |
| Analytics performance smoke | Generated/Test-only | Covered by `subscription_suite_reports` automated smoke data; full large demo-data generator remains Phase 8 |
| Generated analytics lifecycle | Test-only | Covered by `subscription_suite_reports` lifecycle tests for manager-only generation and scoped reruns |
| ARPU summaries | Generated | Generate from **Subscriptions -> Reporting -> Generate ARPU Summary** after opening and closing MRR snapshots; static XML is intentionally avoided |
| LTV summaries | Generated | Generate from **Subscriptions -> Reporting -> Generate LTV Summary** after ARPU summaries and retention cohorts; static XML is intentionally avoided |
| Churn reason summaries | Generated | Generate from **Subscriptions -> Reporting -> Generate Churn Reasons** for cancelled/expired subscriptions in a selected period; static XML is intentionally avoided; review MRR source quality and feedback coverage buckets |
| Top plan summaries | Generated | Generate from **Subscriptions -> Reporting -> Generate Top Plans** after snapshots, KPI summaries, ARPU, LTV, forecasts, and churn reasons; static XML is intentionally avoided |
| At-risk subscription summaries | Generated | Generate from **Subscriptions -> Reporting -> Generate At-Risk Subscriptions** after creating operational signals such as past-due subscriptions, open invoices, payment attempts, dunning attempts, pending cancellations, upcoming invoices, and renewal dates; static XML is intentionally avoided |
| Payment recovery summaries | Generated | Generate from **Subscriptions -> Reporting -> Generate Payment Recovery** after creating payment attempts, open unpaid/partial subscription invoices, dunning attempts, and optional at-risk summaries; static XML is intentionally avoided |
| Trial conversion summaries | Generated | Generate from **Subscriptions -> Reporting -> Generate Trial Conversion** after selecting a period with trial-started subscriptions; conversion is inferred from `subscription_start_date`, and static XML is intentionally avoided |
| Analytics generation guide | Odoo-native guide | Open **Subscriptions -> Reporting -> Analytics Generation Guide** before generating Phase 6 analytics; it lists prerequisites and the recommended generated-record sequence |
| Deferred revenue schedules | Generated | Generate from posted subscription invoices with `subscription_period_start` and `subscription_period_end`; static schedule XML is intentionally avoided so schedules reconcile to the generated invoice amount |
| Revenue recognition posting | No | Later Phase 7 slice |

## Demo Expansion Rules

- Demo XML should be safe to install repeatedly.
- Accounting-heavy scenarios should use demo scripts if static XML would create fragile records.
- Demo records should be findable by clear names from Odoo search views.
- Portal demo records should identify the partner/user used for portal login.
- Every new phase should add at least one visible demo scenario or document why it cannot.

## Phase Demo Targets

| Phase | Required demo additions |
| --- | --- |
| Phase 0 | Inventory, portal customer instructions, validation checklist |
| Phase 1 | Due subscriptions, billing runs, billing attempts, failed billing example. `demo_subscription_due_billing` is the initial due subscription fixture and should be confirmed before cron validation. |
| Phase 2 | Scheduled cancellation, pause/resume, renewal quotation, and upsell quotation examples are present. |
| Phase 3 | Portal users and subscriptions with allowed/blocked actions |
| Phase 4 | Past-due subscriptions, dunning stages, payment attempts, recovery path |
| Phase 5 | Seat, add-on, tiered, volume, usage, and time-limited discount examples |
| Phase 6 | MRR snapshots, reconciliation rows, movement anomalies, KPI summaries, KPI dashboards, waterfalls, retention cohorts, revenue forecasts, ARPU summaries, LTV summaries, churn reason summaries, top plan summaries, at-risk subscription summaries, payment recovery summaries, trial conversion summaries, analytics generation guidance, analytics smoke coverage, and generated-record lifecycle checks are generated from current or controlled records; churn reason summaries expose MRR source quality and feedback coverage buckets; at-risk summaries use current operational payment, dunning, renewal, and cancellation signals; payment recovery summaries use payment attempts, open invoices, dunning escalation, and at-risk rows; trial conversion summaries use existing trial dates and inferred conversion from subscription start date; later add multi-month MRR movement history and richer churn feedback classification |
| Phase 7 | Deferred revenue schedules are generated from posted subscription invoices with valid service periods; journal posting, reversals, credit-note adjustment examples, and finance reconciliation reports remain later Phase 7 targets |
| Phase 8 | Complete end-to-end demo story and optional large-data generator |
