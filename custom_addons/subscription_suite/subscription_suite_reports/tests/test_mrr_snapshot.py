from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class TestSubscriptionMrrSnapshot(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Snapshot Customer'})
        self.product = self.env['product.product'].create({
            'name': 'Snapshot Subscription Product',
            'list_price': 100.0,
            'type': 'service',
        })
        self.plan = self.env['subscription.plan'].create({
            'name': 'Snapshot Monthly',
            'code': 'SNAP-MONTHLY',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.other_plan = self.env['subscription.plan'].create({
            'name': 'Snapshot Pro',
            'code': 'SNAP-PRO',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.snapshot_date = fields.Date.today() - relativedelta(days=1)

    def _create_subscription(self, state, plan=None, price=100.0):
        subscription = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'is_subscription': True,
            'subscription_state': state,
            'subscription_plan_id': (plan or self.plan).id,
            'subscription_start_date': fields.Date.today() - relativedelta(days=30),
            'next_invoice_date': fields.Date.today() + relativedelta(days=1),
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'is_recurring': True,
                'price_unit': price,
                'product_uom_qty': 1.0,
            })],
        })
        subscription.invalidate_recordset(['recurring_total', 'mrr'])
        return subscription

    def _snapshot_for_plan(self, plan):
        return self.env['subscription.mrr.snapshot'].search([
            ('snapshot_date', '=', self.snapshot_date),
            ('subscription_plan_id', '=', plan.id),
        ], limit=1)

    def test_snapshot_generation_buckets_counts_and_mrr_by_state(self):
        self._create_subscription('active', price=100.0)
        self._create_subscription('trial', price=20.0)
        self._create_subscription('paused', price=30.0)
        self._create_subscription('past_due', price=40.0)
        self._create_subscription('cancelled', price=50.0)
        self._create_subscription('expired', price=60.0)

        snapshots = self.env['subscription.mrr.snapshot'].sudo().generate_for_date(self.snapshot_date)

        self.assertIn(self.plan.id, snapshots.mapped('subscription_plan_id').ids)
        snapshot = self._snapshot_for_plan(self.plan)
        self.assertEqual(snapshot.subscription_count, 6)
        self.assertEqual(snapshot.active_count, 1)
        self.assertEqual(snapshot.trial_count, 1)
        self.assertEqual(snapshot.paused_count, 1)
        self.assertEqual(snapshot.past_due_count, 1)
        self.assertEqual(snapshot.cancelled_count, 1)
        self.assertEqual(snapshot.expired_count, 1)
        self.assertEqual(snapshot.churned_count, 2)
        self.assertAlmostEqual(snapshot.active_mrr, 100.0, places=2)
        self.assertAlmostEqual(snapshot.trial_mrr, 20.0, places=2)
        self.assertAlmostEqual(snapshot.paused_mrr, 30.0, places=2)
        self.assertAlmostEqual(snapshot.past_due_mrr, 40.0, places=2)
        self.assertAlmostEqual(snapshot.churned_mrr, 110.0, places=2)
        self.assertAlmostEqual(snapshot.total_recurring_mrr, 190.0, places=2)
        self.assertAlmostEqual(snapshot.arr, 2280.0, places=2)

    def test_snapshot_generation_is_idempotent_for_same_date(self):
        self._create_subscription('active', price=100.0)
        Snapshot = self.env['subscription.mrr.snapshot'].sudo()

        Snapshot.generate_for_date(self.snapshot_date)
        self._create_subscription('active', price=25.0)
        Snapshot.generate_for_date(self.snapshot_date)

        snapshots = Snapshot.search([
            ('snapshot_date', '=', self.snapshot_date),
            ('subscription_plan_id', '=', self.plan.id),
        ])
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots.subscription_count, 2)
        self.assertAlmostEqual(snapshots.total_recurring_mrr, 125.0, places=2)

    def test_snapshot_generation_creates_separate_plan_buckets(self):
        self._create_subscription('active', plan=self.plan, price=100.0)
        self._create_subscription('active', plan=self.other_plan, price=250.0)

        snapshots = self.env['subscription.mrr.snapshot'].sudo().generate_for_date(self.snapshot_date)

        self.assertIn(self.plan.id, snapshots.mapped('subscription_plan_id').ids)
        self.assertIn(self.other_plan.id, snapshots.mapped('subscription_plan_id').ids)
        basic_snapshot = self._snapshot_for_plan(self.plan)
        pro_snapshot = self._snapshot_for_plan(self.other_plan)
        self.assertAlmostEqual(basic_snapshot.total_recurring_mrr, 100.0, places=2)
        self.assertAlmostEqual(pro_snapshot.total_recurring_mrr, 250.0, places=2)

    def test_generate_wizard_returns_snapshot_action(self):
        self._create_subscription('active', price=100.0)
        wizard = self.env['subscription.mrr.snapshot.generate.wizard'].sudo().create({
            'snapshot_date': self.snapshot_date,
            'company_id': self.env.company.id,
        })

        action = wizard.action_generate_snapshot()

        self.assertEqual(action['res_model'], 'subscription.mrr.snapshot')
        self.assertEqual(action['type'], 'ir.actions.act_window')
        snapshot = self._snapshot_for_plan(self.plan)
        self.assertTrue(snapshot)
