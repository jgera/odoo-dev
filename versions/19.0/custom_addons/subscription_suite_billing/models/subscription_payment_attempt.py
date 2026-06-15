from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SubscriptionPaymentAttempt(models.Model):
    _name = 'subscription.payment.attempt'
    _description = 'Subscription Payment Attempt'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'attempt_date desc, id desc'

    name = fields.Char(string='Reference', required=True, copy=False, default=lambda self: _('New'))
    subscription_id = fields.Many2one(
        'sale.order',
        string='Subscription',
        required=True,
        ondelete='cascade',
        domain=[('is_subscription', '=', True)],
        index=True,
    )
    invoice_id = fields.Many2one('account.move', string='Invoice', required=True, ondelete='cascade', index=True)
    transaction_id = fields.Many2one('payment.transaction', string='Transaction', readonly=True, index=True)
    partner_id = fields.Many2one(related='subscription_id.partner_id', string='Customer', store=True, readonly=True)
    company_id = fields.Many2one(related='subscription_id.company_id', string='Company', store=True, readonly=True)
    currency_id = fields.Many2one(related='invoice_id.currency_id', string='Currency', store=True, readonly=True)
    provider_id = fields.Many2one('payment.provider', string='Provider', readonly=True, index=True)
    token_id = fields.Many2one('payment.token', string='Payment Token', readonly=True, index=True)
    token_role = fields.Selection([
        ('primary', 'Primary'),
        ('backup', 'Backup'),
    ], string='Payment Method Role', default='primary', readonly=True, index=True)
    requested_by_id = fields.Many2one('res.users', string='Requested By', readonly=True)
    source = fields.Selection([
        ('cron', 'Cron'),
        ('portal', 'Portal'),
        ('manual', 'Manual'),
    ], string='Source', required=True, default='manual', readonly=True, index=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('error', 'Error'),
    ], string='Status', default='pending', required=True, tracking=True, index=True)
    provider_state = fields.Char(string='Provider State', readonly=True)
    provider_reference = fields.Char(string='Provider Reference', readonly=True)
    amount = fields.Monetary(string='Amount', currency_field='currency_id', readonly=True)
    attempt_date = fields.Datetime(string='Attempt Date', required=True, default=fields.Datetime.now, index=True)
    completed_at = fields.Datetime(string='Completed At', readonly=True, index=True)
    failure_message = fields.Text(string='Failure Message', readonly=True)
    recovery_required = fields.Boolean(string='Recovery Required', readonly=True, index=True)
    recovery_note = fields.Text(string='Recovery Note', readonly=True)

    def action_open_invoice(self):
        self.ensure_one()
        return {
            'name': _('Invoice'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
        }

    def action_open_subscription(self):
        self.ensure_one()
        return {
            'name': _('Subscription'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.subscription_id.id,
            'view_mode': 'form',
        }

    def action_open_transaction(self):
        self.ensure_one()
        if not self.transaction_id:
            return False
        return {
            'name': _('Payment Transaction'),
            'type': 'ir.actions.act_window',
            'res_model': 'payment.transaction',
            'res_id': self.transaction_id.id,
            'view_mode': 'form',
        }

    def action_refresh_transaction_state(self):
        for attempt in self:
            if not attempt.transaction_id:
                raise UserError(_('Only payment attempts linked to a transaction can be refreshed.'))
            attempt._sync_from_transaction(log_subscription=True)
        return True

    @api.model
    def _create_for_invoice(self, subscription, invoice, source='manual', requested_by=None, token=None, token_role='primary'):
        subscription.ensure_one()
        invoice.ensure_one()
        token = token or subscription.payment_token_id
        amount = invoice.amount_residual
        if invoice.currency_id.is_zero(amount):
            amount = invoice.amount_total
        return self.create({
            'name': self.env['ir.sequence'].next_by_code('subscription.payment.attempt') or _('New'),
            'subscription_id': subscription.id,
            'invoice_id': invoice.id,
            'provider_id': token.provider_id.id if token else False,
            'token_id': token.id if token else False,
            'token_role': token_role,
            'requested_by_id': requested_by.id if requested_by else self.env.user.id,
            'source': source,
            'amount': amount,
            'state': 'pending',
        })

    def _finalize_from_transaction(self, transaction):
        return self._sync_from_transaction(transaction=transaction)

    def _sync_from_transaction(self, transaction=None, log_subscription=False):
        self.ensure_one()
        transaction = transaction or self.transaction_id
        if not transaction:
            raise UserError(_('Only payment attempts linked to a transaction can be refreshed.'))
        transaction.ensure_one()
        previous_state = self.state
        previous_provider_state = self.provider_state
        state = self._map_transaction_state(transaction.state)
        values = {
            'transaction_id': transaction.id,
            'provider_id': transaction.provider_id.id,
            'token_id': transaction.token_id.id if transaction.token_id else self.token_id.id,
            'provider_state': transaction.state,
            'provider_reference': transaction.provider_reference if 'provider_reference' in transaction._fields else False,
            'state': state,
            'completed_at': fields.Datetime.now() if state in ('success', 'failed', 'cancelled', 'error') else False,
            'recovery_required': state in ('failed', 'cancelled', 'error'),
            'failure_message': self._get_transaction_failure_message(transaction) if state in ('failed', 'cancelled', 'error') else False,
            'recovery_note': self._get_recovery_note(state, transaction),
        }
        self.write(values)
        if previous_state != state or previous_provider_state != transaction.state:
            self.message_post(body=_(
                'Payment attempt refreshed from provider state %(provider_state)s to %(state)s for invoice %(invoice)s.',
                provider_state=transaction.state or _('Unknown'),
                state=dict(self._fields['state'].selection).get(state, state),
                invoice=self.invoice_id.display_name,
            ))
        if log_subscription and previous_state != state:
            event_type = 'payment_success' if state == 'success' else 'payment_pending' if state == 'pending' else 'payment_failed'
            self.subscription_id._log_subscription_event(
                event_type,
                _('Payment attempt %(attempt)s refreshed to %(state)s for invoice %(invoice)s.') % {
                    'attempt': self.name,
                    'state': dict(self._fields['state'].selection).get(state, state),
                    'invoice': self.invoice_id.display_name,
                },
                new_values={
                    'payment_attempt_id': self.id,
                    'transaction_id': transaction.id,
                    'transaction_state': transaction.state,
                },
            )
        return state

    def _record_exception(self, error):
        for attempt in self:
            attempt.write({
                'state': 'error',
                'completed_at': fields.Datetime.now(),
                'failure_message': str(error),
                'recovery_required': True,
                'recovery_note': _('Payment retry raised an exception. Review the provider configuration and transaction logs before retrying.'),
            })
            attempt.message_post(body=_('Payment attempt failed with an exception: %s') % str(error))

    def _map_transaction_state(self, transaction_state):
        if transaction_state == 'done':
            return 'success'
        if transaction_state in ('cancel', 'canceled', 'cancelled'):
            return 'cancelled'
        if transaction_state == 'error':
            return 'failed'
        return 'pending'

    def _get_transaction_failure_message(self, transaction):
        if 'state_message' in transaction._fields and transaction.state_message:
            return transaction.state_message
        if 'last_state_change' in transaction._fields and transaction.last_state_change:
            return str(transaction.last_state_change)
        return _('Payment provider returned state: %s') % (transaction.state or _('Unknown'))

    def _get_recovery_note(self, state, transaction):
        if state == 'success':
            return _('Payment was recovered successfully.')
        if state == 'pending':
            if self.source == 'portal':
                return _('Customer payment retry was submitted and is waiting for provider confirmation.')
            return _('Payment request is waiting for provider confirmation.')
        if state == 'cancelled':
            return _('Payment was cancelled by the provider or customer. Ask the customer to retry or use the invoice payment page.')
        if self.source == 'portal':
            return _('Customer payment retry failed. Ask the customer to update the payment method or pay the invoice directly.')
        return _('Payment failed at the provider. Review the transaction and retry after the payment method or provider issue is resolved.')
