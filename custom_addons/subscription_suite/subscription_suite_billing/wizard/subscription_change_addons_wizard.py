from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


class SubscriptionChangeAddonsWizard(models.TransientModel):
    _name = 'subscription.change.addons.wizard'
    _description = 'Change Subscription Add-ons'

    subscription_id = fields.Many2one('sale.order', string='Subscription', required=True, readonly=True)
    operation = fields.Selection([
        ('add', 'Add'),
        ('remove', 'Remove'),
    ], string='Operation', default='add', required=True)
    change_timing = fields.Selection([
        ('immediate', 'Immediately with Proration'),
        ('next_period', 'Next Billing Period'),
    ], string='Apply', default='immediate', required=True)
    product_id = fields.Many2one('product.product', string='Add-on Product', domain=[('type', '=', 'service')])
    addon_line_id = fields.Many2one('sale.order.line', string='Existing Add-on')
    quantity = fields.Float(string='Quantity', default=1.0, required=True)
    price_unit = fields.Monetary(string='Unit Price', currency_field='currency_id')
    discount = fields.Float(string='Discount (%)', default=0.0)
    effective_date = fields.Date(string='Effective Date', default=fields.Date.today, required=True)
    current_addon_quantity = fields.Float(string='Current Add-on Quantity', compute='_compute_impact')
    new_addon_quantity = fields.Float(string='New Add-on Quantity', compute='_compute_impact')
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
            subscription._check_addon_change_allowed()
        return values

    @api.onchange('operation')
    def _onchange_operation(self):
        for wizard in self:
            wizard.product_id = False
            wizard.addon_line_id = False
            wizard.price_unit = 0.0
            wizard.discount = 0.0
            wizard.quantity = 1.0

    @api.onchange('product_id')
    def _onchange_product_id(self):
        for wizard in self:
            if wizard.product_id and wizard.operation == 'add':
                wizard.price_unit = wizard.product_id.list_price

    @api.onchange('addon_line_id')
    def _onchange_addon_line_id(self):
        for wizard in self:
            if wizard.addon_line_id and wizard.operation == 'remove':
                wizard.product_id = wizard.addon_line_id.product_id
                wizard.price_unit = wizard.addon_line_id.price_unit
                wizard.discount = wizard.addon_line_id.discount
                wizard.quantity = min(1.0, wizard.addon_line_id.product_uom_qty)

    @api.onchange('change_timing', 'subscription_id')
    def _onchange_change_timing(self):
        for wizard in self:
            if wizard.change_timing == 'next_period' and wizard.subscription_id:
                wizard.effective_date = wizard.subscription_id.next_invoice_date or fields.Date.today()
            elif wizard.change_timing == 'immediate' and not wizard.effective_date:
                wizard.effective_date = fields.Date.today()

    @api.constrains('quantity', 'operation', 'addon_line_id', 'product_id')
    def _check_quantity(self):
        for wizard in self:
            if wizard.quantity is None:
                continue
            product = wizard.product_id or wizard.addon_line_id.product_id
            line = wizard.addon_line_id
            precision_rounding = 0.01
            if line:
                precision_rounding = (line.product_uom_id or line.product_id.uom_id).rounding or precision_rounding
            elif product and product.uom_id:
                precision_rounding = product.uom_id.rounding or precision_rounding
            if float_compare(wizard.quantity, 1.0, precision_rounding=precision_rounding) < 0:
                raise ValidationError(_("Add-on quantity must be at least 1."))
            if wizard.operation == 'remove' and line and float_compare(wizard.quantity, line.product_uom_qty, precision_rounding=precision_rounding) > 0:
                raise ValidationError(_("Cannot remove more add-on quantity than the subscription currently has."))

    @api.depends('subscription_id', 'operation', 'product_id', 'addon_line_id', 'quantity', 'price_unit', 'discount', 'effective_date', 'change_timing')
    def _compute_impact(self):
        for wizard in self:
            wizard.current_addon_quantity = 0.0
            wizard.new_addon_quantity = 0.0
            wizard.current_mrr = 0.0
            wizard.new_mrr = 0.0
            wizard.net_amount = 0.0
            wizard.proration_preview = ""
            if not wizard.subscription_id or not wizard.quantity:
                continue

            subscription = wizard.subscription_id
            current_mrr = subscription.mrr
            product = wizard.product_id
            addon_line = wizard.addon_line_id
            if wizard.operation == 'add':
                if not product:
                    continue
                addon_line = subscription._get_addon_lines(product)[:1]
                current_quantity = addon_line.product_uom_qty if addon_line else 0.0
                new_quantity = current_quantity + wizard.quantity
                new_mrr = subscription._get_mrr_after_addon_change(
                    addon_line=addon_line,
                    product=product,
                    quantity=wizard.quantity,
                    price_unit=wizard.price_unit,
                    discount=wizard.discount,
                    operation='add',
                )
            else:
                if not addon_line:
                    continue
                product = addon_line.product_id
                current_quantity = addon_line.product_uom_qty
                new_quantity = max(0.0, current_quantity - wizard.quantity)
                new_mrr = subscription._get_mrr_after_addon_change(
                    addon_line=addon_line,
                    quantity=wizard.quantity,
                    operation='remove',
                )

            period_start = (
                subscription.current_period_start
                or subscription.last_invoice_date
                or subscription.subscription_start_date
                or wizard.effective_date
            )
            period_end = (
                subscription.current_period_end
                or subscription.next_invoice_date
                or subscription.subscription_plan_id.get_next_invoice_date(period_start)
            )
            effective_date = wizard.effective_date or fields.Date.today()
            total_days = (period_end - period_start).days or 1
            used_days = max(0, (effective_date - period_start).days)
            remaining_days = max(0, total_days - used_days)
            net_amount = 0.0 if wizard.change_timing == 'next_period' else remaining_days * ((new_mrr / 30.0) - (current_mrr / 30.0))
            symbol = wizard.currency_id.symbol or '$'

            wizard.current_addon_quantity = current_quantity
            wizard.new_addon_quantity = new_quantity
            wizard.current_mrr = current_mrr
            wizard.new_mrr = new_mrr
            wizard.net_amount = net_amount
            if wizard.change_timing == 'next_period':
                wizard.proration_preview = _(
                    "<p>Add-on <b>%(product)s</b> will change from <b>%(old_qty)s</b> to <b>%(new_qty)s</b> on <b>%(date)s</b>.</p>"
                    "<p>No proration document is generated because the change applies at the billing boundary.</p>",
                    product=product.display_name,
                    old_qty=current_quantity,
                    new_qty=new_quantity,
                    date=wizard.effective_date,
                )
            elif subscription._compare_mrr(new_mrr, current_mrr) >= 0:
                wizard.proration_preview = _(
                    "<p>Add-on <b>%(product)s</b> will increase from <b>%(old_qty)s</b> to <b>%(new_qty)s</b>.</p>"
                    "<p>Estimated prorated charge: <b>%(symbol)s%(amount).2f</b></p>",
                    product=product.display_name,
                    old_qty=current_quantity,
                    new_qty=new_quantity,
                    symbol=symbol,
                    amount=abs(net_amount),
                )
            else:
                wizard.proration_preview = _(
                    "<p>Add-on <b>%(product)s</b> will decrease from <b>%(old_qty)s</b> to <b>%(new_qty)s</b>.</p>"
                    "<p>Estimated prorated credit: <b>%(symbol)s%(amount).2f</b></p>",
                    product=product.display_name,
                    old_qty=current_quantity,
                    new_qty=new_quantity,
                    symbol=symbol,
                    amount=abs(net_amount),
                )

    def action_confirm_change(self):
        self.ensure_one()
        if self.operation == 'add' and not self.product_id:
            raise ValidationError(_("Select an add-on product to add."))
        if self.operation == 'remove' and not self.addon_line_id:
            raise ValidationError(_("Select an existing add-on line to remove."))

        if self.change_timing == 'next_period':
            self.subscription_id._schedule_addon_change(
                self.operation,
                product=self.product_id,
                quantity=self.quantity,
                price_unit=self.price_unit,
                discount=self.discount,
                addon_line=self.addon_line_id,
                effective_date=self.effective_date,
            )
        else:
            self.subscription_id._execute_addon_change(
                self.operation,
                product=self.product_id,
                quantity=self.quantity,
                price_unit=self.price_unit,
                discount=self.discount,
                addon_line=self.addon_line_id,
                effective_date=self.effective_date,
            )
        return {'type': 'ir.actions.act_window_close'}
