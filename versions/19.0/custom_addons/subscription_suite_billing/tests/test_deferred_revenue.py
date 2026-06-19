from datetime import date

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestSubscriptionDeferredRevenue(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Deferred Revenue Customer'})
        self.product = self.env['product.product'].create({
            'name': 'Deferred Revenue Product',
            'type': 'service',
            'list_price': 1200.0,
            'invoice_policy': 'order',
        })
        self.plan = self.env['subscription.plan'].create({
            'name': 'Deferred Revenue Annual',
            'code': 'DEFERRED-ANNUAL',
            'billing_interval_count': 1,
            'billing_interval_unit': 'year',
            'plan_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 1.0,
                'price_unit': 1200.0,
                'description': 'Deferred Revenue Product',
            })],
        })
        self.period_start = date(2026, 1, 1)
        self.period_end = date(2026, 4, 1)

    def _create_subscription(self, amount=1200.0, period_start=False, period_end=False):
        period_start = period_start or self.period_start
        period_end = period_end or self.period_end
        subscription = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'is_subscription': True,
            'subscription_state': 'active',
            'subscription_plan_id': self.plan.id,
            'billing_interval_count': 1,
            'billing_interval_unit': 'year',
            'subscription_start_date': period_start,
            'last_invoice_date': period_start,
            'next_invoice_date': period_end,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'name': 'Deferred Revenue Product',
                'product_uom_qty': 1.0,
                'price_unit': amount,
                'is_recurring': True,
            })],
        })
        subscription.action_confirm()
        return subscription

    def _create_posted_subscription_invoice(self, amount=1200.0, period_start=False, period_end=False):
        subscription = self._create_subscription(
            amount=amount,
            period_start=period_start,
            period_end=period_end,
        )
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'subscription_id': subscription.id,
            'subscription_period_start': period_start or self.period_start,
            'subscription_period_end': period_end or self.period_end,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'name': 'Deferred Revenue Product',
                'quantity': 1.0,
                'price_unit': amount,
            })],
        })
        invoice.action_post()
        return subscription, invoice

    def test_posted_subscription_invoice_creates_ready_schedule(self):
        subscription, invoice = self._create_posted_subscription_invoice()

        schedules = self.env['subscription.deferred.revenue'].generate_for_invoices(invoice)
        schedule = schedules[:1]

        self.assertEqual(schedule.state, 'ready', schedule.block_reason)
        self.assertEqual(schedule.subscription_id, subscription)
        self.assertEqual(schedule.invoice_id, invoice)
        self.assertEqual(schedule.service_period_start, self.period_start)
        self.assertEqual(schedule.service_period_end, self.period_end)
        self.assertAlmostEqual(schedule.amount_total, invoice.amount_untaxed, places=2)
        self.assertEqual(len(schedule.line_ids), 3, schedule.block_reason)
        self.assertAlmostEqual(sum(schedule.line_ids.mapped('amount')), invoice.amount_untaxed, places=2)

    def test_rerun_updates_existing_schedule_without_duplicates(self):
        _subscription, invoice = self._create_posted_subscription_invoice()

        first = self.env['subscription.deferred.revenue'].generate_for_invoices(invoice)
        second = self.env['subscription.deferred.revenue'].generate_for_invoices(
            invoice,
            method='equal_monthly',
        )

        self.assertEqual(first, second)
        self.assertEqual(
            self.env['subscription.deferred.revenue'].search_count([('invoice_id', '=', invoice.id)]),
            1,
        )
        self.assertEqual(second.recognition_method, 'equal_monthly')
        self.assertEqual(len(second.line_ids), 3)

    def test_straight_line_daily_allocation_reconciles_with_rounding(self):
        _subscription, invoice = self._create_posted_subscription_invoice(
            amount=1000.0,
            period_start=date(2026, 1, 15),
            period_end=date(2026, 4, 1),
        )

        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(
            invoice,
            method='straight_line_daily',
        )

        self.assertEqual(len(schedule.line_ids), 3, schedule.block_reason)
        self.assertAlmostEqual(sum(schedule.line_ids.mapped('amount')), invoice.amount_untaxed, places=2)
        self.assertAlmostEqual(schedule.line_ids[-1].amount, 1000.0 - sum(schedule.line_ids[:-1].mapped('amount')), places=2)

    def test_equal_monthly_allocation_reconciles_with_rounding(self):
        _subscription, invoice = self._create_posted_subscription_invoice(amount=1000.0)

        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(
            invoice,
            method='equal_monthly',
        )

        self.assertEqual(len(schedule.line_ids), 3, schedule.block_reason)
        self.assertAlmostEqual(sum(schedule.line_ids.mapped('amount')), invoice.amount_untaxed, places=2)
        self.assertAlmostEqual(schedule.line_ids[0].amount, 333.33, places=2)
        self.assertAlmostEqual(schedule.line_ids[-1].amount, 333.34, places=2)

    def test_missing_service_period_creates_blocked_schedule(self):
        _subscription, invoice = self._create_posted_subscription_invoice()
        invoice.write({
            'subscription_period_start': False,
            'subscription_period_end': False,
        })

        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(invoice)

        self.assertEqual(schedule.state, 'blocked')
        self.assertIn('service period', schedule.block_reason)
        self.assertFalse(schedule.line_ids)

    def test_draft_non_subscription_and_refund_sources_are_blocked_or_excluded(self):
        subscription = self._create_subscription()
        draft_invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'subscription_id': subscription.id,
            'subscription_period_start': self.period_start,
            'subscription_period_end': self.period_end,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'name': 'Draft subscription invoice',
                'quantity': 1.0,
                'price_unit': 100.0,
            })],
        })
        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(draft_invoice)
        self.assertEqual(schedule.state, 'blocked')

        plain_invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'name': 'Plain invoice',
                'quantity': 1.0,
                'price_unit': 100.0,
            })],
        })
        plain_invoice.action_post()
        plain_schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(plain_invoice)
        self.assertFalse(plain_schedule)

        refund = self.env['account.move'].create({
            'move_type': 'out_refund',
            'partner_id': self.partner.id,
            'subscription_id': subscription.id,
            'subscription_period_start': self.period_start,
            'subscription_period_end': self.period_end,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'name': 'Refund',
                'quantity': 1.0,
                'price_unit': 100.0,
            })],
        })
        refund.action_post()
        refund_schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(refund)
        self.assertEqual(refund_schedule.state, 'blocked')

    def test_smart_button_domains_are_scoped(self):
        subscription, invoice = self._create_posted_subscription_invoice()
        schedule = self.env['subscription.deferred.revenue'].generate_for_invoices(invoice)

        subscription_action = subscription.action_view_deferred_revenue_schedules()
        invoice_action = invoice.action_view_deferred_revenue_schedules()

        self.assertIn(('subscription_id', '=', subscription.id), subscription_action['domain'])
        self.assertIn(('invoice_id', '=', invoice.id), invoice_action['domain'])
        self.assertEqual(schedule.invoice_id, invoice)

    def test_non_manager_cannot_generate_schedules(self):
        _subscription, invoice = self._create_posted_subscription_invoice()
        public_env = self.env(user=self.env.ref('base.public_user'))

        with self.assertRaises(AccessError):
            public_env['subscription.deferred.revenue'].generate_for_invoices(invoice)
