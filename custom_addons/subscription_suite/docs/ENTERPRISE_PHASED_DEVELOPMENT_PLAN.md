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

### Engineering Standard

- Quantity decisions must use Odoo float precision helpers with the relevant UoM rounding.
- Monetary decisions must use `currency_id.compare_amounts()` or `currency_id.is_zero()`.
- Future pricing, seats, usage, proration, discounts, payment recovery, and analytics slices should include near-equal precision tests instead of relying on raw float equality.

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
| Payment recovery ledger | Portal retries now record pending, success, and failed attempt outcomes with clearer recovery notes, subscription logs, manager recovery visibility, and repeatable demo recovery scenarios | Customer recovery is more auditable; provider-specific mapping remains deferred |
| Payment collection | Basic token transaction creation exists, but no retry campaign, provider-specific result handling, attempt ledger, or backup payment method | Payment failures become opaque |
| Dunning | Policy cron exists, but no attempt model, no recovery metrics, limited customer recovery workflow | Hard to operate at scale |
| Portal | Subscription, invoice, pending plan change, lifecycle, cancellation, and approval visibility exists; customers can request next-period plan changes, pause/resume, and cancellations through approval-gated requests | Update-payment still requires support |
| Pause/resume | Pause/resume now adjusts the next invoice date by paused duration and respects max pause days | Remaining work is mostly portal self-service and support workflow polish |
| Cancellation | Immediate and end-of-period cancellation now exist, including scheduled cancellation reversal and cron finalization | Remaining work is mostly renewal/upsell lifecycle parity and optional approvals |
| Renewals/upsells | Linked renewal and upsell quotations, sales history, upsell effective date, proration ledger, draft adjustment invoices/credit notes, immediate and scheduled next-period plan changes, approval-gated plan change requests, upgrade/downgrade path checks, minimum commitment enforcement, and plan-level renewal/upsell quote guards now exist | Sales workflow parity is improving; remaining work is optional approval routing and deeper quote lifecycle automation |
| Usage/seats | Seat-line classification, read-only seat totals, tiered/volume pricing, and a backend usage-metering foundation now exist; no customer seat self-service, external usage API, or entitlement sync yet | Core Phase 5 monetization mechanics are in place; customer-facing and integration-heavy workflows remain later work |
| Analytics | Generated MRR snapshots, reconciliation, anomalies, KPI summaries, dashboards, waterfalls, retention cohorts, forecasts, ARPU, LTV, churn reasons, top plans, at-risk rows, payment recovery, and trial conversion now exist with source drilldowns and scoped reruns | Management reporting is broad and operationally useful; remaining gaps are executive packaging, normalized multi-currency reporting, and finance-grade revenue recognition |
| Revenue recognition | Deferred schedules, preview, manual posting, credit-note adjustments, reconciliation, posting hardening, and scheduled posting cron foundation now exist | Remaining gaps are cron operational hardening, setup validation, finance reports, and advanced refund/allocation handling |
| Multi-currency | Amounts remain in order currency; no normalized company-currency MRR ledger | Cross-currency analytics can mislead |
| Security | Groups and multi-company rules exist; deterministic portal helper tests cover ownership-sensitive flows, but live portal route tests still need a stable local harness | Route-level access regressions may go unnoticed |
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
   - Add plan-level renewal quote and past-due renewal quote policy guards - current slice.

2. Upsell workflow
   - Add `action_upsell_subscription` - done.
   - Create linked upsell quotation - done.
   - Add recurring products to existing subscription after confirmation - done.
   - Apply prorated price for remaining period - draft adjustment invoice/credit-note generation done.
   - Log MRR expansion movement - done.
   - Add plan-level upsell quote and past-due upsell quote policy guards - current slice.

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
- Sales managers can disable renewal, upsell, and past-due quote creation per plan - current slice.
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
- Payment recovery banner clarity for invoice status, due date, residual amount, saved-method availability, and next action - initial version done.
- Portal retry feedback loop for pending, success, failed, and manager-visible recovery attempts - initial version done.
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

- Deterministic portal helper tests for portal user filtering and another-customer rejection.
- Deterministic portal helper tests for CSRF-protected POST action handlers.
- Cancel/pause/resume/change-plan permission cases.
- Portal invoice visibility.
- Payment recovery security tests for retry, saved-token selection, and validation-return ownership - initial coverage done.
- Live `HttpCase` route coverage remains a Phase 8 hardening item until the local route-test harness is stable.

**Continuous validation:**

- Portal helper tests must cover ownership, policy, and blocked-state behavior before new portal actions are considered complete.
- Stable live portal route tests should be introduced before broadening portal self-service beyond the current approval-gated actions.
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

