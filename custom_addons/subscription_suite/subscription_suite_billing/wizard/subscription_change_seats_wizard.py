from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SubscriptionChangeSeatsWizard(models.TransientModel):
    _name = 'subscription.change.seats.wizard'
    _description = 'Change Subscription Seats'

    subscription_id = fields.Many2one('sale.order', string='Subscription', required=True, readonly=True)
    current_seat_quantity = fields.Float(string='Current Seats', readonly=True)
    new_seat_quantity = fields.Float(string='New Seats', required=True)
    effective_date = fields.Date(string='Effective Date', default=fields.Date.today, required=True)
    current_mrr = fields.Monetary(string='Current MRR', currency_field='currency_id', compute='_compute_impact')
    new_mrr = fields.Monetary(string='New MRR', currency_field='currency_id', compute='_compute_impact')
    net_amount = fields.Monetary(string='Net Amount', currency_field='currency_id', compute='_compute_impact')
    proration_preview = fields.Html(string='Proration Summary', compute='_compute_impact')
    currency_id = fields.Many2one('res.currency', related='subscription_id.currency_id')

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        subscription = self.env['sale.order'].browse(values.get('subscription_id'))
        if subscription:
            seat_line = subscription._check_seat_change_allowed()
            values['current_seat_quantity'] = seat_line.product_uom_qty
            values['new_seat_quantity'] = seat_line.product_uom_qty
        return values

    @api.constrains('new_seat_quantity')
    def _check_new_seat_quantity(self):
        for wizard in self:
            if wizard.new_seat_quantity < 1:
                raise ValidationError(_("Seat quantity must be at least 1."))

    @api.depends('subscription_id', 'new_seat_quantity', 'effective_date')
    def _compute_impact(self):
        for wizard in self:
            wizard.new_mrr = 0.0
            wizard.current_mrr = 0.0
            wizard.net_amount = 0.0
            wizard.proration_preview = ""
            if not wizard.subscription_id or not wizard.new_seat_quantity:
                continue

            seat_line = wizard.subscription_id._get_single_seat_line()
            current_mrr = wizard.subscription_id.mrr
            new_mrr = wizard.subscription_id._get_mrr_after_seat_change(seat_line, wizard.new_seat_quantity)
            period_start = (
                wizard.subscription_id.current_period_start
                or wizard.subscription_id.last_invoice_date
                or wizard.subscription_id.subscription_start_date
                or wizard.effective_date
            )
            period_end = (
                wizard.subscription_id.current_period_end
                or wizard.subscription_id.next_invoice_date
                or wizard.subscription_id.subscription_plan_id.get_next_invoice_date(period_start)
            )
            effective_date = wizard.effective_date or fields.Date.today()
            total_days = (period_end - period_start).days or 1
            used_days = max(0, (effective_date - period_start).days)
            remaining_days = max(0, total_days - used_days)
            net_amount = remaining_days * ((new_mrr / 30.0) - (current_mrr / 30.0))
            symbol = wizard.currency_id.symbol or '$'

            wizard.current_mrr = current_mrr
            wizard.new_mrr = new_mrr
            wizard.net_amount = net_amount
            if wizard.subscription_id._compare_mrr(new_mrr, current_mrr) >= 0:
                wizard.proration_preview = _(
                    "<p>Seats will increase from <b>%(old_qty)s</b> to <b>%(new_qty)s</b>.</p>"
                    "<p>Estimated prorated charge: <b>%(symbol)s%(amount).2f</b></p>",
                    old_qty=seat_line.product_uom_qty,
                    new_qty=wizard.new_seat_quantity,
                    symbol=symbol,
                    amount=abs(net_amount),
                )
            else:
                wizard.proration_preview = _(
                    "<p>Seats will decrease from <b>%(old_qty)s</b> to <b>%(new_qty)s</b>.</p>"
                    "<p>Estimated prorated credit: <b>%(symbol)s%(amount).2f</b></p>",
                    old_qty=seat_line.product_uom_qty,
                    new_qty=wizard.new_seat_quantity,
                    symbol=symbol,
                    amount=abs(net_amount),
                )

    def action_confirm_change(self):
        self.ensure_one()
        self.subscription_id._execute_seat_change(
            self.new_seat_quantity,
            effective_date=self.effective_date,
        )
        return {'type': 'ir.actions.act_window_close'}
