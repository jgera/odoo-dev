from odoo.tests.common import TransactionCase
from odoo import fields
from datetime import date

class TestProrationMath(TransactionCase):

    def setUp(self):
        super(TestProrationMath, self).setUp()
        self.plan_100 = self.env['subscription.plan'].create({
            'name': 'Plan 100',
            'code': 'PLAN100',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month'
        })
        self.plan_200 = self.env['subscription.plan'].create({
            'name': 'Plan 200',
            'code': 'PLAN200',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month'
        })
        self.product = self.env['product.product'].create({
            'name': 'Proration Product',
            'type': 'service',
            'list_price': 100.0,
        })
        
        self.partner = self.env['res.partner'].create({'name': 'Test Customer'})
        self.sub = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'is_subscription': True,
            'subscription_state': 'active',
            'subscription_plan_id': self.plan_100.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'name': 'Proration Product',
                'product_uom_qty': 1.0,
                'price_unit': 100.0,
                'is_recurring': True,
            })],
        })

    def test_01_mid_month_upgrade(self):
        """Test a mid-month upgrade from 100 to 200 calculates exact 50% proration."""
        # Force a 30 day period
        period_start = date(2023, 4, 1)
        period_end = date(2023, 5, 1) # 30 days
        change_date = date(2023, 4, 16) # Exactly 15 days used, 15 days remaining
        
        proration = self.env['subscription.proration'].create({
            'subscription_id': self.sub.id,
            'change_type': 'upgrade',
            'change_date': change_date,
            'old_plan_id': self.plan_100.id,
            'new_plan_id': self.plan_200.id,
            'period_start': period_start,
            'period_end': period_end,
            'old_daily_rate': 100.0 / 30.0,
            'new_daily_rate': 200.0 / 30.0,
        })
        
        self.assertEqual(proration.total_period_days, 30)
        self.assertEqual(proration.used_days, 15)
        self.assertEqual(proration.remaining_days, 15)
        
        # Credit for 15 remaining days of old plan = 50.0
        self.assertAlmostEqual(proration.credit_amount, 50.0, places=2)
        
        # Charge for 15 remaining days of new plan = 100.0
        self.assertAlmostEqual(proration.charge_amount, 100.0, places=2)
        
        # Net amount due today = 50.0
        self.assertAlmostEqual(proration.net_amount, 50.0, places=2)

    def test_credit_note_created_for_negative_proration(self):
        period_start = date(2023, 4, 1)
        period_end = date(2023, 5, 1)
        change_date = date(2023, 4, 16)

        proration = self.env['subscription.proration'].create({
            'subscription_id': self.sub.id,
            'change_type': 'downgrade',
            'change_date': change_date,
            'old_plan_id': self.plan_200.id,
            'new_plan_id': self.plan_100.id,
            'period_start': period_start,
            'period_end': period_end,
            'old_daily_rate': 200.0 / 30.0,
            'new_daily_rate': 100.0 / 30.0,
        })

        proration.action_apply_proration()

        self.assertEqual(proration.state, 'applied')
        self.assertTrue(proration.credit_note_id)
        self.assertEqual(proration.credit_note_id.move_type, 'out_refund')
        self.assertEqual(proration.credit_note_id.state, 'draft')
        self.assertEqual(proration.credit_note_id.subscription_id, self.sub)
        self.assertEqual(proration.credit_note_id.proration_id, proration)
        self.assertAlmostEqual(proration.credit_note_id.amount_untaxed, 50.0, places=2)