2. Add `subscription.dunning.attempt` - initial version done.
   - Links policy, step, subscription, invoice, email, action taken, recovery result.

3. Improve retry strategy
   - Configurable retry schedule - initial policy-line delay and max retry fields done.
   - Retry count - auto/manual retry counts done on dunning attempts.
   - Manual retry action from dunning attempts - initial version done.
   - Optional backup payment method field - manager-configured next-retry fallback done.

4. Customer recovery flow
   - Portal banner for failed payment - initial open-invoice recovery banner done.
   - Update payment method action - initial portal selector and native validation flow done.
   - Retry payment action - initial saved-token retry route done.
   - Dunning emails link to portal recovery page - initial version done.

5. Recovery analytics - initial dashboard version done.
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
- Portal recovery demo saved-method scenario includes a manager-configured backup payment method.

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
- Backup payment method is used on the next retry after a primary-method failure.
- Final action idempotency - initial version done.
- Recovery report numbers.

**Continuous validation:**

- Demo database must show at least one recoverable past-due subscription and one final-action path.
- Portal demo data must include saved-method recovery, no-method blocked recovery, clear paid/active state, and another portal customer for isolation checks.
- Saved-method recovery demo must include a backup payment method for fallback validation.
- Recovery dashboard must separate portal-originated attempts into pending, failed, recovered, and manual-action drilldowns.
- Tests must prove successful payment returns a subscription to active exactly once.

---

### Phase 5 - Pricing Models, Seats, Add-ons, And Usage

**Objective:** Support the monetization patterns expected by SaaS and enterprise subscription businesses.

**Current slice status:** Phase 5 backend discount operations are complete. Coupon codes, portal promo entry, discount proration credits, discount analytics, accounting deferrals, invoice line-per-tier breakdowns, public usage ingestion, customer self-service, and external entitlement sync remain deferred.

**Build items:**

1. Pricing model expansion
   - Flat recurring - done.
   - Per-seat recurring - foundation done.
   - Tiered pricing - foundation done with graduated tier totals converted to effective unit price.
   - Volume pricing - foundation done with matched tier price applied to all units.
   - Add-ons - backend manager operations done for flat add-ons.
   - One-time setup and onboarding fees.

2. Seat management
   - Seat quantity on subscription line - foundation done through recurring sale order lines marked as `seat`.
   - Portal-visible seat count - read-only summary done.
   - Immediate backend seat increase/decrease with proration - done.
   - Scheduled backend seat increase/decrease at the next billing period - done.
   - Backend add-on add/remove with immediate proration and next-period scheduling - done.
   - Optional seat sync hooks for external applications.

3. Usage-based billing
   - Add `subscription.usage.meter` - foundation done.
   - Add `subscription.usage.event` - foundation done for backend-entered/imported events.
   - Add `subscription.usage.summary` - foundation done with one summary per subscription, meter, and billing period.
   - Generate invoice lines from usage summaries - foundation done with one overage line per billable meter.
   - Support included usage and overage rates - foundation done for summed usage.
   - Usage event audit hardening - done for cancelling ready events, recomputing draft summaries, and locking invoiced events.

4. Discounts and coupons
   - Time-limited recurring discounts - foundation done using plan-line and sale-line metadata plus Odoo sale line `discount`.
   - Backend discount operations - hardening done for manager updates, promotion clearing, manual refresh, and audit logs.
   - Coupon application history.
   - Discount expiration handling - foundation done before recurring billing with subscription logs and MRR recalculation.

**Demo data updates:**

- Add flat, seat-based, add-on, tiered, volume, and usage-based demo plans.
- Seat-based demo plan and subscription exist for validating base plus seat recurring lines.
- Volume and graduated seat-pricing demo plans exist for validating tier setup and effective unit prices.
- API-call usage meter, overage product, usage rule, and demo events exist for overage billing walkthroughs.
- Promotional monthly plan and subscriptions exist for active and expired promotional discount walkthroughs.
- Future-dated promotional subscription exists for backend refresh and search-filter walkthroughs.
- Add coupon examples later when coupon-code support exists.

**Documentation updates:**

- Add pricing model guide.
- Add usage-meter setup guide.
- Add seat management workflow.
- Add examples showing invoice output for each pricing model.
- Keep future recurring-discount features Odoo-native by using sale order line `discount` as the invoice-facing effective value and metadata fields only for lifecycle/audit decisions.

**Acceptance gates:**

