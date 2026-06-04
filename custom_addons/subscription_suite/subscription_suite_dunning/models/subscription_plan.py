from odoo import models, fields

class SubscriptionPlan(models.Model):
    _inherit = 'subscription.plan'

    dunning_policy_id = fields.Many2one('subscription.dunning.policy', string='Dunning Policy')
