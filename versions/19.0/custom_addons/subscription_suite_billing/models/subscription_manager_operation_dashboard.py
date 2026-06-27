from datetime import timedelta

from odoo import _, fields, models


class SubscriptionManagerOperationDashboard(models.Model):
    _name = 'subscription.manager.operation.dashboard'
    _description = 'Subscription Manager Operation Dashboard'

    name = fields.Char(default='Manager Operations Dashboard', required=True)
    total_open_count = fields.Integer(compute='_compute_metrics')
    pending_request_count = fields.Integer(compute='_compute_metrics')
    pending_plan_change_count = fields.Integer(compute='_compute_metrics')
    pending_lifecycle_count = fields.Integer(compute='_compute_metrics')
    pending_cancellation_count = fields.Integer(compute='_compute_metrics')
    failed_billing_count = fields.Integer(compute='_compute_metrics')
    critical_count = fields.Integer(compute='_compute_metrics')
    oldest_pending_age_days = fields.Integer(compute='_compute_metrics')
    oldest_operation_id = fields.Many2one(
        'subscription.manager.operation',
        compute='_compute_metrics',
        string='Oldest Pending Item',
    )
    failed_operation_run_count = fields.Integer(compute='_compute_metrics')
    partial_operation_run_count = fields.Integer(compute='_compute_metrics')
    recent_operation_failure_count = fields.Integer(compute='_compute_metrics')
    unresolved_operation_error_count = fields.Integer(compute='_compute_metrics')

    def _compute_metrics(self):
        Operation = self.env['subscription.manager.operation']
        OperationRun = self.env['subscription.operation.run']
        domains = self._operation_domains()
        run_domains = self._operation_run_domains()
        oldest_operation = Operation.search(domains['pending_requests'], order='event_date asc, id asc', limit=1)
        metrics = {
            'total_open_count': Operation.search_count([]),
            'pending_request_count': Operation.search_count(domains['pending_requests']),
            'pending_plan_change_count': Operation.search_count(domains['pending_plan_changes']),
            'pending_lifecycle_count': Operation.search_count(domains['pending_lifecycle']),
            'pending_cancellation_count': Operation.search_count(domains['pending_cancellations']),
            'failed_billing_count': Operation.search_count(domains['failed_billing']),
            'critical_count': Operation.search_count(domains['critical']),
            'oldest_pending_age_days': oldest_operation.age_days if oldest_operation else 0,
            'oldest_operation_id': oldest_operation,
            'failed_operation_run_count': OperationRun.search_count(run_domains['failed']),
            'partial_operation_run_count': OperationRun.search_count(run_domains['partial']),
            'recent_operation_failure_count': OperationRun.search_count(run_domains['recent_failures']),
            'unresolved_operation_error_count': OperationRun.search_count(run_domains['needs_review']),
        }
        for dashboard in self:
            for field_name, value in metrics.items():
                dashboard[field_name] = value

    def _operation_domains(self):
        return {
            'all': [],
            'pending_requests': [('action_state', '=', 'pending')],
            'pending_plan_changes': [
                ('operation_type', '=', 'plan_change'),
                ('action_state', '=', 'pending'),
            ],
            'pending_lifecycle': [
                ('operation_type', '=', 'lifecycle'),
                ('action_state', '=', 'pending'),
            ],
            'pending_cancellations': [
                ('operation_type', '=', 'cancellation'),
                ('action_state', '=', 'pending'),
            ],
            'failed_billing': [('operation_type', '=', 'billing_recovery')],
            'critical': [('priority', '=', 'critical')],
        }

    def _operation_run_domains(self):
        recent_cutoff = fields.Datetime.now() - timedelta(days=7)
        return {
            'failed': [('state', '=', 'failed')],
            'partial': [('state', '=', 'partial')],
            'needs_review': [
                ('state', 'in', ['failed', 'partial']),
                ('reviewed', '=', False),
            ],
            'recent_failures': [
                ('state', 'in', ['failed', 'partial']),
                ('reviewed', '=', False),
                ('started_at', '>=', recent_cutoff),
            ],
        }

    def _open_operations(self, name, domain):
        action = self.env['ir.actions.actions']._for_xml_id(
            'subscription_suite_billing.action_subscription_manager_operation'
        )
        action.update({
            'name': name,
            'domain': domain,
            'context': {'search_default_group_type': 0},
        })
        return action

    def action_open_all(self):
        return self._open_operations(_('Manager Operations'), self._operation_domains()['all'])

    def action_open_pending_requests(self):
        return self._open_operations(_('Pending Requests'), self._operation_domains()['pending_requests'])

    def action_open_pending_plan_changes(self):
        return self._open_operations(_('Pending Plan Changes'), self._operation_domains()['pending_plan_changes'])

    def action_open_pending_lifecycle(self):
        return self._open_operations(_('Pending Lifecycle Requests'), self._operation_domains()['pending_lifecycle'])

    def action_open_pending_cancellations(self):
        return self._open_operations(_('Pending Cancellations'), self._operation_domains()['pending_cancellations'])

    def action_open_failed_billing(self):
        return self._open_operations(_('Billing Recovery'), self._operation_domains()['failed_billing'])

    def action_open_critical(self):
        return self._open_operations(_('Critical Operations'), self._operation_domains()['critical'])

    def action_open_oldest_pending(self):
        self.ensure_one()
        if not self.oldest_operation_id:
            return self.action_open_pending_requests()
        return self._open_operations(_('Oldest Pending Item'), [('id', '=', self.oldest_operation_id.id)])

    def _open_operation_runs(self, name, domain):
        action = self.env['ir.actions.actions']._for_xml_id(
            'subscription_suite_billing.action_subscription_operation_run'
        )
        action.update({'name': name, 'domain': domain, 'context': {}})
        return action

    def action_open_failed_operation_runs(self):
        return self._open_operation_runs(
            _('Failed Operational Runs'),
            self._operation_run_domains()['failed'],
        )

    def action_open_partial_operation_runs(self):
        return self._open_operation_runs(
            _('Partial Operational Runs'),
            self._operation_run_domains()['partial'],
        )

    def action_open_recent_operation_failures(self):
        return self._open_operation_runs(
            _('Recent Operational Failures'),
            self._operation_run_domains()['recent_failures'],
        )

    def action_open_unresolved_operation_errors(self):
        return self._open_operation_runs(
            _('Operational Runs Requiring Review'),
            self._operation_run_domains()['needs_review'],
        )
