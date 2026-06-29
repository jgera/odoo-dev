# Subscription Suite Finance Guide

## Purpose

Subscription Suite includes operational deferred revenue tooling for
subscription invoices. It can generate schedules, preview recognition, post
recognition journal entries, process linked credit-note adjustments, and
generate reconciliation rows.

Finance teams should review local accounting requirements before production
use. The suite does not replace jurisdiction-specific accounting advice.

## Company Recognition Setup

Configure recognition settings per company:

- Deferred revenue account.
- Revenue account.
- Recognition journal.
- Default recognition method.
- Scheduled posting enabled flag.
- Scheduled posting cutoff rule.

The deferred revenue account must be a liability account. The revenue account
must be an income account. The journal must be suitable for general accounting
entries and must belong to the target company or be company-neutral.

## Schedule Generation

Generate schedules from posted customer invoices linked to subscriptions.
Schedules require clear subscription service-period start and end dates.

Generation rules:

- Draft invoices are excluded.
- Credit notes are handled through adjustment flow, not normal schedule
  generation.
- Non-subscription invoices are excluded.
- One-time service lines should not feed subscription deferred revenue.
- Missing or invalid service periods create blocked schedules instead of
  guessed allocation.

Rerunning generation updates draft schedules without duplicating them.

## Recognition Methods

Supported foundation methods:

- Straight-line daily.
- Equal monthly.

Schedule lines reconcile back to the eligible invoice untaxed amount in invoice
currency. Rounding remainder is assigned deterministically so generated lines
sum to the schedule amount.

## Recognition Preview

Use **Subscriptions -> Billing -> Preview Recognition** to inspect due draft
recognition lines through a cutoff date.

Preview:

- Does not create journal entries.
- Does not change recognition line state.
- Excludes future, blocked, cancelled, and already recognized lines.
- Shows debit deferred revenue and credit revenue impact.
- Keeps totals separated by company and currency.

## Manual Posting

Use **Subscriptions -> Billing -> Post Recognition** after preview review.

Posting:

- Selects due draft lines from ready schedules.
- Creates one posted journal entry per deferred revenue schedule/invoice.
- Debits deferred revenue and credits revenue.
- Marks included lines recognized only after the journal entry posts.
- Links each recognized line to its recognition move.
- Skips already recognized lines on rerun.

Posting is manager-only and should be tested in staging before production.

## Credit-Note Adjustments

Credit-note adjustment handles posted refunds linked to subscription invoices.

Supported paths:

- Unrecognized credited periods reduce or cancel matching draft recognition
  lines.
- Already recognized credited periods create reversal journal entries linked to
  the recognition move.

Ambiguous credit notes without a linked source invoice or clear service period
are blocked. Reruns are idempotent and should not duplicate reversal moves.

## Reconciliation

Generate deferred revenue reconciliation rows for a period after invoices,
schedules, recognition entries, and credit-note adjustments exist.

Review:

- Invoice deferred amount.
- Schedule amount.
- Recognized line amount.
- Posted journal amount.
- Credit-note adjustment amount.
- Remaining deferred amount.
- Variance amount and status.
- Drilldowns to invoices, schedules, lines, moves, credit notes, and
  adjustments.

Reconciliation rows are generated audit reports. They do not mutate accounting
records.

## Scheduled Posting

Scheduled recognition posting is disabled until explicitly configured. It uses
the same posting helper as manual posting.

Before enabling:

1. Generate schedules manually.
2. Preview recognition manually.
3. Post recognition manually.
4. Generate reconciliation.
5. Confirm company configuration and cutoff rule.
6. Review recognition run logs after the first scheduled execution.

## Finance Limitations

- Amounts use source invoice currency; cross-currency normalization is not
  included.
- Advanced partial-refund allocation requires unambiguous invoice and service
  period links.
- Accounting-document import is not included.
- Jurisdiction-specific revenue policy remains the responsibility of the
  finance team.

