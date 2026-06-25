from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    subscription_deferred_revenue_account_id = fields.Many2one(
        'account.account',
        string='Subscription Deferred Revenue Account',
    )
    subscription_revenue_account_id = fields.Many2one(
        'account.account',
        string='Subscription Revenue Account',
    )
    subscription_recognition_journal_id = fields.Many2one(
        'account.journal',
        string='Subscription Recognition Journal',
    )
    subscription_default_recognition_method = fields.Selection(
        [
            ('straight_line_daily', 'Straight-line Daily'),
            ('equal_monthly', 'Equal Monthly'),
        ],
        string='Subscription Default Recognition Method',
        default='straight_line_daily',
    )
    subscription_enable_scheduled_recognition_posting = fields.Boolean(
        string='Enable Scheduled Subscription Revenue Recognition',
    )
    subscription_scheduled_recognition_cutoff_rule = fields.Selection(
        [
            ('today', 'Today'),
            ('prior_month_end', 'Prior Month End'),
        ],
        string='Scheduled Subscription Recognition Cutoff',
        default='prior_month_end',
    )
