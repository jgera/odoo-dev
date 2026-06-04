from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestBillingAttempts(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Billing Attempt Customer'})
        self.product = self.env['product.product'].create({
            'name': 'Billing Attempt Product',
            'type': 'service',
            'list_price': 100.0,
            'invoice_policy': 'order',
        })
        self.plan = self.env['subscription.plan'].create({
            'name': 'Billing Attempt Plan',
            'code': 'TEST-BILLING-ATTEMPT',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'plan_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 1.0,
                'price_unit': 100.0,
                'description': 'Billing Attempt Product',
            })],
        })

    def _create_due_subscription(self, with_line=True):
        values = {
            'partner_id': self.partner.id,
            'is_subscription': True,
            'subscription_state': 'active',
            'subscription_plan_id': self.plan.id,
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'subscription_start_date': fields.Date.today(),
            'next_invoice_date': fields.Date.today(),
        }
        if with_line:
            values['order_line'] = [(0, 0, {
                'product_id': self.product.id,
                'name': 'Billing Attempt Product',
                'product_uom_qty': 1.0,
                'price_unit': 100.0,
                'is_recurring': True,
            })]
        subscription = self.env['sale.order'].create(values)
        subscription.action_confirm()
        return subscription

    def test_cron_creates_successful_billing_attempt_and_invoice_once(self):
        subscription = self._create_due_subscription()

        first_run = self.env['sale.order']._cron_generate_subscription_invoices()
        subscription.invalidate_recordset()

        attempts = self.env['subscription.billing.attempt'].search([
            ('subscription_id', '=', subscription.id),
        ])
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts.state, 'success')
        self.assertTrue(attempts.invoice_id)
        self.assertEqual(attempts.invoice_id.subscription_id, subscription)
        self.assertEqual(attempts.invoice_id.subscription_period_start, fields.Date.today())
        self.assertEqual(attempts.invoice_id.subscription_period_end, fields.Date.today())
        self.assertEqual(first_run.success_count, 1)
        self.assertEqual(first_run.failed_count, 0)

        invoice = attempts.invoice_id
        second_run = self.env['sale.order']._cron_generate_subscription_invoices()
        second_attempts = self.env['subscription.billing.attempt'].search([
            ('subscription_id', '=', subscription.id),
        ])
        invoices = self.env['account.move'].search([
            ('subscription_id', '=', subscription.id),
        ])

        self.assertEqual(second_attempts, attempts)
        self.assertEqual(invoices, invoice)
        self.assertEqual(second_run.subscription_count, 0)

    def test_cron_records_skipped_attempt_when_no_invoice_is_generated(self):
        subscription = self._create_due_subscription(with_line=False)

        run = self.env['sale.order']._cron_generate_subscription_invoices()

        attempt = self.env['subscription.billing.attempt'].search([
            ('subscription_id', '=', subscription.id),
        ], limit=1)
        self.assertTrue(attempt)
        self.assertEqual(attempt.state, 'skipped')
        self.assertFalse(attempt.invoice_id)
        self.assertEqual(run.skipped_count, 1)

    def test_manual_retry_reuses_failed_attempt_and_creates_invoice(self):
        subscription = self._create_due_subscription()
        attempt = subscription._get_or_create_billing_attempt()
        attempt._record_failure(Exception('temporary connection timeout'))

        self.assertEqual(attempt.state, 'failed')
        self.assertTrue(attempt.retryable)
        self.assertEqual(attempt.failure_category, 'system')
        self.assertEqual(attempt.failure_count, 1)

        attempt.action_retry()

        self.assertEqual(attempt.state, 'success')
        self.assertTrue(attempt.invoice_id)
        self.assertEqual(attempt.attempt_no, 2)
        self.assertFalse(attempt.retryable)
        self.assertFalse(attempt.failure_category)

        attempts = self.env['subscription.billing.attempt'].search([
            ('subscription_id', '=', subscription.id),
        ])
        self.assertEqual(attempts, attempt)

    def test_cron_skips_subscription_already_locked_for_billing(self):
        subscription = self._create_due_subscription()
        subscription.write({
            'billing_in_progress': True,
            'billing_locked_at': fields.Datetime.now(),
        })

        run = self.env['sale.order']._cron_generate_subscription_invoices()

        self.assertEqual(run.subscription_count, 0)
        self.assertFalse(self.env['subscription.billing.attempt'].search([
            ('subscription_id', '=', subscription.id),
        ]))

    def test_retry_cron_processes_due_retryable_attempt(self):
        subscription = self._create_due_subscription()
        attempt = subscription._get_or_create_billing_attempt()
        attempt._record_failure(Exception('temporary connection timeout'))
        attempt.write({'next_retry_at': fields.Datetime.now() - timedelta(minutes=5)})

        retried_attempts = self.env['subscription.billing.attempt']._cron_retry_failed_billing_attempts()

        self.assertEqual(retried_attempts, attempt)
        self.assertEqual(attempt.state, 'success')
        self.assertTrue(attempt.invoice_id)
        self.assertEqual(attempt.attempt_no, 2)
        self.assertFalse(attempt.retry_exhausted)

    def test_retry_cron_marks_exhausted_attempt_and_schedules_activity(self):
        subscription = self._create_due_subscription()
        attempt = subscription._get_or_create_billing_attempt()
        attempt._record_failure(Exception('temporary connection timeout'))
        attempt.write({
            'attempt_no': 3,
            'next_retry_at': fields.Datetime.now() - timedelta(minutes=5),
        })
        self.env['ir.config_parameter'].sudo().set_param('subscription_suite.billing_retry_max_attempts', 3)

        self.env['subscription.billing.attempt']._cron_retry_failed_billing_attempts()

        self.assertEqual(attempt.state, 'failed')
        self.assertFalse(attempt.retryable)
        self.assertTrue(attempt.retry_exhausted)
        self.assertTrue(attempt.recovery_required)
        self.assertTrue(attempt.recovery_note)
        self.assertFalse(attempt.next_retry_at)
        activity = self.env['mail.activity'].search([
            ('res_model', '=', 'sale.order'),
            ('res_id', '=', subscription.id),
            ('summary', '=', 'Subscription billing needs manual recovery'),
        ])
        self.assertEqual(len(activity), 1)

    def test_repeated_failure_metadata_and_chatter_are_recorded(self):
        subscription = self._create_due_subscription()
        attempt = subscription._get_or_create_billing_attempt()

        attempt._record_failure(Exception('temporary connection timeout'))
        first_failure_at = attempt.first_failure_at
        attempt._record_failure(Exception('temporary connection timeout again'))

        self.assertEqual(attempt.state, 'failed')
        self.assertEqual(attempt.failure_count, 2)
        self.assertEqual(attempt.first_failure_at, first_failure_at)
        self.assertTrue(attempt.last_failure_at)
        self.assertEqual(attempt.last_failure_message, 'temporary connection timeout again')
        self.assertEqual(attempt.failure_category, 'system')
        self.assertTrue(attempt.retryable)
        self.assertFalse(attempt.recovery_required)
        self.assertIn('retry cron', attempt.recovery_note)
        failure_messages = attempt.message_ids.filtered(lambda message: 'Billing failure' in (message.body or ''))
        self.assertGreaterEqual(len(failure_messages), 2)

    def test_duplicate_exception_handler_does_not_double_count_same_failure(self):
        subscription = self._create_due_subscription()
        attempt = subscription._get_or_create_billing_attempt()

        error = Exception('temporary connection timeout')
        attempt._record_failure(error)
        attempt._record_failure_once(error)

        self.assertEqual(attempt.failure_count, 1)
        failure_messages = attempt.message_ids.filtered(lambda message: 'Billing failure' in (message.body or ''))
        self.assertEqual(len(failure_messages), 1)

    def test_non_retryable_failure_requires_recovery(self):
        subscription = self._create_due_subscription()
        attempt = subscription._get_or_create_billing_attempt()

        attempt._record_failure(Exception('missing income account'))

        self.assertEqual(attempt.state, 'failed')
        self.assertEqual(attempt.failure_category, 'configuration')
        self.assertFalse(attempt.retryable)
        self.assertTrue(attempt.recovery_required)
        self.assertIn('Configuration issue', attempt.recovery_note)

    def test_retry_policy_settings_update_config_parameters(self):
        settings = self.env['res.config.settings'].create({
            'subscription_billing_retry_max_attempts': 5,
            'subscription_billing_retry_batch_size': 25,
            'subscription_billing_retry_delay_hours': 2,
        })

        settings.execute()

        ICP = self.env['ir.config_parameter'].sudo()
        self.assertEqual(ICP.get_param('subscription_suite.billing_retry_max_attempts'), '5')
        self.assertEqual(ICP.get_param('subscription_suite.billing_retry_batch_size'), '25')
        self.assertEqual(ICP.get_param('subscription_suite.billing_retry_delay_hours'), '2')

    def test_retry_policy_settings_reject_invalid_values(self):
        with self.assertRaises(ValidationError):
            self.env['res.config.settings'].create({
                'subscription_billing_retry_max_attempts': 0,
                'subscription_billing_retry_batch_size': 25,
                'subscription_billing_retry_delay_hours': 2,
            })
