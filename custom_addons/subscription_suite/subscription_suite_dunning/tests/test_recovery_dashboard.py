from odoo import fields
from odoo.tests.common import TransactionCase


class TestRecoveryDashboard(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({
            'name': 'Recovery Dashboard Customer',
            'email': 'recovery-dashboard@example.com',
        })
        self.product = self.env['product.product'].create({
            'name': 'Recovery Dashboard Subscription',
            'type': 'service',
            'list_price': 100.0,
        })
        self.policy = self.env['subscription.dunning.policy'].create({
            'name': 'Recovery Dashboard Policy',
            'grace_period_days': 1,
            'final_action': 'cancel',
            'final_action_delay': 3,
        })
        self.plan = self.env['subscription.plan'].create({
            'name': 'Recovery Dashboard Plan',
            'code': 'RECOVERY-DASH',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'dunning_policy_id': self.policy.id,
            'plan_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 1.0,
                'price_unit': 100.0,
                'description': 'Recovery Dashboard Subscription',
            })],
        })
        self.subscription = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'is_subscription': True,
            'subscription_state': 'past_due',
            'subscription_plan_id': self.plan.id,
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'subscription_start_date': fields.Date.today(),
            'dunning_start_date': fields.Date.today(),
            'next_dunning_date': fields.Date.today(),
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'name': 'Recovery Dashboard Subscription',
                'product_uom_qty': 1.0,
                'price_unit': 100.0,
                'is_recurring': True,
            })],
        })
        self.invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_date': fields.Date.today(),
            'subscription_id': self.subscription.id,
        })

    def test_recovery_dashboard_metrics_and_drilldowns(self):
        payment_attempt = self.env['subscription.payment.attempt'].create({
            'name': 'RECOVERY-PAY-001',
            'subscription_id': self.subscription.id,
            'invoice_id': self.invoice.id,
            'source': 'portal',
            'state': 'failed',
            'amount': 100.0,
            'failure_message': 'card declined',
            'recovery_required': True,
            'recovery_note': 'Customer needs to update payment method.',
        })
        pending_portal_attempt = self.env['subscription.payment.attempt'].create({
            'name': 'RECOVERY-PAY-002',
            'subscription_id': self.subscription.id,
            'invoice_id': self.invoice.id,
            'source': 'portal',
            'state': 'pending',
            'amount': 100.0,
            'recovery_note': 'Customer retry is waiting for provider confirmation.',
        })
        recovered_portal_attempt = self.env['subscription.payment.attempt'].create({
            'name': 'RECOVERY-PAY-003',
            'subscription_id': self.subscription.id,
            'invoice_id': self.invoice.id,
            'source': 'portal',
            'state': 'success',
            'amount': 100.0,
            'recovery_note': 'Customer retry recovered the invoice.',
        })
        cron_failed_attempt = self.env['subscription.payment.attempt'].create({
            'name': 'RECOVERY-PAY-004',
            'subscription_id': self.subscription.id,
            'invoice_id': self.invoice.id,
            'source': 'cron',
            'state': 'failed',
            'amount': 100.0,
            'failure_message': 'cron provider decline',
            'recovery_required': True,
        })
        pending_attempt = self.env['subscription.dunning.attempt'].create({
            'subscription_id': self.subscription.id,
            'invoice_id': self.invoice.id,
            'policy_id': self.policy.id,
            'action_type': 'email',
            'state': 'pending',
            'amount_at_risk': 100.0,
        })
        failed_attempt = self.env['subscription.dunning.attempt'].create({
            'subscription_id': self.subscription.id,
            'invoice_id': self.invoice.id,
            'policy_id': self.policy.id,
            'action_type': 'email',
            'state': 'failed',
            'amount_at_risk': 100.0,
            'error_message': 'mail gateway unavailable',
        })
        retryable_attempt = self.env['subscription.dunning.attempt'].create({
            'subscription_id': self.subscription.id,
            'invoice_id': self.invoice.id,
            'policy_id': self.policy.id,
            'action_type': 'email_and_retry',
            'state': 'done',
            'auto_retry_enabled': True,
            'max_auto_retries': 2,
            'next_auto_retry_at': fields.Datetime.now(),
        })
        retry_exhausted_attempt = self.env['subscription.dunning.attempt'].create({
            'subscription_id': self.subscription.id,
            'invoice_id': self.invoice.id,
            'policy_id': self.policy.id,
            'action_type': 'email_and_retry',
            'state': 'done',
            'auto_retry_enabled': True,
            'max_auto_retries': 1,
            'auto_retry_count': 1,
            'retry_exhausted': True,
        })
        final_attempt = self.env['subscription.dunning.attempt'].create({
            'subscription_id': self.subscription.id,
            'invoice_id': self.invoice.id,
            'policy_id': self.policy.id,
            'action_type': 'final_cancel',
            'state': 'done',
            'amount_at_risk': 100.0,
        })
        recovered_subscription = self.subscription.copy({
            'name': 'Recovered Recovery Dashboard Subscription',
            'subscription_state': 'active',
            'dunning_start_date': False,
            'next_dunning_date': False,
        })
        recovered_subscription._log_subscription_event('dunning_success', 'Recovered during dashboard test')
        self.env.flush_all()

        dashboard = self.env.ref('subscription_suite_billing.subscription_manager_operation_dashboard_main')
        domains = dashboard._dunning_recovery_domains()
        SaleOrder = self.env['sale.order']
        PaymentAttempt = self.env['subscription.payment.attempt']
        DunningAttempt = self.env['subscription.dunning.attempt']

        self.assertEqual(dashboard.active_dunning_count, SaleOrder.search_count(domains['active_dunning']))
        self.assertEqual(dashboard.failed_payment_count, PaymentAttempt.search_count(domains['failed_payments']))
        self.assertEqual(
            dashboard.portal_recovery_attempt_count,
            PaymentAttempt.search_count(domains['portal_recovery_attempts']),
        )
        self.assertEqual(
            dashboard.portal_recovery_pending_count,
            PaymentAttempt.search_count(domains['portal_recovery_pending']),
        )
        self.assertEqual(
            dashboard.portal_recovery_failed_count,
            PaymentAttempt.search_count(domains['portal_recovery_failed']),
        )
        self.assertEqual(
            dashboard.portal_recovery_recovered_count,
            PaymentAttempt.search_count(domains['portal_recovery_recovered']),
        )
        self.assertEqual(
            dashboard.portal_recovery_manual_action_count,
            PaymentAttempt.search_count(domains['portal_recovery_manual_action']),
        )
        self.assertEqual(
            dashboard.pending_dunning_attempt_count,
            DunningAttempt.search_count(domains['pending_dunning_attempts']),
        )
        self.assertEqual(
            dashboard.failed_dunning_attempt_count,
            DunningAttempt.search_count(domains['failed_dunning_attempts']),
        )
        self.assertEqual(
            dashboard.retryable_dunning_attempt_count,
            DunningAttempt.search_count(domains['retryable_dunning_attempts']),
        )
        self.assertEqual(
            dashboard.retry_exhausted_dunning_attempt_count,
            DunningAttempt.search_count(domains['retry_exhausted_dunning_attempts']),
        )
        self.assertEqual(
            dashboard.final_dunning_action_count,
            DunningAttempt.search_count(domains['final_dunning_actions']),
        )
        self.assertEqual(
            dashboard.past_due_mrr_at_risk,
            sum(SaleOrder.search(domains['active_dunning']).mapped('mrr')),
        )
        self.assertIn(self.subscription, SaleOrder.search(domains['active_dunning']))
        self.assertIn(payment_attempt, PaymentAttempt.search(domains['failed_payments']))
        self.assertIn(cron_failed_attempt, PaymentAttempt.search(domains['failed_payments']))
        self.assertIn(payment_attempt, PaymentAttempt.search(domains['portal_recovery_attempts']))
        self.assertIn(pending_portal_attempt, PaymentAttempt.search(domains['portal_recovery_pending']))
        self.assertIn(payment_attempt, PaymentAttempt.search(domains['portal_recovery_failed']))
        self.assertIn(recovered_portal_attempt, PaymentAttempt.search(domains['portal_recovery_recovered']))
        self.assertIn(payment_attempt, PaymentAttempt.search(domains['portal_recovery_manual_action']))
        self.assertNotIn(cron_failed_attempt, PaymentAttempt.search(domains['portal_recovery_attempts']))
        self.assertIn(pending_attempt, DunningAttempt.search(domains['pending_dunning_attempts']))
        self.assertIn(failed_attempt, DunningAttempt.search(domains['failed_dunning_attempts']))
        self.assertIn(retryable_attempt, DunningAttempt.search(domains['retryable_dunning_attempts']))
        self.assertIn(retry_exhausted_attempt, DunningAttempt.search(domains['retry_exhausted_dunning_attempts']))
        self.assertIn(final_attempt, DunningAttempt.search(domains['final_dunning_actions']))
        self.assertIn(recovered_subscription.id, dashboard._get_recovered_this_month_subscription_ids())

        self.assertEqual(dashboard.action_open_active_dunning()['domain'], domains['active_dunning'])
        self.assertEqual(dashboard.action_open_failed_payments()['domain'], domains['failed_payments'])
        self.assertEqual(
            dashboard.action_open_portal_recovery_attempts()['domain'],
            domains['portal_recovery_attempts'],
        )
        self.assertEqual(
            dashboard.action_open_portal_recovery_pending()['domain'],
            domains['portal_recovery_pending'],
        )
        self.assertEqual(
            dashboard.action_open_portal_recovery_failed()['domain'],
            domains['portal_recovery_failed'],
        )
        self.assertEqual(
            dashboard.action_open_portal_recovery_recovered()['domain'],
            domains['portal_recovery_recovered'],
        )
        self.assertEqual(
            dashboard.action_open_portal_recovery_manual_action()['domain'],
            domains['portal_recovery_manual_action'],
        )
        self.assertEqual(
            dashboard.action_open_pending_dunning_attempts()['domain'],
            domains['pending_dunning_attempts'],
        )
        self.assertEqual(
            dashboard.action_open_final_dunning_actions()['domain'],
            domains['final_dunning_actions'],
        )
        self.assertEqual(
            dashboard.action_open_retryable_dunning_attempts()['domain'],
            domains['retryable_dunning_attempts'],
        )
