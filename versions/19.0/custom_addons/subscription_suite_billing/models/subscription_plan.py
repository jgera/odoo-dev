from odoo import fields, models


class SubscriptionPlan(models.Model):
    _inherit = 'subscription.plan'

    approval_required_for_upgrade = fields.Boolean(string='Require Approval for Upgrades')
    approval_required_for_downgrade = fields.Boolean(string='Require Approval for Downgrades')
