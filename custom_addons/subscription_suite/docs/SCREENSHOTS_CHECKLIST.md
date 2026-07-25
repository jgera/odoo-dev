# Screenshots Checklist

Use a prepared demo database with representative customers and subscriptions.
Avoid credentials, local filesystem paths, and unrelated browser chrome.

Official listing screenshots should be captured from the RC database, reviewed,
then placed under `subscription_suite/static/description/screenshots`. Keep the
full evidence set local or in the release evidence folder only when every image
is safe to commit.

Recommended capture rules:

- Use a clean browser window around 1440x900.
- Disable debug overlays unless the screenshot is explicitly for an admin guide.
- Do not show passwords, tokens, local paths, database manager screens, or
  unrelated browser tabs.
- Prefer real demo records over empty configuration pages.
- Record every omitted checklist item with an approved reason in the RC evidence
  report.

## Core Subscription Screens

- Subscriptions list with active, trial, paused, past-due, cancelled, and
  expired examples.
- Subscription form with plan, state, MRR, next invoice date, billing period,
  payment method, seat quantity, and smart buttons.
- Plan form with products, policies, pricing, usage rules, and upgrade paths.
- Renewal or upsell quotation linked to an origin subscription.

## Billing And Recovery

- Billing attempts list.
- Payment attempts list with source, state, token role, recovery note, and
  linked transaction where available.
- Manager Operations payment recovery metrics and drilldowns.
- Past-due subscription with recovery context.

## Dunning

- Dunning policy or attempt list.
- Retry-exhausted or final-action example.
- Manager Operations dunning drilldown.

## Portal

- Portal home subscriptions entry.
- Portal subscription list.
- Portal subscription detail with recurring items and invoice history.
- Payment recovery banner with invoice, residual, due date, and retry action.
- Payment method selection or validation flow entry.
- Plan change, pause/resume, and cancellation request history.

## Pricing And Expansion

- Seat-based subscription line.
- Backend Change Seats wizard result.
- Add-on operation or pending add-on change.
- Tiered or volume pricing setup.
- Usage meter and usage summary.
- Promotional discount metadata on a recurring line.

## Analytics

- MRR KPI dashboard.
- MRR waterfall.
- Retention cohorts.
- Revenue forecast.
- ARPU or LTV summary.
- Churn reasons.
- Top plans.
- At-risk subscriptions.
- Payment recovery analytics.
- Trial conversion analytics.

## Finance

- Deferred revenue schedule form.
- Recognition preview wizard.
- Posted recognition journal entry.
- Credit-note adjustment.
- Deferred revenue reconciliation list.
- Recognition run log.

## Operations And Migration

- Operational Runs list with success, partial, failed, and skipped examples.
- Operations digest configuration.
- Data operation validation result.
- Data operation line diagnostics.
- Migration runbook or template list.

## Configuration

- Subscription settings showing company-scoped recognition configuration.
- Scheduled actions review screen for required crons.
- User/group setup for subscription manager and accounting read-only review.
