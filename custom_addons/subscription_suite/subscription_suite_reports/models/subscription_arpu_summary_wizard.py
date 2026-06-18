from dateutil.relativedelta import relativedelta

from odoo import fields, models


class SubscriptionArpuSummaryGenerateWizard(models.TransientModel):
    _name = 'subscription.arpu.summary.generate.wizard'
    _description = 'Generate Subscription ARPU Summary'

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
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    subscription_plan_id = fields.Many2one('subscription.plan', string='Subscription Plan')

    def action_generate(self):
        self.ensure_one()
        rows = self.env['subscription.arpu.summary'].generate_for_period(
            self.opening_date,
            self.closing_date,
            company=self.company_id,
            plan=self.subscription_plan_id,
        )
        return {
            'name': 'ARPU Summary',
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.arpu.summary',
            'view_mode': 'list,pivot,graph,form',
            'domain': [('id', 'in', rows.ids)],
        }
