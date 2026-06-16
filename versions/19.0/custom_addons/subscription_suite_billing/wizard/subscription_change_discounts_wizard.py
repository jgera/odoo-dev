from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


class SubscriptionChangeDiscountsWizard(models.TransientModel):
    _name = 'subscription.change.discounts.wizard'
    _description = 'Change Subscription Discounts'

    subscription_id = fields.Many2one('sale.order', string='Subscription', required=True, readonly=True)
    operation = fields.Selection([
        ('update', 'Update Discount'),
        ('clear_promo', 'Clear Promotion'),
    ], string='Operation', default='update', required=True)
    line_id = fields.Many2one('sale.order.line', string='Recurring Line', required=True)
    base_discount = fields.Float(string='Base Discount (%)', default=0.0)
    promo_discount = fields.Float(string='Promotional Discount (%)', default=0.0)
    promo_start_date = fields.Date(string='Promo Start Date')
    promo_end_date = fields.Date(string='Promo End Date')
    current_effective_discount = fields.Float(string='Current Effective Discount (%)', readonly=True)
    new_effective_discount = fields.Float(string='New Effective Discount (%)', compute='_compute_impact')
    current_mrr = fields.Monetary(string='Current MRR', currency_field='currency_id', compute='_compute_impact')
    new_mrr = fields.Monetary(string='New MRR', currency_field='currency_id', compute='_compute_impact')
    impact_summary = fields.Html(string='Discount Summary', compute='_compute_impact')
    currency_id = fields.Many2one('res.currency', related='subscription_id.currency_id')

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        subscription = self.env['sale.order'].browse(values.get('subscription_id'))
        if subscription:
            subscription._check_discount_change_allowed()
            line = subscription._get_discount_candidate_lines()[:1]
            if line:
                values.setdefault('line_id', line.id)
                values.setdefault('base_discount', line.subscription_base_discount or line.discount or 0.0)
                values.setdefault('promo_discount', line.subscription_promo_discount)
                values.setdefault('promo_start_date', line.subscription_promo_discount_start_date)
                values.setdefault('promo_end_date', line.subscription_promo_discount_end_date)
                values.setdefault('current_effective_discount', line.discount)
        return values

    @api.onchange('line_id')
    def _onchange_line_id(self):
        for wizard in self:
            if not wizard.line_id:
                continue
            wizard.base_discount = wizard.line_id.subscription_base_discount or wizard.line_id.discount or 0.0
            wizard.promo_discount = wizard.line_id.subscription_promo_discount
            wizard.promo_start_date = wizard.line_id.subscription_promo_discount_start_date
            wizard.promo_end_date = wizard.line_id.subscription_promo_discount_end_date
            wizard.current_effective_discount = wizard.line_id.discount

    @api.onchange('operation')
    def _onchange_operation(self):
        for wizard in self:
            if wizard.operation == 'clear_promo':
                wizard.promo_discount = 0.0
                wizard.promo_start_date = False
                wizard.promo_end_date = False

    @api.constrains('line_id', 'subscription_id')
    def _check_line_id(self):
        for wizard in self:
            if not wizard.line_id or not wizard.subscription_id:
                continue
            if wizard.line_id.order_id != wizard.subscription_id:
                raise ValidationError(_("Select a recurring line from this subscription."))
            if wizard.line_id.display_type or not wizard.line_id.is_recurring:
                raise ValidationError(_("Discounts can only be changed on recurring subscription lines."))

    @api.constrains('base_discount', 'promo_discount', 'promo_start_date', 'promo_end_date')
    def _check_discount_values(self):
        for wizard in self:
            for value in (wizard.base_discount or 0.0, wizard.promo_discount or 0.0):
                if (
                    float_compare(value, 0.0, precision_digits=6) < 0
                    or float_compare(value, 100.0, precision_digits=6) > 0
                ):
                    raise ValidationError(_("Discount percentages must be between 0 and 100."))
            if wizard.promo_start_date and wizard.promo_end_date and wizard.promo_end_date <= wizard.promo_start_date:
                raise ValidationError(_("Promotional discount end date must be after the start date."))

    def _preview_effective_discount(self):
        self.ensure_one()
        if self.operation == 'clear_promo':
            return self.base_discount or 0.0
        today = fields.Date.context_today(self)
        if not self.promo_discount:
            return self.base_discount or 0.0
        if self.promo_start_date and today < self.promo_start_date:
            return self.line_id.discount if self.line_id else self.base_discount or 0.0
        if self.promo_end_date and today > self.promo_end_date:
            return self.base_discount or 0.0
        base_discount = self.base_discount or 0.0
        promo_discount = self.promo_discount or 0.0
        return 100.0 * (1.0 - ((1.0 - base_discount / 100.0) * (1.0 - promo_discount / 100.0)))

    @api.depends('subscription_id', 'line_id', 'base_discount', 'promo_discount', 'promo_start_date', 'promo_end_date', 'operation')
    def _compute_impact(self):
        for wizard in self:
            wizard.current_mrr = wizard.subscription_id.mrr if wizard.subscription_id else 0.0
            wizard.new_mrr = wizard.current_mrr
            wizard.new_effective_discount = 0.0
            wizard.impact_summary = ""
            if not wizard.subscription_id or not wizard.line_id:
                continue

            old_subtotal = wizard.line_id.price_subtotal
            effective_discount = wizard._preview_effective_discount()
            new_subtotal = wizard.line_id._get_subscription_line_total() * (1 - effective_discount / 100.0)
            recurring_total = wizard.subscription_id.recurring_total - old_subtotal + new_subtotal
            new_mrr = wizard.subscription_id._monthly_equivalent_amount(recurring_total)
            wizard.new_effective_discount = effective_discount
            wizard.new_mrr = new_mrr
            wizard.impact_summary = _(
                "<p>Line <b>%(line)s</b> will use an effective discount of <b>%(discount).2f%%</b>.</p>"
                "<p>No proration document is generated; the change affects recurring billing forward.</p>",
                line=wizard.line_id.product_id.display_name or wizard.line_id.name,
                discount=effective_discount,
            )

    def action_confirm_change(self):
        self.ensure_one()
        self.subscription_id._check_discount_change_allowed()
        if self.operation == 'clear_promo':
            self.subscription_id._clear_line_promotion(self.line_id, base_discount=self.base_discount)
        else:
            self.subscription_id._apply_line_discount_change(
                self.line_id,
                base_discount=self.base_discount,
                promo_discount=self.promo_discount,
                promo_start_date=self.promo_start_date,
                promo_end_date=self.promo_end_date,
            )
        return {'type': 'ir.actions.act_window_close'}
