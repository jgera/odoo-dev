from odoo import fields, models


class SubscriptionAtRiskSummaryGenerateWizard(models.TransientModel):
    _name = 'subscription.at.risk.summary.generate.wizard'
    _description = 'Generate At-Risk Subscription Summaries'

    as_of_date = fields.Date(string='As Of Date', required=True, default=fields.Date.context_today)
    lookahead_days = fields.Integer(string='Lookahead Days', required=True, default=30)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )
    subscription_plan_id = fields.Many2one('subscription.plan', string='Subscription Plan')

    def action_generate(self):
        self.ensure_one()
        rows = self.env['subscription.at.risk.summary'].generate_for_date(
            self.as_of_date,
            lookahead_days=self.lookahead_days,
            company=self.company_id,
            plan=self.subscription_plan_id,
        )
        return {
            'name': 'At-Risk Subscriptions',
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.at.risk.summary',
            'view_mode': 'list,pivot,graph,form',
            'domain': [('id', 'in', rows.ids)],
            'target': 'current',
        }
