from dateutil.relativedelta import relativedelta

from odoo import fields, models


class SubscriptionMrrWaterfallGenerateWizard(models.TransientModel):
    _name = 'subscription.mrr.waterfall.generate.wizard'
    _description = 'Generate Subscription MRR Waterfall'

    opening_date = fields.Date(
        string='Opening Date',
        required=True,
        default=lambda self: fields.Date.today() - relativedelta(months=1),
    )
    closing_date = fields.Date(string='Closing Date', required=True, default=fields.Date.today)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    subscription_plan_id = fields.Many2one('subscription.plan', string='Subscription Plan')

    def action_generate(self):
        self.ensure_one()
        rows = self.env['subscription.mrr.waterfall'].generate_for_period(
            self.opening_date,
            self.closing_date,
            company=self.company_id,
            currency=self.currency_id,
            plan=self.subscription_plan_id,
        )
        return {
            'name': 'MRR Waterfall',
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.mrr.waterfall',
            'view_mode': 'list,graph,form',
            'domain': [('id', 'in', rows.ids)],
        }
