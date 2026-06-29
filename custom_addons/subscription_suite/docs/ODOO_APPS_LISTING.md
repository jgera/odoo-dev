# Odoo Apps Listing Draft

## Title

Subscription Suite for Odoo 19 Community

## Short Summary

Enterprise-grade subscription lifecycle, recurring billing, dunning, portal
recovery, analytics, deferred revenue, observability, and migration tools for
Odoo 19 Community.

## Description

Subscription Suite extends Odoo 19 Community with a complete operational
subscription system. It supports plans, recurring subscription orders,
renewal and upsell controls, seat and add-on operations, tiered pricing, usage
metering, promotional discounts, payment recovery, dunning, customer portal
requests, generated SaaS analytics, deferred revenue workflows, operational
monitoring, and audited CSV migration.

The suite is designed for teams that need transparent subscription operations
inside Odoo without moving to a separate subscription platform.

## Key Features

- Subscription plans with recurring products, policy controls, upgrade and
  downgrade paths.
- Renewal and upsell quotation workflows.
- Recurring billing with idempotent billing attempts.
- Payment recovery with primary and backup payment-token handling.
- Customer portal subscription view, lifecycle requests, payment-method
  selection, validation-return handling, and retry guidance.
- Dunning policies and recovery escalation.
- Seat, add-on, usage, tiered pricing, and time-limited discount foundations.
- Generated MRR, retention, forecast, ARPU, LTV, churn, at-risk, trial, and
  payment recovery analytics.
- Deferred revenue schedules, recognition preview, journal posting,
  credit-note adjustments, reconciliation, and scheduled posting controls.
- Unified operational run summaries, manager drilldowns, optional digest, and
  retention cleanup.
- Audited CSV validation/apply tools and safe MRR/billing-attempt backfills.

## Included Addons

- `subscription_suite`
- `subscription_suite_billing`
- `subscription_suite_dunning`
- `subscription_suite_portal`
- `subscription_suite_reports`

## Requirements

- Odoo 19 Community.
- Odoo accounting and payment dependencies required by the installed suite.
- Correct company, journal, account, payment provider, and scheduled-action
  configuration before production use.

## Configuration Notes

After installation:

1. Configure users and subscription managers.
2. Configure plans, products, taxes, journals, and payment providers.
3. Validate recurring billing and dunning in staging.
4. Configure company-specific revenue recognition accounts and journal.
5. Generate analytics in sequence.
6. Review release checklist, known limitations, and migration runbook.

## Support Statement

Support should include installation review, configuration review, issue
reproduction steps, server logs, module versions, database name, Odoo version,
and the current Git/release commit.

## Known Limitations Summary

- Odoo 19 Community only.
- Provider-specific payment webhooks are not included.
- Currency-normalized analytics are not included.
- Public usage ingestion API is not included.
- Portal seat/add-on/usage/promotion self-service is not included.
- Migration supports documented UTF-8 CSV templates only.
- Accounting policy review remains required before production revenue
  recognition use.

## Screenshot Plan

Use [Screenshots Checklist](SCREENSHOTS_CHECKLIST.md) to capture listing images
from a prepared demo database. Screenshots should show real records and avoid
local-only technical details, credentials, and browser debug artifacts.

