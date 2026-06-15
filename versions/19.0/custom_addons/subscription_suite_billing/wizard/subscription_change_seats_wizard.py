from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


class SubscriptionChangeSeatsWizard(models.TransientModel):
    _name = 'subscription.change.seats.wizard'
    _description = 'Change Subscription Seats'

    subscription_id = fields.Many2one('sale.order', string='Subscription', required=True, readonly=True)
    current_seat_quantity = fields.Float(string='Current Seats', readonly=True)
    new_seat_quantity = fields.Float(string='New Seats', required=True)
    change_timing = fields.Selection([
        ('immediate', 'Immediately with Proration'),
        ('next_period', 'Next Billing Period'),
    ], string='Apply', default='immediate', required=True)
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
            if not wizard.subscription_id:
                continue
            if wizard.new_seat_quantity is None:
                continue
            seat_line = wizard.subscription_id._get_single_seat_line()
            line_uom = seat_line.product_uom_id or seat_line.product_id.uom_id
            precision_rounding = line_uom.rounding or 0.01
            if float_compare(wizard.new_seat_quantity, 1.0, precision_rounding=precision_rounding) < 0:
                raise ValidationError(_("Seat quantity must be at least 1."))

    @api.onchange('change_timing', 'subscription_id')
    def _onchange_change_timing(self):
        for wizard in self:
            if wizard.change_timing == 'next_period' and wizard.subscription_id:
                wizard.effective_date = wizard.subscription_id.next_invoice_date or fields.Date.today()
            elif wizard.change_timing == 'immediate' and not wizard.effective_date:
                wizard.effective_date = fields.Date.today()

    @api.depends('subscription_id', 'new_seat_quantity', 'effective_date', 'change_timing')
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
            net_amount = 0.0 if wizard.change_timing == 'next_period' else remaining_days * ((new_mrr / 30.0) - (current_mrr / 30.0))
            symbol = wizard.currency_id.symbol or '$'

            wizard.current_mrr = current_mrr
            wizard.new_mrr = new_mrr
            wizard.net_amount = net_amount
            if wizard.change_timing == 'next_period':
                wizard.proration_preview = _(
                    "<p>Seats will change from <b>%(old_qty)s</b> to <b>%(new_qty)s</b> on <b>%(date)s</b>.</p>"
                    "<p>No proration document is generated because the change applies at the billing boundary.</p>",
                    old_qty=seat_line.product_uom_qty,
                    new_qty=wizard.new_seat_quantity,
                    date=wizard.effective_date,
                )
            elif wizard.subscription_id._compare_mrr(new_mrr, current_mrr) >= 0:
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
        if self.change_timing == 'next_period':
            self.subscription_id._schedule_seat_change(
                self.new_seat_quantity,
                effective_date=self.effective_date,
            )
        else:
            self.subscription_id._execute_seat_change(
                self.new_seat_quantity,
                effective_date=self.effective_date,
            )
        return {'type': 'ir.actions.act_window_close'}