- The module can bill flat, seat-based, add-on, and usage overage subscriptions.
- Subscription plan lines support flat, volume, and graduated pricing models with validated contiguous tiers.
- Subscription order lines preserve copied tier metadata and invoice as one recurring line with the effective unit price.
- Seat subscription invoices use Odoo's existing quantity times unit-price mechanics.
- Renewal and upsell quotes preserve subscription component type on copied recurring lines.
- Renewal quotes preserve subscription pricing model and copied tier rows.
- Backend and portal summaries show read-only seat totals when recurring seat lines exist.
- Immediate backend seat changes create proration, subscription logs, and MRR movement.
- Scheduled backend seat changes apply before recurring billing without a proration document, can be cancelled before application, and record subscription logs and MRR movement.
- Backend add-on operations can add/remove recurring add-on lines immediately or at the next billing period with audit, proration, invoice, log, and MRR movement coverage.
- Backend seat changes recompute tier-effective unit prices before MRR and proration calculations.
- Usage invoice lines are reproducible from usage events/summaries.
- Usage event aggregation is idempotent per subscription, meter, and billing period.
- Configured usage rules with no events do not create empty summaries.
- Included usage creates an audit summary without adding an invoice line.
- Cancelled usage events are excluded from billing and draft summary recomputation.
- Invoiced usage events and summaries are immutable from manager correction actions.
- Discount expiration does not require manual invoice edits.
- Active promotional discounts update recurring total, MRR, and invoice line discount before billing.
- Expired promotional discounts revert the invoice-facing discount to the copied base discount without deleting promotion metadata or duplicating logs.
- Managers can update recurring-line discount metadata, clear promotions, and manually refresh discount status without generating proration documents.

**Tests:**

- Immediate backend seat increase/decrease.
- Scheduled backend seat increase/decrease and cancellation.
- Backend add-on add/remove, scheduling, cancellation, and proration.
- Tiered and volume calculations, invalid tier validation, copied tier metadata, tiered invoices, and tier-aware seat changes.
- Usage event aggregation, no-event summary suppression, included-allowance summaries, overage invoice line generation, and no-duplicate billing reruns.
- Usage event cancellation, draft summary recomputation, locked invoiced usage records, and cancelled-event billing exclusion.
- Promotional discount metadata copying, validation, activation, expiry, invoice discount, MRR recalculation, renewal preservation, and idempotent expiry logging.
- Backend discount wizard guards, active/future/expired behavior, promotion clearing, manual refresh, search visibility, and audit logs.
- Coupon expiry.
- Mixed flat plus usage subscription.

**Continuous validation:**

- Demo invoices must clearly show flat charges, seat charges, add-ons, usage overages, and discounts.
- Tests must reconcile usage events to invoice lines.
- Discount changes must remain forward-looking until a later proration/credit slice explicitly adds mid-period discount adjustments.

---

### Phase 6 - Analytics, Forecasting, And Executive Dashboard

**Objective:** Move from basic reporting to business-grade subscription intelligence.

**Current state:**

- SQL report includes MRR, ARR, active/churned/trial/past-due counts and MRR.
- MRR movement model exists for new, expansion, contraction, churn.
- Daily MRR snapshots exist by company, currency, and plan, with manual generation and daily cron.

**Current slice:** Generated Analytics Sequence Hardening. ARPU summary, LTV summary, forecasting foundation, churn reason analytics, top plan analytics, at-risk analytics, payment recovery analytics, trial conversion analytics, analytics performance smoke coverage, and generated analytics lifecycle hardening are complete. This slice adds an Odoo-native analytics generation guide, clarifies prerequisites, and cleans up stale roadmap language before adding marketing attribution, nurture automation, predictive scoring, custom Owl widgets, executive board packs, or Phase 7 revenue recognition.

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
   - ARPU - foundation done as average revenue per subscription.
   - LTV - foundation done as ARPU divided by churn rate.
   - Churn reason summary - foundation done using existing cancellation reasons and feedback coverage.
   - Top plan performance summary - foundation done using existing generated plan-level analytics.
   - At-risk subscription summary - foundation done using explainable rules over subscription, payment recovery, dunning, renewal, and cancellation signals.
   - Failed-payment recovery summary - foundation done using payment attempts, open recovery invoices, dunning escalation, and at-risk rows.
   - Trial conversion summary - foundation done using existing trial dates and inferred conversion from `subscription_start_date`.
   - Analytics generation guide - current slice for manager/user sequence guidance and prerequisite wording.

