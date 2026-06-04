from odoo import models, fields

class DunningPolicy(models.Model):
    _name = 'subscription.dunning.policy'
    _description = 'Subscription Dunning Policy'

    name = fields.Char(string='Name', required=True, translate=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    
    grace_period_days = fields.Integer(string='Grace Period (Days)', default=1, 
        help='Number of days after payment failure before dunning starts.')
    
    line_ids = fields.One2many('subscription.dunning.policy.line', 'policy_id', string='Dunning Steps')
    
    final_action = fields.Selection([
        ('cancel', 'Cancel Subscription'),
        ('pause', 'Pause Subscription'),
        ('none', 'Do Nothing (Leave Past Due)')
    ], string='Final Action', required=True, default='cancel',
    help='Action to take if all dunning steps are completed and payment is still not received.')
    
    final_action_delay = fields.Integer(string='Final Action Delay (Days)', default=3,
        help='Number of days after the last dunning step before taking the final action.')
