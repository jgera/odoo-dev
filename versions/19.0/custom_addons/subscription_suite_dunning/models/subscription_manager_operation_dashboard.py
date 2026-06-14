from odoo import _, fields, models


class SubscriptionManagerOperationDashboard(models.Model):
    _inherit = 'subscription.manager.operation.dashboard'

    active_dunning_count = fields.Integer(compute='_compute_dunning_recovery_metrics')
    past_due_mrr_at_risk = fields.Monetary(
        string='MRR at Risk',
        currency_field='company_currency_id',
        compute='_compute_dunning_recovery_metrics',
    )
    failed_payment_count = fields.Integer(compute='_compute_dunning_recovery_metrics')
    portal_recovery_attempt_count = fields.Integer(compute='_compute_dunning_recovery_metrics')
    portal_recovery_pending_count = fields.Integer(compute='_compute_dunning_recovery_metrics')
    portal_recovery_failed_count = fields.Integer(compute='_compute_dunning_recovery_metrics')
    portal_recovery_recovered_count = fields.Integer(compute='_compute_dunning_recovery_metrics')
    portal_recovery_manual_action_count = fields.Integer(compute='_compute_dunning_recovery_metrics')
    pending_dunning_attempt_count = fields.Integer(compute='_compute_dunning_recovery_metrics')
    failed_dunning_attempt_count = fields.Integer(compute='_compute_dunning_recovery_metrics')
    retryable_dunning_attempt_count = fields.Integer(compute='_compute_dunning_recovery_metrics')
    retry_exhausted_dunning_attempt_count = fields.Integer(compute='_compute_dunning_recovery_metrics')
    final_dunning_action_count = fields.Integer(compute='_compute_dunning_recovery_metrics')
    recovered_this_month_count = fields.Integer(compute='_compute_dunning_recovery_metrics')
    company_currency_id = fields.Many2one(
        'res.currency',
        compute='_compute_dunning_recovery_metrics',
        string='Company Currency',
    )

    def _compute_dunning_recovery_metrics(self):
        SaleOrder = self.env['sale.order']
        PaymentAttempt = self.env['subscription.payment.attempt']
        DunningAttempt = self.env['subscription.dunning.attempt']
        domains = self._dunning_recovery_domains()

        past_due_subscriptions = SaleOrder.search(domains['active_dunning'])
        recovered_subscription_ids = self._get_recovered_this_month_subscription_ids()
        metrics = {
            'active_dunning_count': len(past_due_subscriptions),
            'past_due_mrr_at_risk': sum(past_due_subscriptions.mapped('mrr')),
            'failed_payment_count': PaymentAttempt.search_count(domains['failed_payments']),
            'portal_recovery_attempt_count': PaymentAttempt.search_count(domains['portal_recovery_attempts']),
            'portal_recovery_pending_count': PaymentAttempt.search_count(domains['portal_recovery_pending']),
            'portal_recovery_failed_count': PaymentAttempt.search_count(domains['portal_recovery_failed']),
            'portal_recovery_recovered_count': PaymentAttempt.search_count(domains['portal_recovery_recovered']),
            'portal_recovery_manual_action_count': PaymentAttempt.search_count(domains['portal_recovery_manual_action']),
            'pending_dunning_attempt_count': DunningAttempt.search_count(domains['pending_dunning_attempts']),
            'failed_dunning_attempt_count': DunningAttempt.search_count(domains['failed_dunning_attempts']),
            'retryable_dunning_attempt_count': DunningAttempt.search_count(domains['retryable_dunning_attempts']),
            'retry_exhausted_dunning_attempt_count': DunningAttempt.search_count(domains['retry_exhausted_dunning_attempts']),
            'final_dunning_action_count': DunningAttempt.search_count(domains['final_dunning_actions']),
            'recovered_this_month_count': len(recovered_subscription_ids),
            'company_currency_id': self.env.company.currency_id,
        }
        for dashboard in self:
            for field_name, value in metrics.items():
                dashboard[field_name] = value

    def _dunning_recovery_domains(self):
        return {
            'active_dunning': [
                ('is_subscription', '=', True),
                ('subscription_state', '=', 'past_due'),
            ],
            'failed_payments': [
                ('recovery_required', '=', True),
                ('state', 'in', ['failed', 'error', 'cancelled']),
            ],
            'portal_recovery_attempts': [('source', '=', 'portal')],
            'portal_recovery_pending': [
                ('source', '=', 'portal'),
                ('state', '=', 'pending'),
            ],
            'portal_recovery_failed': [
                ('source', '=', 'portal'),
                ('state', 'in', ['failed', 'error', 'cancelled']),
            ],
            'portal_recovery_recovered': [
                ('source', '=', 'portal'),
                ('state', '=', 'success'),
            ],
            'portal_recovery_manual_action': [
                ('source', '=', 'portal'),
                ('recovery_required', '=', True),
                ('state', 'in', ['failed', 'error', 'cancelled']),
            ],
            'pending_dunning_attempts': [('state', 'in', ['pending', 'sent'])],
            'failed_dunning_attempts': [('state', '=', 'failed')],
            'retryable_dunning_attempts': [
                ('auto_retry_enabled', '=', True),
                ('retry_exhausted', '=', False),
                ('next_auto_retry_at', '!=', False),
            ],
            'retry_exhausted_dunning_attempts': [('retry_exhausted', '=', True)],
            'final_dunning_actions': [
                ('action_type', 'in', ['final_cancel', 'final_pause', 'final_none']),
            ],
            'recovered_this_month': [('id', 'in', self._get_recovered_this_month_subscription_ids())],
        }

    def _get_recovered_this_month_subscription_ids(self):
        month_start = fields.Date.today().replace(day=1)
        logs = self.env['subscription.log'].search([
            ('event_type', '=', 'dunning_success'),
            ('event_date', '>=', month_start),
        ])
        return list(set(logs.mapped('subscription_id').ids))

    def _open_action(self, xml_id, name, domain):
        action = self.env['ir.actions.actions']._for_xml_id(xml_id)
        action.update({
            'name': name,
            'domain': domain,
            'context': {},
        })
        return action

    def action_open_active_dunning(self):
        return {
            'name': _('Active Dunning'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': self._dunning_recovery_domains()['active_dunning'],
            'target': 'current',
        }

    def action_open_failed_payments(self):
        return self._open_action(
            'subscription_suite_billing.action_subscription_failed_payment_attempt',
            _('Failed Payments'),
            self._dunning_recovery_domains()['failed_payments'],
        )

    def action_open_portal_recovery_attempts(self):
        return self._open_action(
            'subscription_suite_billing.action_subscription_payment_attempt',
            _('Portal Recovery Attempts'),
            self._dunning_recovery_domains()['portal_recovery_attempts'],
        )

    def action_open_portal_recovery_pending(self):
        return self._open_action(
            'subscription_suite_billing.action_subscription_payment_attempt',
            _('Portal Recovery Pending'),
            self._dunning_recovery_domains()['portal_recovery_pending'],
        )

    def action_open_portal_recovery_failed(self):
        return self._open_action(
            'subscription_suite_billing.action_subscription_failed_payment_attempt',
            _('Portal Recovery Failed'),
            self._dunning_recovery_domains()['portal_recovery_failed'],
        )

    def action_open_portal_recovery_recovered(self):
        return self._open_action(
            'subscription_suite_billing.action_subscription_payment_attempt',
            _('Portal Recovery Recovered'),
            self._dunning_recovery_domains()['portal_recovery_recovered'],
        )

    def action_open_portal_recovery_manual_action(self):
        return self._open_action(
            'subscription_suite_billing.action_subscription_failed_payment_attempt',
            _('Portal Recovery Manual Action'),
            self._dunning_recovery_domains()['portal_recovery_manual_action'],
        )

    def action_open_pending_dunning_attempts(self):
        return self._open_action(
            'subscription_suite_dunning.action_subscription_dunning_attempt',
            _('Pending Dunning Attempts'),
            self._dunning_recovery_domains()['pending_dunning_attempts'],
        )

    def action_open_failed_dunning_attempts(self):
        return self._open_action(
            'subscription_suite_dunning.action_subscription_dunning_attempt',
            _('Failed Dunning Attempts'),
            self._dunning_recovery_domains()['failed_dunning_attempts'],
        )

    def action_open_retryable_dunning_attempts(self):
        return self._open_action(
            'subscription_suite_dunning.action_subscription_dunning_attempt',
            _('Retryable Dunning Attempts'),
            self._dunning_recovery_domains()['retryable_dunning_attempts'],
        )

    def action_open_retry_exhausted_dunning_attempts(self):
        return self._open_action(
            'subscription_suite_dunning.action_subscription_dunning_attempt',
            _('Retry Exhausted Dunning Attempts'),
            self._dunning_recovery_domains()['retry_exhausted_dunning_attempts'],
        )

    def action_open_final_dunning_actions(self):
        return self._open_action(
            'subscription_suite_dunning.action_subscription_dunning_attempt',
            _('Final Dunning Actions'),
            self._dunning_recovery_domains()['final_dunning_actions'],
        )

    def action_open_recovered_this_month(self):
        return {
            'name': _('Recovered This Month'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': self._dunning_recovery_domains()['recovered_this_month'],
            'target': 'current',
        }
