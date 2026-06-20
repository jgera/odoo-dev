from odoo import _, fields, models
from odoo.exceptions import AccessError, ValidationError


class SubscriptionDeferredRevenuePostWizard(models.TransientModel):
    _name = 'subscription.deferred.revenue.post.wizard'
    _description = 'Post Subscription Revenue Recognition'

    cutoff_date = fields.Date(default=fields.Date.context_today, required=True)
    posting_date = fields.Date(default=fields.Date.context_today, required=True)
    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
    )
    subscription_id = fields.Many2one(
        'sale.order',
        domain=[('is_subscription', '=', True)],
    )
    schedule_id = fields.Many2one(
        'subscription.deferred.revenue',
        domain=[('state', '=', 'ready')],
    )
    recognition_journal_id = fields.Many2one(
        'account.journal',
        default=lambda self: self.env['subscription.deferred.revenue']._get_config_m2o(
            'subscription_suite.recognition_journal_id'
        ),
    )
    deferred_revenue_account_id = fields.Many2one(
        'account.account',
        string='Deferred Revenue Account',
        default=lambda self: self.env['subscription.deferred.revenue']._get_config_m2o(
            'subscription_suite.deferred_revenue_account_id'
        ),
    )
    revenue_account_id = fields.Many2one(
        'account.account',
        default=lambda self: self.env['subscription.deferred.revenue']._get_config_m2o(
            'subscription_suite.revenue_account_id'
        ),
    )

    def _check_post_access(self):
        if not self.env.user.has_group('subscription_suite.group_subscription_manager'):
            raise AccessError(_('Only subscription managers can post revenue recognition.'))

    def _validate_post_configuration(self):
        self.ensure_one()
        self.env['subscription.deferred.revenue.line']._validate_recognition_configuration(
            self.company_id,
            self.recognition_journal_id,
            self.deferred_revenue_account_id,
            self.revenue_account_id,
            schedule=self.schedule_id,
        )
        if self.schedule_id:
            if self.subscription_id and self.schedule_id.subscription_id != self.subscription_id:
                raise ValidationError(_('The selected schedule does not belong to the selected subscription.'))

    def _get_due_lines(self):
        self.ensure_one()
        return self.env['subscription.deferred.revenue.line']._get_lines_for_recognition_preview(
            self.cutoff_date,
            company=self.company_id,
            subscription=self.subscription_id,
            schedule=self.schedule_id,
        )

    def action_post_recognition(self):
        self.ensure_one()
        self._check_post_access()
        self._validate_post_configuration()
        due_lines = self._get_due_lines()
        if not due_lines:
            raise ValidationError(_('No due draft recognition lines match the current posting filters.'))

        moves = due_lines._post_recognition_lines(
            self.posting_date,
            self.recognition_journal_id,
            self.deferred_revenue_account_id,
            self.revenue_account_id,
        )

        return {
            'type': 'ir.actions.act_window',
            'name': _('Recognition Journal Entries'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', moves.ids)],
        }
