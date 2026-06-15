from odoo import api, models, fields

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    is_recurring = fields.Boolean(string='Is Recurring', default=False)
    subscription_component_type = fields.Selection([
        ('base', 'Base'),
        ('seat', 'Seat'),
        ('addon', 'Add-on'),
    ], string='Subscription Component', default='base', required=True)
    subscription_pricing_model = fields.Selection([
        ('flat', 'Flat'),
        ('volume', 'Volume'),
        ('graduated', 'Graduated'),
    ], string='Subscription Pricing', default='flat', required=True)
    subscription_tier_ids = fields.One2many(
        'subscription.sale.order.line.tier',
        'order_line_id',
        string='Subscription Pricing Tiers',
        copy=True,
    )
    recurring_interval_count = fields.Integer(string='Recurring Interval Count')
    recurring_interval_unit = fields.Selection([
        ('day', 'Days'),
        ('week', 'Weeks'),
        ('month', 'Months'),
        ('year', 'Years')
    ], string='Recurring Interval Unit')

    @api.constrains(
        'subscription_pricing_model',
        'subscription_tier_ids',
    )
    def _check_subscription_pricing_tiers(self):
        pricing = self.env['subscription.tier.pricing']
        for line in self:
            pricing._validate_tier_rows(
                line.subscription_pricing_model,
                line.subscription_tier_ids,
                currency=line.currency_id,
                uom=line.product_uom_id or line.product_id.uom_id,
            )

    def _get_subscription_line_total(self, quantity=None):
        self.ensure_one()
        quantity = self.product_uom_qty if quantity is None else quantity
        return self.env['subscription.tier.pricing']._compute_tier_total(
            quantity,
            self.subscription_pricing_model,
            self.subscription_tier_ids,
            base_price_unit=self.price_unit,
            currency=self.currency_id,
            uom=self.product_uom_id or self.product_id.uom_id,
        )

    def _get_effective_price_unit(self, quantity=None):
        self.ensure_one()
        quantity = self.product_uom_qty if quantity is None else quantity
        return self.env['subscription.tier.pricing']._compute_effective_price_unit(
            quantity,
            self.subscription_pricing_model,
            self.subscription_tier_ids,
            base_price_unit=self.price_unit,
            currency=self.currency_id,
            uom=self.product_uom_id or self.product_id.uom_id,
        )

    def _get_subscription_discounted_total(self, quantity=None):
        self.ensure_one()
        amount = self._get_subscription_line_total(quantity=quantity)
        return amount * (1 - (self.discount or 0.0) / 100.0)

    def _copy_subscription_tier_commands(self):
        self.ensure_one()
        return [
            (0, 0, {
                'sequence': tier.sequence,
                'min_quantity': tier.min_quantity,
                'max_quantity': tier.max_quantity,
                'price_unit': tier.price_unit,
            })
            for tier in self.subscription_tier_ids
        ]
