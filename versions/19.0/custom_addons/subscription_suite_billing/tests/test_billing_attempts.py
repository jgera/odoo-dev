from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.fields import Command
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

    def _create_subscription_invoice(self, subscription):
        invoice = subscription._generate_subscription_invoice()
        self.assertTrue(invoice)
        return invoice

    def test_seat_subscription_invoice_uses_line_quantity_and_price(self):
        subscription = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'is_subscription': True,
            'subscription_state': 'active',
            'subscription_plan_id': self.plan.id,
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'subscription_start_date': fields.Date.today(),
            'next_invoice_date': fields.Date.today(),
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'name': 'Billing Attempt Seats',
                'product_uom_qty': 6.0,
                'price_unit': 15.0,
                'is_recurring': True,
                'subscription_component_type': 'seat',
            })],
        })
        subscription.action_confirm()

        invoice = self._create_subscription_invoice(subscription)
        invoice_line = invoice.invoice_line_ids.filtered(lambda line: line.product_id == self.product)[:1]

        self.assertEqual(subscription.seat_quantity, 6.0)
        self.assertEqual(invoice_line.quantity, 6.0)
        self.assertAlmostEqual(invoice_line.price_unit, 15.0, places=2)
        self.assertAlmostEqual(invoice_line.price_subtotal, 90.0, places=2)
        self.assertAlmostEqual(invoice.amount_untaxed, 90.0, places=2)

    def _create_payment_provider(self):
        payment_method = self.env.ref('payment.payment_method_unknown')
        redirect_form = self.env['ir.ui.view'].create({
            'name': 'Subscription Payment Attempt Dummy Redirect Form',
            'type': 'qweb',
            'arch': '<form action="dummy" method="post"/>',
        })
        provider = self.env['payment.provider'].create({
            'name': 'Subscription Payment Attempt Dummy Provider',
            'code': 'none',
            'state': 'test',
            'is_published': True,
            'allow_tokenization': True,
            'payment_method_ids': [Command.set([payment_method.id])],
            'redirect_form_view_id': redirect_form.id,
            'available_currency_ids': [Command.set([self.env.company.currency_id.id])],
        })
        payment_method.write({
            'active': True,
            'support_tokenization': True,
        })
        return provider

    def _create_payment_transaction(self, subscription, invoice, state='done', state_message=None):
        provider = self._create_payment_provider()
        payment_method = provider.payment_method_ids[:1]
        token = self.env['payment.token'].sudo().create({
            'provider_id': provider.id,
            'payment_method_id': payment_method.id,
            'payment_details': '4242',
            'partner_id': subscription.partner_id.id,
            'provider_ref': 'subscription-payment-attempt-token',
            'active': True,
        })
        subscription.payment_token_id = token.id
        transaction = self.env['payment.transaction'].sudo().create({
            'provider_id': provider.id,
            'payment_method_id': payment_method.id,
            'token_id': token.id,
            'operation': 'online_token',
            'amount': invoice.amount_total,
            'currency_id': invoice.currency_id.id,
            'partner_id': subscription.partner_id.id,
            'reference': '%s-%s' % (invoice.name, state),
        })
        if state == 'done':
            transaction._set_done(state_message=state_message)
        elif state == 'error':
            transaction._set_error(state_message or 'Payment was declined')
        elif state == 'cancel':
            transaction._set_canceled(state_message=state_message)
        elif state == 'pending':
            transaction._set_pending(state_message=state_message)
        return transaction

    def _create_payment_token(self, subscription, provider_ref='subscription-payment-attempt-token', details='4242'):
        provider = self._create_payment_provider()
        payment_method = provider.payment_method_ids[:1]
        return self.env['payment.token'].sudo().create({
            'provider_id': provider.id,
            'payment_method_id': payment_method.id,
            'payment_details': details,
            'partner_id': subscription.partner_id.id,
            'provider_ref': provider_ref,
            'active': True,
        })

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

    def test_payment_attempt_creation_records_invoice_context(self):
        subscription = self._create_due_subscription()
        invoice = self._create_subscription_invoice(subscription)

        attempt = self.env['subscription.payment.attempt']._create_for_invoice(
            subscription,
            invoice,
            source='portal',
            requested_by=self.env.user,
        )

        self.assertEqual(attempt.subscription_id, subscription)
        self.assertEqual(attempt.invoice_id, invoice)
        self.assertEqual(attempt.partner_id, subscription.partner_id)
        self.assertEqual(attempt.source, 'portal')
        self.assertEqual(attempt.state, 'pending')
        self.assertEqual(attempt.amount, invoice.amount_residual or invoice.amount_total)
        self.assertEqual(attempt.token_role, 'primary')

    def test_payment_attempt_finalize_success_from_transaction(self):
        subscription = self._create_due_subscription()
        invoice = self._create_subscription_invoice(subscription)
        attempt = self.env['subscription.payment.attempt']._create_for_invoice(subscription, invoice)
        transaction = self._create_payment_transaction(subscription, invoice, state='done')

        mapped_state = attempt._finalize_from_transaction(transaction)

        self.assertEqual(mapped_state, 'success')
        self.assertEqual(attempt.state, 'success')
        self.assertEqual(attempt.transaction_id, transaction)
        self.assertEqual(attempt.provider_id, transaction.provider_id)
        self.assertEqual(attempt.provider_state, 'done')
        self.assertFalse(attempt.recovery_required)
        self.assertFalse(attempt.failure_message)

    def test_payment_attempt_finalize_failed_transaction_requires_recovery(self):
        subscription = self._create_due_subscription()
        invoice = self._create_subscription_invoice(subscription)
        attempt = self.env['subscription.payment.attempt']._create_for_invoice(subscription, invoice)
        transaction = self._create_payment_transaction(
            subscription,
            invoice,
            state='error',
            state_message='card declined',
        )

        mapped_state = attempt._finalize_from_transaction(transaction)

        self.assertEqual(mapped_state, 'failed')
        self.assertEqual(attempt.state, 'failed')
        self.assertEqual(attempt.provider_state, 'error')
        self.assertTrue(attempt.recovery_required)
        self.assertIn('card declined', attempt.failure_message)
        self.assertTrue(attempt.recovery_note)

    def test_pending_payment_attempt_refresh_stays_pending(self):
        subscription = self._create_due_subscription()
        invoice = self._create_subscription_invoice(subscription)
        attempt = self.env['subscription.payment.attempt']._create_for_invoice(subscription, invoice)
        transaction = self._create_payment_transaction(subscription, invoice, state='pending')
        attempt._finalize_from_transaction(transaction)

        result = attempt.action_refresh_transaction_state()

        self.assertTrue(result)
        self.assertEqual(attempt.state, 'pending')
        self.assertEqual(attempt.provider_state, 'pending')
        self.assertFalse(attempt.completed_at)
        self.assertFalse(attempt.recovery_required)

    def test_pending_payment_attempt_refresh_to_success_logs_outcome(self):
        subscription = self._create_due_subscription()
        invoice = self._create_subscription_invoice(subscription)
        attempt = self.env['subscription.payment.attempt']._create_for_invoice(subscription, invoice)
        transaction = self._create_payment_transaction(subscription, invoice, state='pending')
        attempt._finalize_from_transaction(transaction)

        transaction._set_done()
        attempt.action_refresh_transaction_state()

        self.assertEqual(attempt.state, 'success')
        self.assertEqual(attempt.provider_state, 'done')
        self.assertTrue(attempt.completed_at)
        self.assertFalse(attempt.recovery_required)
        self.assertIn('refreshed', attempt.message_ids[:1].body)
        self.assertTrue(subscription.subscription_log_ids.filtered(lambda log: log.event_type == 'payment_success'))

    def test_pending_payment_attempt_refresh_to_cancelled_requires_recovery(self):
        subscription = self._create_due_subscription()
        invoice = self._create_subscription_invoice(subscription)
        attempt = self.env['subscription.payment.attempt']._create_for_invoice(subscription, invoice)
        transaction = self._create_payment_transaction(subscription, invoice, state='pending')
        attempt._finalize_from_transaction(transaction)

        transaction._set_canceled(state_message='customer cancelled')
        attempt.action_refresh_transaction_state()

        self.assertEqual(attempt.state, 'cancelled')
        self.assertEqual(attempt.provider_state, 'cancel')
        self.assertTrue(attempt.completed_at)
        self.assertTrue(attempt.recovery_required)
        self.assertIn('customer cancelled', attempt.failure_message)
        self.assertTrue(subscription.subscription_log_ids.filtered(lambda log: log.event_type == 'payment_failed'))

    def test_payment_attempt_exception_records_recovery_context(self):
        subscription = self._create_due_subscription()
        invoice = self._create_subscription_invoice(subscription)
        attempt = self.env['subscription.payment.attempt']._create_for_invoice(subscription, invoice)

        attempt._record_exception(Exception('provider timeout'))

        self.assertEqual(attempt.state, 'error')
        self.assertTrue(attempt.completed_at)
        self.assertTrue(attempt.recovery_required)
        self.assertIn('provider timeout', attempt.failure_message)

    def test_backup_payment_token_cannot_match_primary(self):
        subscription = self._create_due_subscription()
        token = self._create_payment_token(subscription)
        subscription.payment_token_id = token.id

        with self.assertRaises(ValidationError):
            subscription.backup_payment_token_id = token.id

    def test_backup_payment_token_must_belong_to_customer(self):
        subscription = self._create_due_subscription()
        other_subscription = self._create_due_subscription()
        other_subscription.partner_id = self.env['res.partner'].create({'name': 'Other Backup Customer'})
        token = self._create_payment_token(other_subscription, provider_ref='other-backup-token')

        with self.assertRaises(ValidationError):
            subscription.backup_payment_token_id = token.id

    def test_payment_collection_uses_primary_before_failure(self):
        subscription = self._create_due_subscription()
        invoice = self._create_subscription_invoice(subscription)
        primary = self._create_payment_token(subscription, provider_ref='primary-token')
        backup = self._create_payment_token(subscription, provider_ref='backup-token', details='1881')
        subscription.write({
            'payment_token_id': primary.id,
            'backup_payment_token_id': backup.id,
        })

        token, token_role = subscription._get_payment_collection_token(invoice)

        self.assertEqual(token, primary)
        self.assertEqual(token_role, 'primary')

    def test_payment_collection_uses_backup_after_primary_failure(self):
        subscription = self._create_due_subscription()
        invoice = self._create_subscription_invoice(subscription)
        primary = self._create_payment_token(subscription, provider_ref='primary-token')
        backup = self._create_payment_token(subscription, provider_ref='backup-token', details='1881')
        subscription.write({
            'payment_token_id': primary.id,
            'backup_payment_token_id': backup.id,
        })
        self.env['subscription.payment.attempt']._create_for_invoice(
            subscription,
            invoice,
            token=primary,
            token_role='primary',
        ).write({'state': 'failed', 'recovery_required': True})

        token, token_role = subscription._get_payment_collection_token(invoice)

        self.assertEqual(token, backup)
        self.assertEqual(token_role, 'backup')

    def test_payment_collection_returns_to_primary_after_backup_failure(self):
        subscription = self._create_due_subscription()
        invoice = self._create_subscription_invoice(subscription)
        primary = self._create_payment_token(subscription, provider_ref='primary-token')
        backup = self._create_payment_token(subscription, provider_ref='backup-token', details='1881')
        subscription.write({
            'payment_token_id': primary.id,
            'backup_payment_token_id': backup.id,
        })
        self.env['subscription.payment.attempt']._create_for_invoice(
            subscription,
            invoice,
            token=backup,
            token_role='backup',
        ).write({'state': 'failed', 'recovery_required': True})

        token, token_role = subscription._get_payment_collection_token(invoice)

        self.assertEqual(token, primary)
        self.assertEqual(token_role, 'primary')

    def test_auto_collect_records_backup_token_role_after_primary_failure(self):
        subscription = self._create_due_subscription()
        invoice = self._create_subscription_invoice(subscription)
        primary = self._create_payment_token(subscription, provider_ref='primary-token')
        backup = self._create_payment_token(subscription, provider_ref='backup-token', details='1881')
        subscription.write({
            'payment_token_id': primary.id,
            'backup_payment_token_id': backup.id,
        })
        self.env['subscription.payment.attempt']._create_for_invoice(
            subscription,
            invoice,
            token=primary,
            token_role='primary',
        ).write({'state': 'failed', 'recovery_required': True})

        def fake_send_payment_request(transactions):
            transactions._set_pending()

        with patch.object(self.env.registry['payment.transaction'], '_send_payment_request', fake_send_payment_request):
            transaction = subscription._auto_collect_payment(invoice, source='manual', requested_by=self.env.user)

        attempt = self.env['subscription.payment.attempt'].search([
            ('subscription_id', '=', subscription.id),
            ('invoice_id', '=', invoice.id),
        ], limit=1, order='attempt_date desc, id desc')
        self.assertEqual(transaction.token_id, backup)
        self.assertEqual(attempt.token_id, backup)
        self.assertEqual(attempt.token_role, 'backup')

    def test_subscription_payment_attempt_stat_action_filters_subscription(self):
        subscription = self._create_due_subscription()

        action = subscription.action_view_payment_attempts()

        self.assertEqual(action['res_model'], 'subscription.payment.attempt')
        self.assertEqual(action['domain'], [('subscription_id', '=', subscription.id)])
