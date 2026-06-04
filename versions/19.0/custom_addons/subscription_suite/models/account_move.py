from odoo import models, fields, api

class AccountMove(models.Model):
    _inherit = 'account.move'

    subscription_id = fields.Many2one('sale.order', string='Subscription', domain=[('is_subscription', '=', True)])
    is_subscription_invoice = fields.Boolean(string='Is Subscription Invoice', compute='_compute_is_subscription_invoice')
    subscription_period_start = fields.Date(string='Subscription Period Start')
    subscription_period_end = fields.Date(string='Subscription Period End')

    @api.depends('subscription_id')
    def _compute_is_subscription_invoice(self):
        for move in self:
            move.is_subscription_invoice = bool(move.subscription_id)
