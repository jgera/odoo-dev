# Subscription Suite Admin Guide

## Administration Scope

This guide is for Odoo administrators configuring Subscription Suite in an
Odoo 19 Community database. Use
[Installation And Configuration Guide](INSTALLATION_AND_CONFIGURATION_GUIDE.md)
for the initial install commands.

## Users And Access

Review these roles before go-live:

- Subscription users can inspect allowed operational records.
- Subscription managers can create, configure, generate, post, adjust, import,
  and run manager-only workflows.
- Accounting read-only users can inspect finance schedules, lines,
  adjustments, reconciliations, and recognition run logs.
- Accounting managers use normal Odoo accounting rights for posted journal
  entries, but do not gain subscription mutation rights unless also assigned
  subscription manager access.
- Portal users can access only their commercial partner's portal records.

After creating users, test visibility with at least two companies and two
portal customers.

## Company Setup

Configure each company that will run subscriptions:

- Company currency.
- Subscription users and managers.
- Journals, taxes, accounts, and payment providers.
- Revenue recognition settings when finance workflows are used.
- Scheduled-action policy for billing, dunning, recognition, analytics, digest,
  and cleanup.

Multi-company users should be tested with restricted allowed companies before
release.

## Plans And Operational Defaults

Administrators should standardize:

- Plan codes and naming.
- Recurring products and units of measure.
- Upgrade and downgrade paths.
- Renewal and upsell policy.
- Dunning policy.
- Payment retry policy.
- Usage meters and overage products.
- Discount metadata policy.

Use codes and import references consistently if CSV migration or repeatable
demo data will be used.

## Scheduled Actions

Do not enable all crons by default in a new database. Recommended sequence:

1. Prove manual recurring billing.
2. Prove failed-payment recovery and dunning on test records.
3. Prove analytics generation sequence.
4. Prove deferred revenue schedule, preview, posting, adjustment, and
   reconciliation.
5. Enable only required scheduled actions.
6. Review `subscription.operation.run` summaries after the first scheduled run.

Operations digest and successful-run cleanup are disabled by default and should
be enabled only after recipients and retention policy are approved.

## Observability

Open **Subscriptions -> Operations -> Operational Runs** to review job
summaries. Failed and partial runs are retained by cleanup policy and should be
investigated before rerunning related jobs.

Operational runs summarize work. Source records such as billing attempts,
payment attempts, dunning attempts, recognition runs, and generated analytics
remain authoritative.

## Backups And Recovery

Before upgrades, migration apply mode, finance posting, or release-candidate
validation:

- Back up the database.
- Back up the filestore.
- Record the Git commit and addon versions.
- Confirm restore steps in a non-production environment.

CSV apply is row-isolated and does not provide automated rollback. Recovery is
through normal Odoo correction, reimport with stable references, or database
restore when required.

## Release Validation

Before release:

- Run `python scripts\subscription_suite_release_check.py --static-only`.
- Run a fresh install on a disposable database.
- Run a full upgrade on a staging copy.
- Run all five addon test tags when preparing a release candidate.
- Review [Release Checklist](RELEASE_CHECKLIST.md).
- Review [Known Limitations](KNOWN_LIMITATIONS.md).

