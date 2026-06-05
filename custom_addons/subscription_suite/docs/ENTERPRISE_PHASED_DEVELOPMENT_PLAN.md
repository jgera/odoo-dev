# Subscription Suite - Enterprise Phased Development Plan

**Target Odoo version:** 19.0 only  
**Document status:** Working execution roadmap  
**Created:** 2026-06-04  
**Scope:** `custom_addons/subscription_suite`  

This document translates the original PRD into an enterprise-grade delivery plan. It is based on the current addon code, the existing PRD, Odoo 19 subscription behavior, and current subscription billing competitors.

The goal is not to copy every SaaS billing platform feature. The goal is to build the strongest Odoo 19 Community-native subscription suite: sale-order based, accounting-aware, testable, resilient under cron load, and useful to sales, finance, support, and customers.

---

## 1. Product Positioning

Subscription Suite should become:

- An Odoo-native subscription engine for Community Edition.
- A practical alternative to Odoo Enterprise Subscriptions for teams that want open source control.
- A deeper operational module than simple recurring invoice addons.
- A finance-safe billing system with clear logs, retries, analytics, and accounting traceability.

The strongest differentiator remains the current architectural decision: subscriptions extend `sale.order`. That keeps subscriptions close to Odoo's native quotation, sales, invoicing, tax, pricelist, payment, chatter, portal, and accounting surfaces.

---

## 2. Current Implementation Audit

### 2.1 Addons Present Today

| Addon | Current purpose | State |
| --- | --- | --- |
| `subscription_suite` | Core plans, subscription states, sale order fields, recurring invoice cron, cancellation wizard, logs, MRR movement, demo data, menus | Implemented foundation |
| `subscription_suite_billing` | Proration model, immediate and next-period plan change wizard, payment-token auto-collection cron | Partial enterprise billing |
| `subscription_suite_dunning` | Dunning policies, dunning steps, failed-payment state handling, recovery cron | Initial dunning engine |
| `subscription_suite_portal` | Portal list/detail pages and invoice history display | Read-only portal plus initial polish |
| `subscription_suite_reports` | SQL report model, MRR/ARR/churn measures, MRR movement views | Basic analytics foundation |

### 2.2 Implemented Strengths

- Odoo 19-only scope is explicit.
- `sale.order` is the subscription record, which matches Odoo-native sales and invoice workflows.
- Lifecycle states exist: `draft`, `trial`, `active`, `paused`, `past_due`, `cancelled`, `expired`.
- Subscription plans include recurring products, trial days, setup fee, pause rules, upgrade/downgrade paths, cancellation policy, and monthly equivalent pricing.
- Core subscription actions exist: confirm, convert trial, pause, resume, cancel, expire.
- Recurring invoice cron creates invoices from subscription orders.
- Plan change supports immediate prorated changes and scheduled next-period changes that apply before renewal invoicing.
- Dunning policy and dunning policy line models exist.
- Customer portal has subscription list/detail pages and invoice history.
- Reporting includes SQL-backed subscription analysis and MRR movement reporting.
- Tests exist for lifecycle, proration, plan change, dunning progression, and basic portal record filtering.

### 2.3 Important Current Gaps

These are not criticisms; they are the exact next enterprise work.

| Area | Current gap | Enterprise risk |
| --- | --- | --- |
| Billing cron | Billing run, billing attempt, idempotency key, duplicate-period guard, processing lock, retry classification, manual retry, automated retry scheduling, retry exhaustion activities, failed-billing queue, and retry settings now exist | Duplicate invoices are reduced and failed billing recovery is visible; remaining work is deeper operational reporting |
| Invoice generation | Billing attempts now track success, failure, skipped state, invoice link, period, amount, error message, failure category, retryability, retry timing, retry exhaustion, failure counts, first/last failure times, recovery notes, and chatter logs | Auditability is improved; remaining reporting work belongs in broader analytics |
| Payment collection | Basic token transaction creation exists, but no retry campaign, provider-specific result handling, attempt ledger, or backup payment method | Payment failures become opaque |
| Dunning | Policy cron exists, but no attempt model, no recovery metrics, limited customer recovery workflow | Hard to operate at scale |
| Portal | Subscription, invoice, pending plan change, lifecycle, cancellation, and approval visibility exists; customers can request next-period plan changes, pause/resume, and cancellations through approval-gated requests | Update-payment still requires support |
| Pause/resume | Pause/resume now adjusts the next invoice date by paused duration and respects max pause days | Remaining work is mostly portal self-service and support workflow polish |
| Cancellation | Immediate and end-of-period cancellation now exist, including scheduled cancellation reversal and cron finalization | Remaining work is mostly renewal/upsell lifecycle parity and optional approvals |
| Renewals/upsells | Linked renewal and upsell quotations, sales history, upsell effective date, proration ledger, draft adjustment invoices/credit notes, immediate and scheduled next-period plan changes, approval-gated plan change requests, upgrade/downgrade path checks, and minimum commitment enforcement now exist; remaining work is deeper sales-policy controls | Sales workflow parity is improving, but advanced policy depth is still needed |
| Usage/seats | No usage-based billing, seat metering, tiered pricing, or quantity sync | Weak for SaaS and B2B subscriptions |
| Analytics | Basic MRR/ARR exists; no NRR, GRR, retention cohorts, forecast, LTV, trial conversion, or dashboard | Management reporting is incomplete |
| Revenue recognition | Not implemented | Finance/compliance gap for annual/prepaid contracts |
| Multi-currency | Amounts remain in order currency; no normalized company-currency MRR ledger | Cross-currency analytics can mislead |
| Security | Groups and multi-company rules exist, but portal route tests and full model coverage are limited | Access regressions may go unnoticed |
| Performance | No explicit indexes or scale tests for 10K+ subscriptions | Cron/report performance unknown |
| Packaging | No release checklist, migration notes, or full user/admin docs | Hard to deploy confidently |

