from dateutil.relativedelta import relativedelta

from odoo import fields, models


class SubscriptionChurnReasonSummaryGenerateWizard(models.TransientModel):
    _name = 'subscription.churn.reason.summary.generate.wizard'
    _description = 'Generate Subscription Churn Reason Summary'

    opening_date = fields.Date(
        string='Opening Date',
        required=True,
        default=lambda self: fields.Date.today().replace(day=1) - relativedelta(months=1),
    )
    closing_date = fields.Date(
        string='Closing Date',
        required=True,
        default=lambda self: fields.Date.today(),
    )
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    subscription_plan_id = fields.Many2one('subscription.plan', string='Subscription Plan')
    cancellation_reason_id = fields.Many2one('subscription.cancel.reason', string='Cancellation Reason')

    def action_generate(self):
        self.ensure_one()
        rows = self.env['subscription.churn.reason.summary'].generate_for_period(
            self.opening_date,
            self.closing_date,
            company=self.company_id,
            plan=self.subscription_plan_id,
            reason=self.cancellation_reason_id,
        )
        return {
            'name': 'Churn Reasons',
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.churn.reason.summary',
            'view_mode': 'list,pivot,graph,form',
            'domain': [('id', 'in', rows.ids)],
        }
