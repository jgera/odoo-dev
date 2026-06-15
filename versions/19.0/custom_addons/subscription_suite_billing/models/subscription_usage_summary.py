from odoo import _, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


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

    def _get_usage_rule(self):
        self.ensure_one()
        return self.subscription_id.subscription_plan_id.usage_line_ids.filtered(
            lambda line: line.meter_id == self.meter_id
        )[:1]

    def _recompute_values_from_events(self):
        self.ensure_one()
        usage_rule = self._get_usage_rule()
        included_quantity = usage_rule.included_quantity if usage_rule else self.included_quantity
        overage_product = usage_rule.overage_product_id if usage_rule else self.overage_product_id
        overage_price_unit = usage_rule.overage_price_unit if usage_rule else self.overage_price_unit
        events = self.env['subscription.usage.event'].search([
            ('subscription_id', '=', self.subscription_id.id),
            ('meter_id', '=', self.meter_id.id),
            ('state', '=', 'ready'),
            ('event_date', '>=', self.period_start),
            ('event_date', '<', self.period_end),
        ])
        if not events:
            return False, events

        used_quantity = sum(events.mapped('quantity'))
        precision_rounding = self.meter_id.uom_id.rounding or 0.01
        billable_quantity = 0.0
        if float_compare(used_quantity, included_quantity, precision_rounding=precision_rounding) > 0:
            billable_quantity = used_quantity - included_quantity
        return {
            'included_quantity': included_quantity,
            'used_quantity': used_quantity,
            'billable_quantity': billable_quantity,
            'overage_product_id': overage_product.id,
            'overage_price_unit': overage_price_unit,
            'amount': billable_quantity * overage_price_unit,
        }, events

    def action_recompute_usage(self):
        for summary in self:
            if summary.invoice_id:
                raise ValidationError(_('Invoiced usage summaries cannot be recomputed.'))
            values, events = summary._recompute_values_from_events()
            if not values:
                summary.event_ids.filtered(lambda event: event.state != 'invoiced').write({'summary_id': False})
                summary.sudo().unlink()
                continue
            old_events = summary.event_ids.filtered(lambda event: event.id not in events.ids and event.state != 'invoiced')
            if old_events:
                old_events.write({'summary_id': False})
            summary.write(values)
            events.filtered(lambda event: event.summary_id.id != summary.id).write({'summary_id': summary.id})
        return True
