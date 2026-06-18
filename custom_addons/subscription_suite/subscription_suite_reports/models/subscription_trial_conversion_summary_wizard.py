from odoo import fields, models


class SubscriptionTrialConversionSummaryGenerateWizard(models.TransientModel):
    _name = 'subscription.trial.conversion.summary.generate.wizard'
    _description = 'Generate Trial Conversion Summaries'

    opening_date = fields.Date(string='Opening Date', required=True, default=fields.Date.context_today)
    closing_date = fields.Date(string='Closing Date', required=True, default=fields.Date.context_today)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )
    subscription_plan_id = fields.Many2one('subscription.plan', string='Subscription Plan')

    def action_generate(self):
        self.ensure_one()
        rows = self.env['subscription.trial.conversion.summary'].generate_for_period(
            self.opening_date,
            self.closing_date,
            company=self.company_id,
            plan=self.subscription_plan_id,
        )
        return {
            'name': 'Trial Conversion',
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.trial.conversion.summary',
            'view_mode': 'list,pivot,graph,form',
            'domain': [('id', 'in', rows.ids)],
            'target': 'current',
        }
