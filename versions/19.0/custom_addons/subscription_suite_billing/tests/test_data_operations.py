import base64
import csv
import io
from datetime import date

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestSubscriptionDataOperations(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Operation = self.env['subscription.data.operation']
        self.company = self.env.company
        self.partner = self.env['res.partner'].create({
            'name': 'Migration Customer',
            'ref': 'MIG-CUSTOMER',
        })
        self.product = self.env['product.product'].create({
            'name': 'Migration Service',
            'default_code': 'MIG-SERVICE',
            'type': 'service',
            'list_price': 75.0,
        })
        self.plan = self.env['subscription.plan'].create({
            'name': 'Migration Existing Plan',
            'code': 'MIG-EXISTING',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.pricelist = self.env['product.pricelist'].create({
            'name': 'Migration Pricelist',
            'currency_id': self.company.currency_id.id,
            'company_id': self.company.id,
        })
        self.meter = self.env['subscription.usage.meter'].create({
            'name': 'Migration API Calls',
            'code': 'MIG-API',
            'uom_id': self.env.ref('uom.product_uom_unit').id,
            'company_id': self.company.id,
        })
        self.user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Migration Restricted User',
            'login': 'migration-user@example.com',
            'email': 'migration-user@example.com',
            'company_id': self.company.id,
            'company_ids': [Command.set(self.company.ids)],
            'group_ids': [Command.set([
                self.env.ref('base.group_user').id,
                self.env.ref('subscription_suite.group_subscription_user').id,
            ])],
        })

    def _csv(self, headers, rows):
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=headers, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
        return base64.b64encode(output.getvalue().encode())

    def _run_csv(self, template, headers, rows, mode='validate', validation=False):
        return self.Operation.execute_csv(
            template,
            mode,
            self.company,
            '%s.csv' % template,
            self._csv(headers, rows),
            validation_run=validation,
        )

    def _subscription(self, reference='MIG-SUB-1', state='active'):
        return self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'pricelist_id': self.pricelist.id,
            'company_id': self.company.id,
            'is_subscription': True,
            'subscription_import_reference': reference,
            'subscription_plan_id': self.plan.id,
            'subscription_state': state,
            'subscription_start_date': date(2026, 1, 1),
            'next_invoice_date': date(2026, 7, 1),
            'order_line': [Command.create({
                'product_id': self.product.id,
                'name': self.product.name,
                'product_uom_qty': 1.0,
                'price_unit': 75.0,
                'is_recurring': True,
            })],
        })

    def _payment_token(self, partner, provider_ref):
        payment_method = self.env.ref('payment.payment_method_unknown')
        redirect_form = self.env['ir.ui.view'].create({
            'name': 'Migration Dummy Redirect Form %s' % provider_ref,
            'type': 'qweb',
            'arch': '<form action="dummy" method="post"/>',
        })
        provider = self.env['payment.provider'].create({
            'name': 'Migration Dummy Provider %s' % provider_ref,
            'code': 'none',
            'state': 'test',
            'allow_tokenization': True,
            'payment_method_ids': [Command.set([payment_method.id])],
            'redirect_form_view_id': redirect_form.id,
            'available_currency_ids': [Command.set([self.company.currency_id.id])],
        })
        payment_method.write({
            'active': True,
            'support_tokenization': True,
        })
        token = self.env['payment.token'].sudo().create({
            'provider_id': provider.id,
            'payment_method_id': payment_method.id,
            'payment_details': '4242',
            'partner_id': partner.id,
            'provider_ref': provider_ref,
            'active': True,
        })
        return provider, token

    def test_schema_failure_is_audited_without_business_mutation(self):
        operation = self._run_csv('plans', ['code'], [{'code': 'BAD'}])

        self.assertEqual(operation.state, 'failed')
        self.assertTrue(operation.schema_error)
        self.assertEqual(operation.operation_run_id.state, 'failed')
        self.assertFalse(self.env['subscription.plan'].search([('code', '=', 'BAD')]))

    def test_validate_then_apply_plan_is_idempotent(self):
        headers = [
            'code', 'name', 'billing_interval_count', 'billing_interval_unit',
            'trial_days', 'currency',
        ]
        rows = [{
            'code': 'MIG-PLAN',
            'name': 'Imported Plan',
            'billing_interval_count': '1',
            'billing_interval_unit': 'month',
            'trial_days': '7',
            'currency': self.company.currency_id.name,
        }]
        validation = self._run_csv('plans', headers, rows)
        self.assertEqual(validation.state, 'success')
        self.assertFalse(self.env['subscription.plan'].search([('code', '=', 'MIG-PLAN')]))

        applied = self._run_csv('plans', headers, rows, mode='apply', validation=validation)
        rerun = self._run_csv('plans', headers, rows, mode='apply', validation=validation)
        plans = self.env['subscription.plan'].search([
            ('code', '=', 'MIG-PLAN'), ('company_id', '=', self.company.id),
        ])

        self.assertEqual(len(plans), 1)
        self.assertEqual(applied.created_count, 1)
        self.assertEqual(rerun.updated_count, 1)
        self.assertEqual(applied.operation_run_id.state, 'success')

    def test_subscription_and_line_import_resolve_stable_references(self):
        subscription_headers = [
            'external_reference', 'partner_ref', 'plan_code', 'state',
            'pricelist_name', 'currency',
        ]
        subscription_rows = [{
            'external_reference': 'MIG-CSV-SUB',
            'partner_ref': self.partner.ref,
            'plan_code': self.plan.code,
            'state': 'active',
            'pricelist_name': self.pricelist.name,
            'currency': self.company.currency_id.name,
        }]
        validation = self._run_csv('subscriptions', subscription_headers, subscription_rows)
        applied = self._run_csv(
            'subscriptions', subscription_headers, subscription_rows,
            mode='apply', validation=validation,
        )
        subscription = self.env['sale.order'].search([
            ('subscription_import_reference', '=', 'MIG-CSV-SUB'),
        ])
        self.assertEqual(applied.created_count, 1, applied.line_ids.mapped('message'))
        self.assertEqual(subscription.partner_id, self.partner)

        line_headers = [
            'subscription_reference', 'line_reference', 'product_default_code',
        ]
        line_rows = [{
            'subscription_reference': 'MIG-CSV-SUB',
            'line_reference': 'BASE',
            'product_default_code': self.product.default_code,
        }]
        line_validation = self._run_csv('subscription_lines', line_headers, line_rows)
        self._run_csv(
            'subscription_lines', line_headers, line_rows,
            mode='apply', validation=line_validation,
        )
        lines = subscription.order_line.filtered(
            lambda line: line.subscription_import_reference == 'BASE'
        )
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines.is_recurring)

    def test_row_isolation_and_error_report(self):
        headers = [
            'code', 'name', 'billing_interval_count', 'billing_interval_unit',
            'currency',
        ]
        rows = [
            {
                'code': 'MIG-GOOD', 'name': 'Good', 'billing_interval_count': '1',
                'billing_interval_unit': 'month', 'currency': self.company.currency_id.name,
            },
            {
                'code': 'MIG-BAD', 'name': 'Bad', 'billing_interval_count': '0',
                'billing_interval_unit': 'invalid', 'currency': self.company.currency_id.name,
            },
        ]
        validation = self._run_csv('plans', headers, rows)
        applied = self._run_csv('plans', headers, rows, mode='apply', validation=validation)

        self.assertEqual(applied.state, 'partial')
        self.assertEqual(applied.created_count, 1)
        self.assertEqual(applied.failed_count, 1)
        self.assertTrue(applied.error_report)
        self.assertTrue(self.env['subscription.plan'].search([('code', '=', 'MIG-GOOD')]))

    def test_usage_event_import_is_idempotent(self):
        subscription = self._subscription()
        headers = [
            'external_reference', 'subscription_reference', 'meter_code',
            'event_date', 'quantity',
        ]
        rows = [{
            'external_reference': 'MIG-USAGE-1',
            'subscription_reference': subscription.subscription_import_reference,
            'meter_code': self.meter.code,
            'event_date': '2026-06-01',
            'quantity': '12',
        }]
        validation = self._run_csv('usage_events', headers, rows)
        first = self._run_csv('usage_events', headers, rows, mode='apply', validation=validation)
        second = self._run_csv('usage_events', headers, rows, mode='apply', validation=validation)

        self.assertEqual(first.created_count, 1)
        self.assertEqual(second.updated_count, 1)
        self.assertEqual(self.env['subscription.usage.event'].search_count([
            ('external_reference', '=', 'MIG-USAGE-1'),
        ]), 1)

    def test_payment_assignment_requires_existing_customer_token(self):
        subscription = self._subscription('MIG-PAYMENT')
        other_partner = self.env['res.partner'].create({
            'name': 'Other Migration Customer',
            'ref': 'MIG-OTHER-CUSTOMER',
        })
        provider, other_token = self._payment_token(other_partner, 'migration-other-token')
        headers = [
            'subscription_reference', 'role', 'provider_code', 'provider_reference',
        ]
        unsafe_rows = [{
            'subscription_reference': subscription.subscription_import_reference,
            'role': 'primary',
            'provider_code': provider.code,
            'provider_reference': other_token.provider_ref,
        }]
        unsafe_validation = self._run_csv('payment_assignments', headers, unsafe_rows)
        unsafe_apply = self._run_csv(
            'payment_assignments', headers, unsafe_rows,
            mode='apply', validation=unsafe_validation,
        )

        self.assertEqual(unsafe_apply.failed_count, 1)
        self.assertFalse(subscription.payment_token_id)

        provider, own_token = self._payment_token(self.partner, 'migration-own-token')
        safe_rows = [{
            'subscription_reference': subscription.subscription_import_reference,
            'role': 'primary',
            'provider_code': provider.code,
            'provider_reference': own_token.provider_ref,
        }]
        safe_validation = self._run_csv('payment_assignments', headers, safe_rows)
        safe_apply = self._run_csv(
            'payment_assignments', headers, safe_rows,
            mode='apply', validation=safe_validation,
        )

        subscription.invalidate_recordset(['payment_token_id'])
        self.assertEqual(safe_apply.updated_count, 1)
        self.assertEqual(subscription.payment_token_id, own_token)

    def test_mrr_backfill_is_idempotent_and_skips_historical_states(self):
        live = self._subscription('MIG-MRR-LIVE')
        cancelled = self._subscription('MIG-MRR-CANCELLED', state='cancelled')
        live.invalidate_recordset(['mrr'])

        validation = self.Operation.execute_mrr_backfill('validate', self.company)
        applied = self.Operation.execute_mrr_backfill('apply', self.company)
        rerun = self.Operation.execute_mrr_backfill('apply', self.company)

        movement = self.env['subscription.mrr.movement'].search([
            ('backfill_key', '=', 'mrr-backfill:%s' % live.id),
        ])
        self.assertTrue(validation)
        self.assertEqual(len(movement), 1)
        self.assertEqual(movement.amount, live.mrr)
        self.assertFalse(self.env['subscription.mrr.movement'].search([
            ('subscription_id', '=', cancelled.id),
        ]))
        self.assertGreater(rerun.skipped_count, 0)

    def test_billing_attempt_backfill_links_valid_invoice_once(self):
        subscription = self._subscription('MIG-BILLING')
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'subscription_id': subscription.id,
            'invoice_date': date(2026, 5, 1),
            'subscription_period_start': date(2026, 5, 1),
            'subscription_period_end': date(2026, 6, 1),
            'invoice_line_ids': [Command.create({
                'product_id': self.product.id,
                'name': self.product.name,
                'quantity': 1.0,
                'price_unit': 75.0,
            })],
        })
        invoice.action_post()

        validation = self.Operation.execute_billing_attempt_backfill(
            'validate', self.company, date(2026, 5, 1), date(2026, 5, 31)
        )
        applied = self.Operation.execute_billing_attempt_backfill(
            'apply', self.company, date(2026, 5, 1), date(2026, 5, 31)
        )
        rerun = self.Operation.execute_billing_attempt_backfill(
            'apply', self.company, date(2026, 5, 1), date(2026, 5, 31)
        )
        attempts = self.env['subscription.billing.attempt'].search([
            ('invoice_id', '=', invoice.id),
        ])

        self.assertTrue(validation)
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts.state, 'success')
        self.assertGreaterEqual(applied.created_count, 1)
        self.assertGreater(rerun.skipped_count, 0)

    def test_non_manager_cannot_run_or_read_data_operations(self):
        with self.assertRaises(AccessError):
            self.Operation.with_user(self.user).execute_mrr_backfill('validate', self.company)
        with self.assertRaises(AccessError):
            self.Operation.with_user(self.user).search([]).read(['name'])
