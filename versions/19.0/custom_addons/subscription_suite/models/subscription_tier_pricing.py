from odoo import _, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare, float_is_zero


class SubscriptionTierPricing(models.AbstractModel):
    _name = 'subscription.tier.pricing'
    _description = 'Subscription Tier Pricing Helper'

    def _tier_precision_rounding(self, uom=None):
        return (uom and uom.rounding) or 0.01

    def _currency_compare(self, currency, amount, compare_to=0.0):
        if currency:
            return currency.compare_amounts(amount, compare_to)
        return float_compare(amount, compare_to, precision_rounding=0.01)

    def _validate_tier_rows(self, pricing_model, tiers, currency=None, uom=None):
        if pricing_model == 'flat':
            return True

        precision_rounding = self._tier_precision_rounding(uom)
        sorted_tiers = tiers.sorted(lambda tier: (tier.sequence, tier.min_quantity, tier.id))
        if not sorted_tiers:
            raise ValidationError(_('Add pricing tiers before enabling tiered pricing.'))

        expected_min = 1.0
        for index, tier in enumerate(sorted_tiers):
            if float_compare(tier.min_quantity, 0.0, precision_rounding=precision_rounding) <= 0:
                raise ValidationError(_('Tier minimum quantity must be positive.'))
            if float_compare(tier.min_quantity, expected_min, precision_rounding=precision_rounding) != 0:
                raise ValidationError(_('Tier ranges must be continuous without gaps or overlaps.'))
            if self._currency_compare(currency, tier.price_unit, 0.0) <= 0:
                raise ValidationError(_('Tier unit price must be positive.'))

            is_last = index == len(sorted_tiers) - 1
            if tier.max_quantity:
                if float_compare(tier.max_quantity, tier.min_quantity, precision_rounding=precision_rounding) <= 0:
                    raise ValidationError(_('Tier maximum quantity must be greater than the minimum quantity.'))
                if is_last:
                    raise ValidationError(_('The final tier must be open-ended.'))
                expected_min = tier.max_quantity
            elif not is_last:
                raise ValidationError(_('Only the final tier can be open-ended.'))
        return True

    def _get_matching_volume_tier(self, quantity, tiers, uom=None):
        precision_rounding = self._tier_precision_rounding(uom)
        for tier in tiers.sorted(lambda tier: (tier.sequence, tier.min_quantity, tier.id)):
            if float_compare(quantity, tier.min_quantity, precision_rounding=precision_rounding) < 0:
                continue
            if not tier.max_quantity or float_compare(quantity, tier.max_quantity, precision_rounding=precision_rounding) <= 0:
                return tier
        return tiers[-1:] if tiers else self.env[tiers._name]

    def _compute_tier_total(self, quantity, pricing_model, tiers, base_price_unit=0.0, currency=None, uom=None):
        precision_rounding = self._tier_precision_rounding(uom)
        if float_compare(quantity, 0.0, precision_rounding=precision_rounding) <= 0:
            return 0.0
        if pricing_model == 'flat':
            return quantity * (base_price_unit or 0.0)

        self._validate_tier_rows(pricing_model, tiers, currency=currency, uom=uom)
        if pricing_model == 'volume':
            tier = self._get_matching_volume_tier(quantity, tiers, uom=uom)
            return quantity * (tier.price_unit if tier else 0.0)

        total = 0.0
        lower_boundary = 0.0
        for tier in tiers.sorted(lambda item: (item.sequence, item.min_quantity, item.id)):
            upper_boundary = tier.max_quantity or quantity
            bracket_upper = min(quantity, upper_boundary)
            bracket_quantity = bracket_upper - lower_boundary
            if float_compare(bracket_quantity, 0.0, precision_rounding=precision_rounding) > 0:
                total += bracket_quantity * tier.price_unit
            lower_boundary = upper_boundary
            if float_compare(quantity, upper_boundary, precision_rounding=precision_rounding) <= 0:
                break
        return total

    def _compute_effective_price_unit(self, quantity, pricing_model, tiers, base_price_unit=0.0, currency=None, uom=None):
        precision_rounding = self._tier_precision_rounding(uom)
        if float_is_zero(quantity, precision_rounding=precision_rounding):
            return base_price_unit or 0.0
        total = self._compute_tier_total(
            quantity,
            pricing_model,
            tiers,
            base_price_unit=base_price_unit,
            currency=currency,
            uom=uom,
        )
        return total / quantity
