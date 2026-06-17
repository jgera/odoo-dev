from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class TestSubscriptionMrrKpiDashboard(TransactionCase):

    def setUp(self):
        super().setUp()
        self.currency = self.env.company.currency_id
        self.other_currency = self.env['res.currency'].search([('id', '!=', self.currency.id)], limit=1)
        if not self.other_currency:
            self.other_currency = self.env['res.currency'].create({
                'name': 'TST',
                'symbol': 'T',
                'rounding': 0.01,
                'decimal_places': 2,
            })
        self.plan = self.env['subscription.plan'].create({
            'name': 'Dashboard Monthly',
            'code': 'DASH-MONTHLY',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.other_plan = self.env['subscription.plan'].create({
            'name': 'Dashboard Pro',
            'code': 'DASH-PRO',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.opening_date = fields.Date.today() - relativedelta(days=30)
        self.closing_date = fields.Date.today()

    def _create_summary(
        self,
        plan=None,
        currency=None,
        status='ready',
        opening=100.0,
        closing=125.0,
        new=5.0,
        expansion=30.0,
        contraction=-5.0,
        churn=-5.0,
        variance=0.0,
    ):
        currency = currency or self.currency
        plan = plan or self.plan
        net = new + expansion + contraction + churn
        nrr = ((opening + expansion + contraction + churn) / opening) * 100.0 if opening else 0.0
        grr = ((opening + contraction + churn) / opening) * 100.0 if opening else 0.0
        return self.env['subscription.mrr.kpi.summary'].sudo().create({
            'opening_date': self.opening_date,
            'closing_date': self.closing_date,
            'company_id': self.env.company.id,
            'currency_id': currency.id,
            'subscription_plan_id': plan.id,
            'bucket_key': '%s:%s:%s' % (self.env.company.id, currency.id, plan.id),
            'generated_at': fields.Datetime.now(),
            'status': status,
            'opening_mrr': opening,
            'closing_mrr': closing,
            'snapshot_delta_mrr': closing - opening,
            'new_mrr': new,
            'expansion_mrr': expansion,
            'contraction_mrr': contraction,
            'churned_mrr': churn,
            'net_new_mrr': net,
            'variance_mrr': variance,
            'nrr': nrr,
            'grr': grr,
        })

    def _generate(self, plan=None, currency=None):
        return self.env['subscription.mrr.kpi.dashboard'].sudo().generate_for_period(
            self.opening_date,
            self.closing_date,
            company=self.env.company,
            currency=currency or self.currency,
            plan=plan,
        )

    def test_dashboard_uses_selected_plan_summary(self):
        self._create_summary(plan=self.plan, opening=100.0, closing=125.0, expansion=30.0, contraction=-5.0, churn=0.0)
        self._create_summary(plan=self.other_plan, opening=200.0, closing=250.0, expansion=50.0, contraction=0.0, churn=0.0)

        dashboard = self._generate(plan=self.plan)

        self.assertEqual(dashboard.status, 'ready')
        self.assertEqual(dashboard.summary_count, 1)
        self.assertEqual(dashboard.subscription_plan_id, self.plan)
        self.assertAlmostEqual(dashboard.opening_mrr, 100.0, places=2)
        self.assertAlmostEqual(dashboard.closing_mrr, 125.0, places=2)
        self.assertAlmostEqual(dashboard.net_new_mrr, 30.0, places=2)

    def test_dashboard_aggregates_multiple_plans_for_currency(self):
        self._create_summary(plan=self.plan, opening=100.0, closing=125.0, new=5.0, expansion=30.0, contraction=-5.0, churn=-5.0)
        self._create_summary(plan=self.other_plan, opening=200.0, closing=250.0, new=0.0, expansion=50.0, contraction=0.0, churn=0.0)

        dashboard = self._generate()

        self.assertFalse(dashboard.subscription_plan_id)
        self.assertEqual(dashboard.summary_count, 2)
        self.assertAlmostEqual(dashboard.opening_mrr, 300.0, places=2)
        self.assertAlmostEqual(dashboard.closing_mrr, 375.0, places=2)
        self.assertAlmostEqual(dashboard.net_new_mrr, 75.0, places=2)
        self.assertAlmostEqual(dashboard.nrr, 123.333333, places=2)
        self.assertAlmostEqual(dashboard.grr, 96.666666, places=2)

    def test_dashboard_keeps_currencies_separate(self):
        self._create_summary(plan=self.plan, currency=self.currency, opening=100.0, closing=120.0, expansion=20.0, contraction=0.0, churn=0.0)
        self._create_summary(plan=self.other_plan, currency=self.other_currency, opening=500.0, closing=600.0, expansion=100.0, contraction=0.0, churn=0.0)

        dashboard = self._generate(currency=self.currency)

        self.assertEqual(dashboard.currency_id, self.currency)
        self.assertEqual(dashboard.summary_count, 1)
        self.assertAlmostEqual(dashboard.opening_mrr, 100.0, places=2)
        self.assertAlmostEqual(dashboard.closing_mrr, 120.0, places=2)

    def test_dashboard_missing_summary_status(self):
        dashboard = self._generate(plan=self.plan)

        self.assertEqual(dashboard.status, 'missing_kpi_summary')
        self.assertEqual(dashboard.summary_count, 0)
        self.assertAlmostEqual(dashboard.opening_mrr, 0.0, places=2)

    def test_dashboard_missing_inputs_status(self):
        self._create_summary(status='missing_reconciliation')

        dashboard = self._generate(plan=self.plan)

        self.assertEqual(dashboard.status, 'missing_inputs')
        self.assertEqual(dashboard.summary_count, 1)

    def test_dashboard_rerun_is_idempotent(self):
        self._create_summary()

        self._generate(plan=self.plan)
        self._generate(plan=self.plan)

        dashboards = self.env['subscription.mrr.kpi.dashboard'].search([
            ('opening_date', '=', self.opening_date),
            ('closing_date', '=', self.closing_date),
            ('company_id', '=', self.env.company.id),
            ('currency_id', '=', self.currency.id),
            ('subscription_plan_id', '=', self.plan.id),
        ])
        self.assertEqual(len(dashboards), 1)

    def test_dashboard_drilldowns_filter_sources(self):
        self._create_summary()
        dashboard = self._generate(plan=self.plan)

        summary_action = dashboard.action_view_kpi_summaries()
        snapshot_action = dashboard.action_view_snapshots()
        reconciliation_action = dashboard.action_view_reconciliations()
        anomaly_action = dashboard.action_view_anomalies()
        movement_action = dashboard.action_view_movements()

        self.assertEqual(summary_action['res_model'], 'subscription.mrr.kpi.summary')
        self.assertIn(('subscription_plan_id', '=', self.plan.id), summary_action['domain'])
        self.assertEqual(snapshot_action['res_model'], 'subscription.mrr.snapshot')
        self.assertIn(('subscription_plan_id', '=', self.plan.id), snapshot_action['domain'])
        self.assertEqual(reconciliation_action['res_model'], 'subscription.mrr.reconciliation')
        self.assertIn(('subscription_plan_id', '=', self.plan.id), reconciliation_action['domain'])
        self.assertEqual(anomaly_action['res_model'], 'subscription.mrr.movement.anomaly')
        self.assertIn(('subscription_plan_id', '=', self.plan.id), anomaly_action['domain'])
        self.assertEqual(movement_action['res_model'], 'subscription.mrr.movement')
        self.assertIn(('subscription_plan_id', '=', self.plan.id), movement_action['domain'])

    def test_generate_wizard_returns_dashboard_form(self):
        self._create_summary()
        wizard = self.env['subscription.mrr.kpi.dashboard.generate.wizard'].sudo().create({
            'opening_date': self.opening_date,
            'closing_date': self.closing_date,
            'company_id': self.env.company.id,
            'currency_id': self.currency.id,
            'subscription_plan_id': self.plan.id,
        })

        action = wizard.action_generate()

        self.assertEqual(action['res_model'], 'subscription.mrr.kpi.dashboard')
        self.assertEqual(action['view_mode'], 'form')