---

## 3. Competitor Benchmark

### 3.1 Odoo Subscriptions 19

Odoo's first-party Subscriptions app is the UX and integration benchmark. It emphasizes:

- Recurring plans and automatic invoicing.
- Manual or automatic subscription creation through sales and online sales.
- Integration with Invoicing, CRM, Sales, and Helpdesk.
- Renewals with renewal quotations and sales history.
- Upsells through linked quotations, with proration for recurring service products.
- Portal self-service closing with configured close reasons.
- Automatic payment behavior and a "payment failure / contract in exception" safety path.
- Reporting pages including subscription analysis, retention analysis, MRR breakdown, and MRR analysis.

Enterprise implication for Subscription Suite:

- We should match Odoo-native flows first: recurring plans, quotation-to-subscription, renewal quotation, upsell quotation, close reasons, portal preview, sales history, and subscription reports.
- Then we should exceed Odoo by adding clearer dunning automation, better proration controls, stronger billing idempotency, richer analytics, and optional revenue recognition.

### 3.2 Stripe Billing

Stripe sets the modern billing infrastructure benchmark:

- Subscriptions and usage-based billing in one flow.
- Customer portal.
- Prorations, installments, credit notes, and debit notes.
- Smart retries, expired card updates, revenue recovery automations, cancellation surveys.
- Billing analytics, revenue recovery analytics, data warehouse sync, automated reconciliation, revenue recognition, and strong compliance posture.

Enterprise implication:

- Build an explicit payment attempt ledger and recovery workflow.
- Treat usage-based billing, data export, and payment-recovery analytics as enterprise features, not extras.
- Add clear extension points for payment providers instead of embedding assumptions in `sale.order`.

### 3.3 Chargebee

Chargebee is a broad subscription operations benchmark:

- Self-service customer portal with subscription management, invoices, payment information, and billing information.
- Dunning with smart retries, card updater, and custom dunning emails.
- Revenue analytics with many out-of-the-box metrics, reports, alerts, and trial analytics.
- Revenue recognition and deferred revenue reporting.

Enterprise implication:

- Add role-specific analytics, trial conversion metrics, and scheduled dashboard/report digests.
- Make dunning observable: recovered revenue, failed recovery, next action, and policy performance.
- Add finance-grade deferred revenue reporting.

### 3.4 Recurly

Recurly is strong in retention and revenue recovery:

- Cancel-save flows and win-back offers.
- Intelligent retries and account updater.
- Subscriber self-service to skip, swap, or cancel plans.
- Revenue recognition and subscription analytics.

Enterprise implication:

- Portal cancellation should not be a single destructive button. It should support retention offers, reason capture, downgrade offers, pause instead of cancel, and end-of-period options.
- Dunning should eventually support retry optimization hooks and recovery reporting.

### 3.5 Paddle

Paddle's customer portal benchmark is useful because it is focused:

- Customers can view payments, download invoices, update payment details, and manage subscriptions.
- Magic-link or authenticated portal access.
- Cancellation flows are triggered before final cancellation.
- Multilingual/customer-market support is treated as a normal portal concern.

Enterprise implication:

- Subscription Suite portal should become a complete billing workspace, not just a subscription display page.
- Portal routes must be CSRF-safe, access-token aware, and covered by HTTP tests.

### 3.6 Zuora

Zuora is the enterprise finance benchmark:

- Quote-to-cash orientation.
- Billing, collections, and revenue recognition on one platform.
- Usage, subscription, and hybrid monetization.
- AR subledger behavior and finance-team compliance workflows.

Enterprise implication:

- Later phases should add contract terms, billing schedule traceability, revenue recognition, audit exports, and reconciliation reports.
- The product should remain Odoo-native rather than becoming an external billing silo.

---

## 4. Enterprise Readiness Principles

Every future phase should follow these principles.

### 4.1 Reliability Before More Buttons

