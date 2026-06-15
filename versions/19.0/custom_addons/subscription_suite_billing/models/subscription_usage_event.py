from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


class SubscriptionUsageEvent(models.Model):
    _name = 'subscription.usage.event'
    _description = 'Subscription Usage Event'
    _order = 'event_date desc, id desc'

    subscription_id = fields.Many2one(
        'sale.order',
        string='Subscription',
        required=True,
        ondelete='cascade',
        domain=[('is_subscription', '=', True)],
    )
    meter_id = fields.Many2one('subscription.usage.meter', string='Meter', required=True)
    quantity = fields.Float(required=True)
    event_date = fields.Date(required=True, default=fields.Date.context_today)
    external_reference = fields.Char(copy=False)
    state = fields.Selection([
        ('ready', 'Ready'),
        ('invoiced', 'Invoiced'),
    ], default='ready', required=True, copy=False)
    summary_id = fields.Many2one('subscription.usage.summary', string='Usage Summary', copy=False, readonly=True)
    company_id = fields.Many2one('res.company', related='subscription_id.company_id', store=True)

    _external_reference_unique = models.Constraint(
        'UNIQUE(external_reference, company_id)',
        'Usage event external reference must be unique per company.',
    )

    @api.constrains('quantity', 'meter_id')
    def _check_quantity(self):
        for event in self:
            precision_rounding = (event.meter_id.uom_id.rounding or 0.01) if event.meter_id else 0.01
            if float_compare(event.quantity, 0.0, precision_rounding=precision_rounding) <= 0:
                raise ValidationError(_('Usage quantity must be positive.'))
