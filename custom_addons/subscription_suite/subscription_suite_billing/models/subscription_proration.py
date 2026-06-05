from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class SubscriptionProration(models.Model):
    _name = 'subscription.proration'
    _description = 'Subscription Proration Record'
    _order = 'create_date desc'

    subscription_id = fields.Many2one('sale.order', string='Subscription', required=True, ondelete='cascade')
    change_type = fields.Selection([
        ('upgrade', 'Upgrade'),
        ('downgrade', 'Downgrade'),
        ('cancel', 'Cancellation')
    ], string='Change Type', required=True)
    
    change_date = fields.Date(string='Change Date', required=True, default=fields.Date.context_today)
    old_plan_id = fields.Many2one('subscription.plan', string='Old Plan', required=True)
    new_plan_id = fields.Many2one('subscription.plan', string='New Plan')
    
    period_start = fields.Date(string='Period Start', required=True)
    period_end = fields.Date(string='Period End', required=True)
    
    total_period_days = fields.Integer(string='Total Days', compute='_compute_proration', store=True)
    used_days = fields.Integer(string='Used Days', compute='_compute_proration', store=True)
    remaining_days = fields.Integer(string='Remaining Days', compute='_compute_proration', store=True)
    
    old_daily_rate = fields.Monetary(string='Old Daily Rate', currency_field='currency_id', required=True)
    new_daily_rate = fields.Monetary(string='New Daily Rate', currency_field='currency_id')
    
    credit_amount = fields.Monetary(string='Credit Amount', currency_field='currency_id', compute='_compute_proration', store=True)
    charge_amount = fields.Monetary(string='Charge Amount', currency_field='currency_id', compute='_compute_proration', store=True)
    net_amount = fields.Monetary(string='Net Amount', currency_field='currency_id', compute='_compute_proration', store=True)
    
    credit_note_id = fields.Many2one('account.move', string='Credit Note', readonly=True)  # Populated when credit note is generated
    adjustment_invoice_id = fields.Many2one('account.move', string='Adjustment Invoice', readonly=True)  # Populated when adjustment invoice is generated
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('applied', 'Applied'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft')
    
    currency_id = fields.Many2one('res.currency', related='subscription_id.currency_id', store=True)
    company_id = fields.Many2one('res.company', related='subscription_id.company_id', store=True)

    @api.constrains('period_start', 'period_end', 'change_date')
    def _check_dates(self):
        for record in self:
            if record.period_start and record.period_end and record.change_date:
                if not (record.period_start <= record.change_date <= record.period_end):
                    raise ValidationError(_('Change date must be between period start and period end.'))

    @api.depends('change_date', 'period_start', 'period_end', 'old_daily_rate', 'new_daily_rate')
    def _compute_proration(self):
        for record in self:
            if record.period_start and record.period_end and record.change_date:
                record.total_period_days = (record.period_end - record.period_start).days or 1
                record.used_days = max(0, (record.change_date - record.period_start).days)
                record.remaining_days = max(0, record.total_period_days - record.used_days)
                
                record.credit_amount = record.remaining_days * record.old_daily_rate
                record.charge_amount = record.remaining_days * (record.new_daily_rate or 0.0)
                record.net_amount = record.charge_amount - record.credit_amount
            else:
                record.total_period_days = 0
                record.used_days = 0
                record.remaining_days = 0
                record.credit_amount = 0.0
                record.charge_amount = 0.0
                record.net_amount = 0.0

    def _get_proration_product(self):
        self.ensure_one()
        plan = self.new_plan_id or self.old_plan_id
        product = plan.plan_line_ids[:1].product_id if plan and plan.plan_line_ids else False
        if not product:
            product = self.subscription_id.order_line.filtered(
                lambda line: line.is_recurring and not line.display_type and line.product_id
            )[:1].product_id
        if not product:
            raise ValidationError(_("A proration adjustment needs at least one recurring product to determine accounting."))
        return product

    def _get_proration_income_account(self, product):
        self.ensure_one()
        account = False
        if hasattr(product, '_get_product_accounts'):
            account = product._get_product_accounts().get('income')
        account = account or product.property_account_income_id or product.categ_id.property_account_income_categ_id
        if not account:
            raise ValidationError(_("Configure an income account on product %s or its product category.") % product.display_name)
        return account

    def _prepare_proration_move_vals(self):
        self.ensure_one()
        if not self.net_amount:
            return False

        product = self._get_proration_product()
        account = self._get_proration_income_account(product)
        move_type = 'out_invoice' if self.net_amount > 0 else 'out_refund'
        amount = abs(self.net_amount)
        taxes = product.taxes_id.filtered(lambda tax: not tax.company_id or tax.company_id == self.company_id)

        return {
            'move_type': move_type,
            'partner_id': self.subscription_id.partner_invoice_id.id or self.subscription_id.partner_id.id,
            'invoice_date': fields.Date.today(),
            'invoice_origin': self.subscription_id.name,
            'currency_id': self.currency_id.id,
            'company_id': self.company_id.id,
            'subscription_id': self.subscription_id.id,
            'subscription_period_start': self.period_start,
            'subscription_period_end': self.period_end,
            'proration_id': self.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': product.id,
                'name': _('Subscription proration adjustment: %(start)s to %(end)s') % {
                    'start': self.change_date,
                    'end': self.period_end,
                },
                'quantity': 1.0,
                'price_unit': amount,
                'account_id': account.id,
                'tax_ids': [(6, 0, taxes.ids)],
            })],
        }

    def _create_proration_move(self):
        self.ensure_one()
        if self.adjustment_invoice_id or self.credit_note_id or not self.net_amount:
            return self.adjustment_invoice_id or self.credit_note_id

        move_vals = self._prepare_proration_move_vals()
        if not move_vals:
            return False

        move = self.env['account.move'].create(move_vals)
        if move.move_type == 'out_invoice':
            self.adjustment_invoice_id = move.id
        else:
            self.credit_note_id = move.id
        return move

    def action_apply_proration(self):
        self.ensure_one()
        if self.state != 'draft':
            raise ValidationError(_("Can only apply draft prorations."))

        move = self._create_proration_move()
        self.state = 'applied'
        self.subscription_id.subscription_plan_id = self.new_plan_id
        
        # Log event
        self.subscription_id._log_subscription_event(
            'plan_changed',
            _(
                'Plan changed from %(old_plan)s to %(new_plan)s with proration net amount %(amount)s%(document)s',
                old_plan=self.old_plan_id.name,
                new_plan=self.new_plan_id.name,
                amount=self.net_amount,
                document=_(' and document %s') % move.name if move else '',
            )
        )
