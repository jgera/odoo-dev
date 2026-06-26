from datetime import date, timedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class TestSubscriptionBillingPerformanceSmoke(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Billing Performance Customer'})
        self.product = self.env['product.product'].create({
            'name': 'Billing Performance Service',
            'type': 'service',
            'list_price': 100.0,
            'invoice_policy': 'order',
        })
        self.plan = self.env['subscription.plan'].create({
            'name': 'Billing Performance Monthly',
            'code': 'PERF-BILLING-MONTHLY',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'plan_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 1.0,
                'price_unit': 100.0,
                'description': 'Billing Performance Service',
            })],
        })
        self.period_start = fields.Date.today() - timedelta(days=30)
        self.period_end = fields.Date.today()
        self.deferred_account = self.env['account.account'].search(
            [('account_type', 'in', ('liability_current', 'liability_non_current'))],
            limit=1,
        ) or self.env['account.account'].search([('account_type', '!=', 'off_balance')], limit=1)
        self.revenue_account = self.env['account.account'].search(
            [('account_type', '=', 'income')],
            limit=1,
        ) or self.deferred_account
        self.recognition_journal = self.env['account.journal'].search([('type', '=', 'general')], limit=1)
        self.env.company.write({
            'subscription_deferred_revenue_account_id': self.deferred_account.id,
            'subscription_revenue_account_id': self.revenue_account.id,
            'subscription_recognition_journal_id': self.recognition_journal.id,
            'subscription_default_recognition_method': 'straight_line_daily',
        })
        self.deferred_account = self.env['account.account'].search(
            [('account_type', 'in', ('liability_current', 'liability_non_current'))],
            limit=1,
        ) or self.env['account.account'].search([('account_type', '!=', 'off_balance')], limit=1)
        self.revenue_account = self.env['account.account'].search(
            [('account_type', '=', 'income')],
            limit=1,
        ) or self.deferred_account
        self.recognition_journal = self.env['account.journal'].search([('type', '=', 'general')], limit=1)
        self.env.company.write({
            'subscription_deferred_revenue_account_id': self.deferred_account.id,
            'subscription_revenue_account_id': self.revenue_account.id,
            'subscription_recognition_journal_id': self.recognition_journal.id,
            'subscription_default_recognition_method': 'straight_line_daily',
        })

    def _create_subscription(self, index, subscription_state='active', due=True):
        next_invoice_date = self.period_end if due else self.period_end + timedelta(days=10)
        subscription = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'is_subscription': True,
            'subscription_state': subscription_state,
            'subscription_plan_id': self.plan.id,
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'subscription_start_date': self.period_start,
            'last_invoice_date': self.period_start,
            'next_invoice_date': next_invoice_date,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'name': 'Billing Performance Service %s' % index,
                'product_uom_qty': 1.0,
                'price_unit': 100.0,
                'is_recurring': True,
            })],
        })
        subscription.action_confirm()
        return subscription

    def test_billing_cron_medium_smoke_is_scoped_and_idempotent(self):
        due_subscriptions = self.env['sale.order']
        for index in range(12):
            due_subscriptions |= self._create_subscription(index)
        future_subscription = self._create_subscription('future', due=False)
        paused_subscription = self._create_subscription('paused', subscription_state='paused')

        self.env['sale.order']._cron_generate_subscription_invoices()
        first_attempts = self.env['subscription.billing.attempt'].search([
            ('subscription_id', 'in', due_subscriptions.ids),
        ])

        self.assertEqual(len(first_attempts), len(due_subscriptions))
        self.assertFalse(self.env['subscription.billing.attempt'].search([
            ('subscription_id', 'in', (future_subscription | paused_subscription).ids),
        ]))
        self.assertEqual(set(first_attempts.mapped('state')), {'success'})

        self.env['sale.order']._cron_generate_subscription_invoices()
        second_attempts = self.env['subscription.billing.attempt'].search([
            ('subscription_id', 'in', due_subscriptions.ids),
        ])

        self.assertEqual(second_attempts, first_attempts)
        self.assertTrue(all(subscription.next_invoice_date > self.period_end for subscription in due_subscriptions))

    def _create_schedule(self, amount=120.0, period_start=False, period_end=False):
        period_start = period_start or date(2026, 1, 1)
        period_end = period_end or date(2026, 4, 1)
        subscription = self._create_subscription('recognition-%s' % amount)
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'subscription_id': subscription.id,
            'invoice_date': period_start,
            'subscription_period_start': period_start,
            'subscription_period_end': period_end,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'name': 'Billing Performance Recognition',
                'quantity': 1.0,
                'price_unit': amount,
            })],
        })
        invoice.action_post()
        return self.env['subscription.deferred.revenue'].generate_for_invoices(invoice)

    def test_recognition_preview_medium_smoke_is_scoped_and_non_mutating(self):
        due_schedule = self._create_schedule(amount=120.0)
        future_schedule = self._create_schedule(
            amount=240.0,
            period_start=date(2026, 5, 1),
            period_end=date(2026, 8, 1),
        )
        due_lines = due_schedule.line_ids.filtered(lambda line: line.period_end <= date(2026, 4, 1))

        preview_lines = self.env['subscription.deferred.revenue.line']._get_lines_for_recognition_preview(
            date(2026, 4, 1),
            company=self.env.company,
        )

        self.assertTrue(due_lines)
        self.assertTrue(due_lines <= preview_lines)
        self.assertFalse(future_schedule.line_ids & preview_lines)
        self.assertEqual(set(due_schedule.line_ids.mapped('state')), {'draft'})
        self.assertEqual(set(future_schedule.line_ids.mapped('state')), {'draft'})
