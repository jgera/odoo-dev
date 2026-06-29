from odoo import api, models, fields, _
from odoo.exceptions import ValidationError
from odoo.tools import float_compare

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    is_recurring = fields.Boolean(string='Is Recurring', default=False)
    subscription_import_reference = fields.Char(
        string='Subscription Line Import Reference',
        copy=False,
        index=True,
    )
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
    subscription_base_discount = fields.Float(
        string='Base Subscription Discount (%)',
        default=0.0,
        copy=True,
        help="Permanent recurring discount copied from the subscription plan line.",
    )
    subscription_promo_discount = fields.Float(string='Promotional Discount (%)', default=0.0, copy=True)
    subscription_promo_discount_start_date = fields.Date(string='Promo Start Date', copy=True)
    subscription_promo_discount_end_date = fields.Date(string='Promo End Date', copy=True)
    subscription_promo_discount_state = fields.Selection([
        ('inactive', 'Inactive'),
        ('active', 'Active'),
        ('expired', 'Expired'),
    ], string='Promo Discount Status', default='inactive', copy=False, readonly=True)

    _subscription_line_import_reference_unique = models.Constraint(
        'UNIQUE(order_id, subscription_import_reference)',
        'Subscription line import reference must be unique per order.',
    )

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

    @api.constrains(
        'subscription_base_discount',
        'subscription_promo_discount',
        'subscription_promo_discount_start_date',
        'subscription_promo_discount_end_date',
    )
    def _check_subscription_discount_metadata(self):
        for line in self:
            for field_name in ('subscription_base_discount', 'subscription_promo_discount'):
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

    def _has_subscription_discount_metadata(self):
        self.ensure_one()
        return bool(
            self.subscription_base_discount
            or self.subscription_promo_discount
            or self.subscription_promo_discount_start_date
            or self.subscription_promo_discount_end_date
        )

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

    def _get_subscription_effective_discount(self, on_date=None):
        self.ensure_one()
        if not self._has_subscription_discount_metadata():
            return self.discount or 0.0
        base_discount = self.subscription_base_discount or 0.0
        if self._get_promotional_discount_state(on_date=on_date) != 'active':
            return base_discount
        promo_discount = self.subscription_promo_discount or 0.0
        return 100.0 * (1.0 - ((1.0 - base_discount / 100.0) * (1.0 - promo_discount / 100.0)))

    def _refresh_subscription_effective_discount(self, on_date=None):
        self.ensure_one()
        if not self._has_subscription_discount_metadata():
            return False
        old_discount = self.discount or 0.0
        old_state = self.subscription_promo_discount_state or 'inactive'
        new_state = self._get_promotional_discount_state(on_date=on_date)
        new_discount = self._get_subscription_effective_discount(on_date=on_date)
        if old_state == new_state and float_compare(old_discount, new_discount, precision_digits=6) == 0:
            return False
        self.write({
            'discount': new_discount,
            'subscription_promo_discount_state': new_state,
        })
        return {
            'old_discount': old_discount,
            'new_discount': new_discount,
            'old_state': old_state,
            'new_state': new_state,
        }

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

    def _copy_subscription_discount_values(self):
        self.ensure_one()
        return {
            'subscription_base_discount': self.subscription_base_discount,
            'subscription_promo_discount': self.subscription_promo_discount,
            'subscription_promo_discount_start_date': self.subscription_promo_discount_start_date,
            'subscription_promo_discount_end_date': self.subscription_promo_discount_end_date,
            'subscription_promo_discount_state': self._get_promotional_discount_state(),
        }
