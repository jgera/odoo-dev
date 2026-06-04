# Phase Validation Checklist

Use this checklist after every implementation phase. Do not move to the next phase until the current phase passes or its failures are explicitly documented.

## 1. Scope Check

- [ ] The phase objective is documented.
- [ ] Changed addons are listed.
- [ ] New models, fields, menus, crons, reports, controllers, and tests are listed.
- [ ] Any intentionally deferred behavior is written under known limitations.

## 2. Code Boundary Check

- [ ] Core lifecycle changes are in `subscription_suite`.
- [ ] Billing/proration/payment collection changes are in `subscription_suite_billing`.
- [ ] Dunning/recovery changes are in `subscription_suite_dunning`.
- [ ] Portal routes/templates are in `subscription_suite_portal`.
- [ ] Reports and analytics views are in `subscription_suite_reports`.
- [ ] Cross-addon dependencies are reflected in manifests.

## 3. Demo Data Check

- [ ] Demo data shows the new feature in a normal Odoo UI flow.
- [ ] Demo data covers at least one successful path.
- [ ] Demo data covers at least one edge or exception path where safe.
- [ ] Demo records have clear names and can be found from menus/search views.
- [ ] Portal-facing demo records are attached to a documented partner/user.
- [ ] Demo data does not create accounting inconsistencies on install.

If a scenario is unsafe for static XML demo data, add a repeatable demo script or documented manual setup instead.

## 4. Automated Test Check

- [ ] Tests cover the main successful path.
- [ ] Tests cover failure or blocked behavior.
- [ ] Tests cover access rules or portal permissions when relevant.
- [ ] Tests cover cron idempotency when relevant.
- [ ] Tests can run on the Odoo 19 demo/test database.
- [ ] Test names describe the behavior being protected.

## 5. Documentation Check

- [ ] User workflow is documented.
- [ ] Admin/setup steps are documented.
- [ ] Developer notes explain non-obvious implementation choices.
- [ ] Validation commands are documented.
- [ ] Known limitations are updated.
- [ ] Manual demo checklist is updated.

## 6. Validation Commands

Compile:

```powershell
python -m compileall custom_addons\subscription_suite
```

Upgrade all current suite modules:

```powershell
python scripts\dev_odoo.py --odoo-version 19.0 -d odoo19_subscription_demo -u subscription_suite,subscription_suite_billing,subscription_suite_dunning,subscription_suite_portal,subscription_suite_reports --stop-after-init --no-browser --no-cron --no-dev --log-level=info
```

Run the demo server:

```powershell
python scripts\dev_odoo.py --odoo-version 19.0 -d odoo19_subscription_demo --no-browser --no-cron --no-dev --log-level=info
```

## 7. Manual Smoke Test

- [ ] Open `http://localhost:8069/web?debug=1`.
- [ ] Open the Subscriptions app.
- [ ] Open subscription plans.
- [ ] Open subscriptions in kanban/list/form.
- [ ] Open reporting menus.
- [ ] Open dunning policies if `subscription_suite_dunning` is installed.
- [ ] Open portal as a portal user if the phase touches portal behavior.

## 8. Phase Sign-Off

Record the result:

```text
Phase:
Date:
Database:
Modules upgraded:
Tests run:
Demo data updated:
Docs updated:
Known limitations:
Decision: pass / pass with limitations / blocked
```