2. Snapshot models
   - `subscription.mrr.snapshot` - foundation done with daily company/currency/plan buckets.
   - Daily snapshots by company/currency/plan - foundation done with idempotent manual generation and daily cron.
   - `subscription.mrr.reconciliation` - foundation done for comparing snapshot deltas to MRR movements.
   - `subscription.mrr.movement.anomaly` - foundation done for movement-only and missing-plan analytics audit buckets.
   - `subscription.mrr.kpi.summary` - foundation done for generated period-level MRR KPI metrics.
   - `subscription.mrr.kpi.dashboard` - foundation done for generated dashboard records from KPI summaries.
   - `subscription.mrr.waterfall` - foundation done for generated MRR waterfall buckets.
   - `subscription.retention.cohort` - foundation done for generated monthly retention cohorts.
   - `subscription.revenue.forecast` - foundation done for generated monthly operational revenue forecasts.
   - Analytics performance smoke test - foundation done for repeatable generated-report chain coverage.
   - Generated analytics lifecycle hardening - foundation done for access and scoped-regeneration coverage.
   - `subscription.arpu.summary` - foundation done for generated ARPU by company, currency, optional plan, and snapshot period.
    - `subscription.ltv.summary` - foundation done for generated LTV by company, currency, optional plan, ARPU period, and cohort range.
    - `subscription.churn.reason.summary` - foundation done for generated churn reason analytics by company, currency, optional plan, optional cancellation reason, MRR source quality, and feedback coverage quality.
    - `subscription.plan.performance.summary` - foundation done for generated top-plan performance rows by company, currency, and plan.
    - `subscription.at.risk.summary` - foundation done for generated at-risk subscription rows by company, currency, plan, and subscription.
    - `subscription.payment.recovery.summary` - foundation done for generated recovery rows by company, currency, optional plan, and recovery source.
    - `subscription.trial.conversion.summary` - foundation done for generated trial conversion rows by company, currency, and optional plan.
    - `subscription.analytics.sequence.guide` - current slice for Odoo-native generation-order guidance.
   - Monthly snapshots by company/currency/plan.
   - Normalized company-currency values.

3. Dashboards
   - Backend dashboard action - foundation done.
   - KPI cards - foundation done.
   - Source drilldowns to KPI summaries, snapshots, reconciliations, anomalies, and movements - foundation done.
   - MRR waterfall - foundation done.
   - Retention cohort - foundation done.
    - Churn reasons - foundation done.
   - Top plans - foundation done.
   - At-risk subscriptions - foundation done.
   - Failed-payment recovery - foundation done.
   - Trial conversion - foundation done.
   - Analytics generation guide - current slice.

4. Forecasting
   - Upcoming renewals - current slice.
   - Forecasted MRR - current slice.
   - Expected churn based on scheduled cancellations - current slice.
   - Upcoming invoices - current slice.

**Demo data updates:**

- Generate MRR snapshots from existing demo subscriptions after installing/upgrading the reports module; static snapshot demo XML is intentionally avoided so the records reflect the current demo subscription state.
- Generate MRR reconciliations from existing snapshots and MRR movements; static reconciliation demo XML is intentionally avoided so rows reflect the selected snapshot range.
- Generate MRR movement anomalies from existing movement records; static anomaly demo XML is intentionally avoided so rows reflect the selected audit range.
- Generate MRR KPI summaries from snapshots, reconciliation rows, and MRR movements; static KPI summary demo XML is intentionally avoided so rows reflect the selected period.
- Generate MRR KPI dashboards from KPI summaries; static dashboard demo XML is intentionally avoided so dashboard values reflect the selected period, company, currency, and optional plan.
- Generate MRR waterfalls from KPI summaries; static waterfall demo XML is intentionally avoided so rows reflect the selected period, company, currency, and optional plan.
- Generate retention cohorts from existing subscription start and cancellation dates; static cohort XML is intentionally avoided so rows reflect the selected cohort range.
- Generate revenue forecasts from existing subscription invoice, renewal, and scheduled cancellation dates; static forecast XML is intentionally avoided so rows reflect the selected forecast range.
- Validate the full generated analytics chain with a modest controlled dataset before adding more Phase 6 KPI models.
- Validate generated analytics lifecycle behavior: manager-only generation and scoped reruns that preserve adjacent company, currency, plan, date, and all-plan rows.
- Generate ARPU summaries from opening and closing MRR snapshots; static ARPU XML is intentionally avoided so rows reflect the selected snapshot period.
- Generate LTV summaries from ARPU summaries and retention cohorts; static LTV XML is intentionally avoided so rows reflect the selected ARPU period and cohort range.
- Generate churn reason summaries from cancelled and expired subscriptions with cancellation dates; static churn reason summary XML is intentionally avoided so rows reflect selected periods, plans, reasons, and feedback coverage.
- Validate churn reason summary quality fields: movement MRR vs fallback MRR source, missing reason, and no/partial/full feedback coverage.
- Generate top plan summaries from snapshots, KPI summaries, ARPU summaries, LTV summaries, churn reason summaries, and revenue forecasts; static top-plan summary XML is intentionally avoided so rows reflect the selected period and generated analytics inputs.
- Generate at-risk subscription summaries from current subscription, invoice, payment attempt, dunning attempt, renewal, and cancellation state; static at-risk summary XML is intentionally avoided so rows reflect current manager work.
- Generate payment recovery summaries from payment attempts, open recovery invoices, dunning attempts, and at-risk rows; static recovery summary XML is intentionally avoided so rows reflect current payment recovery workload.
- Generate trial conversion summaries from trial subscriptions; static trial conversion summary XML is intentionally avoided so rows reflect selected trial periods and current subscription state.
- Open **Analytics Generation Guide** before running the generated analytics stack so users follow the same sequence used by automated tests.
- Add historical MRR movement records across multiple months.
- Add subscriptions in multiple cohorts, plans, countries, salespeople, and states.
- Add churn reasons and scheduled cancellations to make retention and forecast reports meaningful.

