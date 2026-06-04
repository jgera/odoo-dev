from datetime import date

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestPlanChange(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Plan Change Customer'})
        self.basic_product = self.env['product.product'].create({
            'name': 'Basic Subscription',
            'type': 'service',
            'list_price': 29.0,
        })
        self.pro_product = self.env['product.product'].create({
            'name': 'Pro Subscription',
            'type': 'service',
            'list_price': 299.0,
        })
        self.basic_plan = self.env['subscription.plan'].create({
            'name': 'Basic Monthly',
            'code': 'TEST-BASIC-MONTHLY',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'plan_line_ids': [(0, 0, {
                'product_id': self.basic_product.id,
                'quantity': 1.0,
                'price_unit': 29.0,
                'description': 'Basic Subscription',
            })],
        })
        self.pro_plan = self.env['subscription.plan'].create({
            'name': 'Pro Annual',
            'code': 'TEST-PRO-ANNUAL',
            'billing_interval_count': 1,
            'billing_interval_unit': 'year',
            'plan_line_ids': [(0, 0, {
                'product_id': self.pro_product.id,
                'quantity': 1.0,
                'price_unit': 299.0,
                'description': 'Pro Subscription',
            })],
        })

    def test_plan_change_updates_subscription_and_logs_mrr_movement(self):
        subscription = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'is_subscription': True,
            'subscription_state': 'active',
            'subscription_plan_id': self.pro_plan.id,
            'billing_interval_count': 1,
            'billing_interval_unit': 'year',
            'subscription_start_date': date(2026, 1, 1),
            'next_invoice_date': date(2027, 1, 1),
            'order_line': [(0, 0, {
                'product_id': self.pro_product.id,
                'name': 'Pro Subscription',
                'product_uom_qty': 1.0,
                'price_unit': 299.0,
                'is_recurring': True,
            })],
        })

        self.assertAlmostEqual(subscription.mrr, 299.0 / 12.0, places=2)

        proration = subscription._execute_plan_change(
            self.basic_plan,
            effective_date=date(2026, 6, 1),
        )
        subscription.invalidate_recordset()

        self.assertEqual(subscription.subscription_plan_id, self.basic_plan)
        self.assertEqual(subscription.billing_interval_count, 1)
        self.assertEqual(subscription.billing_interval_unit, 'month')
        self.assertAlmostEqual(subscription.recurring_total, 29.0, places=2)
        self.assertAlmostEqual(subscription.mrr, 29.0, places=2)

        recurring_lines = subscription.order_line.filtered('is_recurring')
        self.assertEqual(len(recurring_lines), 1)
        self.assertEqual(recurring_lines.product_id, self.basic_product)
        self.assertAlmostEqual(recurring_lines.price_unit, 29.0, places=2)

        self.assertEqual(proration.state, 'applied')
        self.assertEqual(proration.change_type, 'upgrade')
        self.assertAlmostEqual(proration.old_daily_rate, (299.0 / 12.0) / 30.0, places=2)
        self.assertAlmostEqual(proration.new_daily_rate, 29.0 / 30.0, places=2)

        movement = self.env['subscription.mrr.movement'].search([
            ('subscription_id', '=', subscription.id),
        ], order='id desc', limit=1)
        self.assertEqual(movement.movement_type, 'expansion')
        self.assertAlmostEqual(movement.previous_mrr, 299.0 / 12.0, places=2)
        self.assertAlmostEqual(movement.new_mrr, 29.0, places=2)
        self.assertAlmostEqual(movement.amount, 29.0 - (299.0 / 12.0), places=2)

    def test_plan_change_rejects_unconfigured_upgrade_path(self):
        blocked_plan = self.env['subscription.plan'].create({
            'name': 'Blocked Enterprise',
            'code': 'TEST-BLOCKED-ENTERPRISE',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'plan_line_ids': [(0, 0, {
                'product_id': self.pro_product.id,
                'quantity': 1.0,
                'price_unit': 499.0,
                'description': 'Blocked Enterprise',
            })],
        })
        self.basic_plan.upgrade_plan_ids = self.pro_plan
        subscription = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'is_subscription': True,
            'subscription_state': 'active',
            'subscription_plan_id': self.basic_plan.id,
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'subscription_start_date': date(2026, 1, 1),
            'next_invoice_date': date(2026, 2, 1),
            'order_line': [(0, 0, {
                'product_id': self.basic_product.id,
                'name': 'Basic Subscription',
                'product_uom_qty': 1.0,
                'price_unit': 29.0,
                'is_recurring': True,
            })],
        })

        with self.assertRaises(ValidationError):
            subscription._execute_plan_change(blocked_plan, effective_date=date(2026, 1, 15))

    def test_upsell_quote_confirmation_creates_proration_record(self):
        addon_product = self.env['product.product'].create({
            'name': 'Priority Support',
            'type': 'service',
            'list_price': 60.0,
        })
        subscription = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'is_subscription': True,
            'subscription_state': 'active',
            'subscription_plan_id': self.basic_plan.id,
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'last_invoice_date': date(2026, 1, 1),
            'subscription_start_date': date(2026, 1, 1),
            'next_invoice_date': date(2026, 1, 31),
            'order_line': [(0, 0, {
                'product_id': self.basic_product.id,
                'name': 'Basic Subscription',
                'product_uom_qty': 1.0,
                'price_unit': 29.0,
                'is_recurring': True,
            })],
        })

        quote_action = subscription.action_upsell_subscription()
        quote = self.env['sale.order'].browse(quote_action['res_id'])
        quote.write({
            'subscription_quote_effective_date': date(2026, 1, 16),
            'order_line': [(0, 0, {
                'product_id': addon_product.id,
                'name': 'Priority Support',
                'product_uom_qty': 1.0,
                'price_unit': 60.0,
                'is_recurring': True,
            })],
        })
        quote.action_confirm()

        proration = self.env['subscription.proration'].search([
            ('subscription_id', '=', subscription.id),
        ], limit=1)
        self.assertTrue(proration)
        self.assertEqual(proration.state, 'applied')
        self.assertEqual(proration.change_type, 'upgrade')
        self.assertEqual(proration.period_start, date(2026, 1, 1))
        self.assertEqual(proration.period_end, date(2026, 1, 31))
        self.assertEqual(proration.change_date, date(2026, 1, 16))
        self.assertAlmostEqual(proration.old_daily_rate, 29.0 / 30.0, places=2)
        self.assertAlmostEqual(proration.new_daily_rate, 89.0 / 30.0, places=2)
        self.assertAlmostEqual(proration.net_amount, 30.0, places=2)
