# RC Acceptance Runbook

Use this runbook when preparing a release-candidate database and evidence pack.
It complements `RELEASE_CHECKLIST.md`; it does not replace manual product,
finance, portal, and owner review.

## Database

Use a disposable database for official RC evidence:

```powershell
python scripts\subscription_suite_rc_acceptance.py -d odoo19_subscription_rc --fresh-install --confirm-recreate --run-tests
```

The command records JSON and Markdown evidence under
`custom_addons/subscription_suite/docs/release_evidence`.

For a faster rehearsal without touching PostgreSQL:

```powershell
python scripts\subscription_suite_rc_acceptance.py -d odoo19_subscription_rc --dry-run --portal-smoke
```

## Required Review Order

1. Run static checks.
2. Fresh install all five addons in the RC database.
3. Run all five tagged addon test suites.
4. Run a full installed-suite upgrade.
5. Prepare or verify RC demo scenarios.
6. Validate portal ownership with two unrelated portal customers.
7. Generate finance and analytics records in the documented order.
8. Capture screenshots from the RC database.
9. Review known limitations, release notes, and listing copy.
10. Record final release decision in `RELEASE_CHECKLIST.md`.

## Manual Gates

The runner intentionally leaves these gates manual:

- Portal smoke: automated helper tests remain authoritative, but release review
  should still open the customer portal as two customers and confirm denied
  cross-customer access.
- Screenshot review: screenshots must be inspected visually for credentials,
  local filesystem paths, debug artifacts, and unsupported claims.
- Commercial metadata: author, website, pricing, support channel, and ownership
  details require product-owner sign-off before publishing.

## Evidence Rules

- Commit only concise Markdown evidence when it is useful for release review.
- Keep raw logs, database dumps, filestore copies, benchmark JSON, screenshots
  with sensitive data, and local configuration out of Git.
- Every failed, blocked, or skipped gate needs a short owner decision before
  release.

