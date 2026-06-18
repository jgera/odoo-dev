from odoo import fields, models


class SubscriptionPlanPerformanceSummaryGenerateWizard(models.TransientModel):
    _name = 'subscription.plan.performance.summary.generate.wizard'
    _description = 'Generate Subscription Top Plan Summary'

    opening_date = fields.Date(string='Opening Date', required=True)
    closing_date = fields.Date(string='Closing Date', required=True, default=fields.Date.context_today)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )
    subscription_plan_id = fields.Many2one('subscription.plan', string='Subscription Plan')

    def action_generate(self):
        self.ensure_one()
        rows = self.env['subscription.plan.performance.summary'].generate_for_period(
            self.opening_date,
            self.closing_date,
            company=self.company_id,
            plan=self.subscription_plan_id,
        )
        return {
            'name': 'Top Plans',
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.plan.performance.summary',
            'view_mode': 'list,pivot,graph,form',
            'domain': [('id', 'in', rows.ids)],
            'target': 'current',
        }
