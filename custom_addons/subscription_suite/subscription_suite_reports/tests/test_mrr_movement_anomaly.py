from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class TestSubscriptionMrrMovementAnomaly(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Anomaly Customer'})
        self.product = self.env['product.product'].create({
            'name': 'Anomaly Product',
            'list_price': 100.0,
            'type': 'service',
        })
        self.plan = self.env['subscription.plan'].create({
            'name': 'Anomaly Monthly',
            'code': 'ANOMALY-MONTHLY',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.other_plan = self.env['subscription.plan'].create({
            'name': 'Anomaly Pro',
            'code': 'ANOMALY-PRO',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.opening_date = fields.Date.today() - relativedelta(days=30)
        self.closing_date = fields.Date.today()
        self.currency = self.env.company.currency_id

    def _create_subscription(self, plan=None):
        values = {
            'partner_id': self.partner.id,
            'is_subscription': True,
            'subscription_state': 'active',
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'is_recurring': True,
                'price_unit': 100.0,
                'product_uom_qty': 1.0,
            })],
        }
        if plan:
            values['subscription_plan_id'] = plan.id
        return self.env['sale.order'].create(values)

    def _create_snapshot(self, snapshot_date, plan=None, amount=0.0):
        return self.env['subscription.mrr.snapshot'].sudo().create({
            'snapshot_date': snapshot_date,
            'company_id': self.env.company.id,
            'currency_id': self.currency.id,
            'subscription_plan_id': (plan or self.plan).id,
            'subscription_count': 1,
            'active_count': 1,
            'active_mrr': amount,
            'total_recurring_mrr': amount,
            'arr': amount * 12,
        })

    def _create_movement(self, movement_type, amount, plan=None, movement_date=None):
        subscription = self._create_subscription(plan=plan)
        return self.env['subscription.mrr.movement'].create({
            'name': '%s anomaly movement' % movement_type,
            'movement_date': movement_date or self.closing_date,
            'movement_type': movement_type,
            'subscription_id': subscription.id,
            'previous_mrr': 0.0,
            'new_mrr': amount,
            'amount': amount,
        })

    def _generate(self, plan=None):
        return self.env['subscription.mrr.movement.anomaly'].sudo().generate_for_period(
            self.opening_date,
            self.closing_date,
            company=self.env.company,
            plan=plan,
        )

    def _anomaly_for_plan(self, plan=None):
        return self.env['subscription.mrr.movement.anomaly'].search([
            ('opening_date', '=', self.opening_date),
            ('closing_date', '=', self.closing_date),
            ('company_id', '=', self.env.company.id),
            ('currency_id', '=', self.currency.id),
            ('subscription_plan_id', '=', plan.id if plan else False),
        ], limit=1)

    def test_detects_movement_only_bucket_without_snapshots(self):
        self._create_movement('new', 50.0, plan=self.plan)
        self._create_movement('expansion', 20.0, plan=self.plan)
        self._create_movement('contraction', -10.0, plan=self.plan)
        self._create_movement('churn', -5.0, plan=self.plan)

        anomalies = self._generate()

        self.assertIn(self.plan.id, anomalies.mapped('subscription_plan_id').ids)
        anomaly = self._anomaly_for_plan(self.plan)
        self.assertEqual(anomaly.anomaly_type, 'movement_only')
        self.assertEqual(anomaly.movement_count, 4)
        self.assertAlmostEqual(anomaly.new_mrr, 50.0, places=2)
        self.assertAlmostEqual(anomaly.expansion_mrr, 20.0, places=2)
        self.assertAlmostEqual(anomaly.contraction_mrr, -10.0, places=2)
        self.assertAlmostEqual(anomaly.churned_mrr, -5.0, places=2)
        self.assertAlmostEqual(anomaly.net_movement_mrr, 55.0, places=2)

    def test_detects_missing_plan_movements(self):
        self._create_movement('new', 25.0, plan=None)

        self._generate()

        anomaly = self._anomaly_for_plan()
        self.assertTrue(anomaly)
        self.assertEqual(anomaly.anomaly_type, 'missing_plan')
        self.assertEqual(anomaly.movement_count, 1)
        self.assertAlmostEqual(anomaly.net_movement_mrr, 25.0, places=2)

    def test_ignores_movement_bucket_when_snapshot_exists(self):
        self._create_snapshot(self.opening_date, plan=self.plan, amount=100.0)
        self._create_movement('expansion', 20.0, plan=self.plan)

        anomalies = self._generate()

        self.assertNotIn(self.plan.id, anomalies.mapped('subscription_plan_id').ids)

    def test_multiple_plans_create_separate_anomalies(self):
        self._create_movement('new', 10.0, plan=self.plan)
        self._create_movement('new', 15.0, plan=self.other_plan)

        anomalies = self._generate()

        self.assertIn(self.plan.id, anomalies.mapped('subscription_plan_id').ids)
        self.assertIn(self.other_plan.id, anomalies.mapped('subscription_plan_id').ids)
        self.assertAlmostEqual(self._anomaly_for_plan(self.plan).net_movement_mrr, 10.0, places=2)
        self.assertAlmostEqual(self._anomaly_for_plan(self.other_plan).net_movement_mrr, 15.0, places=2)

    def test_anomaly_rerun_is_idempotent_for_same_scope(self):
        self._create_movement('new', 10.0, plan=self.plan)

        self._generate()
        self._create_movement('expansion', 5.0, plan=self.plan)
        self._generate()

        anomalies = self.env['subscription.mrr.movement.anomaly'].search([
            ('opening_date', '=', self.opening_date),
            ('closing_date', '=', self.closing_date),
            ('subscription_plan_id', '=', self.plan.id),
        ])
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies.movement_count, 2)
        self.assertAlmostEqual(anomalies.net_movement_mrr, 15.0, places=2)

    def test_drilldown_action_filters_source_movements(self):
        self._create_movement('new', 10.0, plan=self.plan)
        self._generate()
        anomaly = self._anomaly_for_plan(self.plan)

        action = anomaly.action_view_movements()

        self.assertEqual(action['res_model'], 'subscription.mrr.movement')
        self.assertIn(('subscription_plan_id', '=', self.plan.id), action['domain'])
        self.assertIn(('currency_id', '=', self.currency.id), action['domain'])
