from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class TestSubscriptionMrrReconciliation(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Reconciliation Customer'})
        self.product = self.env['product.product'].create({
            'name': 'Reconciliation Product',
            'list_price': 100.0,
            'type': 'service',
        })
        self.plan = self.env['subscription.plan'].create({
            'name': 'Reconciliation Monthly',
            'code': 'RECON-MONTHLY',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.other_plan = self.env['subscription.plan'].create({
            'name': 'Reconciliation Pro',
            'code': 'RECON-PRO',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.opening_date = fields.Date.today() - relativedelta(days=30)
        self.closing_date = fields.Date.today()
        self.currency = self.env.company.currency_id

    def _create_subscription(self, plan=None):
        return self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'is_subscription': True,
            'subscription_state': 'active',
            'subscription_plan_id': (plan or self.plan).id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'is_recurring': True,
                'price_unit': 100.0,
                'product_uom_qty': 1.0,
            })],
        })

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
            'name': '%s movement' % movement_type,
            'movement_date': movement_date or self.closing_date,
            'movement_type': movement_type,
            'subscription_id': subscription.id,
            'previous_mrr': 0.0,
            'new_mrr': amount,
            'amount': amount,
        })

    def _generate(self, plan=None):
        return self.env['subscription.mrr.reconciliation'].sudo().generate_for_period(
            self.opening_date,
            self.closing_date,
            company=self.env.company,
            plan=plan,
        )

    def _reconciliation_for_plan(self, plan=None):
        return self.env['subscription.mrr.reconciliation'].search([
            ('opening_date', '=', self.opening_date),
            ('closing_date', '=', self.closing_date),
            ('company_id', '=', self.env.company.id),
            ('currency_id', '=', self.currency.id),
            ('subscription_plan_id', '=', (plan or self.plan).id),
        ], limit=1)

    def test_matched_reconciliation_when_delta_equals_movements(self):
        self._create_snapshot(self.opening_date, amount=100.0)
        self._create_snapshot(self.closing_date, amount=130.0)
        self._create_movement('new', 50.0)
        self._create_movement('expansion', 20.0)
        self._create_movement('contraction', -10.0)
        self._create_movement('churn', -30.0)

        self._generate()

        reconciliation = self._reconciliation_for_plan()
        self.assertEqual(reconciliation.status, 'matched')
        self.assertAlmostEqual(reconciliation.opening_mrr, 100.0, places=2)
        self.assertAlmostEqual(reconciliation.closing_mrr, 130.0, places=2)
        self.assertAlmostEqual(reconciliation.snapshot_delta_mrr, 30.0, places=2)
        self.assertAlmostEqual(reconciliation.new_mrr, 50.0, places=2)
        self.assertAlmostEqual(reconciliation.expansion_mrr, 20.0, places=2)
        self.assertAlmostEqual(reconciliation.contraction_mrr, -10.0, places=2)
        self.assertAlmostEqual(reconciliation.churned_mrr, -30.0, places=2)
        self.assertAlmostEqual(reconciliation.net_movement_mrr, 30.0, places=2)
        self.assertAlmostEqual(reconciliation.variance_mrr, 0.0, places=2)

    def test_variance_reconciliation_when_movements_do_not_match_delta(self):
        self._create_snapshot(self.opening_date, amount=100.0)
        self._create_snapshot(self.closing_date, amount=150.0)
        self._create_movement('expansion', 20.0)

        self._generate()

        reconciliation = self._reconciliation_for_plan()
        self.assertEqual(reconciliation.status, 'variance')
        self.assertAlmostEqual(reconciliation.snapshot_delta_mrr, 50.0, places=2)
        self.assertAlmostEqual(reconciliation.net_movement_mrr, 20.0, places=2)
        self.assertAlmostEqual(reconciliation.variance_mrr, 30.0, places=2)

    def test_missing_opening_snapshot_status(self):
        self._create_snapshot(self.closing_date, amount=150.0)
        self._create_movement('new', 150.0)

        self._generate()

        reconciliation = self._reconciliation_for_plan()
        self.assertEqual(reconciliation.status, 'missing_opening_snapshot')
        self.assertAlmostEqual(reconciliation.opening_mrr, 0.0, places=2)
        self.assertAlmostEqual(reconciliation.closing_mrr, 150.0, places=2)

    def test_missing_closing_snapshot_status(self):
        self._create_snapshot(self.opening_date, amount=150.0)
        self._create_movement('churn', -150.0)

        self._generate()

        reconciliation = self._reconciliation_for_plan()
        self.assertEqual(reconciliation.status, 'missing_closing_snapshot')
        self.assertAlmostEqual(reconciliation.opening_mrr, 150.0, places=2)
        self.assertAlmostEqual(reconciliation.closing_mrr, 0.0, places=2)

    def test_multiple_plans_create_separate_rows(self):
        self._create_snapshot(self.opening_date, plan=self.plan, amount=100.0)
        self._create_snapshot(self.closing_date, plan=self.plan, amount=120.0)
        self._create_snapshot(self.opening_date, plan=self.other_plan, amount=200.0)
        self._create_snapshot(self.closing_date, plan=self.other_plan, amount=250.0)
        self._create_movement('expansion', 20.0, plan=self.plan)
        self._create_movement('expansion', 50.0, plan=self.other_plan)

        reconciliations = self._generate()

        self.assertIn(self.plan.id, reconciliations.mapped('subscription_plan_id').ids)
        self.assertIn(self.other_plan.id, reconciliations.mapped('subscription_plan_id').ids)
        self.assertEqual(self._reconciliation_for_plan(self.plan).status, 'matched')
        self.assertEqual(self._reconciliation_for_plan(self.other_plan).status, 'matched')

    def test_reconciliation_rerun_is_idempotent_for_same_scope(self):
        self._create_snapshot(self.opening_date, amount=100.0)
        self._create_snapshot(self.closing_date, amount=120.0)
        self._create_movement('expansion', 20.0)

        self._generate()
        self._create_movement('new', 10.0)
        self._generate()

        reconciliations = self.env['subscription.mrr.reconciliation'].search([
            ('opening_date', '=', self.opening_date),
            ('closing_date', '=', self.closing_date),
            ('subscription_plan_id', '=', self.plan.id),
        ])
        self.assertEqual(len(reconciliations), 1)
        self.assertAlmostEqual(reconciliations.net_movement_mrr, 30.0, places=2)
        self.assertEqual(reconciliations.status, 'variance')

    def test_drilldown_actions_filter_source_records(self):
        self._create_snapshot(self.opening_date, amount=100.0)
        self._create_snapshot(self.closing_date, amount=120.0)
        self._create_movement('expansion', 20.0)
        self._generate()
        reconciliation = self._reconciliation_for_plan()

        snapshot_action = reconciliation.action_view_snapshots()
        movement_action = reconciliation.action_view_movements()

        self.assertEqual(snapshot_action['res_model'], 'subscription.mrr.snapshot')
        self.assertIn(('subscription_plan_id', '=', self.plan.id), snapshot_action['domain'])
        self.assertEqual(movement_action['res_model'], 'subscription.mrr.movement')
        self.assertIn(('subscription_plan_id', '=', self.plan.id), movement_action['domain'])
