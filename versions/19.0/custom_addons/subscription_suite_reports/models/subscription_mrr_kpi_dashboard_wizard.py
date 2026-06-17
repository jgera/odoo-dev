from dateutil.relativedelta import relativedelta

from odoo import fields, models


class SubscriptionMrrKpiDashboardGenerateWizard(models.TransientModel):
    _name = 'subscription.mrr.kpi.dashboard.generate.wizard'
    _description = 'Generate Subscription MRR KPI Dashboard'

    opening_date = fields.Date(
        string='Opening Date',
        required=True,
        default=lambda self: fields.Date.today() - relativedelta(months=1),
    )
    closing_date = fields.Date(string='Closing Date', required=True, default=fields.Date.today)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    subscription_plan_id = fields.Many2one('subscription.plan', string='Subscription Plan')

    def action_generate(self):
        self.ensure_one()
        dashboard = self.env['subscription.mrr.kpi.dashboard'].generate_for_period(
            self.opening_date,
            self.closing_date,
            company=self.company_id,
            currency=self.currency_id,
            plan=self.subscription_plan_id,
        )
        return {
            'name': 'MRR KPI Dashboard',
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.mrr.kpi.dashboard',
            'view_mode': 'form',
            'res_id': dashboard.id,
        }