**Documentation updates:**

- Add metric-definition guide.
- Add dashboard user guide.
- Add report validation guide that explains how to manually reconcile key metrics.
- Add performance test instructions for large datasets.

**Acceptance gates:**

- Managers can generate or regenerate daily MRR snapshots for a date without duplicate rows.
- Snapshot records separate values by company, currency, and subscription plan.
- Snapshot counts and MRR buckets match the current subscription records at generation time.
- Managers can generate or regenerate reconciliation rows for a date range without duplicates.
- Reconciliation rows clearly identify matched buckets, variance buckets, and missing opening or closing snapshots.
- Managers can generate movement-only anomaly rows for date ranges without duplicates.
- Anomaly rows expose source movement drilldowns for buckets missing both snapshots or missing plan data.
- Managers can generate KPI summary rows for date ranges without duplicates.
- KPI summaries expose Net New MRR, NRR, and GRR by company, currency, and plan.
- KPI definitions are documented and match SQL outputs.
- Managers can generate KPI dashboard rows for one company/currency/period and optional plan without duplicates.
- KPI dashboard rows aggregate plan-level KPI summaries only within the selected currency and expose source drilldowns.
- Managers can generate waterfall rows for one company/currency/period and optional plan without duplicates.
- Waterfall rows show ordered opening, new, expansion, contraction, churned, and closing MRR buckets with source drilldowns.
- Waterfall rows expose expected closing MRR, actual closing MRR, and variance so managers can spot source KPI math mismatches.
- Managers can generate retention cohort rows for monthly cohort ranges without duplicates.
- Retention cohort rows show starting, retained, and churned subscription/MRR buckets by cohort age and source drilldowns.
- Managers can generate revenue forecast rows for monthly forecast ranges without duplicates.
- Forecast rows show active base MRR, upcoming invoice MRR, renewal due MRR, scheduled churn MRR, net forecast MRR, and source drilldowns.
- A repeatable analytics smoke test generates snapshots, reconciliation, anomalies, KPI summaries, dashboards, waterfalls, retention cohorts, and forecasts together without duplicate rows or broken all-plan/currency scoping.
- Non-manager users cannot generate or regenerate analytics records.
- Scoped regeneration does not delete adjacent generated rows outside the selected company, currency, plan, date range, or all-plan bucket.
- Managers can generate ARPU summary rows from opening and closing snapshots without duplicates.
- ARPU summary rows show opening count, closing count, average count, opening MRR, closing MRR, average MRR, zero-safe ARPU, missing-snapshot statuses, and source drilldowns.
- Managers can generate LTV summary rows from ARPU summaries and retention cohorts without duplicates.
- LTV summary rows show ARPU, churn rate, estimated lifetime months, LTV, missing-source statuses, zero-churn status, and source drilldowns.
- Managers can generate churn reason summary rows from cancelled and expired subscriptions without duplicates.
- Churn reason summary rows show churned subscription count, churned MRR, average churned MRR, feedback count, feedback coverage, missing-reason status, all-reason aggregates, and source drilldowns.
- Churn reason summary rows expose whether churned MRR came from recorded churn movements, fallback subscription MRR, or mixed sources.
- Churn reason summary rows expose no/partial/full feedback coverage buckets so managers can spot weak cancellation data capture.
- Managers can generate top plan summary rows from existing generated analytics without duplicates.
- Top plan rows show opening MRR, closing MRR, ARR, net new MRR, subscription state counts, ARPU, LTV, churned MRR, feedback coverage, upcoming invoice MRR, scheduled churn MRR, net forecast MRR, missing-input statuses, and source drilldowns.
- Managers can generate at-risk subscription summary rows from current operational signals without duplicates.
- At-risk rows show risk score, low/medium/high/critical buckets, MRR at risk, payment recovery signals, failed payment attempts, dunning escalation, scheduled churn, upcoming invoices, renewal due dates, missing primary payment methods, and source drilldowns.
- Managers can generate payment recovery summary rows for a selected period without duplicates.
- Payment recovery rows separate portal, cron, manual, and all-source buckets while keeping company, currency, and plan scopes distinct.
- Payment recovery rows show failed, pending, recovered, cancelled/error, manual-action-required, retry-exhausted/final-dunning counts, recovery amounts, recovered amounts, pending amounts, failed amounts, open recovery invoices, linked at-risk subscriptions, MRR at risk, and source drilldowns.
- Payment recovery recovery amount is workload-oriented and avoids double-counting an invoice that already has a payment attempt in the selected period.
- Managers can generate trial conversion summary rows for a selected period without duplicates.
- Trial conversion rows show trials started, converted, expired, still active, converted MRR, active trial MRR, conversion rate, expiry rate, average trial length, and source drilldowns.
- Trial conversion uses existing fields only; conversion date is inferred from `subscription_start_date`.
- Dashboard loads in under 3 seconds with 10K subscriptions.
- MRR movement totals reconcile to snapshot deltas.
- Filters by company, plan, salesperson, country, and period work.

