from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class TestManagerOperations(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Operations Customer'})
        self.product = self.env['product.product'].create({
            'name': 'Operations Subscription',
            'type': 'service',
            'list_price': 100.0,
        })
        self.plan = self.env['subscription.plan'].create({
            'name': 'Operations Basic',
            'code': 'OPS-BASIC',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'plan_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 1.0,
                'price_unit': 100.0,
                'description': 'Operations Subscription',
            })],
        })
        self.upgrade_plan = self.env['subscription.plan'].create({
            'name': 'Operations Pro',
            'code': 'OPS-PRO',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'plan_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 1.0,
                'price_unit': 200.0,
                'description': 'Operations Subscription',
            })],
        })
        self.cancel_reason = self.env['subscription.cancel.reason'].create({
            'name': 'Operations cancellation',
        })
        self.subscription = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'is_subscription': True,
            'subscription_state': 'active',
            'subscription_plan_id': self.plan.id,
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'subscription_start_date': fields.Date.today(),
            'last_invoice_date': fields.Date.today(),
            'next_invoice_date': fields.Date.today() + relativedelta(days=30),
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'name': 'Operations Subscription',
                'product_uom_qty': 1.0,
                'price_unit': 100.0,
                'is_recurring': True,
            })],
        })

    def test_manager_operations_collect_actionable_records(self):
        lifecycle_request = self.env['subscription.lifecycle.request'].create({
            'subscription_id': self.subscription.id,
            'request_type': 'pause',
            'feedback': 'Pause for operations test',
        })
        cancellation_request = self.env['subscription.cancellation.request'].create({
            'subscription_id': self.subscription.id,
            'reason_id': self.cancel_reason.id,
            'feedback': 'Cancel for operations test',
            'requested_effective_date': self.subscription.next_invoice_date,
            'requested_policy': 'end_of_period',
        })
        plan_request = self.env['subscription.plan.change.request'].create({
            'subscription_id': self.subscription.id,
            'current_plan_id': self.plan.id,
            'requested_plan_id': self.upgrade_plan.id,
            'requested_effective_date': self.subscription.next_invoice_date,
            'requested_timing': 'next_period',
            'change_type': 'upgrade',
            'old_mrr': 100.0,
            'new_mrr': 200.0,
        })
        billing_attempt = self.env['subscription.billing.attempt'].create({
            'name': 'OPS-BILL-001',
            'subscription_id': self.subscription.id,
            'period_start': fields.Date.today(),
            'period_end': self.subscription.next_invoice_date,
            'attempt_no': 1,
            'idempotency_key': 'ops-manager-dashboard',
            'state': 'pending',
        })
        billing_attempt._record_failure(Exception('missing income account'))
        self.env.flush_all()

        operations = self.env['subscription.manager.operation'].search([
            ('subscription_id', '=', self.subscription.id),
        ])
        expected_sources = {
            ('subscription.lifecycle.request', lifecycle_request.id): 'lifecycle',
            ('subscription.cancellation.request', cancellation_request.id): 'cancellation',
            ('subscription.plan.change.request', plan_request.id): 'plan_change',
            ('subscription.billing.attempt', billing_attempt.id): 'billing_recovery',
        }
        indexed_operations = {
            (operation.source_model, operation.source_res_id): operation.operation_type
            for operation in operations
        }

        for source, operation_type in expected_sources.items():
            self.assertEqual(indexed_operations.get(source), operation_type)
        self.assertTrue(operations.filtered(lambda operation: operation.priority == 'critical'))

        plan_operation = operations.filtered(lambda operation: operation.operation_type == 'plan_change')
        source_action = plan_operation.action_open_source()
        self.assertEqual(source_action['res_model'], 'subscription.plan.change.request')
        self.assertEqual(source_action['res_id'], plan_request.id)

        subscription_action = plan_operation.action_open_subscription()
        self.assertEqual(subscription_action['res_model'], 'sale.order')
        self.assertEqual(subscription_action['res_id'], self.subscription.id)
