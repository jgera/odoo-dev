from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestGeneratedAnalyticsLifecycle(TransactionCase):

    def setUp(self):
        super().setUp()
        self.currency = self.env.company.currency_id
        self.company = self.env['res.company'].create({
            'name': 'Generated Analytics Lifecycle Company',
            'currency_id': self.currency.id,
        })
        self.other_company = self.env['res.company'].create({
            'name': 'Generated Analytics Other Company',
            'currency_id': self.currency.id,
        })
        self.plan = self.env['subscription.plan'].create({
            'name': 'Generated Analytics Plan',
            'code': 'GENERATED-ANALYTICS',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.other_plan = self.env['subscription.plan'].create({
            'name': 'Generated Analytics Other Plan',
            'code': 'GENERATED-ANALYTICS-OTHER',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.opening_date = fields.Date.today() - relativedelta(days=30)
        self.closing_date = fields.Date.today()
        self.forecast_month = self.closing_date.replace(day=1)
        self.next_month = self.forecast_month + relativedelta(months=1)
        self.generated_user = self.env.ref('base.public_user')

    def _snapshot_values(self, company=None, plan=None, snapshot_date=None, amount=100.0):
        return {
            'snapshot_date': snapshot_date or self.opening_date,
            'company_id': (company or self.company).id,
            'currency_id': self.currency.id,
            'subscription_plan_id': (plan or self.plan).id,
            'subscription_count': 1,
            'active_count': 1,
            'active_mrr': amount,
            'total_recurring_mrr': amount,
            'arr': amount * 12,
        }

    def _create_snapshot(self, **kwargs):
        return self.env['subscription.mrr.snapshot'].sudo().create(self._snapshot_values(**kwargs))

    def _create_reconciliation(self, company=None, plan=None):
        return self.env['subscription.mrr.reconciliation'].sudo().create({
            'opening_date': self.opening_date,
            'closing_date': self.closing_date,
            'company_id': (company or self.company).id,
            'currency_id': self.currency.id,
            'subscription_plan_id': (plan or self.plan).id,
            'status': 'matched',
            'opening_mrr': 100.0,
            'closing_mrr': 120.0,
            'snapshot_delta_mrr': 20.0,
            'expansion_mrr': 20.0,
            'net_movement_mrr': 20.0,
        })

    def _create_anomaly(self, company=None, plan=None):
        plan = plan or self.plan
        return self.env['subscription.mrr.movement.anomaly'].sudo().create({
            'opening_date': self.opening_date,
            'closing_date': self.closing_date,
            'bucket_key': '%s:%s:%s' % ((company or self.company).id, self.currency.id, plan.id if plan else 'no_plan'),
            'anomaly_type': 'movement_only' if plan else 'missing_plan',
            'company_id': (company or self.company).id,
            'currency_id': self.currency.id,
            'subscription_plan_id': plan.id if plan else False,
            'movement_count': 1,
            'expansion_mrr': 20.0,
            'net_movement_mrr': 20.0,
        })

    def _create_summary(self, company=None, plan=None):
        return self.env['subscription.mrr.kpi.summary'].sudo().create({
            'opening_date': self.opening_date,
            'closing_date': self.closing_date,
            'company_id': (company or self.company).id,
            'currency_id': self.currency.id,
            'subscription_plan_id': (plan or self.plan).id if plan else False,
            'bucket_key': '%s:%s:%s' % ((company or self.company).id, self.currency.id, (plan or self.plan).id if plan else 'all_plans'),
            'status': 'ready',
            'opening_mrr': 100.0,
            'closing_mrr': 120.0,
            'snapshot_delta_mrr': 20.0,
            'expansion_mrr': 20.0,
            'net_new_mrr': 20.0,
            'nrr': 120.0,
            'grr': 100.0,
        })

    def _create_dashboard(self, company=None, plan=None):
        return self.env['subscription.mrr.kpi.dashboard'].sudo().create({
            'name': 'Generated Analytics Dashboard Sentinel',
            'opening_date': self.opening_date,
            'closing_date': self.closing_date,
            'company_id': (company or self.company).id,
            'currency_id': self.currency.id,
            'subscription_plan_id': plan.id if plan else False,
            'bucket_key': '%s:%s:%s' % ((company or self.company).id, self.currency.id, plan.id if plan else 'all_plans'),
            'status': 'ready',
            'summary_count': 1,
            'opening_mrr': 100.0,
            'closing_mrr': 120.0,
            'snapshot_delta_mrr': 20.0,
            'expansion_mrr': 20.0,
            'net_new_mrr': 20.0,
            'nrr': 120.0,
            'grr': 100.0,
        })

    def _create_waterfall(self, company=None, plan=None, bucket_type='opening'):
        return self.env['subscription.mrr.waterfall'].sudo().create({
            'opening_date': self.opening_date,
            'closing_date': self.closing_date,
            'company_id': (company or self.company).id,
            'currency_id': self.currency.id,
            'subscription_plan_id': plan.id if plan else False,
            'bucket_key': '%s:%s:%s' % ((company or self.company).id, self.currency.id, plan.id if plan else 'all_plans'),
            'status': 'ready',
            'source_count': 1,
            'bucket_sequence': 10,
            'bucket_type': bucket_type,
            'bucket_label': '01 Opening MRR',
            'amount': 100.0,
            'starting_mrr': 0.0,
            'ending_mrr': 100.0,
            'expected_closing_mrr': 120.0,
            'actual_closing_mrr': 120.0,
        })

    def _create_cohort(self, company=None, plan=None):
        return self.env['subscription.retention.cohort'].sudo().create({
            'cohort_month': self.forecast_month,
            'period_month': self.forecast_month,
            'cohort_age_months': 0,
            'company_id': (company or self.company).id,
            'currency_id': self.currency.id,
            'subscription_plan_id': plan.id if plan else False,
            'bucket_key': '%s:%s:%s:%s:%s' % (
                (company or self.company).id,
                self.currency.id,
                plan.id if plan else 'all_plans',
                self.forecast_month,
                self.forecast_month,
            ),
            'status': 'ready',
            'starting_subscription_count': 1,
            'retained_subscription_count': 1,
            'starting_mrr': 100.0,
            'retained_mrr': 100.0,
            'retention_rate': 100.0,
        })

    def _create_forecast(self, company=None, plan=None):
        return self.env['subscription.revenue.forecast'].sudo().create({
            'forecast_month': self.forecast_month,
            'company_id': (company or self.company).id,
            'currency_id': self.currency.id,
            'subscription_plan_id': plan.id if plan else False,
            'bucket_key': '%s:%s:%s:%s' % (
                (company or self.company).id,
                self.currency.id,
                plan.id if plan else 'all_plans',
                self.forecast_month,
            ),
            'status': 'ready',
            'source_count': 1,
            'active_base_mrr': 100.0,
            'net_forecast_mrr': 100.0,
        })

    def test_non_manager_cannot_generate_analytics_records(self):
        user_env = self.env(user=self.generated_user)

        with self.assertRaises(AccessError):
            user_env['subscription.mrr.snapshot'].generate_for_date(self.opening_date, company=self.company)
        with self.assertRaises(AccessError):
            user_env['subscription.mrr.reconciliation'].generate_for_period(
                self.opening_date, self.closing_date, company=self.company
            )
        with self.assertRaises(AccessError):
            user_env['subscription.mrr.movement.anomaly'].generate_for_period(
                self.opening_date, self.closing_date, company=self.company
            )
        with self.assertRaises(AccessError):
            user_env['subscription.mrr.kpi.summary'].generate_for_period(
                self.opening_date, self.closing_date, company=self.company
            )
        with self.assertRaises(AccessError):
            user_env['subscription.mrr.kpi.dashboard'].generate_for_period(
                self.opening_date, self.closing_date, self.company, self.currency
            )
        with self.assertRaises(AccessError):
            user_env['subscription.mrr.waterfall'].generate_for_period(
                self.opening_date, self.closing_date, self.company, self.currency
            )
        with self.assertRaises(AccessError):
            user_env['subscription.retention.cohort'].generate_for_period(
                self.forecast_month, self.next_month, company=self.company
            )
        with self.assertRaises(AccessError):
            user_env['subscription.revenue.forecast'].generate_for_period(
                self.forecast_month, self.next_month, company=self.company
            )

    def test_company_scoped_snapshot_regeneration_preserves_adjacent_company(self):
        other_company_snapshot = self._create_snapshot(company=self.other_company)

        self.env['subscription.mrr.snapshot'].sudo().generate_for_date(self.opening_date, company=self.company)

        self.assertTrue(other_company_snapshot.exists())

    def test_plan_scoped_regeneration_preserves_adjacent_generated_rows(self):
        sentinels = (
            self._create_reconciliation(plan=self.other_plan),
            self._create_anomaly(plan=self.other_plan),
            self._create_summary(plan=self.other_plan),
            self._create_dashboard(plan=False),
            self._create_dashboard(plan=self.other_plan),
            self._create_waterfall(plan=False),
            self._create_waterfall(plan=self.other_plan),
            self._create_cohort(plan=False),
            self._create_cohort(plan=self.other_plan),
            self._create_forecast(plan=False),
            self._create_forecast(plan=self.other_plan),
        )

        self.env['subscription.mrr.reconciliation'].sudo().generate_for_period(
            self.opening_date, self.closing_date, company=self.company, plan=self.plan
        )
        self.env['subscription.mrr.movement.anomaly'].sudo().generate_for_period(
            self.opening_date, self.closing_date, company=self.company, plan=self.plan
        )
        self.env['subscription.mrr.kpi.summary'].sudo().generate_for_period(
            self.opening_date, self.closing_date, company=self.company, plan=self.plan
        )
        self.env['subscription.mrr.kpi.dashboard'].sudo().generate_for_period(
            self.opening_date, self.closing_date, self.company, self.currency, plan=self.plan
        )
        self.env['subscription.mrr.waterfall'].sudo().generate_for_period(
            self.opening_date, self.closing_date, self.company, self.currency, plan=self.plan
        )
        self.env['subscription.retention.cohort'].sudo().generate_for_period(
            self.forecast_month, self.next_month, company=self.company, plan=self.plan
        )
        self.env['subscription.revenue.forecast'].sudo().generate_for_period(
            self.forecast_month, self.next_month, company=self.company, plan=self.plan
        )

        for sentinel in sentinels:
            self.assertTrue(sentinel.exists())
