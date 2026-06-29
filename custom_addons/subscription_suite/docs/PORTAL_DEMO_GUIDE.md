# Portal Demo Guide

This guide explains how to validate the current customer portal behavior for subscriptions.

## Current Portal Scope

The portal currently supports:

- Portal home subscription count.
- `/my/subscriptions` subscription list.
- `/my/subscription/<id>` subscription detail page.
- Status badges.
- MRR, recurring amount, next invoice date, billing period, payment method, and auto-pay display.
- Recurring subscription items.
- Subscription invoice history when invoices are linked to the subscription.
- Payment recovery banner for eligible unpaid or partial subscription invoices.
- Saved payment-token selection for customer-owned tokens.
- Payment method validation return through Odoo payment validation.
- Payment retry for eligible recovery invoices when a saved method is available.
- Scheduled plan change and scheduled cancellation visibility.
- Plan change request history.
- Pause/resume lifecycle request history.
- Cancellation request history.
- Customer-initiated next-period plan change requests for configured upgrade/downgrade paths.
- Customer-initiated pause/resume requests with backend manager approval.
- Customer-initiated cancellation requests with reason capture and backend manager approval.
- Chatter/history display.

The portal does not yet support update payment method, retry payment, or immediate customer-executed destructive actions.

## Backend Setup

1. Start Odoo:

```powershell
python scripts\dev_odoo.py --odoo-version 19.0 -d odoo19_subscription_demo --no-browser --no-cron --no-dev --log-level=info
```

2. Open:

```text
http://localhost:8069/web?debug=1
```

3. Open the Subscriptions app.

4. Pick one demo subscription:

| Demo subscription | Partner |
| --- | --- |
| `demo_subscription_active` | `base.res_partner_2` |
| `demo_subscription_trial` | `base.res_partner_3` |
| `demo_subscription_paused` | `base.res_partner_4` |
| `demo_subscription_cancelled` | `base.res_partner_1` |
| `demo_subscription_scheduled_cancellation` | `base.res_partner_4` |

5. Grant portal access to that customer from the Contacts app or customer form.

## Portal Validation

Log in as the portal user and validate:

- Open `/my`.
- A Subscriptions entry is visible on the portal home page.
- Open `/my/subscriptions`.
- Only subscriptions for the portal user's commercial partner are shown.
- Open a subscription from the list.
- The detail page shows:
  - plan
  - subscription reference
  - status
  - MRR
  - recurring amount
  - next invoice
  - billing period
  - current period
  - payment method status
  - scheduled plan change or cancellation status when available
  - plan change, lifecycle, and cancellation request history when available
  - recurring items
  - invoice history or "no invoices" message

## Self-Service Validation

Plan change request:

- Open an active subscription whose current plan has configured upgrade or downgrade paths.
- Select a target plan in **Request Plan Change**.
- Submit the request.
- Confirm the portal shows a success message.
- In the backend, open **Subscriptions -> Subscriptions -> Plan Change Requests** and confirm a pending next-period request exists.

Cancellation request:

- Open an active, trial, paused, or past-due subscription that does not already have a pending cancellation or pending cancellation request.
- Select a reason in **Request Cancellation**.
- Submit the request.
- Confirm the portal shows a success message.
- In the backend, open **Subscriptions -> Subscriptions -> Cancellation Requests** and confirm a pending request exists.
- Approve as a subscription manager and confirm the existing cancellation policy is applied.

Pause/resume request:

- Open an active subscription whose plan allows pausing.
- Submit **Request Pause** from the portal.
- In the backend, open **Subscriptions -> Subscriptions -> Lifecycle Requests** and confirm a pending pause request exists.
- Approve as a subscription manager and confirm the subscription moves to Paused.
- Open the paused subscription from the portal.
- Submit **Request Resume**.
- Approve as a subscription manager and confirm the subscription moves to Active.

## Unauthenticated Check

Without logging in, this URL should redirect to login:

```text
http://localhost:8069/my/subscriptions
```

Expected result:

```text
/web/login?redirect=%2Fmy%2Fsubscriptions
```

## Current Known Gaps

- Portal seat, add-on, usage, and promotion self-service are not implemented.
- Provider-specific payment UX depends on configured Odoo payment providers.
- Portal route tests are currently deterministic helper/model coverage and should become `HttpCase` tests once the local authenticated HTTP test flow is stable.
- Portal demo depends on creating/granting a portal user manually.
