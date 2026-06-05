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

    def _compute_metrics(self):
        Operation = self.env['subscription.manager.operation']
        domains = self._operation_domains()
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
