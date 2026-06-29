# Subscription Suite Troubleshooting Guide

## Install Or Upgrade Fails

Check:

- All addons are loaded from `versions/19.0/custom_addons`.
- All five modules are installed or upgraded together.
- `python scripts\subscription_suite_release_check.py --static-only` passes.
- No empty or wrong addon path is ahead of the Odoo 19 addon path.
- The working branch contains the expected release commit.

For a clean validation database, use the release-check fresh-install command
from [Installation And Configuration Guide](INSTALLATION_AND_CONFIGURATION_GUIDE.md).

## Missing Field Or Broken View

If the web client reports an undefined field:

1. Confirm the addon containing the model field is installed.
2. Upgrade all five suite modules together.
3. Clear Odoo assets only after the module upgrade succeeds.
4. Confirm the database is using the versioned addon path, not a stale mirror.

Do not fix a view by deleting fields until the model loading path has been
verified.

## Portal Shows No Database Selected

On localhost, `/my` can fail when Odoo cannot infer the database. Log in with:

```text
/web/login?db=DATABASE_NAME
```

Then open:

```text
/my/subscriptions
```

If the page is still empty, confirm the contact has portal access and belongs
to the same commercial partner as the subscription.

## Portal Access Or Ownership Errors

Use two portal customers to verify isolation. If one customer can see another
customer's subscription, invoice, token, transaction, or request, treat it as a
security defect and run the portal access tests before release.

If a customer cannot see their own subscription, check:

- Portal user partner.
- Commercial partner relationship.
- Subscription partner.
- Access token route only when using shared document links.

## Payment Recovery Issues

If retry is unavailable:

- Confirm the invoice is posted and unpaid or partially paid.
- Confirm the invoice is linked to the subscription.
- Confirm the subscription has an eligible saved payment token.
- Confirm no latest portal attempt is still pending.
- Review `subscription.payment.attempt` recovery notes.

If a token cannot be selected, confirm it belongs to the customer's commercial
partner, is active, and matches the configured provider.

## Dunning Does Not Run

Check:

- Subscription is past due.
- Dunning policy is configured.
- Next dunning date is due.
- Dunning scheduled action is enabled only after manual validation.
- Retry-exhausted or final-action flags are not blocking further retries.

Review dunning attempts and operational runs for skipped or failed records.

## Analytics Missing Inputs

Generated analytics must be run in sequence. Missing-input statuses usually
mean an upstream report has not been generated for the same period, company,
currency, and plan.

Use the sequence in [User Guide](USER_GUIDE.md) and regenerate only the affected
scope. Reruns should update existing generated rows rather than duplicate them.

## Finance Configuration Errors

If schedule generation, preview, posting, or cron posting blocks:

- Confirm company-specific deferred revenue account, revenue account, journal,
  and recognition method are configured.
- Confirm deferred account is liability type.
- Confirm revenue account is income type.
- Confirm journal belongs to the target company or is company-neutral.
- Confirm invoice service-period dates are present.
- Review blocked schedule reason or recognition run error summary.

## Migration CSV Failures

Open the data operation result and download the error CSV.

Common causes:

- Missing required columns.
- Wrong template type.
- Apply file hash does not match validation run.
- Ambiguous pricelist.
- Cross-company partner, product, plan, token, or subscription reference.
- Invalid tier boundaries.
- Payment token does not already exist for the subscription customer.
- Blank update used where field clearing was intended.

Correct the CSV and validate again before apply.

## Operational Runs

Operational runs summarize scheduled and manager-triggered work.

If a run is `partial` or `failed`:

1. Open the source drilldowns.
2. Review exact failed/skipped counts.
3. Correct the source data or configuration.
4. Use only workflow-specific retry actions.

Do not attempt generic replay for accounting or billing operations.

