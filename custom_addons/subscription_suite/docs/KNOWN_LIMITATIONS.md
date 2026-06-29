# Known Limitations

## Billing And Payments

- Provider behavior uses Odoo payment transactions and tokens; provider-specific webhook integrations are not included.
- Recovery analytics are operational records, not accounting settlement reports.
- Complex payment allocation across several subscriptions remains an accounting workflow.

## Portal

- Portal lifecycle operations use existing approval/request flows.
- Stable live `HttpCase` coverage for every portal route remains incomplete.
- Portal seat, add-on, usage, and promotion self-service are not included.
- Portal payment-method validation and retry use Odoo payment providers and
  transactions; provider-specific portal behavior depends on provider setup.

## Pricing And Usage

- Tiered pricing uses an effective unit price on one invoice line.
- Usage ingestion is backend-only; there is no public metering API.
- Only one pending add-on operation per subscription is supported.
- Discount changes apply forward without mid-period discount credits.

## Analytics

- Generated analytics must be generated in sequence.
- Currency values remain separated; normalized cross-currency totals are not provided.
- Forecasting is deterministic and does not predict churn probability.
- LTV excludes CAC and gross margin.

## Revenue Recognition

- Recognition uses company-scoped configuration and source invoice currency.
- Advanced partial-refund allocation requires unambiguous invoice and service-period links.
- Jurisdiction-specific accounting review remains required.

## Operations

- The 10K benchmark is a local measurement, not a universal production SLA.
- Migration supports documented UTF-8 CSV schemas only; Excel ingestion and
  arbitrary third-party schema mapping are not included.
- CSV apply is row-isolated rather than file-atomic, blank updates do not clear
  fields, and automated rollback is not included.
- Migration does not create payment tokens or import invoices, payments,
  accounting entries, historical churn, or currency-converted values.
- Operational monitoring summarizes supported scheduled jobs but does not provide
  external alerting, raw traceback storage, queue-worker telemetry, or generic replay.
- Operations digest and successful-run cleanup are opt-in and their Odoo scheduled
  actions are disabled by default.
