from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class DunningPolicyLine(models.Model):
    _name = 'subscription.dunning.policy.line'
    _description = 'Subscription Dunning Policy Step'
    _order = 'delay_days'

    name = fields.Char(string='Name', compute='_compute_name')

    policy_id = fields.Many2one('subscription.dunning.policy', required=True, ondelete='cascade')
    delay_days = fields.Integer(string='Days After Failure', required=True,
        help='Number of days after payment failure to execute this step.')
    
    email_template_id = fields.Many2one('mail.template', string='Email Template',
        domain="[('model', '=', 'sale.order')]")
        
    action_type = fields.Selection([
        ('email', 'Send Email'),
        ('email_and_retry', 'Send Email & Retry Payment'),
    ], string='Action', default='email', required=True)
    retry_delay_hours = fields.Integer(
        string='Retry Delay (Hours)',
        default=1,
        help='Hours to wait after sending the dunning step before the automatic retry runs.',
    )
    max_auto_retries = fields.Integer(
        string='Max Auto Retries',
        default=1,
        help='Maximum automatic payment retries for attempts created from this step.',
    )

    @api.depends('delay_days', 'action_type')
    def _compute_name(self):
        for line in self:
            line.name = 'Day %s: %s' % (line.delay_days, dict(line._fields['action_type'].selection).get(line.action_type, ''))

    @api.constrains('action_type', 'email_template_id')
    def _check_email_template(self):
        for line in self:
            if line.action_type in ('email', 'email_and_retry') and not line.email_template_id:
                raise ValidationError(_('Email template is required when the dunning step sends an email.'))

    @api.constrains('retry_delay_hours', 'max_auto_retries')
    def _check_retry_settings(self):
        for line in self:
            if line.retry_delay_hours < 0:
                raise ValidationError(_('Retry delay cannot be negative.'))
            if line.max_auto_retries < 0:
                raise ValidationError(_('Max auto retries cannot be negative.'))
