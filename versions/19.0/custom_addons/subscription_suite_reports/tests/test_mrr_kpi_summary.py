from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class TestSubscriptionMrrKpiSummary(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'KPI Customer'})
        self.product = self.env['product.product'].create({
            'name': 'KPI Product',
            'list_price': 100.0,
            'type': 'service',
        })
        self.plan = self.env['subscription.plan'].create({
            'name': 'KPI Monthly',
            'code': 'KPI-MONTHLY',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.other_plan = self.env['subscription.plan'].create({
            'name': 'KPI Pro',
            'code': 'KPI-PRO',
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

    def _create_movement(self, movement_type, amount, plan=None):
        return self.env['subscription.mrr.movement'].create({
            'name': '%s KPI movement' % movement_type,
            'movement_date': self.closing_date,
            'movement_type': movement_type,
            'subscription_id': self._create_subscription(plan=plan).id,
            'previous_mrr': 0.0,
            'new_mrr': amount,
            'amount': amount,
        })

    def _create_reconciliation(self, plan=None, opening=100.0, closing=120.0, new=0.0, expansion=30.0, contraction=-5.0, churn=-5.0):
        net = new + expansion + contraction + churn
        return self.env['subscription.mrr.reconciliation'].sudo().create({
            'opening_date': self.opening_date,
            'closing_date': self.closing_date,
            'company_id': self.env.company.id,
            'currency_id': self.currency.id,
            'subscription_plan_id': (plan or self.plan).id,
            'status': 'matched',
            'opening_mrr': opening,
            'closing_mrr': closing,
            'snapshot_delta_mrr': closing - opening,
            'new_mrr': new,
            'expansion_mrr': expansion,
            'contraction_mrr': contraction,
            'churned_mrr': churn,
            'net_movement_mrr': net,
            'variance_mrr': (closing - opening) - net,
        })

    def _generate(self, plan=None):
        return self.env['subscription.mrr.kpi.summary'].sudo().generate_for_period(
            self.opening_date,
            self.closing_date,
            company=self.env.company,
            plan=plan,
        )

    def _summary_for_plan(self, plan=None):
        return self.env['subscription.mrr.kpi.summary'].search([
            ('opening_date', '=', self.opening_date),
            ('closing_date', '=', self.closing_date),
            ('company_id', '=', self.env.company.id),
            ('currency_id', '=', self.currency.id),
            ('subscription_plan_id', '=', (plan or self.plan).id),
        ], limit=1)

    def test_kpi_summary_uses_reconciliation_and_computes_retention(self):
        self._create_snapshot(self.opening_date, amount=100.0)
        self._create_snapshot(self.closing_date, amount=120.0)
        self._create_reconciliation(new=10.0, expansion=30.0, contraction=-5.0, churn=-15.0)

        self._generate()

        summary = self._summary_for_plan()
        self.assertEqual(summary.status, 'ready')
        self.assertAlmostEqual(summary.opening_mrr, 100.0, places=2)
        self.assertAlmostEqual(summary.closing_mrr, 120.0, places=2)
        self.assertAlmostEqual(summary.snapshot_delta_mrr, 20.0, places=2)
        self.assertAlmostEqual(summary.new_mrr, 10.0, places=2)
        self.assertAlmostEqual(summary.expansion_mrr, 30.0, places=2)
        self.assertAlmostEqual(summary.contraction_mrr, -5.0, places=2)
        self.assertAlmostEqual(summary.churned_mrr, -15.0, places=2)
        self.assertAlmostEqual(summary.net_new_mrr, 20.0, places=2)
        self.assertAlmostEqual(summary.nrr, 110.0, places=2)
        self.assertAlmostEqual(summary.grr, 80.0, places=2)

    def test_zero_opening_mrr_keeps_retention_safe(self):
        self._create_snapshot(self.opening_date, amount=0.0)
        self._create_snapshot(self.closing_date, amount=50.0)
        self._create_reconciliation(opening=0.0, closing=50.0, new=50.0, expansion=0.0, contraction=0.0, churn=0.0)

        self._generate()

        summary = self._summary_for_plan()
        self.assertEqual(summary.status, 'ready')
        self.assertAlmostEqual(summary.nrr, 0.0, places=2)
        self.assertAlmostEqual(summary.grr, 0.0, places=2)

    def test_missing_opening_snapshot_status(self):
        self._create_snapshot(self.closing_date, amount=120.0)
        self._create_reconciliation(opening=0.0, closing=120.0, new=120.0, expansion=0.0, contraction=0.0, churn=0.0)

        self._generate()

        self.assertEqual(self._summary_for_plan().status, 'missing_opening_snapshot')

    def test_missing_closing_snapshot_status(self):
        self._create_snapshot(self.opening_date, amount=120.0)
        self._create_reconciliation(opening=120.0, closing=0.0, new=0.0, expansion=0.0, contraction=0.0, churn=-120.0)

        self._generate()

        self.assertEqual(self._summary_for_plan().status, 'missing_closing_snapshot')

    def test_missing_reconciliation_falls_back_to_direct_movements(self):
        self._create_snapshot(self.opening_date, amount=100.0)
        self._create_snapshot(self.closing_date, amount=115.0)
        self._create_movement('expansion', 20.0)
        self._create_movement('contraction', -5.0)

        self._generate()

        summary = self._summary_for_plan()
        self.assertEqual(summary.status, 'missing_reconciliation')
        self.assertAlmostEqual(summary.expansion_mrr, 20.0, places=2)
        self.assertAlmostEqual(summary.contraction_mrr, -5.0, places=2)
        self.assertAlmostEqual(summary.net_new_mrr, 15.0, places=2)

    def test_multiple_plans_create_separate_summaries(self):
        self._create_snapshot(self.opening_date, plan=self.plan, amount=100.0)
        self._create_snapshot(self.closing_date, plan=self.plan, amount=120.0)
        self._create_snapshot(self.opening_date, plan=self.other_plan, amount=200.0)
        self._create_snapshot(self.closing_date, plan=self.other_plan, amount=240.0)
        self._create_reconciliation(plan=self.plan, opening=100.0, closing=120.0, expansion=20.0, contraction=0.0, churn=0.0)
        self._create_reconciliation(plan=self.other_plan, opening=200.0, closing=240.0, expansion=40.0, contraction=0.0, churn=0.0)

        summaries = self._generate()

        self.assertIn(self.plan.id, summaries.mapped('subscription_plan_id').ids)
        self.assertIn(self.other_plan.id, summaries.mapped('subscription_plan_id').ids)
        self.assertEqual(self._summary_for_plan(self.plan).status, 'ready')
        self.assertEqual(self._summary_for_plan(self.other_plan).status, 'ready')

    def test_summary_rerun_is_idempotent(self):
        self._create_snapshot(self.opening_date, amount=100.0)
        self._create_snapshot(self.closing_date, amount=120.0)
        self._create_reconciliation(expansion=20.0, contraction=0.0, churn=0.0)

        self._generate()
        self._generate()

        summaries = self.env['subscription.mrr.kpi.summary'].search([
            ('opening_date', '=', self.opening_date),
            ('closing_date', '=', self.closing_date),
            ('subscription_plan_id', '=', self.plan.id),
        ])
        self.assertEqual(len(summaries), 1)

    def test_drilldown_actions_filter_sources(self):
        self._create_snapshot(self.opening_date, amount=100.0)
        self._create_snapshot(self.closing_date, amount=120.0)
        self._create_movement('expansion', 20.0)
        self._create_reconciliation(expansion=20.0, contraction=0.0, churn=0.0)
        self._generate()
        summary = self._summary_for_plan()

        snapshot_action = summary.action_view_snapshots()
        reconciliation_action = summary.action_view_reconciliation()
        movement_action = summary.action_view_movements()

        self.assertEqual(snapshot_action['res_model'], 'subscription.mrr.snapshot')
        self.assertIn(('subscription_plan_id', '=', self.plan.id), snapshot_action['domain'])
        self.assertEqual(reconciliation_action['res_model'], 'subscription.mrr.reconciliation')
        self.assertIn(('subscription_plan_id', '=', self.plan.id), reconciliation_action['domain'])
        self.assertEqual(movement_action['res_model'], 'subscription.mrr.movement')
        self.assertIn(('subscription_plan_id', '=', self.plan.id), movement_action['domain'])
