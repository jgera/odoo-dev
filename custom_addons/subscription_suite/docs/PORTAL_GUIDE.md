# Subscription Suite Portal Guide

## Portal Scope

The customer portal lets portal users inspect their subscriptions, invoices,
scheduled changes, request history, payment recovery state, and eligible
self-service requests.

Portal users can access only records belonging to their commercial partner.
Backend manager approval remains required for lifecycle changes that are not
immediate customer-safe actions.

## Customer Access

Create portal access from the customer contact. The portal user must belong to
the intended commercial partner for the subscription.

Portal URLs:

- `/my`
- `/my/subscriptions`
- `/my/subscription/<id>`

If no database is selected on localhost, use the Odoo database selector or log
in through `/web/login?db=DATABASE_NAME` before opening `/my`.

## Subscription Detail

The subscription page shows:

- Plan and subscription reference.
- State and status badges.
- MRR and recurring amount.
- Billing period and next invoice date.
- Current payment method status.
- Seat count when seat lines exist.
- Recurring subscription items.
- Invoice history.
- Scheduled plan change or cancellation.
- Plan change, lifecycle, and cancellation request history.
- Chatter/history where exposed by portal templates.

## Lifecycle Requests

Customers can submit supported requests from the portal:

- Next-period plan change through configured upgrade/downgrade paths.
- Pause request when the plan allows pausing.
- Resume request for paused subscriptions.
- Cancellation request with reason capture.

Managers review requests in the backend and approve or reject them.

## Payment Method And Recovery

The portal supports payment recovery around Odoo payment tokens and payment
transactions:

- Customers can see an eligible unpaid or partial subscription invoice recovery
  banner.
- Customers can select an existing saved token that belongs to their commercial
  partner.
- Customers can validate a new saved payment method through Odoo's payment
  validation flow.
- Customers can retry payment for an eligible invoice when a saved method is
  available and no pending retry blocks duplicate submission.
- Pending, failed, cancelled, paid, and missing-method states are shown with
  Odoo-native portal alerts.

The portal does not create payment providers or bypass Odoo payment transaction
behavior. Provider-specific webhook behavior is outside this suite.

## Ownership Boundaries

The portal must reject access to another customer's:

- Subscription detail.
- Recovery invoice.
- Payment token.
- Payment validation transaction.
- Lifecycle request.
- Cancellation request.

When testing, use two different portal customers and confirm each customer sees
only their own subscriptions and recovery work.

## Current Limitations

- Portal seat, add-on, usage, and promotion self-service are not included.
- Portal routes have deterministic helper/model coverage; full live `HttpCase`
  route coverage remains deferred until the local authenticated route harness
  is stable.
- Payment-provider-specific UX depends on configured Odoo providers.

