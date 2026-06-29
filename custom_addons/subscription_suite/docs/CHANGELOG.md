# Changelog

## Unreleased

### Added

- Odoo 19 subscription lifecycle, billing, payment recovery, and dunning.
- Portal visibility and controlled lifecycle/payment-recovery operations.
- Seat, add-on, usage, tiered pricing, and discount foundations.
- Generated MRR, retention, forecast, ARPU, LTV, churn, risk, recovery, and trial analytics.
- Deferred revenue schedules, posting, adjustments, reconciliation, and scheduled controls.
- Security, multi-company, performance smoke, and 10K benchmark foundations.
- Release acceptance runner and release-readiness documentation.
- Unified operational run summaries, manager health drilldowns, opt-in failure
  digest, and safe successful-run retention controls.
- Audited UTF-8 CSV migration for plans, subscriptions, recurring lines, tiers,
  payment-token assignments, and usage events, plus idempotent MRR and
  billing-attempt backfills.

### Known Limitations

- See `KNOWN_LIMITATIONS.md`.

## Release Process

1. Move entries from `Unreleased` into a versioned heading.
2. Use `## 19.0.x.y.z - YYYY-MM-DD`.
3. Record upgrade notes and data migrations explicitly.
4. Link the release commit and benchmark report in release notes.
