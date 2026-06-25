from datetime import date, timedelta

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
        self.seat_product = self.env['product.product'].create({
            'name': 'Team Seat',
            'type': 'service',
            'list_price': 12.0,
            'invoice_policy': 'order',
        })
        self.addon_product = self.env['product.product'].create({
            'name': 'Priority Support',
            'type': 'service',
            'list_price': 20.0,
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

    def _create_seat_subscription(self, seat_quantity=10.0, state='active', confirm=True, **values):
        defaults = {
            'partner_id': self.partner.id,
            'is_subscription': True,
            'subscription_state': state,
            'subscription_plan_id': self.basic_plan.id,
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'subscription_start_date': date(2026, 1, 1),
            'last_invoice_date': date(2026, 1, 1),
            'next_invoice_date': date(2026, 1, 31),
            'order_line': [
                (0, 0, {
                    'product_id': self.basic_product.id,
                    'name': 'Basic Subscription',
                    'product_uom_qty': 1.0,
                    'price_unit': 29.0,
                    'is_recurring': True,
                    'subscription_component_type': 'base',
                }),
                (0, 0, {
                    'product_id': self.seat_product.id,
                    'name': 'Team Seats',
                    'product_uom_qty': seat_quantity,
                    'price_unit': 12.0,
                    'is_recurring': True,
                    'subscription_component_type': 'seat',
                }),
            ],
        }
        defaults.update(values)
        subscription = self.env['sale.order'].create(defaults)
        if confirm:
            subscription.action_confirm()
        return subscription

    def _tier_commands(self):
        return [
            (0, 0, {'sequence': 10, 'min_quantity': 1.0, 'max_quantity': 10.0, 'price_unit': 12.0}),
            (0, 0, {'sequence': 20, 'min_quantity': 10.0, 'price_unit': 10.0}),
        ]

    def _create_volume_seat_plan(self, quantity=25.0):
        return self.env['subscription.plan'].create({
            'name': 'Volume Seats Monthly',
            'code': 'TEST-VOLUME-SEATS',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'plan_line_ids': [(0, 0, {
                'product_id': self.seat_product.id,
                'quantity': quantity,
                'price_unit': 12.0,
                'description': 'Volume Seats',
                'subscription_component_type': 'seat',
                'subscription_pricing_model': 'volume',
                'tier_ids': self._tier_commands(),
            })],
        })

    def test_apply_tiered_plan_copies_effective_price_and_tiers(self):
        subscription = self._create_basic_subscription()
        plan = self._create_volume_seat_plan(quantity=25.0)

        subscription._apply_subscription_plan(plan)
        subscription.invalidate_recordset(['recurring_total', 'mrr', 'seat_quantity'])
        seat_line = subscription.order_line.filtered(lambda line: line.subscription_component_type == 'seat')[:1]

        self.assertEqual(seat_line.subscription_pricing_model, 'volume')
        self.assertEqual(len(seat_line.subscription_tier_ids), 2)
        self.assertAlmostEqual(seat_line.price_unit, 10.0, places=2)
        self.assertAlmostEqual(subscription.recurring_total, 250.0, places=2)
        self.assertAlmostEqual(subscription.mrr, 250.0, places=2)
        self.assertEqual(subscription.seat_quantity, 25.0)

    def test_tiered_seat_increase_recomputes_effective_price_and_mrr(self):
        subscription = self._create_seat_subscription(seat_quantity=9.0)
        seat_line = subscription.order_line.filtered(lambda line: line.subscription_component_type == 'seat')[:1]
        seat_line.write({
            'subscription_pricing_model': 'volume',
            'subscription_tier_ids': self._tier_commands(),
        })
        subscription.invalidate_recordset(['recurring_total', 'mrr'])
        old_mrr = subscription.mrr

        proration = subscription._execute_seat_change(12.0, effective_date=date(2026, 1, 16))
        subscription.invalidate_recordset(['recurring_total', 'mrr', 'seat_quantity'])

        self.assertAlmostEqual(old_mrr, 137.0, places=2)
        self.assertAlmostEqual(seat_line.price_unit, 10.0, places=2)
        self.assertEqual(seat_line.product_uom_qty, 12.0)
        self.assertAlmostEqual(subscription.recurring_total, 149.0, places=2)
        self.assertAlmostEqual(subscription.mrr, 149.0, places=2)
        self.assertEqual(proration.proration_scope, 'seat_change')
        self.assertEqual(proration.change_type, 'upgrade')

    def test_immediate_seat_increase_updates_mrr_and_creates_adjustment_invoice(self):
        subscription = self._create_seat_subscription()
        old_mrr = subscription.mrr

        proration = subscription._execute_seat_change(15.0, effective_date=date(2026, 1, 16))
        subscription.invalidate_recordset()
        seat_line = subscription.order_line.filtered(lambda line: line.subscription_component_type == 'seat')

        self.assertEqual(seat_line.product_uom_qty, 15.0)
        self.assertEqual(subscription.seat_quantity, 15.0)
        self.assertAlmostEqual(subscription.recurring_total, 209.0, places=2)
        self.assertAlmostEqual(subscription.mrr, 209.0, places=2)
        self.assertEqual(proration.proration_scope, 'seat_change')
        self.assertEqual(proration.change_type, 'upgrade')
        self.assertEqual(proration.old_seat_quantity, 10.0)
        self.assertEqual(proration.new_seat_quantity, 15.0)
        self.assertEqual(proration.state, 'applied')
        self.assertTrue(proration.adjustment_invoice_id)
        self.assertEqual(proration.adjustment_invoice_id.move_type, 'out_invoice')
        self.assertAlmostEqual(proration.net_amount, 30.0, places=2)

        movement = self.env['subscription.mrr.movement'].search([
            ('subscription_id', '=', subscription.id),
        ], order='id desc', limit=1)
        self.assertEqual(movement.movement_type, 'expansion')
        self.assertAlmostEqual(movement.previous_mrr, old_mrr, places=2)
        self.assertAlmostEqual(movement.new_mrr, 209.0, places=2)

        log = self.env['subscription.log'].search([
            ('subscription_id', '=', subscription.id),
            ('description', 'ilike', 'Seats changed from 10'),
        ], limit=1)
        self.assertTrue(log)

    def test_immediate_seat_decrease_creates_credit_note(self):
        subscription = self._create_seat_subscription()

        proration = subscription._execute_seat_change(5.0, effective_date=date(2026, 1, 16))
        subscription.invalidate_recordset()

        self.assertEqual(subscription.seat_quantity, 5.0)
        self.assertAlmostEqual(subscription.mrr, 89.0, places=2)
        self.assertEqual(proration.change_type, 'downgrade')
        self.assertTrue(proration.credit_note_id)
        self.assertEqual(proration.credit_note_id.move_type, 'out_refund')
        self.assertAlmostEqual(proration.net_amount, -30.0, places=2)

        movement = self.env['subscription.mrr.movement'].search([
            ('subscription_id', '=', subscription.id),
        ], order='id desc', limit=1)
        self.assertEqual(movement.movement_type, 'contraction')

    def test_change_seats_action_and_wizard_apply_immediate_change(self):
        subscription = self._create_seat_subscription()
        action = subscription.action_change_seats()
        self.assertEqual(action['res_model'], 'subscription.change.seats.wizard')

        wizard = self.env['subscription.change.seats.wizard'].with_context(action['context']).create({
            'subscription_id': subscription.id,
            'new_seat_quantity': 12.0,
            'effective_date': date(2026, 1, 16),
        })
        self.assertAlmostEqual(wizard.current_mrr, 149.0, places=2)
        self.assertAlmostEqual(wizard.new_mrr, 173.0, places=2)
        self.assertAlmostEqual(wizard.net_amount, 12.0, places=2)
        wizard.action_confirm_change()
        subscription.invalidate_recordset()
        self.assertEqual(subscription.seat_quantity, 12.0)

    def test_wizard_schedules_next_period_seat_change_without_proration(self):
        subscription = self._create_seat_subscription()
        action = subscription.action_change_seats()

        wizard = self.env['subscription.change.seats.wizard'].with_context(action['context']).create({
            'subscription_id': subscription.id,
            'new_seat_quantity': 12.0,
            'change_timing': 'next_period',
            'effective_date': date(2026, 1, 31),
        })
        self.assertEqual(wizard.net_amount, 0.0)
        wizard.action_confirm_change()
        subscription.invalidate_recordset()

        self.assertEqual(subscription.seat_quantity, 10.0)
        self.assertEqual(subscription.pending_seat_quantity, 12.0)
        self.assertEqual(subscription.pending_seat_change_date, date(2026, 1, 31))
        self.assertFalse(subscription.proration_ids.filtered(lambda proration: proration.proration_scope == 'seat_change'))

    def test_scheduled_seat_increase_applies_before_billing_invoice(self):
        today = fields.Date.today()
        subscription = self._create_seat_subscription(confirm=False, last_invoice_date=today, next_invoice_date=today)
        subscription.action_confirm()
        subscription._schedule_seat_change(12.0, effective_date=today)

        self.env['sale.order']._cron_generate_subscription_invoices()
        subscription.invalidate_recordset()

        self.assertEqual(subscription.seat_quantity, 12.0)
        self.assertFalse(subscription.pending_seat_change_date)
        self.assertFalse(subscription.proration_ids.filtered(lambda proration: proration.proration_scope == 'seat_change'))
        self.assertAlmostEqual(subscription.mrr, 173.0, places=2)

        invoice = self.env['account.move'].search([
            ('subscription_id', '=', subscription.id),
        ], order='id desc', limit=1)
        self.assertTrue(invoice)
        seat_invoice_line = invoice.invoice_line_ids.filtered(lambda line: line.product_id == self.seat_product)
        self.assertEqual(seat_invoice_line.quantity, 12.0)
        self.assertAlmostEqual(invoice.amount_untaxed, 173.0, places=2)

        movement = self.env['subscription.mrr.movement'].search([
            ('subscription_id', '=', subscription.id),
        ], order='id desc', limit=1)
        self.assertEqual(movement.movement_type, 'expansion')

    def test_scheduled_seat_decrease_and_cancel(self):
        subscription = self._create_seat_subscription()
        subscription._schedule_seat_change(5.0, effective_date=date(2026, 1, 31))
        subscription.invalidate_recordset()

        self.assertEqual(subscription.pending_seat_quantity, 5.0)
        subscription.action_cancel_pending_seat_change()
        subscription.invalidate_recordset()

        self.assertFalse(subscription.pending_seat_change_date)
        self.assertFalse(subscription.pending_seat_quantity)
        self.assertEqual(subscription.seat_quantity, 10.0)

    def test_pending_seat_change_noop_is_cleared_without_movement(self):
        subscription = self._create_seat_subscription()
        subscription._schedule_seat_change(12.0, effective_date=date(2026, 1, 31))
        seat_line = subscription._get_single_seat_line()
        seat_line.write({'product_uom_qty': 12.0})
        subscription.invalidate_recordset(['seat_quantity', 'recurring_total', 'mrr'])
        movement_count = self.env['subscription.mrr.movement'].search_count([
            ('subscription_id', '=', subscription.id),
        ])

        applied = subscription._apply_pending_seat_change()
        subscription.invalidate_recordset()

        self.assertFalse(applied)
        self.assertFalse(subscription.pending_seat_change_date)
        self.assertEqual(subscription.seat_quantity, 12.0)
        self.assertEqual(self.env['subscription.mrr.movement'].search_count([
            ('subscription_id', '=', subscription.id),
        ]), movement_count)

    def test_immediate_addon_add_updates_mrr_and_creates_adjustment_invoice(self):
        subscription = self._create_seat_subscription()
        old_mrr = subscription.mrr

        proration = subscription._execute_addon_change(
            'add',
            product=self.addon_product,
            quantity=2.0,
            price_unit=20.0,
            effective_date=date(2026, 1, 16),
        )
        subscription.invalidate_recordset()
        addon_line = subscription._get_addon_lines(self.addon_product)

        self.assertEqual(addon_line.product_uom_qty, 2.0)
        self.assertAlmostEqual(subscription.mrr, 189.0, places=2)
        self.assertEqual(proration.proration_scope, 'addon_change')
        self.assertEqual(proration.change_type, 'upgrade')
        self.assertEqual(proration.addon_product_id, self.addon_product)
        self.assertEqual(proration.old_addon_quantity, 0.0)
        self.assertEqual(proration.new_addon_quantity, 2.0)
        self.assertTrue(proration.adjustment_invoice_id)
        self.assertAlmostEqual(proration.net_amount, 20.0, places=2)

        movement = self.env['subscription.mrr.movement'].search([
            ('subscription_id', '=', subscription.id),
        ], order='id desc', limit=1)
        self.assertEqual(movement.movement_type, 'expansion')
        self.assertAlmostEqual(movement.previous_mrr, old_mrr, places=2)
        self.assertAlmostEqual(movement.new_mrr, 189.0, places=2)

    def test_immediate_addon_remove_creates_credit_note(self):
        subscription = self._create_seat_subscription()
        subscription._execute_addon_change(
            'add',
            product=self.addon_product,
            quantity=2.0,
            price_unit=20.0,
            effective_date=date(2026, 1, 1),
        )
        addon_line = subscription._get_addon_lines(self.addon_product)

        proration = subscription._execute_addon_change(
            'remove',
            addon_line=addon_line,
            quantity=1.0,
            effective_date=date(2026, 1, 16),
        )
        subscription.invalidate_recordset()

        self.assertEqual(addon_line.product_uom_qty, 1.0)
        self.assertAlmostEqual(subscription.mrr, 169.0, places=2)
        self.assertEqual(proration.proration_scope, 'addon_change')
        self.assertEqual(proration.change_type, 'downgrade')
        self.assertEqual(proration.old_addon_quantity, 2.0)
        self.assertEqual(proration.new_addon_quantity, 1.0)
        self.assertTrue(proration.credit_note_id)
        self.assertAlmostEqual(proration.net_amount, -10.0, places=2)

        movement = self.env['subscription.mrr.movement'].search([
            ('subscription_id', '=', subscription.id),
        ], order='id desc', limit=1)
        self.assertEqual(movement.movement_type, 'contraction')

    def test_change_addons_action_and_wizard_schedule_next_period(self):
        subscription = self._create_seat_subscription()
        action = subscription.action_change_addons()
        self.assertEqual(action['res_model'], 'subscription.change.addons.wizard')

        wizard = self.env['subscription.change.addons.wizard'].with_context(action['context']).create({
            'subscription_id': subscription.id,
            'operation': 'add',
            'change_timing': 'next_period',
            'product_id': self.addon_product.id,
            'quantity': 2.0,
            'price_unit': 20.0,
            'effective_date': date(2026, 1, 31),
        })
        self.assertEqual(wizard.net_amount, 0.0)
        wizard.action_confirm_change()
        subscription.invalidate_recordset()

        self.assertFalse(subscription._get_addon_lines(self.addon_product))
        self.assertEqual(subscription.pending_addon_change_operation, 'add')
        self.assertEqual(subscription.pending_addon_product_id, self.addon_product)
        self.assertEqual(subscription.pending_addon_quantity, 2.0)
        self.assertEqual(subscription.pending_addon_change_date, date(2026, 1, 31))

    def test_scheduled_addon_add_applies_before_billing_invoice(self):
        today = fields.Date.today()
        subscription = self._create_seat_subscription(confirm=False, last_invoice_date=today, next_invoice_date=today)
        subscription.action_confirm()
        subscription._schedule_addon_change(
            'add',
            product=self.addon_product,
            quantity=2.0,
            price_unit=20.0,
            effective_date=today,
        )

        self.env['sale.order']._cron_generate_subscription_invoices()
        subscription.invalidate_recordset()
        addon_line = subscription._get_addon_lines(self.addon_product)

        self.assertEqual(addon_line.product_uom_qty, 2.0)
        self.assertFalse(subscription.pending_addon_change_date)
        self.assertFalse(subscription.proration_ids.filtered(lambda proration: proration.proration_scope == 'addon_change'))
        self.assertAlmostEqual(subscription.mrr, 189.0, places=2)

        invoice = self.env['account.move'].search([
            ('subscription_id', '=', subscription.id),
        ], order='id desc', limit=1)
        self.assertTrue(invoice)
        addon_invoice_line = invoice.invoice_line_ids.filtered(lambda line: line.product_id == self.addon_product)
        self.assertEqual(addon_invoice_line.quantity, 2.0)
        self.assertAlmostEqual(invoice.amount_untaxed, 189.0, places=2)

    def test_scheduled_addon_remove_and_cancel(self):
        subscription = self._create_seat_subscription()
        subscription._execute_addon_change(
            'add',
            product=self.addon_product,
            quantity=2.0,
            price_unit=20.0,
            effective_date=date(2026, 1, 1),
        )
        addon_line = subscription._get_addon_lines(self.addon_product)
        subscription._schedule_addon_change(
            'remove',
            addon_line=addon_line,
            quantity=1.0,
            effective_date=date(2026, 1, 31),
        )
        subscription.invalidate_recordset()

        self.assertEqual(subscription.pending_addon_change_operation, 'remove')
        self.assertEqual(subscription.pending_addon_line_id, addon_line)
        subscription.action_cancel_pending_addon_change()
        subscription.invalidate_recordset()

        self.assertFalse(subscription.pending_addon_change_date)
        self.assertEqual(addon_line.product_uom_qty, 2.0)

    def test_scheduled_addon_remove_applies_before_billing_invoice(self):
        today = fields.Date.today()
        subscription = self._create_seat_subscription(confirm=False, last_invoice_date=today, next_invoice_date=today)
        subscription.action_confirm()
        subscription._execute_addon_change(
            'add',
            product=self.addon_product,
            quantity=2.0,
            price_unit=20.0,
            effective_date=today,
        )
        addon_line = subscription._get_addon_lines(self.addon_product)
        subscription._schedule_addon_change(
            'remove',
            addon_line=addon_line,
            quantity=1.0,
            effective_date=today,
        )

        self.env['sale.order']._cron_generate_subscription_invoices()
        subscription.invalidate_recordset()

        self.assertEqual(addon_line.product_uom_qty, 1.0)
        self.assertFalse(subscription.pending_addon_change_date)
        self.assertAlmostEqual(subscription.mrr, 169.0, places=2)

        invoice = self.env['account.move'].search([
            ('subscription_id', '=', subscription.id),
        ], order='id desc', limit=1)
        addon_invoice_line = invoice.invoice_line_ids.filtered(lambda line: line.product_id == self.addon_product)
        self.assertEqual(addon_invoice_line.quantity, 1.0)

    def test_addon_change_guards(self):
        subscription = self._create_seat_subscription()
        with self.assertRaises(ValidationError):
            subscription._execute_addon_change('add', quantity=1.0)
        with self.assertRaises(ValidationError):
            subscription._execute_addon_change('add', product=self.addon_product, quantity=0.0, price_unit=20.0)
        with self.assertRaises(ValidationError):
            subscription._execute_addon_change('remove', quantity=1.0)

        subscription._execute_addon_change('add', product=self.addon_product, quantity=1.0, price_unit=20.0)
        addon_line = subscription._get_addon_lines(self.addon_product)
        with self.assertRaises(ValidationError):
            subscription._execute_addon_change('remove', addon_line=addon_line, quantity=2.0)

        quote = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'subscription_quote_type': 'upsell',
            'subscription_origin_id': subscription.id,
        })
        with self.assertRaises(ValidationError):
            quote._execute_addon_change('add', product=self.addon_product, quantity=1.0, price_unit=20.0)

        cancelled = self._create_seat_subscription(state='cancelled')
        with self.assertRaises(ValidationError):
            cancelled._schedule_addon_change('add', product=self.addon_product, quantity=1.0, price_unit=20.0)

    def test_discount_wizard_applies_active_promotion_and_logs(self):
        subscription = self._create_basic_subscription()
        line = subscription.order_line.filtered('is_recurring')[:1]
        wizard = self.env['subscription.change.discounts.wizard'].create({
            'subscription_id': subscription.id,
            'line_id': line.id,
            'base_discount': 10.0,
            'promo_discount': 20.0,
            'promo_start_date': fields.Date.today() - timedelta(days=1),
            'promo_end_date': fields.Date.today() + timedelta(days=10),
        })

        wizard.action_confirm_change()
        subscription.invalidate_recordset(['recurring_total', 'mrr'])

        self.assertAlmostEqual(line.subscription_base_discount, 10.0, places=2)
        self.assertAlmostEqual(line.subscription_promo_discount, 20.0, places=2)
        self.assertEqual(line.subscription_promo_discount_state, 'active')
        self.assertAlmostEqual(line.discount, 28.0, places=2)
        self.assertAlmostEqual(subscription.recurring_total, 20.88, places=2)
        self.assertAlmostEqual(subscription.mrr, 20.88, places=2)
        self.assertTrue(subscription.subscription_log_ids.filtered(
            lambda log: log.event_type == 'discount_changed' and 'updated' in (log.description or '')
        ))

    def test_discount_wizard_stores_future_promotion_without_applying_it(self):
        subscription = self._create_basic_subscription()
        line = subscription.order_line.filtered('is_recurring')[:1]
        wizard = self.env['subscription.change.discounts.wizard'].create({
            'subscription_id': subscription.id,
            'line_id': line.id,
            'base_discount': 5.0,
            'promo_discount': 20.0,
            'promo_start_date': fields.Date.today() + timedelta(days=5),
            'promo_end_date': fields.Date.today() + timedelta(days=15),
        })

        wizard.action_confirm_change()
        subscription.invalidate_recordset(['recurring_total', 'mrr'])

        self.assertAlmostEqual(line.subscription_base_discount, 5.0, places=2)
        self.assertAlmostEqual(line.subscription_promo_discount, 20.0, places=2)
        self.assertEqual(line.subscription_promo_discount_state, 'inactive')
        self.assertAlmostEqual(line.discount, 5.0, places=2)
        self.assertAlmostEqual(subscription.recurring_total, 27.55, places=2)

    def test_discount_wizard_clear_promotion_restores_base_discount(self):
        subscription = self._create_basic_subscription()
        line = subscription.order_line.filtered('is_recurring')[:1]
        line.write({
            'subscription_base_discount': 5.0,
            'subscription_promo_discount': 20.0,
            'subscription_promo_discount_start_date': fields.Date.today() - timedelta(days=1),
            'subscription_promo_discount_end_date': fields.Date.today() + timedelta(days=10),
            'subscription_promo_discount_state': 'active',
            'discount': 24.0,
        })
        wizard = self.env['subscription.change.discounts.wizard'].create({
            'subscription_id': subscription.id,
            'operation': 'clear_promo',
            'line_id': line.id,
            'base_discount': 5.0,
        })

        wizard.action_confirm_change()
        subscription.invalidate_recordset(['recurring_total', 'mrr'])

        self.assertAlmostEqual(line.subscription_base_discount, 5.0, places=2)
        self.assertFalse(line.subscription_promo_discount)
        self.assertFalse(line.subscription_promo_discount_start_date)
        self.assertFalse(line.subscription_promo_discount_end_date)
        self.assertEqual(line.subscription_promo_discount_state, 'inactive')
        self.assertAlmostEqual(line.discount, 5.0, places=2)
        self.assertAlmostEqual(subscription.recurring_total, 27.55, places=2)
        self.assertTrue(subscription.subscription_log_ids.filtered(
            lambda log: log.event_type == 'discount_changed' and 'cleared' in (log.description or '')
        ))

    def test_manual_discount_refresh_activates_due_promo_once(self):
        subscription = self._create_basic_subscription()
        line = subscription.order_line.filtered('is_recurring')[:1]
        line.write({
            'subscription_base_discount': 5.0,
            'subscription_promo_discount': 20.0,
            'subscription_promo_discount_start_date': fields.Date.today() - timedelta(days=1),
            'subscription_promo_discount_end_date': fields.Date.today() + timedelta(days=10),
            'subscription_promo_discount_state': 'inactive',
            'discount': 5.0,
        })

        subscription.action_refresh_discounts()
        subscription.action_refresh_discounts()

        self.assertEqual(line.subscription_promo_discount_state, 'active')
        self.assertAlmostEqual(line.discount, 24.0, places=2)
        activation_logs = subscription.subscription_log_ids.filtered(
            lambda log: log.event_type == 'discount_changed' and 'activated' in (log.description or '')
        )
        self.assertEqual(len(activation_logs), 1)

    def test_discount_wizard_guards(self):
        subscription = self._create_basic_subscription()
        line = subscription.order_line.filtered('is_recurring')[:1]
        regular_order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {
                'product_id': self.basic_product.id,
                'name': 'Regular line',
                'product_uom_qty': 1.0,
                'price_unit': 29.0,
            })],
        })
        quote = self._create_basic_subscription(subscription_quote_type='renewal')
        cancelled = self._create_basic_subscription(subscription_state='cancelled')
        expired = self._create_basic_subscription(subscription_state='expired')

        with self.assertRaises(ValidationError):
            regular_order.action_change_discounts()
        with self.assertRaises(ValidationError):
            quote.action_change_discounts()
        with self.assertRaises(ValidationError):
            cancelled.action_change_discounts()
        with self.assertRaises(ValidationError):
            expired.action_change_discounts()
        with self.assertRaises(ValidationError):
            self.env['subscription.change.discounts.wizard'].create({
                'subscription_id': subscription.id,
                'line_id': line.id,
                'base_discount': 101.0,
            })
        with self.assertRaises(ValidationError):
            self.env['subscription.change.discounts.wizard'].create({
                'subscription_id': subscription.id,
                'line_id': line.id,
                'promo_discount': 10.0,
                'promo_start_date': fields.Date.today(),
                'promo_end_date': fields.Date.today(),
            })
        nonrecurring = self.env['sale.order.line'].create({
            'order_id': subscription.id,
            'product_id': self.basic_product.id,
            'name': 'Non-recurring',
            'product_uom_qty': 1.0,
            'price_unit': 10.0,
            'is_recurring': False,
        })
        with self.assertRaises(ValidationError):
            self.env['subscription.change.discounts.wizard'].create({
                'subscription_id': subscription.id,
                'line_id': nonrecurring.id,
            })

    def test_immediate_seat_change_guards(self):
        subscription = self._create_seat_subscription()
        with self.assertRaises(ValidationError):
            subscription._execute_seat_change(10.0, effective_date=date(2026, 1, 16))
        with self.assertRaises(ValidationError):
            subscription._schedule_seat_change(10.0, effective_date=date(2026, 1, 31))
        with self.assertRaises(ValidationError):
            subscription._execute_seat_change(10.000000001, effective_date=date(2026, 1, 16))
        with self.assertRaises(ValidationError):
            subscription._execute_seat_change(0.0, effective_date=date(2026, 1, 16))
        with self.assertRaises(ValidationError):
            subscription._execute_seat_change(0.994, effective_date=date(2026, 1, 16))

        missing_seats = self._create_basic_subscription()
        missing_seats.action_confirm()
        with self.assertRaises(ValidationError):
            missing_seats._execute_seat_change(2.0, effective_date=date(2026, 1, 16))

        multiple_seats = self._create_seat_subscription(confirm=False)
        multiple_seats.write({
            'order_line': [(0, 0, {
                'product_id': self.seat_product.id,
                'name': 'Extra Seat Pool',
                'product_uom_qty': 1.0,
                'price_unit': 12.0,
                'is_recurring': True,
                'subscription_component_type': 'seat',
            })],
        })
        multiple_seats.action_confirm()
        with self.assertRaises(ValidationError):
            multiple_seats._execute_seat_change(12.0, effective_date=date(2026, 1, 16))

        cancelled = self._create_seat_subscription(state='cancelled')
        with self.assertRaises(ValidationError):
            cancelled._execute_seat_change(12.0, effective_date=date(2026, 1, 16))

        expired = self._create_seat_subscription(state='expired')
        with self.assertRaises(ValidationError):
            expired._execute_seat_change(12.0, effective_date=date(2026, 1, 16))
        with self.assertRaises(ValidationError):
            expired._schedule_seat_change(12.0, effective_date=date(2026, 1, 31))

        quote = self._create_seat_subscription(confirm=False)
        with self.assertRaises(ValidationError):
            quote._execute_seat_change(12.0, effective_date=date(2026, 1, 16))

        regular_order = self.env['sale.order'].create({'partner_id': self.partner.id})
        with self.assertRaises(ValidationError):
            regular_order._execute_seat_change(12.0, effective_date=date(2026, 1, 16))

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
        self.assertEqual(recurring_lines.subscription_component_type, 'base')
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

    def test_portal_plan_change_request_rejects_other_customer_requester(self):
        self.basic_plan.upgrade_plan_ids = self.premium_plan
        subscription = self._create_basic_subscription()
        other_partner = self.env['res.partner'].create({'name': 'Other Plan Change Customer'})
        other_user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Other Plan Change User',
            'login': 'other_plan_change_user@example.com',
            'email': 'other_plan_change_user@example.com',
            'partner_id': other_partner.id,
            'group_ids': [(6, 0, [
                self.env.ref('base.group_portal').id,
            ])],
        })

        with self.assertRaises(ValidationError):
            subscription.sudo()._portal_request_plan_change(
                self.premium_plan,
                other_user,
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
