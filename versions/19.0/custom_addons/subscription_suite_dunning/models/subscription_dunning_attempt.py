from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SubscriptionDunningAttempt(models.Model):
    _name = 'subscription.dunning.attempt'
    _description = 'Subscription Dunning Attempt'
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
    partner_id = fields.Many2one(related='subscription_id.partner_id', string='Customer', store=True, readonly=True, index=True)
    company_id = fields.Many2one(related='subscription_id.company_id', string='Company', store=True, readonly=True, index=True)
    currency_id = fields.Many2one(related='subscription_id.currency_id', string='Currency', store=True, readonly=True, index=True)
    invoice_id = fields.Many2one('account.move', string='Invoice', readonly=True, index=True)
    policy_id = fields.Many2one('subscription.dunning.policy', string='Policy', readonly=True, index=True)
    policy_line_id = fields.Many2one('subscription.dunning.policy.line', string='Policy Step', readonly=True, index=True)
    email_template_id = fields.Many2one('mail.template', string='Email Template', readonly=True)
    mail_mail_id = fields.Many2one('mail.mail', string='Email', readonly=True)
    payment_attempt_id = fields.Many2one('subscription.payment.attempt', string='Payment Attempt', readonly=True)
    manual_retry_count = fields.Integer(string='Manual Retries', readonly=True)
    last_manual_retry_at = fields.Datetime(string='Last Manual Retry At', readonly=True)
    auto_retry_enabled = fields.Boolean(string='Auto Retry Enabled', readonly=True, index=True)
    auto_retry_count = fields.Integer(string='Auto Retries', readonly=True)
    max_auto_retries = fields.Integer(string='Max Auto Retries', readonly=True)
    next_auto_retry_at = fields.Datetime(string='Next Auto Retry At', readonly=True, index=True)
    last_auto_retry_at = fields.Datetime(string='Last Auto Retry At', readonly=True)
    retry_exhausted = fields.Boolean(string='Retry Exhausted', readonly=True, index=True)
    action_type = fields.Selection([
        ('email', 'Email'),
        ('email_and_retry', 'Email and Retry'),
        ('final_cancel', 'Final Cancellation'),
        ('final_pause', 'Final Pause'),
        ('final_none', 'Final No Action'),
    ], string='Action', required=True, readonly=True, index=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('done', 'Done'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped'),
    ], string='Status', default='pending', required=True, tracking=True, index=True)
    attempt_date = fields.Datetime(string='Attempt Date', required=True, default=fields.Datetime.now, index=True)
    completed_at = fields.Datetime(string='Completed At', readonly=True, index=True)
    days_since_start = fields.Integer(string='Days Since Failure', readonly=True)
    amount_at_risk = fields.Monetary(string='Amount at Risk', currency_field='currency_id', readonly=True)
    recovery_url = fields.Char(string='Recovery URL', readonly=True)
    note = fields.Text(string='Note', readonly=True)
    error_message = fields.Text(string='Error Message', readonly=True)

    def action_open_subscription(self):
        self.ensure_one()
        return {
            'name': _('Subscription'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.subscription_id.id,
            'view_mode': 'form',
        }

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

    def action_open_payment_attempt(self):
        self.ensure_one()
        if not self.payment_attempt_id:
            return False
        return {
            'name': _('Payment Attempt'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.payment.attempt',
            'res_id': self.payment_attempt_id.id,
            'view_mode': 'form',
        }

    def action_retry_payment(self):
        self.ensure_one()
        self._check_retry_allowed(manual=True)
        payment_attempt, transaction = self._retry_payment(source='manual', requested_by=self.env.user)

        note = _('Manual payment retry requested by %s.') % self.env.user.display_name
        if transaction and transaction.state == 'done':
            note = _('Manual payment retry recovered the subscription.')
        elif transaction:
            note = _('Manual payment retry returned provider state: %s') % transaction.state

        values = {
            'last_manual_retry_at': fields.Datetime.now(),
            'manual_retry_count': self.manual_retry_count + 1,
            'note': note,
        }
        if payment_attempt:
            values['payment_attempt_id'] = payment_attempt.id
        self.write(values)
        return self.action_open_payment_attempt() if payment_attempt else False

    def _retry_payment(self, source='manual', requested_by=None):
        self.ensure_one()
        previous_attempt = self.env['subscription.payment.attempt'].search(
            [
                ('subscription_id', '=', self.subscription_id.id),
                ('invoice_id', '=', self.invoice_id.id),
            ],
            order='attempt_date desc, id desc',
            limit=1,
        )
        transaction = self.subscription_id._auto_collect_payment(
            self.invoice_id,
            source=source,
            requested_by=requested_by,
        )
        payment_attempt = self.env['subscription.payment.attempt'].search(
            [
                ('subscription_id', '=', self.subscription_id.id),
                ('invoice_id', '=', self.invoice_id.id),
            ],
            order='attempt_date desc, id desc',
            limit=1,
        )
        if payment_attempt == previous_attempt:
            payment_attempt = False
        return payment_attempt, transaction

    def _check_retry_allowed(self, manual=False):
        self.ensure_one()
        if self.action_type in ('final_cancel', 'final_pause', 'final_none'):
            raise UserError(_('Final dunning actions cannot be retried.'))
        if not self.invoice_id:
            raise UserError(_('A dunning attempt needs an invoice before payment can be retried.'))
        if self.invoice_id.payment_state not in ('not_paid', 'partial'):
            raise UserError(_('Only unpaid or partially paid invoices can be retried.'))
        if not self.subscription_id.payment_token_id:
            raise UserError(_('The subscription does not have a saved payment method.'))
        if not manual and self.retry_exhausted:
            raise UserError(_('Automatic retries are exhausted for this dunning attempt.'))
        if not manual and self.auto_retry_count >= self.max_auto_retries:
            raise UserError(_('The maximum automatic retry count has been reached.'))
        return True

    @api.model
    def _cron_retry_dunning_attempts(self, limit=50):
        now = fields.Datetime.now()
        attempts = self.search([
            ('auto_retry_enabled', '=', True),
            ('retry_exhausted', '=', False),
            ('next_auto_retry_at', '!=', False),
            ('next_auto_retry_at', '<=', now),
            ('action_type', '=', 'email_and_retry'),
            ('state', 'in', ['done', 'sent']),
        ], order='next_auto_retry_at asc, id asc', limit=limit)
        for attempt in attempts:
            attempt._run_auto_retry()
        return True

    def _run_auto_retry(self):
        self.ensure_one()
        try:
            self._check_retry_allowed(manual=False)
        except UserError as error:
            self.write({
                'retry_exhausted': True,
                'next_auto_retry_at': False,
                'note': str(error),
            })
            return False

        payment_attempt, transaction = self._retry_payment(source='cron')
        retry_count = self.auto_retry_count + 1
        values = {
            'auto_retry_count': retry_count,
            'last_auto_retry_at': fields.Datetime.now(),
            'next_auto_retry_at': False,
            'note': _('Automatic payment retry executed.'),
        }
        if payment_attempt:
            values['payment_attempt_id'] = payment_attempt.id
        if transaction and transaction.state == 'done':
            values['note'] = _('Automatic payment retry recovered the subscription.')
            values['retry_exhausted'] = False
        elif retry_count >= self.max_auto_retries:
            values['retry_exhausted'] = True
            values['note'] = _('Automatic payment retries are exhausted.')
        else:
            delay = self.policy_line_id.retry_delay_hours if self.policy_line_id else 1
            values['next_auto_retry_at'] = fields.Datetime.add(fields.Datetime.now(), hours=delay)
        self.write(values)
        return True

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('subscription.dunning.attempt') or _('New')
        return super().create(vals_list)

    def mark_done(self, note=False, state='done'):
        values = {
            'state': state,
            'completed_at': fields.Datetime.now(),
        }
        if note:
            values['note'] = note
        self.write(values)

    def mark_failed(self, error):
        self.write({
            'state': 'failed',
            'completed_at': fields.Datetime.now(),
            'error_message': str(error),
        })
        self.message_post(body=_('Dunning attempt failed: %s') % str(error))
