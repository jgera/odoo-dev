from odoo import fields, models


class SubscriptionUsageSummary(models.Model):
    _name = 'subscription.usage.summary'
    _description = 'Subscription Usage Summary'
    _order = 'period_end desc, id desc'

    subscription_id = fields.Many2one(
        'sale.order',
        string='Subscription',
        required=True,
        ondelete='cascade',
        domain=[('is_subscription', '=', True)],
    )
    meter_id = fields.Many2one('subscription.usage.meter', string='Meter', required=True)
    period_start = fields.Date(required=True)
    period_end = fields.Date(required=True)
    included_quantity = fields.Float(readonly=True)
    used_quantity = fields.Float(readonly=True)
    billable_quantity = fields.Float(readonly=True)
    overage_product_id = fields.Many2one('product.product', string='Overage Product', readonly=True)
    overage_price_unit = fields.Monetary(string='Overage Unit Price', readonly=True)
    amount = fields.Monetary(readonly=True)
    invoice_id = fields.Many2one('account.move', string='Invoice', readonly=True, copy=False)
    invoice_line_id = fields.Many2one('account.move.line', string='Invoice Line', readonly=True, copy=False)
    event_ids = fields.One2many('subscription.usage.event', 'summary_id', string='Usage Events', readonly=True)
    currency_id = fields.Many2one('res.currency', related='subscription_id.currency_id', store=True)
    company_id = fields.Many2one('res.company', related='subscription_id.company_id', store=True)

    _summary_unique = models.Constraint(
        'UNIQUE(subscription_id, meter_id, period_start, period_end)',
        'Usage summary already exists for this subscription, meter, and billing period.',
    )