**Tests:**

- SQL report correctness.
- Snapshot generation, state bucket totals, MRR bucket totals, ARR, plan grouping, and idempotent reruns.
- MRR reconciliation matched/variance/missing-snapshot statuses, movement buckets, drilldowns, plan grouping, and idempotent reruns.
- MRR movement anomaly detection for movement-only buckets, missing-plan buckets, ignored normal buckets, drilldowns, plan grouping, and idempotent reruns.
- MRR KPI summary formulas for Net New MRR, NRR, GRR, missing inputs, missing reconciliation fallback, drilldowns, plan grouping, and idempotent reruns.
- MRR KPI dashboard generation, multi-plan aggregation, currency separation, missing summary/input status, source drilldowns, and idempotent reruns.
- MRR waterfall generation, ordered bucket math, variance status, multi-plan aggregation, all-plan drilldowns, currency separation, missing summary/input status, source drilldowns, and idempotent reruns.
- Retention cohort generation, churn timing, trial-start fallback, plan/currency separation, all-plan drilldowns, and idempotent reruns.
- Revenue forecast generation, upcoming invoice buckets, renewal due buckets, scheduled churn buckets, plan/currency separation, all-plan drilldowns, and idempotent reruns.
- Analytics performance smoke test with generated records, multi-plan/currency scoping, all-plan drilldowns, churn reason generation, top-plan generation, payment recovery generation, trial conversion generation, and idempotent reruns.
- Generated analytics lifecycle tests for manager-only generation and adjacent-scope preservation.
- ARPU summary generation from snapshots, missing opening/closing statuses, zero-safe ARPU, plan/currency separation, all-plan aggregation, source drilldowns, scoped reruns, and manager-only generation.
- LTV summary generation from ARPU and retention cohorts, zero-churn handling, missing-source statuses, plan/currency separation, all-plan aggregation, source drilldowns, scoped reruns, and manager-only generation.
- Churn reason summary generation from cancelled/expired subscriptions, period filtering, state exclusion, missing-reason status, MRR source quality, feedback coverage buckets, plan/reason/currency separation, all-plan/all-reason aggregation, source drilldowns, scoped reruns, and manager-only generation.
- Top plan summary generation from snapshots, KPI summaries, ARPU summaries, LTV summaries, churn reason summaries, and revenue forecasts; plan/currency separation, source drilldowns, missing-input statuses, scoped reruns, and manager-only generation.
- At-risk subscription summary generation from subscription, invoice, payment attempt, dunning attempt, renewal, and cancellation signals; score buckets, plan/currency separation, source drilldowns, scoped reruns, and manager-only generation.
- Payment recovery summary generation from payment attempts, open invoices, dunning escalation, and at-risk rows; source buckets, plan/currency separation, source drilldowns, scoped reruns, and manager-only generation.
- Trial conversion summary generation from trial dates and inferred conversion state; conversion/expiry rates, active trial buckets, converted MRR, active trial MRR, plan/currency separation, source drilldowns, scoped reruns, and manager-only generation.

**Continuous validation:**

- Demo reports must show non-empty MRR waterfall, churn, trial conversion, retention, and forecast views.
- Tests must compare dashboard/report numbers against known demo fixtures.

---

