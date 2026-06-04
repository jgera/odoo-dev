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

    def action_apply_proration(self):
        self.ensure_one()
        if self.state != 'draft':
            raise ValidationError(_("Can only apply draft prorations."))
        
        # In a real implementation, this would generate the actual credit note
        # and adjustment invoice via account.move.create()
        
        self.state = 'applied'
        self.subscription_id.subscription_plan_id = self.new_plan_id
        
        # Log event
        self.subscription_id._log_subscription_event(
            'plan_changed',
            f'Plan changed from {self.old_plan_id.name} to {self.new_plan_id.name} with proration net amount {self.net_amount}'
        )
