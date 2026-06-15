from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.tools import float_compare

class SubscriptionPlanLine(models.Model):
    _name = 'subscription.plan.line'
    _description = 'Subscription Plan Line'
    _order = 'sequence, id'

    plan_id = fields.Many2one('subscription.plan', string='Plan', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    subscription_component_type = fields.Selection([
        ('base', 'Base'),
        ('seat', 'Seat'),
        ('addon', 'Add-on'),
    ], string='Component Type', default='base', required=True)
    product_id = fields.Many2one('product.product', string='Product', required=True, domain=[('type', '=', 'service')])
    quantity = fields.Float(string='Quantity', default=1.0, required=True)
    uom_id = fields.Many2one('uom.uom', related='product_id.uom_id', string='Unit of Measure')
    price_unit = fields.Monetary(string='Unit Price', help="Leave empty to use product price")
    subscription_pricing_model = fields.Selection([
        ('flat', 'Flat'),
        ('volume', 'Volume'),
        ('graduated', 'Graduated'),
    ], string='Pricing Model', default='flat', required=True)
    tier_ids = fields.One2many(
        'subscription.plan.line.tier',
        'plan_line_id',
        string='Pricing Tiers',
        copy=True,
    )
    discount = fields.Float(string='Discount (%)', default=0.0)
    subscription_promo_discount = fields.Float(string='Promotional Discount (%)', default=0.0)
    subscription_promo_discount_start_date = fields.Date(string='Promo Start Date')
    subscription_promo_discount_end_date = fields.Date(string='Promo End Date')
    description = fields.Text(string='Description', translate=True)
    
    currency_id = fields.Many2one('res.currency', related='plan_id.currency_id')
    company_id = fields.Many2one('res.company', related='plan_id.company_id')

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.description = self.product_id.get_product_multiline_description_sale()
            if not self.price_unit:
                self.price_unit = self.product_id.list_price

    @api.constrains(
        'subscription_pricing_model',
        'tier_ids',
    )
    def _check_subscription_pricing_tiers(self):
        pricing = self.env['subscription.tier.pricing']
        for line in self:
            pricing._validate_tier_rows(
                line.subscription_pricing_model,
                line.tier_ids,
                currency=line.currency_id,
                uom=line.uom_id,
            )

    @api.constrains(
        'discount',
        'subscription_promo_discount',
        'subscription_promo_discount_start_date',
        'subscription_promo_discount_end_date',
    )
    def _check_subscription_discounts(self):
        for line in self:
            for field_name in ('discount', 'subscription_promo_discount'):
                value = line[field_name] or 0.0
                if (
                    float_compare(value, 0.0, precision_digits=6) < 0
                    or float_compare(value, 100.0, precision_digits=6) > 0
                ):
                    raise ValidationError(_("Subscription discounts must be between 0 and 100 percent."))
            if (
                line.subscription_promo_discount_start_date
                and line.subscription_promo_discount_end_date
                and line.subscription_promo_discount_end_date <= line.subscription_promo_discount_start_date
            ):
                raise ValidationError(_("Promotional discount end date must be after the start date."))

    def _get_subscription_line_total(self, quantity=None):
        self.ensure_one()
        quantity = self.quantity if quantity is None else quantity
        return self.env['subscription.tier.pricing']._compute_tier_total(
            quantity,
            self.subscription_pricing_model,
            self.tier_ids,
            base_price_unit=self.price_unit,
            currency=self.currency_id,
            uom=self.uom_id,
        )

    def _get_effective_price_unit(self, quantity=None):
        self.ensure_one()
        quantity = self.quantity if quantity is None else quantity
        return self.env['subscription.tier.pricing']._compute_effective_price_unit(
            quantity,
            self.subscription_pricing_model,
            self.tier_ids,
            base_price_unit=self.price_unit,
            currency=self.currency_id,
            uom=self.uom_id,
        )

    def _copy_tier_commands(self):
        self.ensure_one()
        return [
            (0, 0, {
                'sequence': tier.sequence,
                'min_quantity': tier.min_quantity,
                'max_quantity': tier.max_quantity,
                'price_unit': tier.price_unit,
            })
            for tier in self.tier_ids
        ]

    def _get_promotional_discount_state(self, on_date=None):
        self.ensure_one()
        on_date = on_date or fields.Date.context_today(self)
        if not self.subscription_promo_discount:
            return 'inactive'
        if self.subscription_promo_discount_start_date and on_date < self.subscription_promo_discount_start_date:
            return 'inactive'
        if self.subscription_promo_discount_end_date and on_date > self.subscription_promo_discount_end_date:
            return 'expired'
        return 'active'

    def _get_effective_discount(self, on_date=None):
        self.ensure_one()
        base_discount = self.discount or 0.0
        if self._get_promotional_discount_state(on_date=on_date) != 'active':
            return base_discount
        promo_discount = self.subscription_promo_discount or 0.0
        return 100.0 * (1.0 - ((1.0 - base_discount / 100.0) * (1.0 - promo_discount / 100.0)))

    def _prepare_sale_order_line_values(self, plan):
        self.ensure_one()
        return {
            'product_id': self.product_id.id,
            'name': self.description or self.product_id.get_product_multiline_description_sale(),
            'product_uom_qty': self.quantity,
            'price_unit': self._get_effective_price_unit(self.quantity),
            'discount': self._get_effective_discount(),
            'is_recurring': True,
            'subscription_component_type': self.subscription_component_type,
            'subscription_pricing_model': self.subscription_pricing_model,
            'subscription_tier_ids': self._copy_tier_commands(),
            'subscription_base_discount': self.discount,
            'subscription_promo_discount': self.subscription_promo_discount,
            'subscription_promo_discount_start_date': self.subscription_promo_discount_start_date,
            'subscription_promo_discount_end_date': self.subscription_promo_discount_end_date,
            'subscription_promo_discount_state': self._get_promotional_discount_state(),
            'recurring_interval_count': plan.billing_interval_count,
            'recurring_interval_unit': plan.billing_interval_unit,
        }
