from odoo import fields, models


class SubscriptionPlan(models.Model):
    _inherit = 'subscription.plan'

    usage_line_ids = fields.One2many(
        'subscription.plan.usage.line',
        'plan_id',
        string='Usage Rules',
        copy=True,
    )
    approval_required_for_upgrade = fields.Boolean(string='Require Approval for Upgrades')
    approval_required_for_downgrade = fields.Boolean(string='Require Approval for Downgrades')
