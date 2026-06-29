# Migration And Data Operations Runbook

## Scope

The migration framework imports UTF-8 CSV files into operational Subscription
Suite records. It does not import invoices, payments, journal entries, or
historical lifecycle events.

Only Subscription Managers can validate, apply, or inspect data operations.
Each execution creates a persistent audit record without storing raw CSV rows.

## Before Import

1. Back up the PostgreSQL database and Odoo filestore.
2. Test restoration on a disposable database.
3. Confirm the target company, currencies, partners, products, pricelists,
   users, payment providers/tokens, and usage meters already exist.
4. Copy the templates from `docs/import_templates` and retain their headers.
5. Export UTF-8 CSV. Excel files are not accepted directly.

Partners resolve by exact `res.partner.ref`; products resolve by exact
`default_code`. Ambiguous or cross-company references fail validation.

## Recommended File Order

1. `plans.csv`
2. `plan_lines.csv`
3. `plan_line_tiers.csv`
4. `subscriptions.csv`
5. `subscription_lines.csv`
6. `subscription_line_tiers.csv`
7. `payment_assignments.csv`
8. `usage_events.csv`

Stable references make reruns idempotent. Blank values preserve existing
values during updates; this foundation does not clear fields through CSV.

## Validate And Apply

1. Open **Subscriptions -> Configuration -> Data Operations**.
2. Create an import operation, select the company and template type, upload one
   CSV, and keep the mode on **Validate**.
3. Review schema errors, failed rows, warnings, and the downloadable result CSV.
4. Correct the source file and validate again until the accepted rows are
   understood.
5. Create an **Apply** operation and select the prior validation run.
6. Upload the exact same file. Company, template type, and SHA-256 hash must
   match the validation.
7. Review created, updated, skipped, warning, and failed counts.

Apply is row-isolated. A failed row rolls back to its savepoint while valid rows
continue. It is not file-atomic.

Payment assignment imports only attach an existing active Odoo token matching
the subscription company, commercial customer, provider code, and provider
reference. They never create tokens.

## Backfills

### MRR Movement

Use MRR backfill for live trial, active, paused, or past-due subscriptions with
positive MRR and no movement history. Validate first, then apply. Existing
history and cancelled/expired subscriptions are skipped with an audit reason.

### Billing Attempts

Select a company and invoice-date range. Eligible records are posted
subscription customer invoices with a positive untaxed amount and valid
subscription service-period dates. Validate first, then apply.

The backfill creates successful audit attempts only. It does not generate
invoices, collect payments, or alter invoice/payment state.

## Correction And Recovery

- Download and retain the operation result CSV.
- Correct source data and rerun validation with a new file.
- Rerunning the same validated file updates by stable reference and does not
  duplicate supported records.
- There is no automated rollback. Correct individual imported records through
  approved Odoo workflows or restore the verified database and filestore
  backup when the import must be fully reversed.

## Deferred Capabilities

- Excel ingestion and arbitrary third-party schema mapping
- Payment-token creation
- Invoice, payment, accounting, and historical churn import
- Currency conversion
- Automated rollback
- External migration API ingestion