Billing must be idempotent before customer self-service grows. A customer portal action that changes plans or cancels subscriptions is dangerous if the billing cron can duplicate invoices or lose retries.

### 4.2 Ledger Every Important Event

Enterprise users need evidence. Create explicit records for billing runs, invoice attempts, payment attempts, dunning attempts, plan changes, and revenue recognition lines.

### 4.3 Odoo-Native UX First

Use Odoo actions, wizards, chatter, smart buttons, activities, search views, kanban/list/form/pivot/graph views, and portal patterns. Do not build an isolated app inside Odoo.

### 4.4 Financial Correctness Beats Feature Count

A smaller feature set with correct invoicing, auditability, and recovery is more valuable than broad but fragile functionality.

### 4.5 Portal Actions Need Product Policy

Pause, resume, cancel, renew, and change-plan actions should be controlled by plan settings and access rules. The portal should not bypass business policy.

### 4.6 Reports Need Stable Definitions

MRR, ARR, churn, NRR, GRR, expansion, contraction, trial conversion, ARPU, LTV, retention, and recovery should be defined once and reused across reports.

### 4.7 Continuous Demo, Test, And Documentation Updates

Every phase must leave the suite easier to validate than before. A feature is not complete until demo data proves it, automated tests protect it, and documentation explains how to use and verify it.

Each phase should update three artifacts:

- **Demo data:** realistic records that show the new behavior in the backend, portal, and reports where applicable.
- **Automated tests:** focused coverage for successful paths, failure paths, access rules, and upgrade safety.
- **Documentation:** operator-facing steps, developer notes, demo walkthrough, known limitations, and exact validation commands.

This rule prevents the module from becoming a collection of hidden features that only work in manually-created records.

---

## 5. Phased Development Roadmap

The phases are ordered from easiest/lowest risk to more complex/enterprise-heavy. Each phase should end with module upgrades, demo-data updates, tests, and a short demo script.

For every phase, update or create:

- `demo/` XML records or a documented demo setup command.
- A test file covering the new behavior.
- A docs page or roadmap section explaining setup, usage, and validation.
- A short manual demo checklist for the Odoo backend and portal when relevant.

### Phase 0 - Stabilize Baseline And Documentation

**Objective:** Make the current suite easy to install, test, and reason about before adding more behavior.

**Why now:** The codebase already has several modules and partial features. Enterprise work needs a reliable baseline.

**Build items:**

- Add a docs index linking PRD, flow, roadmap, install guide, test guide, and demo guide.
- Update README known limitations to match current reality.
- Add a module matrix: installed modules, dependencies, menus, crons, models, tests.
- Add a standard upgrade command and test command for each addon.
- Add a demo user/portal setup guide.
- Add "definition of done" for every future phase.
- Create a demo-data inventory showing which records belong to each phase.
- Create a validation checklist template to reuse after every phase.

**Acceptance gates:**

- Fresh demo install works with all five current modules.
- Upgrade works for all five current modules.
- Existing tests pass.
- User can follow docs to open backend, reports, plans, subscriptions, dunning policies, and portal.

**Suggested tests/checks:**

- `python -m compileall versions\19.0\custom_addons`
- Odoo install with demo data.
- Odoo module upgrade for all suite addons.
- Existing test suite run.

**Demo data updates:**

- Confirm demo plans, products, customers, and subscriptions cover active, trial, paused, cancelled, and past-due scenarios.
- Add or document a portal customer that can be used for portal testing.
- Add a demo checklist that maps each menu/report/portal page to the demo records.

**Documentation updates:**

- Add docs index.
- Add install and upgrade commands.
- Add test commands.
- Add demo walkthrough.
- Add known limitations and phase status table.

---

### Phase 1 - Billing Reliability And Idempotency

**Objective:** Make recurring invoice generation safe under retries, crashes, overlapping crons, and operational errors.

**Why this is the next real enterprise phase:** Billing correctness is the foundation. Duplicate invoices, silent failures, or skipped renewals will damage trust faster than missing analytics.

**Current state:**

- `_cron_generate_subscription_invoices()` searches active subscriptions with `next_invoice_date <= today`.
- It uses batch size and savepoints.
- `_generate_subscription_invoice()` creates invoice(s), sets `subscription_id`, updates last/next invoice dates, and logs an event.

**Current Phase 1 status:**

- Done: `subscription.billing.run`.
- Done: `subscription.billing.attempt`.
- Done: unique billing-period idempotency key.
- Done: cron attempts marked success, failed, or skipped.
- Done: Billing Runs, Billing Attempts, and subscription smart button.
- Done: explicit lock or "in progress" marker on subscription records.
- Done: retry classification.
- Done: manager-facing Failed Billing queue and manual retry action.
- Done: automated retry scheduler for retryable billing attempts.
- Done: activity creation when retries are exhausted.
- Done: settings UI for retry policy tuning.
- Done: richer logs and reporting for repeated failures.
- Done: Manager Operations queue combining pending customer requests and failed billing recovery items.
- Done: Operations Dashboard with manager KPI counts and filtered drilldowns.

