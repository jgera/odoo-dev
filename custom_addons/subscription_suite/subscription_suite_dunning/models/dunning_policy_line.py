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

    @api.depends('delay_days', 'action_type')
    def _compute_name(self):
        for line in self:
            line.name = 'Day %s: %s' % (line.delay_days, dict(line._fields['action_type'].selection).get(line.action_type, ''))

    @api.constrains('action_type', 'email_template_id')
    def _check_email_template(self):
        for line in self:
            if line.action_type == 'email' and not line.email_template_id:
                raise ValidationError(_('Email template is required when action type is Email.'))
