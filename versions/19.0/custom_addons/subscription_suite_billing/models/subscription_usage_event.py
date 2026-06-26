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
        index=True,
    )
    meter_id = fields.Many2one('subscription.usage.meter', string='Meter', required=True, index=True)
    quantity = fields.Float(required=True)
    event_date = fields.Date(required=True, default=fields.Date.context_today, index=True)
    external_reference = fields.Char(copy=False, index=True)
    state = fields.Selection([
        ('ready', 'Ready'),
        ('invoiced', 'Invoiced'),
        ('cancelled', 'Cancelled'),
    ], default='ready', required=True, copy=False, index=True)
    summary_id = fields.Many2one('subscription.usage.summary', string='Usage Summary', copy=False, readonly=True, index=True)
    company_id = fields.Many2one('res.company', related='subscription_id.company_id', store=True, index=True)

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

    def _check_mutable(self, vals):
        if 'state' in vals and not self.env.context.get('allow_usage_state_change'):
            raise ValidationError(_('Use the usage event actions to change status.'))
        protected_fields = {
            'subscription_id',
            'meter_id',
            'quantity',
            'event_date',
            'external_reference',
        }
        if protected_fields.intersection(vals):
            locked = self.filtered(lambda event: event.state in ('invoiced', 'cancelled'))
            if locked:
                raise ValidationError(_('Invoiced or cancelled usage events cannot be edited.'))

    def write(self, vals):
        self._check_mutable(vals)
        return super().write(vals)

    def unlink(self):
        locked = self.filtered(lambda event: event.state in ('invoiced', 'cancelled'))
        if locked:
            raise ValidationError(_('Invoiced or cancelled usage events cannot be deleted.'))
        return super().unlink()

    def action_cancel_event(self):
        for event in self:
            if event.state != 'ready':
                raise ValidationError(_('Only ready usage events can be cancelled.'))
            summary = event.summary_id
            event.with_context(allow_usage_state_change=True).write({
                'state': 'cancelled',
                'summary_id': False,
            })
            if summary and not summary.invoice_id:
                summary.action_recompute_usage()
        return True