**Build items:**

1. Add `subscription.billing.run` - done
   - Fields: name, run_date, company_id, state, started_at, finished_at, subscription_count, success_count, failed_count, skipped_count, total_amount, log.

2. Add `subscription.billing.attempt` - done
   - Fields: run_id, subscription_id, period_start, period_end, invoice_id, state, error_message, attempt_no, idempotency_key, company_id, currency_id, amount.
   - Add SQL unique constraint on the idempotency key.

3. Add billing-period computation - done
   - Use `last_invoice_date` and `next_invoice_date` explicitly.
   - Preserve subscription period metadata on invoice.

4. Harden cron processing - done
   - Process in batches.
   - Create attempt before invoice creation.
   - Mark success/failure/skipped.
   - Use savepoints.
   - Avoid duplicate attempts.
   - Add subscription processing locks.
   - Classify failures as configuration, invoice validation, system, or unknown.
   - Add automated retry scheduling.
   - Add activities when retries are exhausted.

5. Add operational views - done
   - Billing Runs menu.
   - Billing Attempts menu.
   - Failed Billing menu.
   - Repeated Failures menu.
   - Manager Operations queue for pending requests and failed billing recovery.
   - Operations Dashboard with open, pending, critical, oldest pending, request-type, and failed-billing KPIs.
   - Smart button on subscription.
   - Filters for failed, retryable, retry exhausted, recovery required, repeated failures, success, skipped.
   - Filters for plan changes, lifecycle requests, cancellations, billing recovery, and critical operations.

6. Add indexes
   - `sale_order(is_subscription, subscription_state, next_invoice_date, company_id)`.
   - Attempt fields used by cron/reporting.

**Demo data updates:**

- Add subscriptions with due invoice dates, future invoice dates, and already-billed periods.
- Add one subscription designed to fail invoice generation in tests, not in normal demo install.
- Add demo billing runs and attempts only if they are safe to load without creating accounting inconsistencies; otherwise provide a demo script to generate them.

**Documentation updates:**

- Document the billing run lifecycle.
- Document billing attempt states and retry rules.
- Add an operator guide for reviewing failed billing attempts.
- Add a validation command for double-running the billing cron without duplicate invoices.
- Document retry policy settings under Subscriptions -> Configuration -> Settings.

**Acceptance gates:**

- Running the invoice cron twice for the same period does not create duplicate invoices.
- If invoice generation fails for one subscription, the run continues for the others.
- Failed attempts are visible and retryable.
- Invoice period start/end is always set.
- Managers can see failed billing attempts from the UI.
- Managers can see pending plan-change, lifecycle, cancellation, and billing recovery work in one operations queue.
- Managers can start from an operations dashboard and drill into each actionable category.

**Tests:**

- Idempotent cron double-run.
- One failing subscription does not block the batch.
- Attempt state transitions.
- Unique idempotency constraint.
- Multi-company filtering.
- Invoice period metadata.

**Continuous validation:**

- Demo database shows billing runs, successful attempts, skipped attempts, and failed attempts.
- Tests prove duplicate prevention before portal self-service work begins.

---

### Phase 2 - Lifecycle Parity With Odoo Enterprise UX

**Objective:** Match the core Odoo subscription workflows before inventing new ones.

**Benchmark:** Odoo has renewal quotations, upsell quotations, close reasons, portal closing, sales history, automatic payments, and reporting flows.

**Build items:**

1. Renewal workflow
   - Add `action_renew_subscription` - done.
   - Create linked renewal quotation - done.
   - Add generic subscription quote relationship fields - done.
   - Add sales history smart button - done.
   - Preserve start date, next invoice date, recurring plan, and chatter trail - done.

2. Upsell workflow
   - Add `action_upsell_subscription` - done.
   - Create linked upsell quotation - done.
   - Add recurring products to existing subscription after confirmation - done.
   - Apply prorated price for remaining period - draft adjustment invoice/credit-note generation done.
   - Log MRR expansion movement - done.

3. Structured plan change workflow
   - Strengthen current plan-change wizard.
   - Support immediate vs next-period effective date - done for immediate proration and scheduled renewal-boundary changes.
   - Support upgrade/downgrade path policy - done for configured plan paths.
   - Support approval gates for restricted plan changes - done with auditable plan change request records.
   - Support cancellation-policy constraints and minimum commitments - minimum commitment done for cancellation and downgrade.

4. Pause/resume correctness
   - Complete paused-period billing-date adjustment - done.
   - Respect max pause days - done.
   - Log pause duration and resulting next invoice date change - done.

5. Cancellation policy
   - Immediate cancellation - done.
   - End-of-current-period cancellation - done.
   - Optional admin approval for restricted plans.
   - Cancellation reason and feedback capture - done.
   - Optional churn-prevention offer placeholder.

