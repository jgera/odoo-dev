from odoo import models, fields, api

class ResPartner(models.Model):
    _inherit = 'res.partner'

    subscription_count = fields.Integer(string='Subscription Count', compute='_compute_subscription_metrics')
    active_subscription_count = fields.Integer(string='Active Subscriptions', compute='_compute_subscription_metrics')
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')
    total_mrr = fields.Monetary(string='Total MRR', compute='_compute_subscription_metrics')
    subscription_ids = fields.One2many('sale.order', 'partner_id', domain=[('is_subscription', '=', True)], string='Subscriptions')
    is_subscriber = fields.Boolean(string='Is Subscriber', compute='_compute_subscription_metrics')

    def _compute_subscription_metrics(self):
        for partner in self:
            subs = self.env['sale.order'].search([
                ('partner_id', '=', partner.id),
                ('is_subscription', '=', True)
            ])
            partner.subscription_count = len(subs)
            active_subs = subs.filtered(lambda s: s.subscription_state in ['active', 'paused', 'past_due'])
            partner.active_subscription_count = len(active_subs)
            partner.total_mrr = sum(active_subs.mapped('mrr'))
            partner.is_subscriber = partner.active_subscription_count > 0
