from dateutil.relativedelta import relativedelta

from odoo import fields, models


class SubscriptionLtvSummaryGenerateWizard(models.TransientModel):
    _name = 'subscription.ltv.summary.generate.wizard'
    _description = 'Generate Subscription LTV Summary'

    opening_date = fields.Date(
        string='Opening Date',
        required=True,
        default=lambda self: fields.Date.today().replace(day=1) - relativedelta(months=1),
    )
    closing_date = fields.Date(
        string='Closing Date',
        required=True,
        default=lambda self: fields.Date.today().replace(day=1),
    )
    cohort_start_month = fields.Date(
        string='Cohort Start Month',
        required=True,
        default=lambda self: fields.Date.today().replace(day=1) - relativedelta(months=3),
    )
    cohort_end_month = fields.Date(
        string='Cohort End Month',
        required=True,
        default=lambda self: fields.Date.today().replace(day=1),
    )
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    subscription_plan_id = fields.Many2one('subscription.plan', string='Subscription Plan')

    def action_generate(self):
        self.ensure_one()
        rows = self.env['subscription.ltv.summary'].generate_for_period(
            self.opening_date,
            self.closing_date,
            self.cohort_start_month,
            self.cohort_end_month,
            company=self.company_id,
            plan=self.subscription_plan_id,
        )
        return {
            'name': 'LTV Summary',
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.ltv.summary',
            'view_mode': 'list,pivot,graph,form',
            'domain': [('id', 'in', rows.ids)],
        }