**Demo data updates:**

- Add subscriptions ready for renewal, upsell, downgrade, pause/resume, and scheduled cancellation.
- Add demo renewal and upsell quotations linked to subscriptions - done.
- Add cancellation reasons that cover price, missing feature, competitor, non-payment, and end of project.
- Add approval-gated plan change records for pending, rejected, and cancelled requests - done.
- Add a scheduled next-period plan change subscription using the Enterprise Monthly demo plan - done.

**Documentation updates:**

- Add sales workflow guide for renewal and upsell quotations.
- Add support guide for pause/resume and cancellation policy handling.
- Add demo script showing plan change, renewal, upsell, pause/resume, and end-of-period cancellation.

**Acceptance gates:**

- Sales team can renew and upsell subscriptions using Odoo-style quotations - initial foundation done.
- Sales history clearly shows related orders and statuses - initial foundation done.
- Plan changes cannot violate plan-defined upgrade/downgrade rules.
- Cancellation and downgrade cannot violate minimum commitment periods.
- Next-period plan changes apply before the renewal invoice and do not create proration documents.
- Restricted plan changes create approval requests and only apply after manager approval.
- Pause/resume does not corrupt next invoice date.
- Cancellations respect plan policy.

**Tests:**

- Renewal quotation creation and confirmation.
- Upsell quotation proration.
- Immediate vs next-period plan change.
- Pause/resume billing date adjustment.
- End-of-period cancellation.
- Minimum commitment restriction.

**Continuous validation:**

- Demo data makes every lifecycle state reachable without custom shell commands.
- Demo data includes Enterprise Monthly, a pending scheduled plan change, and pending/rejected/cancelled plan change approval requests.
- Tests verify every allowed and blocked transition.

---

### Phase 3 - Portal Self-Service

**Objective:** Turn the portal from read-only visibility into controlled customer self-service.

**Current state:**

- Portal home count.
- Subscription list.
- Subscription detail.
- Recurring items.
- Invoice history.
- Scheduled plan change visibility on list and detail pages.
- Plan change request status visibility on detail pages.
- Customer-initiated next-period plan change requests for configured upgrade/downgrade paths.
- Pause/resume lifecycle request status visibility on detail pages.
- Customer-initiated pause/resume requests with backend manager approval.
- Scheduled cancellation and cancellation request status visibility on detail pages.
- Customer-initiated cancellation requests with reason capture and backend manager approval.

**Build items:**

1. Read-only subscription workspace - initial baseline done
   - Show current plan, billing period, MRR, recurring amount, next invoice, auto-pay, and payment method status.
   - Show scheduled plan changes before renewal.
   - Show plan change approval requests with status.
   - Show invoice history through Odoo portal invoice links.

2. Portal actions
   - Request cancellation - done as approval-gated cancellation requests.
   - Request pause - done as approval-gated lifecycle requests.
   - Request resume - done as approval-gated lifecycle requests.
   - Request plan change - done for next-period approval requests.
   - Download invoices through Odoo portal URLs.
   - Update payment method or route to payment-token setup - native Odoo validation route done.
   - Payment recovery banner for open subscription invoices - initial version done.
   - Retry saved payment method for open subscription invoices - initial guarded route done.

3. Action safety
   - CSRF validation.
   - Access-token support where appropriate.
   - Confirmation pages.
   - Plan-policy checks.
   - Chatter and subscription log entries for all customer actions.

4. Retention flow
   - Cancellation reason selection.
   - Optional feedback.
   - Offer pause instead of cancel.
   - Offer downgrade instead of cancel.
   - Optionally support configured retention offers later.

5. Portal UX
   - Status-aware action buttons.
   - Clear billing timeline.
   - Payment failure callout.
   - Next action banner for past-due subscriptions.

**Demo data updates:**

- Add portal users for active, past-due, paused, cancelled, and trial subscriptions.
- Add invoices with paid, open, partial, and in-payment states where feasible.
- Add portal-visible subscriptions with and without saved payment methods.
- Add cancellation request demo records - done with `demo_cancellation_request_pending`.
- Add lifecycle request demo records - done with `demo_lifecycle_request_resume_pending`.

**Documentation updates:**

- Add portal user testing guide.
- Add portal access/security guide.
- Add customer self-service workflow screenshots or checklist.
- Add troubleshooting notes for login, access tokens, and record visibility.

**Acceptance gates:**

