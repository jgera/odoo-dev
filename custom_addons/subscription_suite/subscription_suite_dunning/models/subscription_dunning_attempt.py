from odoo import _, api, fields, models


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
    partner_id = fields.Many2one(related='subscription_id.partner_id', string='Customer', store=True, readonly=True)
    company_id = fields.Many2one(related='subscription_id.company_id', string='Company', store=True, readonly=True)
    currency_id = fields.Many2one(related='subscription_id.currency_id', string='Currency', store=True, readonly=True)
    invoice_id = fields.Many2one('account.move', string='Invoice', readonly=True, index=True)
    policy_id = fields.Many2one('subscription.dunning.policy', string='Policy', readonly=True, index=True)
    policy_line_id = fields.Many2one('subscription.dunning.policy.line', string='Policy Step', readonly=True, index=True)
    email_template_id = fields.Many2one('mail.template', string='Email Template', readonly=True)
    mail_mail_id = fields.Many2one('mail.mail', string='Email', readonly=True)
    payment_attempt_id = fields.Many2one('subscription.payment.attempt', string='Payment Attempt', readonly=True)
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
