from datetime import date

from odoo import fields
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError


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
        self.premium_product = self.env['product.product'].create({
            'name': 'Premium Subscription',
            'type': 'service',
            'list_price': 89.0,
            'invoice_policy': 'order',
        })
        self.premium_plan = self.env['subscription.plan'].create({
            'name': 'Premium Monthly',
            'code': 'TEST-PREMIUM-MONTHLY',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'plan_line_ids': [(0, 0, {
                'product_id': self.premium_product.id,
                'quantity': 1.0,
                'price_unit': 89.0,
                'description': 'Premium Subscription',
            })],
        })
        self.subscription_user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Plan Approval User',
            'login': 'plan_approval_user',
            'email': 'plan_approval_user@example.com',
            'group_ids': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('subscription_suite.group_subscription_user').id,
            ])],
        })

    def _create_basic_subscription(self, **values):
        defaults = {
            'partner_id': self.partner.id,
            'is_subscription': True,
            'subscription_state': 'active',
            'subscription_plan_id': self.basic_plan.id,
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'subscription_start_date': date(2026, 1, 1),
            'last_invoice_date': date(2026, 1, 1),
            'next_invoice_date': date(2026, 2, 1),
            'order_line': [(0, 0, {
                'product_id': self.basic_product.id,
                'name': 'Basic Subscription',
                'product_uom_qty': 1.0,
                'price_unit': 29.0,
                'is_recurring': True,
            })],
        }
        defaults.update(values)
        return self.env['sale.order'].create(defaults)

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
        self.assertTrue(proration.adjustment_invoice_id)
        self.assertEqual(proration.adjustment_invoice_id.move_type, 'out_invoice')
        self.assertEqual(proration.adjustment_invoice_id.subscription_id, subscription)
        self.assertEqual(proration.adjustment_invoice_id.proration_id, proration)
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

    def test_minimum_commitment_blocks_downgrade_before_commitment_end(self):
        self.pro_plan.min_commitment_periods = 1
        starter_product = self.env['product.product'].create({
            'name': 'Starter Subscription',
            'type': 'service',
            'list_price': 9.0,
        })
        starter_plan = self.env['subscription.plan'].create({
            'name': 'Starter Monthly',
            'code': 'TEST-STARTER-MONTHLY',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'plan_line_ids': [(0, 0, {
                'product_id': starter_product.id,
                'quantity': 1.0,
                'price_unit': 9.0,
                'description': 'Starter Subscription',
            })],
        })
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

        with self.assertRaises(UserError):
            subscription._execute_plan_change(starter_plan, effective_date=date(2026, 6, 1))

    def test_schedule_next_period_plan_change_without_proration(self):
        subscription = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'is_subscription': True,
            'subscription_state': 'active',
            'subscription_plan_id': self.basic_plan.id,
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'subscription_start_date': date(2026, 1, 1),
            'last_invoice_date': date(2026, 1, 1),
            'next_invoice_date': date(2026, 2, 1),
            'order_line': [(0, 0, {
                'product_id': self.basic_product.id,
                'name': 'Basic Subscription',
                'product_uom_qty': 1.0,
                'price_unit': 29.0,
                'is_recurring': True,
            })],
        })

        subscription._schedule_plan_change(self.premium_plan, effective_date=date(2026, 2, 1))

        self.assertEqual(subscription.subscription_plan_id, self.basic_plan)
        self.assertEqual(subscription.pending_plan_change_id, self.premium_plan)
        self.assertEqual(subscription.pending_plan_change_date, date(2026, 2, 1))
        self.assertEqual(subscription.pending_plan_change_type, 'upgrade')
        self.assertFalse(subscription.proration_ids)

    def test_billing_applies_due_scheduled_plan_change_before_invoice(self):
        today = fields.Date.today()
        subscription = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'is_subscription': True,
            'subscription_state': 'active',
            'subscription_plan_id': self.basic_plan.id,
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'subscription_start_date': today,
            'last_invoice_date': today,
            'next_invoice_date': today,
            'order_line': [(0, 0, {
                'product_id': self.basic_product.id,
                'name': 'Basic Subscription',
                'product_uom_qty': 1.0,
                'price_unit': 29.0,
                'is_recurring': True,
            })],
        })
        subscription.action_confirm()
        subscription._schedule_plan_change(self.premium_plan, effective_date=today)

        self.env['sale.order']._cron_generate_subscription_invoices()
        subscription.invalidate_recordset()

        self.assertEqual(subscription.subscription_plan_id, self.premium_plan)
        self.assertFalse(subscription.pending_plan_change_id)
        self.assertFalse(subscription.proration_ids)
        self.assertAlmostEqual(subscription.mrr, 89.0, places=2)

        invoice = self.env['account.move'].search([
            ('subscription_id', '=', subscription.id),
        ], limit=1)
        self.assertTrue(invoice)
        self.assertEqual(invoice.invoice_line_ids.product_id, self.premium_product)
        self.assertAlmostEqual(invoice.amount_untaxed, 89.0, places=2)

        movement = self.env['subscription.mrr.movement'].search([
            ('subscription_id', '=', subscription.id),
        ], order='id desc', limit=1)
        self.assertEqual(movement.movement_type, 'expansion')
        self.assertAlmostEqual(movement.previous_mrr, 29.0, places=2)
        self.assertAlmostEqual(movement.new_mrr, 89.0, places=2)

    def test_restricted_plan_change_creates_approval_request(self):
        self.basic_plan.approval_required_for_upgrade = True
        subscription = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'user_id': self.subscription_user.id,
            'is_subscription': True,
            'subscription_state': 'active',
            'subscription_plan_id': self.basic_plan.id,
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'subscription_start_date': date(2026, 1, 1),
            'last_invoice_date': date(2026, 1, 1),
            'next_invoice_date': date(2026, 2, 1),
            'order_line': [(0, 0, {
                'product_id': self.basic_product.id,
                'name': 'Basic Subscription',
                'product_uom_qty': 1.0,
                'price_unit': 29.0,
                'is_recurring': True,
            })],
        })

        request = subscription.with_user(self.subscription_user)._request_plan_change_approval(
            self.premium_plan,
            effective_date=date(2026, 2, 1),
            change_timing='next_period',
        )

        self.assertTrue(request)
        self.assertEqual(request.state, 'pending')
        self.assertEqual(request.requested_by_id, self.subscription_user)
        self.assertEqual(request.change_type, 'upgrade')
        self.assertEqual(request.requested_timing, 'next_period')
        self.assertEqual(subscription.subscription_plan_id, self.basic_plan)
        self.assertFalse(subscription.pending_plan_change_id)

        self.env['subscription.plan.change.request'].browse(request.id).action_approve()
        subscription.invalidate_recordset()

        self.assertEqual(request.state, 'approved')
        self.assertEqual(subscription.subscription_plan_id, self.basic_plan)
        self.assertEqual(subscription.pending_plan_change_id, self.premium_plan)
        self.assertEqual(subscription.pending_plan_change_date, date(2026, 2, 1))

    def test_manager_plan_change_queue_activity_and_subscription_actions(self):
        self.basic_plan.approval_required_for_upgrade = True
        subscription = self._create_basic_subscription(user_id=self.subscription_user.id)

        request = subscription.with_user(self.subscription_user)._request_plan_change_approval(
            self.premium_plan,
            effective_date=date(2026, 2, 1),
            change_timing='next_period',
        )

        self.assertTrue(self.env['mail.activity'].search([
            ('res_model', '=', 'subscription.plan.change.request'),
            ('res_id', '=', request.id),
            ('summary', '=', 'Review subscription request'),
        ]))
        self.assertEqual(request.request_age_days, 0)

        action = subscription.action_view_subscription_plan_change_requests()
        self.assertEqual(action['res_model'], 'subscription.plan.change.request')
        self.assertIn(('subscription_id', '=', subscription.id), action['domain'])
        self.assertEqual(subscription.plan_change_request_count, 1)

        open_action = request.action_open_subscription()
        self.assertEqual(open_action['res_model'], 'sale.order')
        self.assertEqual(open_action['res_id'], subscription.id)

    def test_portal_plan_change_request_creates_next_period_approval_request(self):
        self.basic_plan.upgrade_plan_ids = self.premium_plan
        subscription = self._create_basic_subscription()

        request = subscription.sudo()._portal_request_plan_change(
            self.premium_plan,
            self.subscription_user,
        )

        self.assertTrue(request)
        self.assertEqual(request.state, 'pending')
        self.assertEqual(request.current_plan_id, self.basic_plan)
        self.assertEqual(request.requested_plan_id, self.premium_plan)
        self.assertEqual(request.requested_by_id, self.subscription_user)
        self.assertEqual(request.requested_timing, 'next_period')
        self.assertEqual(request.requested_effective_date, date(2026, 2, 1))
        self.assertEqual(request.change_type, 'upgrade')
        self.assertAlmostEqual(request.old_mrr, 29.0, places=2)
        self.assertAlmostEqual(request.new_mrr, 89.0, places=2)
        self.assertEqual(subscription.subscription_plan_id, self.basic_plan)
        self.assertFalse(subscription.pending_plan_change_id)

    def test_portal_plan_change_request_requires_active_subscription(self):
        self.basic_plan.upgrade_plan_ids = self.premium_plan
        subscription = self._create_basic_subscription(subscription_state='paused')

        with self.assertRaises(ValidationError):
            subscription.sudo()._portal_request_plan_change(
                self.premium_plan,
                self.subscription_user,
            )

    def test_portal_plan_change_request_requires_configured_path(self):
        self.basic_plan.upgrade_plan_ids = self.pro_plan
        subscription = self._create_basic_subscription()

        with self.assertRaises(ValidationError):
            subscription.sudo()._portal_request_plan_change(
                self.premium_plan,
                self.subscription_user,
            )

    def test_portal_plan_change_request_blocks_duplicate_pending_request(self):
        self.basic_plan.upgrade_plan_ids = self.premium_plan
        subscription = self._create_basic_subscription()
        subscription.sudo()._portal_request_plan_change(
            self.premium_plan,
            self.subscription_user,
        )

        with self.assertRaises(ValidationError):
            subscription.sudo()._portal_request_plan_change(
                self.premium_plan,
                self.subscription_user,
            )

    def test_portal_plan_change_request_blocks_scheduled_plan_change(self):
        self.basic_plan.upgrade_plan_ids = self.premium_plan
        subscription = self._create_basic_subscription(
            pending_plan_change_id=self.premium_plan.id,
            pending_plan_change_date=date(2026, 2, 1),
            pending_plan_change_type='upgrade',
        )

        with self.assertRaises(ValidationError):
            subscription.sudo()._portal_request_plan_change(
                self.premium_plan,
                self.subscription_user,
            )

    def test_restricted_plan_change_cannot_bypass_approval(self):
        self.basic_plan.approval_required_for_upgrade = True
        subscription = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'is_subscription': True,
            'subscription_state': 'active',
            'subscription_plan_id': self.basic_plan.id,
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'subscription_start_date': date(2026, 1, 1),
            'last_invoice_date': date(2026, 1, 1),
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
            subscription._schedule_plan_change(self.premium_plan, effective_date=date(2026, 2, 1))

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
        self.assertTrue(proration.adjustment_invoice_id)
        self.assertEqual(proration.adjustment_invoice_id.move_type, 'out_invoice')
        self.assertEqual(proration.adjustment_invoice_id.state, 'draft')
        self.assertEqual(proration.adjustment_invoice_id.subscription_period_start, proration.period_start)
        self.assertEqual(proration.adjustment_invoice_id.subscription_period_end, proration.period_end)
        self.assertAlmostEqual(proration.old_daily_rate, 29.0 / 30.0, places=2)
        self.assertAlmostEqual(proration.new_daily_rate, 89.0 / 30.0, places=2)
        self.assertAlmostEqual(proration.net_amount, 30.0, places=2)
        self.assertAlmostEqual(proration.adjustment_invoice_id.amount_untaxed, 30.0, places=2)
