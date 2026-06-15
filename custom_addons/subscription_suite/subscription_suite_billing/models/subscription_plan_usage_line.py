from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


class SubscriptionPlanUsageLine(models.Model):
    _name = 'subscription.plan.usage.line'
    _description = 'Subscription Plan Usage Rule'
    _order = 'sequence, id'

    plan_id = fields.Many2one('subscription.plan', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    meter_id = fields.Many2one('subscription.usage.meter', string='Meter', required=True)
    included_quantity = fields.Float(string='Included Quantity', default=0.0)
    overage_product_id = fields.Many2one(
        'product.product',
        string='Overage Product',
        required=True,
        domain=[('type', '=', 'service')],
    )
    overage_price_unit = fields.Monetary(string='Overage Unit Price', required=True)
    currency_id = fields.Many2one('res.currency', related='plan_id.currency_id', store=True)
    company_id = fields.Many2one('res.company', related='plan_id.company_id', store=True)

    _meter_plan_unique = models.Constraint(
        'UNIQUE(plan_id, meter_id)',
        'Each usage meter can only be configured once per subscription plan.',
    )

    @api.constrains('included_quantity', 'overage_price_unit', 'meter_id')
    def _check_usage_rule_values(self):
        for line in self:
            precision_rounding = (line.meter_id.uom_id.rounding or 0.01) if line.meter_id else 0.01
            if float_compare(line.included_quantity, 0.0, precision_rounding=precision_rounding) < 0:
                raise ValidationError(_('Included usage quantity cannot be negative.'))
            currency = line.currency_id or line.company_id.currency_id or self.env.company.currency_id
            if currency.compare_amounts(line.overage_price_unit, 0.0) <= 0:
                raise ValidationError(_('Overage unit price must be positive.'))
