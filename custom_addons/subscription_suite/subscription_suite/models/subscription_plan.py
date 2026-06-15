from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class SubscriptionPlan(models.Model):
    _name = 'subscription.plan'
    _description = 'Subscription Plan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, id'

    name = fields.Char(string='Name', required=True, translate=True)
    code = fields.Char(string='Code', required=True, copy=False)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)
    description = fields.Html(string='Description', translate=True)
    
    plan_line_ids = fields.One2many('subscription.plan.line', 'plan_id', string='Plan Lines', copy=True)
    
    billing_interval_count = fields.Integer(string='Billing Interval Count', required=True, default=1)
    billing_interval_unit = fields.Selection([
        ('day', 'Days'),
        ('week', 'Weeks'),
        ('month', 'Months'),
        ('year', 'Years')
    ], string='Billing Interval Unit', required=True, default='month')
    
    trial_days = fields.Integer(string='Trial Days', default=0, help="0 means no trial")
    auto_renew = fields.Boolean(string='Auto Renew', default=True)
    allow_renewal_quote = fields.Boolean(string='Allow Renewal Quotes', default=True)
    allow_upsell_quote = fields.Boolean(string='Allow Upsell Quotes', default=True)
    allow_past_due_renewal_quote = fields.Boolean(string='Allow Past-Due Renewal Quotes', default=True)
    allow_past_due_upsell_quote = fields.Boolean(string='Allow Past-Due Upsell Quotes', default=True)
    setup_fee = fields.Monetary(string='Setup Fee', currency_field='currency_id', default=0.0)
    
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    
    subscriber_count = fields.Integer(string='Active Subscribers', compute='_compute_subscriber_count')
    total_mrr = fields.Monetary(string='Total MRR', currency_field='currency_id', compute='_compute_total_mrr')
    plan_price = fields.Monetary(string='Plan Price', currency_field='currency_id', compute='_compute_plan_price')
    plan_mrr = fields.Monetary(string='Monthly Equivalent', currency_field='currency_id', compute='_compute_plan_mrr')
    
    upgrade_plan_ids = fields.Many2many('subscription.plan', 'subscription_plan_upgrade_rel', 'plan_id', 'upgrade_id', string='Upgrade Plans')
    downgrade_plan_ids = fields.Many2many('subscription.plan', 'subscription_plan_downgrade_rel', 'plan_id', 'downgrade_id', string='Downgrade Plans')
    
    cancellation_policy = fields.Selection([
        ('immediate', 'Immediate'),
        ('end_of_period', 'End of Billing Period')
    ], string='Cancellation Policy', default='end_of_period')
    
    pause_allowed = fields.Boolean(string='Pause Allowed', default=True)
    max_pause_days = fields.Integer(string='Max Pause Days', default=0, help="0 means unlimited")
    min_commitment_periods = fields.Integer(string='Minimum Commitment Periods', default=0)

    _code_company_unique = models.Constraint(
        'UNIQUE(code, company_id)',
        'Plan code must be unique per company.',
    )
    _billing_interval_positive = models.Constraint(
        'CHECK(billing_interval_count > 0)',
        'Billing interval must be positive.',
    )
    _trial_days_non_negative = models.Constraint(
        'CHECK(trial_days >= 0)',
        'Trial days cannot be negative.',
    )

    @api.depends(
        'plan_line_ids.price_unit',
        'plan_line_ids.quantity',
        'plan_line_ids.subscription_pricing_model',
        'plan_line_ids.tier_ids.min_quantity',
        'plan_line_ids.tier_ids.max_quantity',
        'plan_line_ids.tier_ids.price_unit',
    )
    def _compute_plan_price(self):
        for plan in self:
            plan.plan_price = plan._get_plan_recurring_total()

    @api.depends(
        'plan_line_ids.price_unit',
        'plan_line_ids.quantity',
        'plan_line_ids.subscription_pricing_model',
        'plan_line_ids.tier_ids.min_quantity',
        'plan_line_ids.tier_ids.max_quantity',
        'plan_line_ids.tier_ids.price_unit',
        'billing_interval_count',
        'billing_interval_unit',
    )
    def _compute_plan_mrr(self):
        for plan in self:
            plan.plan_mrr = plan._get_plan_mrr()

    def _compute_subscriber_count(self):
        for plan in self:
            plan.subscriber_count = self.env['sale.order'].search_count([
                ('subscription_plan_id', '=', plan.id),
                ('subscription_state', 'in', ['trial', 'active', 'paused', 'past_due'])
            ])

    def _compute_total_mrr(self):
        for plan in self:
            subs = self.env['sale.order'].search([
                ('subscription_plan_id', '=', plan.id),
                ('subscription_state', 'in', ['active', 'paused', 'past_due'])
            ])
            plan.total_mrr = sum(subs.mapped('mrr'))

    def _get_plan_recurring_total(self):
        self.ensure_one()
        return sum(line._get_subscription_line_total() for line in self.plan_line_ids)

    def _get_plan_mrr(self):
        self.ensure_one()
        amount = self._get_plan_recurring_total()
        count = self.billing_interval_count or 1
        unit = self.billing_interval_unit
        if unit == 'day':
            return (amount / count) * 30
        if unit == 'week':
            return (amount / count) * 4.33
        if unit == 'month':
            return amount / count
        if unit == 'year':
            return amount / (12 * count)
        return 0.0

    def action_view_subscribers(self):
        self.ensure_one()
        return {
            'name': _('Subscribers'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': [('subscription_plan_id', '=', self.id), ('is_subscription', '=', True)],
            'context': {'default_subscription_plan_id': self.id, 'default_is_subscription': True},
        }

    def get_next_invoice_date(self, start_date):
        self.ensure_one()
        if not start_date:
            return False
            
        interval = self.billing_interval_count
        unit = self.billing_interval_unit
        
        if unit == 'day':
            return start_date + relativedelta(days=interval)
        elif unit == 'week':
            return start_date + relativedelta(weeks=interval)
        elif unit == 'month':
            return start_date + relativedelta(months=interval)
        elif unit == 'year':
            return start_date + relativedelta(years=interval)
        return start_date