- Portal users can only act on their own subscriptions.
- Portal users can see scheduled plan changes and plan change request status for their own subscriptions.
- Portal users can request allowed next-period plan changes without directly changing the subscription.
- Portal users can request pause/resume without directly changing lifecycle state.
- Portal users can request cancellation without directly cancelling the subscription.
- Managers can process plan-change, lifecycle, and cancellation requests from list/form/activity views.
- Request records create manager review activities and close those activities when approved, rejected, or cancelled.
- Subscription records expose request history through stat buttons so managers can audit customer-requested changes from the subscription itself.
- Portal action permissions match plan policy.
- Every action logs who did what and when.
- Portal cancellation cannot bypass configured close reasons.
- Past-due customers can see recovery instructions.
- Customers can open the unpaid subscription invoice from the portal subscription page.
- Customers can retry a saved payment method when the subscription already has a payment token.
- Customers can assign an existing saved payment method to a subscription.
- Customers can add a payment method through Odoo's native validation flow and return to the subscription.

**Tests:**

- `HttpCase` portal access tests.
- Portal user cannot access another customer's subscription.
- CSRF-protected POST actions.
- Cancel/pause/resume/change-plan permission cases.
- Portal invoice visibility.

**Continuous validation:**

- Portal `HttpCase` tests must exist before new portal actions are considered complete.
- Manual portal demo must verify list, detail, invoice history, and each allowed action.

---

### Phase 4 - Payment Recovery And Dunning Operations

**Objective:** Make failed payment recovery measurable, automated, and operationally visible.

**Current state:**

- `_auto_collect_payment()` creates a `payment.transaction`.
- Dunning starts on failed payment.
- Dunning policies and policy lines exist.
- Dunning cron sends email templates and can pause/cancel.

**Build items:**

1. Add `subscription.payment.attempt` - initial version done.
   - Links subscription, invoice, token, provider, transaction, state, failure message, attempt date, and provider outcome.
   - Portal and cron saved-token retries create audit rows.
   - Failed payment attempts feed the manager operations queue.

2. Add `subscription.dunning.attempt`
   - Links policy, step, subscription, invoice, email, action taken, recovery result.

3. Improve retry strategy
   - Configurable retry schedule.
   - Retry count.
   - Manual retry action.
   - Optional backup payment method field.

4. Customer recovery flow
   - Portal banner for failed payment - initial open-invoice recovery banner done.
   - Update payment method action - initial portal selector and native validation flow done.
   - Retry payment action - initial saved-token retry route done.
   - Dunning emails link to portal recovery page.

5. Recovery analytics
   - Open amount at risk.
   - Recovered amount.
   - Recovery rate by policy.
   - Average days to recover.
   - Failed recovery final actions.
   - Payment-attempt list/search views for provider and state analysis - initial version done.

**Demo data updates:**

- Add past-due subscriptions at different dunning stages.
- Add demo dunning policies with friendly reminder, stronger reminder, final notice, and final action.
- Add payment attempt and dunning attempt demo scenarios where safe; otherwise add a repeatable demo script to generate them.

**Documentation updates:**

- Add dunning setup guide.
- Add failed-payment recovery guide for support and finance users.
- Add policy tuning guide explaining grace periods, retry intervals, and final actions.
- Add validation steps for failed payment, recovery, and final action.

**Acceptance gates:**

- Each payment attempt is traceable.
- Each dunning action is traceable.
- Recovery can be measured by policy and period.
- A past-due subscription can recover to active automatically after successful payment.
- Final action is executed once and only once.

**Tests:**

- Failed transaction creates payment attempt and starts dunning.
- Dunning steps create attempt records.
- Successful retry resolves dunning.
- Final action idempotency.
- Recovery report numbers.

**Continuous validation:**

- Demo database must show at least one recoverable past-due subscription and one final-action path.
- Tests must prove successful payment returns a subscription to active exactly once.

---

### Phase 5 - Pricing Models, Seats, Add-ons, And Usage

**Objective:** Support the monetization patterns expected by SaaS and enterprise subscription businesses.

**Build items:**

1. Pricing model expansion
   - Flat recurring.
   - Per-seat recurring.
   - Tiered pricing.
   - Volume pricing.
   - Add-ons.
   - One-time setup and onboarding fees.

2. Seat management
   - Seat quantity on subscription line.
   - Portal-visible seat count.
   - Optional seat sync hooks for external applications.
   - Seat increase/decrease proration.

3. Usage-based billing
   - Add `subscription.usage.meter`.
   - Add `subscription.usage.event`.
   - Add `subscription.usage.summary`.
   - Generate invoice lines from usage summaries.
   - Support included usage and overage rates.

4. Discounts and coupons
   - Time-limited discounts.
   - Coupon application history.
   - Discount expiration handling.

**Demo data updates:**

- Add flat, seat-based, add-on, tiered, volume, and usage-based demo plans.
- Add demo usage events and summaries for overage billing.
- Add subscriptions with expiring discounts and coupons.

**Documentation updates:**

- Add pricing model guide.
- Add usage-meter setup guide.
- Add seat management workflow.
- Add examples showing invoice output for each pricing model.

**Acceptance gates:**

- The module can bill flat, seat-based, add-on, and usage overage subscriptions.
- Usage invoice lines are reproducible from usage events/summaries.
- Seat changes can be prorated.
- Discount expiration does not require manual invoice edits.

