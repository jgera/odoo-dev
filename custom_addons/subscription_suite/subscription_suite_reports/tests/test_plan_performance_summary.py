from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestSubscriptionPlanPerformanceSummary(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Top Plan Customer'})
        self.product = self.env['product.product'].create({
            'name': 'Top Plan Product',
            'list_price': 100.0,
            'type': 'service',
        })
        self.currency = self.env.company.currency_id
        self.company = self.env['res.company'].create({
            'name': 'Top Plan Company',
            'currency_id': self.currency.id,
        })
        self.other_currency = self.env['res.currency'].search([('id', '!=', self.currency.id)], limit=1)
        if not self.other_currency:
            self.other_currency = self.env['res.currency'].create({
                'name': 'TPX',
                'symbol': 'T',
                'rounding': 0.01,
                'decimal_places': 2,
            })
        self.plan = self.env['subscription.plan'].create({
            'name': 'Top Plan Monthly',
            'code': 'TOP-PLAN-MONTHLY',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.other_plan = self.env['subscription.plan'].create({
            'name': 'Top Plan Pro',
            'code': 'TOP-PLAN-PRO',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.opening_date = fields.Date.today().replace(day=1) + relativedelta(years=9)
        self.closing_date = self.opening_date + relativedelta(months=1, days=-1)
        self.forecast_month = self.opening_date.replace(day=1)

    def _bucket_key(self, company=None, currency=None, plan=None):
        return '%s:%s:%s' % ((company or self.company).id, (currency or self.currency).id, (plan or self.plan).id)

    def _create_snapshot(self, snapshot_date, plan=None, currency=None, total_mrr=100.0, active_count=1):
        return self.env['subscription.mrr.snapshot'].sudo().create({
            'snapshot_date': snapshot_date,
            'company_id': self.company.id,
            'currency_id': (currency or self.currency).id,
            'subscription_plan_id': (plan or self.plan).id,
            'subscription_count': active_count,
            'trial_count': 1,
            'active_count': active_count,
            'paused_count': 2,
            'past_due_count': 3,
            'cancelled_count': 4,
            'expired_count': 5,
            'churned_count': 9,
            'trial_mrr': 10.0,
            'active_mrr': total_mrr,
            'paused_mrr': 20.0,
            'past_due_mrr': 30.0,
            'churned_mrr': 40.0,
            'total_recurring_mrr': total_mrr,
            'arr': total_mrr * 12.0,
        })

    def _create_kpi(self, plan=None, currency=None, net_new_mrr=25.0, status='ready'):
        return self.env['subscription.mrr.kpi.summary'].sudo().create({
            'opening_date': self.opening_date,
            'closing_date': self.closing_date,
            'company_id': self.company.id,
            'currency_id': (currency or self.currency).id,
            'subscription_plan_id': (plan or self.plan).id,
            'bucket_key': self._bucket_key(currency=currency, plan=plan),
            'status': status,
            'opening_mrr': 100.0,
            'closing_mrr': 125.0,
            'snapshot_delta_mrr': 25.0,
            'net_new_mrr': net_new_mrr,
        })

    def _create_arpu(self, plan=None, currency=None, arpu=50.0, status='ready'):
        return self.env['subscription.arpu.summary'].sudo().create({
            'opening_date': self.opening_date,
            'closing_date': self.closing_date,
            'company_id': self.company.id,
            'currency_id': (currency or self.currency).id,
            'subscription_plan_id': (plan or self.plan).id,
            'bucket_key': self._bucket_key(currency=currency, plan=plan),
            'status': status,
            'opening_subscription_count': 2,
            'closing_subscription_count': 4,
            'average_subscription_count': 3,
            'opening_mrr': 100.0,
            'closing_mrr': 200.0,
            'average_mrr': 150.0,
            'arpu': arpu,
        })

    def _create_ltv(self, plan=None, currency=None, ltv=500.0, status='ready'):
        return self.env['subscription.ltv.summary'].sudo().create({
            'opening_date': self.opening_date,
            'closing_date': self.closing_date,
            'cohort_start_month': self.opening_date.replace(day=1),
            'cohort_end_month': self.closing_date.replace(day=1),
            'company_id': self.company.id,
            'currency_id': (currency or self.currency).id,
            'subscription_plan_id': (plan or self.plan).id,
            'bucket_key': self._bucket_key(currency=currency, plan=plan),
            'status': status,
            'arpu': 50.0,
            'starting_subscription_count': 10,
            'churned_subscription_count': 1,
            'churn_rate': 10.0,
            'churn_rate_decimal': 0.1,
            'estimated_lifetime_months': 10.0,
            'ltv': ltv,
        })

    def _create_churn_reason(self, plan=None, currency=None, churned_mrr=30.0, feedback_coverage=80.0):
        return self.env['subscription.churn.reason.summary'].sudo().create({
            'opening_date': self.opening_date,
            'closing_date': self.closing_date,
            'company_id': self.company.id,
            'currency_id': (currency or self.currency).id,
            'subscription_plan_id': (plan or self.plan).id,
            'reason_bucket': 'all_reasons',
            'bucket_key': 'churn:%s' % self._bucket_key(currency=currency, plan=plan),
            'status': 'ready',
            'churned_subscription_count': 2,
            'churned_mrr': churned_mrr,
            'feedback_coverage': feedback_coverage,
            'mrr_source': 'movement',
            'feedback_bucket': 'partial',
        })

    def _create_forecast(self, plan=None, currency=None, upcoming=70.0, scheduled=20.0, net=150.0):
        return self.env['subscription.revenue.forecast'].sudo().create({
            'forecast_month': self.forecast_month,
            'company_id': self.company.id,
            'currency_id': (currency or self.currency).id,
            'subscription_plan_id': (plan or self.plan).id,
            'bucket_key': 'forecast:%s:%s' % (self._bucket_key(currency=currency, plan=plan), self.forecast_month),
            'status': 'ready',
            'source_count': 1,
            'upcoming_invoice_mrr': upcoming,
            'scheduled_churn_mrr': scheduled,
            'net_forecast_mrr': net,
        })

    def _create_full_sources(self, plan=None, currency=None):
        self._create_snapshot(self.opening_date, plan=plan, currency=currency, total_mrr=100.0)
        self._create_snapshot(self.closing_date, plan=plan, currency=currency, total_mrr=150.0, active_count=6)
        self._create_kpi(plan=plan, currency=currency, net_new_mrr=50.0)
        self._create_arpu(plan=plan, currency=currency, arpu=75.0)
        self._create_ltv(plan=plan, currency=currency, ltv=750.0)
        self._create_churn_reason(plan=plan, currency=currency, churned_mrr=35.0, feedback_coverage=90.0)
        self._create_forecast(plan=plan, currency=currency, upcoming=80.0, scheduled=25.0, net=205.0)

    def _generate(self, plan=None):
        return self.env['subscription.plan.performance.summary'].sudo().generate_for_period(
            self.opening_date,
            self.closing_date,
            company=self.company,
            plan=plan,
        )

    def _row(self, rows, plan=None, currency=None):
        return rows.filtered(
            lambda row: row.subscription_plan_id == (plan or self.plan)
            and row.currency_id == (currency or self.currency)
        )

    def test_generates_plan_row_with_source_metrics(self):
        self._create_full_sources()

        row = self._row(self._generate(plan=self.plan))

        self.assertEqual(row.status, 'ready')
        self.assertAlmostEqual(row.opening_mrr, 100.0, places=2)
        self.assertAlmostEqual(row.closing_mrr, 150.0, places=2)
        self.assertAlmostEqual(row.arr, 1800.0, places=2)
        self.assertAlmostEqual(row.net_new_mrr, 50.0, places=2)
        self.assertAlmostEqual(row.arpu, 75.0, places=2)
        self.assertAlmostEqual(row.ltv, 750.0, places=2)
        self.assertEqual(row.subscription_count, 6)
        self.assertEqual(row.trial_count, 1)
        self.assertEqual(row.paused_count, 2)
        self.assertEqual(row.past_due_count, 3)
        self.assertEqual(row.cancelled_count, 4)
        self.assertEqual(row.expired_count, 5)
        self.assertEqual(row.churned_subscription_count, 2)
        self.assertAlmostEqual(row.churned_mrr, 35.0, places=2)
        self.assertAlmostEqual(row.feedback_coverage, 90.0, places=2)
        self.assertAlmostEqual(row.upcoming_invoice_mrr, 80.0, places=2)
        self.assertAlmostEqual(row.scheduled_churn_mrr, 25.0, places=2)
        self.assertAlmostEqual(row.net_forecast_mrr, 205.0, places=2)

    def test_multiple_currencies_remain_separated(self):
        self._create_full_sources(currency=self.currency)
        self._create_full_sources(currency=self.other_currency)

        rows = self._generate()

        self.assertEqual(set(rows.mapped('currency_id').ids), {self.currency.id, self.other_currency.id})

    def test_plan_filter_limits_rows_and_drilldowns(self):
        self._create_full_sources(plan=self.plan)
        self._create_full_sources(plan=self.other_plan)

        row = self._row(self._generate(plan=self.plan))

        self.assertEqual(set(row.mapped('subscription_plan_id').ids), {self.plan.id})
        self.assertIn(('subscription_plan_id', '=', self.plan.id), row.action_view_snapshots()['domain'])
        self.assertIn(('subscription_plan_id', '=', self.plan.id), row.action_view_source_subscriptions()['domain'])

    def test_missing_source_statuses_preserve_available_metrics(self):
        self._create_snapshot(self.opening_date, total_mrr=100.0)
        self._create_snapshot(self.closing_date, total_mrr=150.0)
        self._create_arpu(arpu=60.0)
        row = self._row(self._generate(plan=self.plan))
        self.assertEqual(row.status, 'missing_kpi_summary')
        self.assertAlmostEqual(row.closing_mrr, 150.0, places=2)
        self.assertAlmostEqual(row.arpu, 60.0, places=2)

        self.env['subscription.plan.performance.summary'].search([]).unlink()
        self._create_kpi()
        row = self._row(self._generate(plan=self.plan))
        self.assertEqual(row.status, 'missing_ltv_summary')

        self.env['subscription.plan.performance.summary'].search([]).unlink()
        self._create_ltv()
        row = self._row(self._generate(plan=self.plan))
        self.assertEqual(row.status, 'missing_forecast')

    def test_missing_snapshot_status(self):
        self._create_kpi()

        row = self._row(self._generate(plan=self.plan))

        self.assertEqual(row.status, 'missing_snapshot')
        self.assertAlmostEqual(row.net_new_mrr, 25.0, places=2)

    def test_rerun_is_idempotent(self):
        self._create_full_sources()

        self._generate(plan=self.plan)
        self._generate(plan=self.plan)

        rows = self.env['subscription.plan.performance.summary'].search([
            ('opening_date', '=', self.opening_date),
            ('closing_date', '=', self.closing_date),
            ('company_id', '=', self.company.id),
            ('currency_id', '=', self.currency.id),
            ('subscription_plan_id', '=', self.plan.id),
        ])
        self.assertEqual(len(rows), 1)

    def test_scoped_rerun_preserves_adjacent_rows(self):
        self._create_full_sources(plan=self.plan)
        sentinel = self.env['subscription.plan.performance.summary'].sudo().create({
            'opening_date': self.opening_date,
            'closing_date': self.closing_date,
            'company_id': self.company.id,
            'currency_id': self.currency.id,
            'subscription_plan_id': self.other_plan.id,
            'bucket_key': 'sentinel:other-plan',
            'status': 'ready',
        })

        self._generate(plan=self.plan)

        self.assertTrue(sentinel.exists())

    def test_invalid_period_is_blocked(self):
        with self.assertRaises(ValidationError):
            self.env['subscription.plan.performance.summary'].sudo().generate_for_period(
                self.closing_date,
                self.opening_date,
                company=self.company,
            )

    def test_non_manager_user_cannot_generate_top_plan_summaries(self):
        user_env = self.env(user=self.env.ref('base.public_user'))

        with self.assertRaises(AccessError):
            user_env['subscription.plan.performance.summary'].generate_for_period(
                self.opening_date,
                self.closing_date,
                company=self.company,
            )

    def test_generate_wizard_returns_generated_rows(self):
        self._create_full_sources()
        wizard = self.env['subscription.plan.performance.summary.generate.wizard'].sudo().create({
            'opening_date': self.opening_date,
            'closing_date': self.closing_date,
            'company_id': self.company.id,
            'subscription_plan_id': self.plan.id,
        })

        action = wizard.action_generate()

        self.assertEqual(action['res_model'], 'subscription.plan.performance.summary')
        self.assertEqual(action['view_mode'], 'list,pivot,graph,form')
