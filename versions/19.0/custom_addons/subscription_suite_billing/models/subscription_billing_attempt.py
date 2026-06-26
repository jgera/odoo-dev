from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SubscriptionBillingAttempt(models.Model):
    _name = 'subscription.billing.attempt'
    _description = 'Subscription Billing Attempt'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'attempt_date desc, id desc'

    name = fields.Char(string='Reference', required=True, copy=False, default=lambda self: _('New'))
    run_id = fields.Many2one('subscription.billing.run', string='Billing Run', ondelete='set null', index=True)
    subscription_id = fields.Many2one(
        'sale.order',
        string='Subscription',
        required=True,
        ondelete='cascade',
        domain=[('is_subscription', '=', True)],
        index=True,
    )
    partner_id = fields.Many2one(related='subscription_id.partner_id', string='Customer', store=True, readonly=True)
    company_id = fields.Many2one(related='subscription_id.company_id', string='Company', store=True, readonly=True, index=True)
    currency_id = fields.Many2one(related='subscription_id.currency_id', string='Currency', store=True, readonly=True, index=True)
    invoice_id = fields.Many2one('account.move', string='Invoice', readonly=True)
    period_start = fields.Date(string='Period Start', required=True, index=True)
    period_end = fields.Date(string='Period End', required=True, index=True)
    attempt_date = fields.Datetime(string='Attempt Date', required=True, default=fields.Datetime.now, index=True)
    attempt_no = fields.Integer(string='Attempt #', default=1, readonly=True)
    idempotency_key = fields.Char(string='Idempotency Key', required=True, readonly=True, index=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped'),
    ], string='Status', default='pending', required=True, tracking=True, index=True)
    amount = fields.Monetary(string='Amount', currency_field='currency_id', readonly=True)
    error_message = fields.Text(string='Error Message', readonly=True)
    first_failure_at = fields.Datetime(string='First Failure At', readonly=True)
    last_failure_at = fields.Datetime(string='Last Failure At', readonly=True, index=True)
    failure_count = fields.Integer(string='Failure Count', readonly=True, default=0, index=True)
    last_failure_message = fields.Text(string='Last Failure Message', readonly=True)
    failure_category = fields.Selection([
        ('configuration', 'Configuration'),
        ('invoice_validation', 'Invoice Validation'),
        ('system', 'System'),
        ('unknown', 'Unknown'),
    ], string='Failure Category', readonly=True, index=True)
    retryable = fields.Boolean(string='Retryable', readonly=True, index=True)
    retry_exhausted = fields.Boolean(string='Retry Exhausted', readonly=True, index=True)
    recovery_required = fields.Boolean(string='Recovery Required', readonly=True, index=True)
    recovery_note = fields.Text(string='Recovery Note', readonly=True)
    next_retry_at = fields.Datetime(string='Next Retry At', readonly=True, index=True)
    last_retry_at = fields.Datetime(string='Last Retry At', readonly=True)

    _subscription_billing_attempt_unique = models.Constraint(
        'UNIQUE(idempotency_key)',
        'A billing attempt already exists for this subscription and billing period.',
    )

    def action_open_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            return False
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

    def action_retry(self):
        for attempt in self:
            if attempt.state != 'failed':
                raise UserError(_('Only failed billing attempts can be retried.'))
            if not attempt.retryable:
                raise UserError(_('This billing attempt is not marked as retryable.'))
            if attempt.subscription_id.billing_in_progress:
                raise UserError(_('This subscription is already being processed by another billing operation.'))

        for attempt in self:
            attempt.write({
                'state': 'pending',
                'error_message': False,
                'attempt_date': fields.Datetime.now(),
                'attempt_no': attempt.attempt_no + 1,
                'last_retry_at': fields.Datetime.now(),
                'retry_exhausted': False,
            })
            try:
                attempt.subscription_id._generate_subscription_invoice()
            except Exception as error:
                attempt._record_failure_once(error)
        return True

    @api.model
    def _cron_retry_failed_billing_attempts(self):
        now = fields.Datetime.now()
        max_attempts = self._get_retry_max_attempts()
        batch_size = self._get_retry_batch_size()
        attempts = self.search([
            ('state', '=', 'failed'),
            ('retryable', '=', True),
            ('retry_exhausted', '=', False),
            ('next_retry_at', '!=', False),
            ('next_retry_at', '<=', now),
            ('subscription_id.billing_in_progress', '=', False),
        ], limit=batch_size, order='next_retry_at asc, id asc')

        for attempt in attempts:
            with self.env.cr.savepoint():
                if attempt.attempt_no >= max_attempts:
                    attempt._mark_retry_exhausted()
                    continue
                attempt.action_retry()
                if attempt.state == 'failed' and attempt.attempt_no >= max_attempts:
                    attempt._mark_retry_exhausted()
        return attempts

    def _prepare_failure_values(self, error):
        self.ensure_one()
        category, retryable = self._classify_failure(error)
        now = fields.Datetime.now()
        error_message = str(error)
        next_retry_at = False
        if retryable:
            next_retry_at = now + timedelta(hours=self._get_retry_delay_hours())
        return {
            'state': 'failed',
            'error_message': error_message,
            'first_failure_at': self.first_failure_at or now,
            'last_failure_at': now,
            'failure_count': self.failure_count + 1,
            'last_failure_message': error_message,
            'failure_category': category,
            'retryable': retryable,
            'retry_exhausted': False,
            'recovery_required': not retryable,
            'recovery_note': self._get_recovery_note(category, retryable, error_message),
            'next_retry_at': next_retry_at,
        }

    def _record_failure(self, error):
        for attempt in self:
            values = attempt._prepare_failure_values(error)
            attempt.write(values)
            attempt.message_post(body=_(
                'Billing failure %(count)s recorded. Category: %(category)s. Retryable: %(retryable)s. Error: %(error)s',
                count=values['failure_count'],
                category=dict(attempt._fields['failure_category'].selection).get(values['failure_category']),
                retryable=_('Yes') if values['retryable'] else _('No'),
                error=values['error_message'],
            ))

    def _record_failure_once(self, error):
        for attempt in self:
            error_message = str(error)
            if attempt.state == 'failed' and attempt.last_failure_message == error_message:
                continue
            attempt._record_failure(error)

    def _mark_retry_exhausted(self):
        for attempt in self:
            attempt.write({
                'retryable': False,
                'retry_exhausted': True,
                'recovery_required': True,
                'recovery_note': _('Automatic retries are exhausted. Review the subscription, fix the root cause, then retry manually.'),
                'next_retry_at': False,
            })
            attempt.message_post(body=_(
                'Automatic billing retries are exhausted after %(count)s failures. Manual recovery is required.',
                count=attempt.failure_count,
            ))
            attempt.subscription_id.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_('Subscription billing needs manual recovery'),
                note=_(
                    'Billing attempt %(attempt)s failed %(count)s times and needs manual recovery.\n\nLast error:\n%(error)s',
                    attempt=attempt.display_name,
                    count=attempt.attempt_no,
                    error=attempt.error_message or _('No error message was recorded.'),
                ),
                user_id=(attempt.subscription_id.user_id or self.env.user).id,
            )

    def _get_recovery_note(self, category, retryable, error_message):
        if retryable:
            return _('Temporary failure. The retry cron will try this billing attempt again.')
        if category == 'configuration':
            return _('Configuration issue. Review product accounts, taxes, journals, fiscal position, or currency setup before retrying.')
        if category == 'invoice_validation':
            return _('Invoice validation issue. Review invoiceable subscription lines, quantities, and units of measure before retrying.')
        return _('Manual review required before retrying. Last error: %s') % error_message

    def _get_retry_max_attempts(self):
        return self._get_positive_int_param('subscription_suite.billing_retry_max_attempts', 3)

    def _get_retry_batch_size(self):
        return self._get_positive_int_param('subscription_suite.billing_retry_batch_size', 50)

    def _get_retry_delay_hours(self):
        return self._get_positive_int_param('subscription_suite.billing_retry_delay_hours', 1)

    def _get_positive_int_param(self, key, default):
        value = self.env['ir.config_parameter'].sudo().get_param(key, default)
        try:
            return max(int(value or default), 1)
        except (TypeError, ValueError):
            return default

    def _classify_failure(self, error):
        message = str(error or '').lower()
        configuration_terms = [
            'missing',
            'not configured',
            'no account',
            'no income account',
            'fiscal position',
            'tax',
            'currency',
        ]
        invoice_validation_terms = [
            'cannot create an invoice',
            'no items are available to invoice',
            'no invoiceable',
            'quantity',
            'unit of measure',
        ]
        system_terms = [
            'deadlock',
            'timeout',
            'could not serialize',
            'connection',
            'lock',
            'temporary',
        ]
        if any(term in message for term in configuration_terms):
            return 'configuration', False
        if any(term in message for term in invoice_validation_terms):
            return 'invoice_validation', False
        if any(term in message for term in system_terms):
            return 'system', True
        return 'unknown', True
