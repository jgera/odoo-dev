from odoo import api, fields, models


class SubscriptionPlanLineTier(models.Model):
    _name = 'subscription.plan.line.tier'
    _description = 'Subscription Plan Line Pricing Tier'
    _order = 'sequence, min_quantity, id'

    plan_line_id = fields.Many2one(
        'subscription.plan.line',
        string='Plan Line',
        required=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(string='Sequence', default=10)
    min_quantity = fields.Float(string='Minimum Quantity', required=True, default=1.0)
    max_quantity = fields.Float(string='Maximum Quantity')
    price_unit = fields.Monetary(string='Tier Unit Price', required=True)
    currency_id = fields.Many2one('res.currency', related='plan_line_id.currency_id', store=True)
    company_id = fields.Many2one('res.company', related='plan_line_id.company_id', store=True)

    @api.constrains('min_quantity', 'max_quantity', 'price_unit', 'sequence')
    def _check_parent_pricing_tiers(self):
        self.mapped('plan_line_id')._check_subscription_pricing_tiers()
