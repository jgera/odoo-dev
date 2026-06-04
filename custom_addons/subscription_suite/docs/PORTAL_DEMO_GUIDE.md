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
- Chatter/history display.

The portal does not yet support customer self-service actions such as pause, resume, cancel, change plan, update payment method, or retry payment.

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
  - recurring items
  - invoice history or "no invoices" message

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

- Portal self-service actions are not implemented.
- Portal update-payment flow is not implemented.
- Portal retry-payment flow is not implemented.
- Portal route tests are currently basic and should become `HttpCase` tests before self-service actions are added.
- Portal demo depends on creating/granting a portal user manually.
