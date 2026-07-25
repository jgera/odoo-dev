# Release Checklist

## Source And Version

- [ ] Working tree contains only intended release changes.
- [ ] All five manifests use the intended Odoo 19 version.
- [ ] Dependencies and data files are valid.
- [ ] Changelog and known limitations match the release.
- [ ] No secrets, dumps, benchmark JSON, or local configuration are staged.

## Automated Acceptance

- [ ] `python scripts\subscription_suite_release_check.py --static-only` passes.
- [ ] `python scripts\subscription_suite_rc_acceptance.py -d odoo19_subscription_rc --fresh-install --confirm-recreate --run-tests` produces JSON and Markdown evidence.
- [ ] Fresh installation passes on a disposable database.
- [ ] Upgrade passes on a staging copy of the prior release.
- [ ] All five tagged addon test suites pass.
- [ ] `git diff --check` passes.

## Functional Acceptance

- [ ] Core lifecycle and renewal/upsell workflows pass.
- [ ] Recurring billing rerun is idempotent.
- [ ] Payment recovery and dunning pass.
- [ ] Portal ownership is checked with two customers.
- [ ] Seat, add-on, usage, tiered pricing, and discount examples pass.
- [ ] Generated analytics sequence completes without duplicates.
- [ ] Deferred revenue generation, preview, posting, adjustment, and reconciliation pass.

## Security And Operations

- [ ] User, manager, accounting, and portal permissions are reviewed.
- [ ] Multi-company visibility is verified.
- [ ] Required crons are configured and unwanted crons remain disabled.
- [ ] Failed and partial operational runs are reviewed and source drilldowns resolve.
- [ ] Operations digest recipients are approved, or the digest remains disabled.
- [ ] Run cleanup retention is approved; failed and partial summaries are preserved.
- [ ] Email and payment credentials are tested in staging.
- [ ] Database and filestore backup/restore are proven.
- [ ] The 10K benchmark is reviewed against the performance budget.

## Migration And Data Operations

- [ ] Database and filestore backups are verified before apply mode.
- [ ] Every CSV was validated and apply used the same company, template, and file hash.
- [ ] Import result CSVs and operation counts were reviewed and retained.
- [ ] Cross-company references and payment-token ownership failures were resolved.
- [ ] MRR and billing-attempt backfills were validated before apply.
- [ ] Imported records were spot-checked by stable external reference.

## Packaging

- [ ] Installation/configuration, user, admin, finance, portal, troubleshooting, migration, and testing guidance is current.
- [ ] RC acceptance runbook and latest evidence report are reviewed.
- [ ] Odoo Apps listing copy is reviewed and does not overclaim unsupported features.
- [ ] Screenshot checklist is complete or every omitted screenshot has an approved reason.
- [ ] Listing screenshots are copied to `subscription_suite/static/description/screenshots` only after visual review.
- [ ] `subscription_suite/static/description/index.html` is reviewed against current product scope and limitations.
- [ ] Icon, license, author, website, pricing, and support details are reviewed.
- [ ] Release notes use the release notes template and state upgrade steps.
- [ ] Release commit and tag are created.
- [ ] Release notes state known limitations.

## Sign-Off

```text
Version:
Commit:
Date:
Database:
Fresh install:
Upgrade:
Test tags:
Portal smoke:
Finance reconciliation:
Benchmark reviewed:
Known limitations reviewed:
Approved by:
Decision: release / release with limitations / blocked
```
