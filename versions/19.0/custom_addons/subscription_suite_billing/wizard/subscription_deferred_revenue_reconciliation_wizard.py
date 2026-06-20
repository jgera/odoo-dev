from odoo import _, fields, models
from odoo.exceptions import AccessError, ValidationError


class SubscriptionDeferredRevenueReconciliationWizard(models.TransientModel):
    _name = 'subscription.deferred.revenue.reconciliation.wizard'
    _description = 'Generate Subscription Deferred Revenue Reconciliation'

    opening_date = fields.Date(required=True, default=fields.Date.context_today)
    closing_date = fields.Date(required=True, default=fields.Date.context_today)
    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
    )
    subscription_plan_id = fields.Many2one('subscription.plan', string='Plan')

    def _check_generate_access(self):
        if not self.env.user.has_group('subscription_suite.group_subscription_manager'):
            raise AccessError(_('Only subscription managers can generate deferred revenue reconciliations.'))

    def action_generate(self):
        self.ensure_one()
        self._check_generate_access()
        if self.closing_date < self.opening_date:
            raise ValidationError(_('Closing date must be on or after opening date.'))

        reconciliations = self.env['subscription.deferred.revenue.reconciliation'].generate_reconciliation(
            self.opening_date,
            self.closing_date,
            company=self.company_id,
            plan=self.subscription_plan_id,
        )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Deferred Revenue Reconciliation'),
            'res_model': 'subscription.deferred.revenue.reconciliation',
            'view_mode': 'list,form,pivot,graph',
            'domain': [('id', 'in', reconciliations.ids)],
            'context': {'search_default_group_status': 1},
        }
