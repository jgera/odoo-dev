from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class SubscriptionChangePlanWizard(models.TransientModel):
    _name = 'subscription.change.plan.wizard'
    _description = 'Change Subscription Plan'

    subscription_id = fields.Many2one('sale.order', string='Subscription', required=True, readonly=True)
    current_plan_id = fields.Many2one('subscription.plan', string='Current Plan', readonly=True)
    new_plan_id = fields.Many2one('subscription.plan', string='New Plan', required=True)
    
    change_type = fields.Selection([
        ('upgrade', 'Upgrade'),
        ('downgrade', 'Downgrade')
    ], string='Change Type', compute='_compute_proration_details')
    
    effective_date = fields.Date(string='Effective Date', default=fields.Date.today, required=True)
    
    credit_amount = fields.Monetary(string='Credit Amount (Unused Time)', currency_field='currency_id', compute='_compute_proration_details')
    charge_amount = fields.Monetary(string='Charge Amount (New Plan Time)', currency_field='currency_id', compute='_compute_proration_details')
    net_amount = fields.Monetary(string='Net Amount to Bill', currency_field='currency_id', compute='_compute_proration_details')
    
    available_plan_ids = fields.Many2many('subscription.plan', compute='_compute_available_plans')
    proration_preview = fields.Html(string='Proration Summary', compute='_compute_proration_preview')
    
    currency_id = fields.Many2one('res.currency', related='subscription_id.currency_id')

    @api.depends('subscription_id', 'current_plan_id')
    def _compute_available_plans(self):
        for wizard in self:
            if wizard.current_plan_id:
                upgrades = wizard.current_plan_id.upgrade_plan_ids
                downgrades = wizard.current_plan_id.downgrade_plan_ids
                wizard.available_plan_ids = upgrades + downgrades
            else:
                wizard.available_plan_ids = self.env['subscription.plan'].search([
                    ('company_id', 'in', [self.env.company.id, False]),
                ])

    @api.depends('new_plan_id', 'effective_date', 'subscription_id')
    def _compute_proration_details(self):
        for wizard in self:
            if wizard.new_plan_id and wizard.effective_date and wizard.subscription_id:
                old_mrr = wizard.subscription_id.mrr
                new_mrr = wizard.new_plan_id._get_plan_mrr()
                
                wizard.change_type = 'upgrade' if new_mrr > old_mrr else 'downgrade'
                
                period_start = wizard.subscription_id.current_period_start or wizard.subscription_id.subscription_start_date
                period_end = wizard.subscription_id.current_period_end or wizard.subscription_id.next_invoice_date
                
                if period_start and period_end:
                    total_days = (period_end - period_start).days or 1
                    used_days = max(0, (wizard.effective_date - period_start).days)
                    remaining_days = max(0, total_days - used_days)
                    
                    old_daily_rate = old_mrr / 30
                    new_daily_rate = new_mrr / 30
                    
                    wizard.credit_amount = remaining_days * old_daily_rate
                    wizard.charge_amount = remaining_days * new_daily_rate
                    wizard.net_amount = wizard.charge_amount - wizard.credit_amount
                else:
                    wizard.credit_amount = 0.0
                    wizard.charge_amount = 0.0
                    wizard.net_amount = 0.0
            else:
                wizard.change_type = False
                wizard.credit_amount = 0.0
                wizard.charge_amount = 0.0
                wizard.net_amount = 0.0

    @api.depends('credit_amount', 'charge_amount', 'net_amount', 'change_type')
    def _compute_proration_preview(self):
        for wizard in self:
            if wizard.new_plan_id:
                symbol = wizard.currency_id.symbol or '$'
                if wizard.change_type == 'upgrade':
                    wizard.proration_preview = f"""
                        <p>You are <b>upgrading</b>.</p>
                        <ul>
                            <li>Unused time credit: <b>{symbol}{wizard.credit_amount:.2f}</b></li>
                            <li>Charge for remaining period on new plan: <b>{symbol}{wizard.charge_amount:.2f}</b></li>
                            <li>Total Due Now: <b>{symbol}{wizard.net_amount:.2f}</b></li>
                        </ul>
                    """
                else:
                    wizard.proration_preview = f"""
                        <p>You are <b>downgrading</b>.</p>
                        <ul>
                            <li>Unused time credit: <b>{symbol}{wizard.credit_amount:.2f}</b></li>
                            <li>Charge for remaining period on new plan: <b>{symbol}{wizard.charge_amount:.2f}</b></li>
                            <li>Total Credit Applied to Account: <b>{symbol}{abs(wizard.net_amount):.2f}</b></li>
                        </ul>
                    """
            else:
                wizard.proration_preview = ""

    def action_confirm_change(self):
        self.ensure_one()
        if self.new_plan_id == self.current_plan_id:
            raise ValidationError(_("The new plan must be different from the current plan."))
            
        self.subscription_id._execute_plan_change(self.new_plan_id, self.effective_date)
        return {'type': 'ir.actions.act_window_close'}