### Phase 7 - Accounting And Revenue Recognition

**Objective:** Add finance-grade deferred revenue and recognition workflows.

**Current slice status:** Phase 7 finance setup and access hardening is complete. Deferred revenue schedule generation, hardening, posting preview, manual journal posting, credit-note adjustments, reconciliation reports, posting helper hardening, scheduled posting cron foundation, company-aware setup, account/journal validation, and accounting read-only finance visibility are complete.

**Build items:**

1. Deferred revenue configuration
   - Deferred revenue account - foundation done as company-specific settings default copied onto schedules.
   - Revenue account - foundation done as company-specific settings default copied onto schedules.
   - Recognition journal - foundation done as company-specific settings default copied onto schedules.
   - Recognition method - foundation done for straight-line daily and equal monthly, now company-scoped.
   - Company-level defaults - hardening done with legacy config-parameter fallback for upgrade safety.
   - Account/journal validation - hardening done for missing config, cross-company records, journal type, liability deferred account, and income revenue account.

2. Deferred revenue schedule
   - `subscription.deferred.revenue` - foundation done.
   - `subscription.deferred.revenue.line` - foundation done.
   - Link schedule to subscription and invoice - done.
   - Service period from invoice/subscription period - done with blocked status for missing/invalid periods.
   - Missing revenue recognition configuration - done with blocked status instead of silently generating incomplete schedules.
   - Mixed invoices - done for recurring subscription lines; one-time lines can be explicitly excluded from subscription deferred revenue.
   - Schedule locking - done for ready/cancelled schedules and recognized lines, with internal posting context allowed to set recognition state and journal entry links.

3. Recognition methods
   - Straight-line daily - schedule foundation done.
   - Equal monthly - schedule foundation done.
   - Manual.

4. Recognition posting
   - Preview wizard - foundation done for due draft recognition lines.
   - Manual posting wizard - foundation done for ready schedules, due draft lines, and one posted journal entry per schedule.
   - Shared posting helper - hardening done so manual posting and future scheduled cron use the same validation, move creation, line marking, and chatter behavior.
   - Monthly/daily scheduled posting cron - foundation done with company-scoped config gate, today/prior-month-end cutoff rules, shared posting helper reuse, idempotent recognized-line exclusion, and generated run logs.
   - Journal entry links - foundation done from recognition lines and schedule smart button.
   - Reversal/cancellation handling - foundation done for posted credit notes linked to original subscription invoices.
   - Credit note handling - foundation done with idempotent adjustment records, draft-line adjustment, and recognized-revenue reversal entries.

5. Finance reports
   - Deferred revenue balance - foundation done through generated reconciliation remaining-deferred amount.
   - Recognized revenue by period - foundation done through generated reconciliation recognized-line and posted-journal amounts.
   - Unrecognized revenue by customer/plan - deferred beyond period/plan reconciliation buckets.
   - Reconciliation between invoices, schedules, and journal entries - foundation done with source drilldowns and variance status.
   - Finance schedule filters - hardening done for remaining deferred schedules, recognized lines, and credit-note adjustments.

**Demo data updates:**

- Generate annual prepaid subscription invoices suitable for deferred revenue schedules.
- Add monthly and annual recognition examples.
- Use mixed invoice examples carefully: only recurring subscription service lines should feed deferred revenue; one-time services should be excluded.
- Preview recognition from generated schedules before posting.
- Post due recognition lines from ready schedules to create accounting journal entries.
- Add cancellation/credit-note examples that adjust deferred revenue through generated adjustment records.
- Generate deferred revenue reconciliation rows from posted invoices, schedules, recognition entries, and credit-note adjustments; do not load static reconciliation XML.
- Enable scheduled recognition posting only after reviewing deferred revenue schedules and recognition configuration; generated run logs should be reviewed instead of loading static cron results.
- Configure recognition defaults per company; generated schedules, preview, manual posting, and scheduled posting use the invoice or schedule company setup.

**Documentation updates:**

- Add finance setup guide for company-specific deferred revenue accounts, revenue accounts, recognition journal, method, scheduled posting gate, and cutoff rule.
- Add revenue recognition workflow guide.
- Add reconciliation guide linking invoices, schedules, journal entries, and reports.
- Add accounting caveats and known limitations.

**Acceptance gates:**