**Tests:**

- Seat increase/decrease.
- Tiered and volume calculations.
- Usage event aggregation.
- Overage invoice generation.
- Coupon expiry.
- Mixed flat plus usage subscription.

**Continuous validation:**

- Demo invoices must clearly show flat charges, seat charges, add-ons, usage overages, and discounts.
- Tests must reconcile usage events to invoice lines.

---

### Phase 6 - Analytics, Forecasting, And Executive Dashboard

**Objective:** Move from basic reporting to business-grade subscription intelligence.

**Current state:**

- SQL report includes MRR, ARR, active/churned/trial/past-due counts and MRR.
- MRR movement model exists for new, expansion, contraction, churn.

**Build items:**

1. Metric definitions
   - MRR.
   - ARR.
   - New MRR.
   - Expansion MRR.
   - Contraction MRR.
   - Churned MRR.
   - Net New MRR.
   - NRR.
   - GRR.
   - Customer churn.
   - Revenue churn.
   - Trial conversion.
   - ARPU.
   - LTV.

2. Snapshot models
   - `subscription.mrr.snapshot`.
   - Daily/monthly snapshots by company/currency/plan.
   - Normalized company-currency values.

3. Dashboards
   - Backend dashboard action.
   - KPI cards.
   - MRR waterfall.
   - Retention cohort.
   - Churn reasons.
   - Top plans.
   - At-risk subscriptions.
   - Failed-payment recovery.

4. Forecasting
   - Upcoming renewals.
   - Forecasted MRR.
   - Expected churn based on scheduled cancellations.
   - Upcoming invoices.

**Demo data updates:**

- Add historical MRR movement records across multiple months.
- Add subscriptions in multiple cohorts, plans, countries, salespeople, and states.
- Add churn reasons and scheduled cancellations to make retention and forecast reports meaningful.

**Documentation updates:**

- Add metric-definition guide.
- Add dashboard user guide.
- Add report validation guide that explains how to manually reconcile key metrics.
- Add performance test instructions for large datasets.

**Acceptance gates:**

- KPI definitions are documented and match SQL outputs.
- Dashboard loads in under 3 seconds with 10K subscriptions.
- MRR movement totals reconcile to snapshot deltas.
- Filters by company, plan, salesperson, country, and period work.

**Tests:**

- SQL report correctness.
- Snapshot generation.
- NRR/GRR formula tests.
- Cohort retention tests.
- Performance smoke test with generated records.

**Continuous validation:**

- Demo reports must show non-empty MRR waterfall, churn, trial conversion, retention, and forecast views.
- Tests must compare dashboard/report numbers against known demo fixtures.

---

### Phase 7 - Accounting And Revenue Recognition

**Objective:** Add finance-grade deferred revenue and recognition workflows.

**Build items:**

1. Deferred revenue configuration
   - Deferred revenue account.
   - Revenue account.
   - Recognition journal.
   - Recognition method.
   - Company-level defaults.

2. Deferred revenue schedule
   - `subscription.deferred.revenue`.
   - `subscription.deferred.revenue.line`.
   - Link schedule to subscription and invoice.
   - Service period from invoice/subscription period.

3. Recognition methods
   - Straight-line daily.
   - Equal monthly.
   - Manual.

4. Recognition posting
   - Preview wizard.
   - Monthly cron.
   - Journal entry links.
   - Reversal/cancellation handling.
   - Credit note handling.

5. Finance reports
   - Deferred revenue balance.
   - Recognized revenue by period.
   - Unrecognized revenue by customer/plan.
   - Reconciliation between invoices, schedules, and journal entries.

**Demo data updates:**

- Add annual prepaid subscription invoices suitable for deferred revenue schedules.
- Add monthly and annual recognition examples.
- Add cancellation/credit-note examples that adjust deferred revenue.

**Documentation updates:**

- Add finance setup guide for deferred revenue accounts, revenue accounts, and recognition journal.
- Add revenue recognition workflow guide.
- Add reconciliation guide linking invoices, schedules, journal entries, and reports.
- Add accounting caveats and known limitations.

**Acceptance gates:**

- Annual prepaid invoice creates a 12-month recognition schedule.
- Monthly recognition entries post correctly.
- Total recognized plus remaining deferred equals invoice amount.
- Credit note/cancellation adjusts schedules correctly.
- Finance user can reconcile reports to accounting moves.

**Tests:**

- Schedule creation.
- Straight-line daily calculation.
- Monthly equal calculation.
- Posting journal entries.
- Cancellation and credit note.
- Multi-company and multi-currency.

**Continuous validation:**

- Demo data must reconcile invoice amount, recognized revenue, and remaining deferred revenue.
- Tests must verify journal entry lines and schedule totals.

---

### Phase 8 - Enterprise Security, Scale, And Release Packaging

**Objective:** Make the suite deployable for serious customers.

