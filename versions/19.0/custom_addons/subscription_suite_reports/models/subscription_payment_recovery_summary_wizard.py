from odoo import fields, models


class SubscriptionPaymentRecoverySummaryGenerateWizard(models.TransientModel):
    _name = 'subscription.payment.recovery.summary.generate.wizard'
    _description = 'Generate Payment Recovery Summaries'

    opening_date = fields.Date(string='Opening Date', required=True, default=fields.Date.context_today)
    closing_date = fields.Date(string='Closing Date', required=True, default=fields.Date.context_today)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )
    subscription_plan_id = fields.Many2one('subscription.plan', string='Subscription Plan')
    recovery_source = fields.Selection(
        [
            ('portal', 'Portal'),
            ('cron', 'Cron'),
            ('manual', 'Manual'),
            ('all', 'All Sources'),
        ],
        string='Recovery Source',
    )

    def action_generate(self):
        self.ensure_one()
        rows = self.env['subscription.payment.recovery.summary'].generate_for_period(
            self.opening_date,
            self.closing_date,
            company=self.company_id,
            plan=self.subscription_plan_id,
            source=self.recovery_source,
        )
        return {
            'name': 'Payment Recovery',
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.payment.recovery.summary',
            'view_mode': 'list,pivot,graph,form',
            'domain': [('id', 'in', rows.ids)],
            'target': 'current',
        }