- Posted annual prepaid invoice creates a deferred revenue schedule.
- Schedule line totals equal the invoice untaxed amount.
- Mixed posted invoices recognize only eligible recurring subscription service lines.
- Missing service period invoices are blocked with a clear reason.
- Missing recognition configuration is blocked with a clear reason.
- Invalid recognition configuration is blocked with a clear reason, including wrong account type, wrong journal type, or cross-company account/journal setup.
- Ready schedules and recognized schedule lines cannot be edited or removed through normal operations.
- Recognition preview shows due draft lines and debit deferred revenue / credit revenue impact without posting accounting entries.
- Manual recognition posting creates one posted journal entry per schedule and marks only included due lines recognized.
- Manual recognition posting uses the shared schedule-line helper that scheduled cron must reuse.
- Scheduled recognition posting is disabled by configuration by default, supports today and prior-month-end cutoffs, skips future/blocked/cancelled/already recognized lines, and does not duplicate posted journal entries on rerun.
- Preview, manual posting, and scheduled posting use the target schedule/company configuration rather than a different company's setup.
- Total recognized plus remaining deferred equals invoice amount.
- Credit note/cancellation adjusts schedules correctly by cancelling/reducing draft recognition lines or posting reversal entries for recognized lines.
- Generated reconciliation rows expose ready, variance, missing schedule, missing journal entry, and blocked schedule statuses with drilldowns to every source record.
- Finance users can reconcile reports to accounting moves with read-only access; generation, posting, adjustment, and scheduled-posting setup remain manager-controlled.

**Tests:**

- Schedule creation - foundation covered.
- Straight-line daily calculation - foundation covered.
- Monthly equal calculation - foundation covered.
- Idempotent schedule regeneration - foundation covered.
- Missing configuration blocking - covered.
- Company-specific recognition setup, legacy fallback, invalid account type blocking, and accounting read-only finance access - covered.
- Mixed invoice recurring-line eligibility - covered.
- Ready/recognized schedule locking - covered.
- Recognition preview due-line selection, scoping, totals, manager access, and no-posting/no-state-change behavior - foundation covered.
- Posting journal entries - foundation covered for due-line selection, one posted move per schedule, line recognition links, idempotent rerun exclusion, configuration validation, filtering, preview immutability, and manager-only access.
- Cancellation and credit note - foundation covered for draft-line cancellation, recognized-line reversal entries, idempotency, over-adjustment blocking, ambiguous credit-note blocking, and cancelled schedule blocking.
- Deferred revenue reconciliation - foundation covered for ready rows, variance status, missing schedule, missing journal entry, blocked schedules, credit-note adjustment impact, recognized reversal plus remaining draft lines, plan scoping, source drilldowns, idempotent reruns, and manager-only generation.
- Scheduled recognition posting cron - foundation covered for disabled no-op behavior, today and prior-month-end cutoff rules, missing configuration failure logs, idempotent reruns, run counts, shared posting helper reuse, and no duplicate accounting moves.
- Multi-company and multi-currency.

**Continuous validation:**

- Demo data must reconcile invoice amount, recognized revenue, posted journal amount, credit-note adjustments, and remaining deferred revenue.
- Tests must verify journal entry lines and schedule totals.

---

### Phase 8 - Enterprise Security, Scale, And Release Packaging

**Objective:** Make the suite deployable for serious customers.

**Current slice:** Performance Index And Scale Smoke Foundation. The security/access foundation is complete; this slice adds targeted Odoo-native indexes for existing cron, recovery, finance, usage, and generated-report domains plus medium-scale operational smoke coverage before the final 10K benchmark or release packaging.

**Build items:**

1. Security hardening
   - Full record-rule audit - foundation started with core, billing, dunning, portal-helper, reports, finance, and generated analytics coverage.
   - Portal route audit and stable `HttpCase` harness - still deferred until the local route harness is stable.
   - Multi-company tests - foundation added for generated reports plus billing and dunning records.
   - Manager/user/portal permission matrix - foundation added for subscription users, subscription managers, accounting read-only users, and portal requester ownership.
   - Read/write/delete access review for every model - foundation started with high-risk generated, finance, billing, and dunning records.

2. Performance
   - Indexes for cron and reports - foundation started for billing due-date selection, dunning due-date selection, payment recovery attempts, usage aggregation, deferred revenue schedules/lines/adjustments, and generated analytics bucket fields.
   - Batch size configuration.
   - Medium-scale operational smoke tests - foundation added for billing cron, recognition preview selection, dunning cron, and generated analytics stack idempotency.
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
- All high-risk access rules are tested before release: subscription user, subscription manager, accounting read-only, accounting manager, portal requester, and multi-company cases.
- 10K subscription benchmark is recorded.
- Release notes list known limitations honestly.
- Demo data tells a complete story: trial, active, paused, past due, cancelled, renewed, upsold, recovered, churned.

**Continuous validation:**

- Security hardening must pass core, billing, dunning, portal, and reports test tags plus full installed-suite upgrade.
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
