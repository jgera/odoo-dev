# Release Checklist

## Source And Version

- [ ] Working tree contains only intended release changes.
- [ ] All five manifests use the intended Odoo 19 version.
- [ ] Dependencies and data files are valid.
- [ ] Changelog and known limitations match the release.
- [ ] No secrets, dumps, benchmark JSON, or local configuration are staged.

## Automated Acceptance

- [ ] `python scripts\subscription_suite_release_check.py --static-only` passes.
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
- [ ] Email and payment credentials are tested in staging.
- [ ] Database and filestore backup/restore are proven.
- [ ] The 10K benchmark is reviewed against the performance budget.

## Packaging

- [ ] Installation/configuration and testing guidance is current.
- [ ] Odoo Apps description, screenshots, icon, license, author, and support details are reviewed.
- [ ] Release commit and tag are created.
- [ ] Release notes state upgrade steps and known limitations.

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
