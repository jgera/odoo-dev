from dateutil.relativedelta import relativedelta

from odoo import fields, models


class SubscriptionRevenueForecastGenerateWizard(models.TransientModel):
    _name = 'subscription.revenue.forecast.generate.wizard'
    _description = 'Generate Subscription Revenue Forecast'

    forecast_start_month = fields.Date(
        string='Forecast Start Month',
        required=True,
        default=lambda self: fields.Date.today().replace(day=1),
    )
    forecast_end_month = fields.Date(
        string='Forecast End Month',
        required=True,
        default=lambda self: fields.Date.today().replace(day=1) + relativedelta(months=3),
    )
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    subscription_plan_id = fields.Many2one('subscription.plan', string='Subscription Plan')

    def action_generate(self):
        self.ensure_one()
        rows = self.env['subscription.revenue.forecast'].generate_for_period(
            self.forecast_start_month,
            self.forecast_end_month,
            company=self.company_id,
            plan=self.subscription_plan_id,
        )
        return {
            'name': 'Revenue Forecast',
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.revenue.forecast',
            'view_mode': 'list,pivot,graph,form',
            'domain': [('id', 'in', rows.ids)],
        }