**Build items:**

1. Security hardening
   - Full record-rule audit.
   - Portal route audit.
   - Multi-company tests.
   - Manager/user/portal permission matrix.
   - Read/write/delete access review for every model.

2. Performance
   - Indexes for cron and reports.
   - Batch size configuration.
   - Large demo data generator.
   - 10K subscription cron benchmark.
   - Query review on SQL reports.

3. Observability
   - Billing run logs.
   - Failed cron activities.
   - Admin dashboard for operational errors.
   - Optional digest email for failed billing/dunning.

4. Data operations
   - Import templates.
   - Migration scripts.
   - Backfill MRR movement from existing subscriptions.
   - Backfill billing attempts from existing invoices where possible.

5. Packaging
   - User guide.
   - Admin guide.
   - Finance guide.
   - Portal guide.
   - Test guide.
   - Release checklist.
   - Changelog.
   - Odoo Apps description assets.

**Demo data updates:**

- Consolidate all phase demo records into a coherent demo story.
- Add optional large demo-data generator for scale testing.
- Ensure demo data covers trial, active, paused, past due, cancelled, renewed, upsold, recovered, usage-billed, and revenue-recognized subscriptions.

**Documentation updates:**

- Finalize user, admin, finance, portal, developer, and testing guides.
- Add release checklist.
- Add migration notes.
- Add troubleshooting guide.
- Add Odoo Apps listing content and screenshots checklist.

**Acceptance gates:**

- A fresh production-style database can install and configure the suite using docs.
- All access rules are tested.
- 10K subscription benchmark is recorded.
- Release notes list known limitations honestly.
- Demo data tells a complete story: trial, active, paused, past due, cancelled, renewed, upsold, recovered, churned.

**Continuous validation:**

- Release candidate must pass fresh install, module upgrade, full tests, portal smoke test, and demo walkthrough.
- Large demo database must prove cron and report performance targets.

---

## 6. Recommended Immediate Build Order

The next concrete implementation sequence should be:

1. Create Phase 0 documentation and baseline validation commands.
2. Update demo data inventory and create the first phase validation checklist.
3. Add billing run and billing attempt models.
4. Make recurring invoice generation idempotent.
5. Add billing run/attempt menus and smart buttons.
6. Add tests for duplicate prevention and failure isolation.
7. Update demo data and docs for billing attempts before moving to the next phase.
8. Add portal HTTP tests before adding portal self-service actions.
9. Add end-of-period cancellation and pause/resume date correctness.
10. Add payment attempt and dunning attempt ledgers.
11. Add customer portal recovery/update-payment flow.
12. Add renewal and upsell quotation workflows.

This sequence intentionally puts reliability before large UX expansion.

---

## 7. Definition Of Done For Enterprise Phases

Each phase is done only when all of the following are true:

- Code is implemented in the right addon boundary.
- Menus/actions/views are available to the correct users.
- Access rights and record rules are updated.
- Tests cover success, failure, and permission cases.
- Module upgrade succeeds on the demo database.
- Demo data or a repeatable demo script shows the feature.
- Demo data is updated before the phase is considered complete.
- Documentation is updated.
- Documentation includes setup, usage, validation, and known limitations.
- A manual demo checklist exists for the phase.
- Known limitations are stated plainly.

---

## 8. Source Benchmark Links

Primary sources used for the competitor and Odoo benchmark:

- Odoo Subscriptions app page: https://www.odoo.com/en_US/app/subscriptions
- Odoo 19 Subscriptions documentation: https://www.odoo.com/documentation/19.0/applications/sales/subscriptions.html
- Odoo 19 Upsell subscriptions: https://www.odoo.com/documentation/19.0/applications/sales/subscriptions/upselling.html
- Odoo 19 Renew subscriptions: https://www.odoo.com/documentation/19.0/applications/sales/subscriptions/renewals.html
- Odoo 19 Close subscriptions: https://www.odoo.com/documentation/19.0/applications/sales/subscriptions/closing.html
- Odoo 19 Automatic payments: https://www.odoo.com/documentation/19.0/applications/sales/subscriptions/automatic_payments.html
- Odoo 19 Subscription reports: https://www.odoo.com/documentation/19.0/applications/sales/subscriptions/reports.html
- Stripe Billing: https://stripe.com/billing
- Chargebee features: https://www.chargebee.com/features/
- Recurly: https://recurly.com/
- Paddle customer portal: https://developer.paddle.com/concepts/sell/customer-portal/
- Zuora products: https://www.zuora.com/products/

---

## 9. Strategic Product Bet

The module should not try to be a generic external billing platform inside Odoo. That would create a large, fragile product.

The stronger product bet is:

> Be the best Odoo-native subscription operations suite for Community Edition, with finance-safe billing, clear dunning, useful portal self-service, and analytics that subscription managers can trust.

This keeps the module focused and makes every phase valuable even before the entire PRD is complete.
