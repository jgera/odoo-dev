# Release Notes Template

## Version

`19.0.x.y.z`

## Release Date

`YYYY-MM-DD`

## Commit

`COMMIT_SHA`

## Highlights

- 

## Added

- 

## Changed

- 

## Fixed

- 

## Upgrade Notes

- Back up database and filestore before upgrading.
- Upgrade all five Subscription Suite addons together.
- Run the release acceptance command on a staging copy before production.

## Migration Notes

- CSV imports require validation before apply.
- Apply mode must use the same company, template, and file hash as validation.
- Payment tokens are assigned only when existing tokens already match the
  provider, company, and customer ownership rules.

## Validation Evidence

```text
Commit:
Database:
Fresh install:
Upgrade:
Static check:
Test tags:
Portal smoke:
Finance reconciliation:
Benchmark reviewed:
```

## Known Limitations

See `KNOWN_LIMITATIONS.md`.

## Support

Include Odoo version, database name, installed module versions, reproduction
steps, logs, screenshots, and the release commit when reporting an issue.

