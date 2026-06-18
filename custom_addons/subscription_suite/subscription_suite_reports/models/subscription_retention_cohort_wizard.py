from dateutil.relativedelta import relativedelta

from odoo import fields, models


class SubscriptionRetentionCohortGenerateWizard(models.TransientModel):
    _name = 'subscription.retention.cohort.generate.wizard'
    _description = 'Generate Subscription Retention Cohorts'

    cohort_start_month = fields.Date(
        string='Cohort Start Month',
        required=True,
        default=lambda self: fields.Date.today().replace(day=1) - relativedelta(months=6),
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
        rows = self.env['subscription.retention.cohort'].generate_for_period(
            self.cohort_start_month,
            self.cohort_end_month,
            company=self.company_id,
            plan=self.subscription_plan_id,
        )
        return {
            'name': 'Retention Cohorts',
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.retention.cohort',
            'view_mode': 'list,pivot,graph,form',
            'domain': [('id', 'in', rows.ids)],
        }
