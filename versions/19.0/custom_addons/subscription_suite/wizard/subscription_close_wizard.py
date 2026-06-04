from odoo import models, fields, api

class SubscriptionCloseWizard(models.TransientModel):
    _name = 'subscription.close.wizard'
    _description = 'Close Subscription Wizard'

    subscription_id = fields.Many2one('sale.order', string='Subscription', required=True, readonly=True)
    cancel_reason_id = fields.Many2one('subscription.cancel.reason', string='Cancellation Reason', required=True)
    feedback = fields.Text(string='Feedback')
    cancel_date = fields.Date(string='Cancellation Date', default=fields.Date.today, required=True)
    cancellation_policy = fields.Selection(related='subscription_id.subscription_plan_id.cancellation_policy', string='Policy')

    @api.onchange('subscription_id')
    def _onchange_subscription_id(self):
        if self.subscription_id:
            policy = self.subscription_id.subscription_plan_id.cancellation_policy
            self.cancel_date = self.subscription_id._get_cancellation_effective_date(policy=policy)

    def action_cancel(self):
        self.ensure_one()
        policy = self.cancellation_policy or 'immediate'
        if policy == 'end_of_period':
            self.subscription_id._action_schedule_cancel(
                reason_id=self.cancel_reason_id.id,
                feedback=self.feedback,
                effective_date=self.cancel_date,
                policy=policy,
            )
        else:
            self.subscription_id._action_cancel(
                reason_id=self.cancel_reason_id.id,
                feedback=self.feedback,
                cancellation_date=self.cancel_date,
                cancellation_policy=policy,
            )
        return {'type': 'ir.actions.act_window_close'}
