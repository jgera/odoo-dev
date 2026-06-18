from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class TestAnalyticsPerformanceSmoke(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env['res.company'].create({
            'name': 'Analytics Smoke Company',
            'currency_id': self.env.company.currency_id.id,
        })
        self.currency = self.company.currency_id
        self.other_currency = self.env['res.currency'].search([('id', '!=', self.currency.id)], limit=1)
        if not self.other_currency:
            self.other_currency = self.env['res.currency'].create({
                'name': 'ASX',
                'symbol': 'A',
                'rounding': 0.01,
                'decimal_places': 2,
            })
        self.other_pricelist = self.env['product.pricelist'].create({
            'name': 'Analytics Smoke Alternate Currency',
            'currency_id': self.other_currency.id,
            'company_id': self.company.id,
        })
        self.partner = self.env['res.partner'].create({'name': 'Analytics Smoke Customer'})
        self.product = self.env['product.product'].create({
            'name': 'Analytics Smoke Service',
            'list_price': 100.0,
            'type': 'service',
        })
        self.plan = self.env['subscription.plan'].create({
            'name': 'Analytics Smoke Monthly',
            'code': 'ANALYTICS-SMOKE-MONTHLY',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.other_plan = self.env['subscription.plan'].create({
            'name': 'Analytics Smoke Pro',
            'code': 'ANALYTICS-SMOKE-PRO',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.churn_reason = self.env['subscription.cancel.reason'].create({'name': 'Analytics Smoke Churn'})
        self.opening_date = fields.Date.today() - relativedelta(days=30)
        self.closing_date = fields.Date.today()
        self.cohort_start_month = self.opening_date.replace(day=1)
        self.forecast_start_month = self.closing_date.replace(day=1)
        self.forecast_end_month = self.forecast_start_month + relativedelta(months=1)

    def _date_in_month(self, month, day=10):
        return month + relativedelta(days=day - 1)

    def _create_subscription(
        self,
        plan=None,
        currency=None,
        state='active',
        price=100.0,
        start_date=None,
        next_invoice_date=False,
        subscription_end_date=False,
        pending_cancellation=False,
        cancellation_effective_date=False,
        cancellation_date=False,
        cancellation_reason=False,
        cancellation_feedback=False,
    ):
        currency = currency or self.currency
        return self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'currency_id': currency.id,
            'pricelist_id': self.other_pricelist.id if currency == self.other_currency else False,
            'is_subscription': True,
            'subscription_state': state,
            'subscription_plan_id': (plan or self.plan).id,
            'subscription_start_date': start_date or self.cohort_start_month,
            'next_invoice_date': next_invoice_date,
            'subscription_end_date': subscription_end_date,
            'pending_cancellation': pending_cancellation,
            'cancellation_effective_date': cancellation_effective_date,
            'cancellation_date': cancellation_date,
            'cancellation_reason_id': cancellation_reason.id if cancellation_reason else False,
            'cancellation_feedback': cancellation_feedback,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'is_recurring': True,
                'price_unit': price,
                'product_uom_qty': 1.0,
            })],
        })

    def _create_no_plan_subscription(self):
        subscription = self._create_subscription(next_invoice_date=self._date_in_month(self.forecast_start_month))
        subscription.subscription_plan_id = False
        return subscription

    def _create_movement(self, subscription, movement_type, amount):
        return self.env['subscription.mrr.movement'].create({
            'name': '%s analytics smoke movement' % movement_type,
            'movement_date': self.closing_date,
            'movement_type': movement_type,
            'subscription_id': subscription.id,
            'previous_mrr': max((subscription.mrr or 0.0) - amount, 0.0),
            'new_mrr': subscription.mrr or 0.0,
            'amount': amount,
        })

    def _generate_chain(self):
        Snapshot = self.env['subscription.mrr.snapshot'].sudo()
        Reconciliation = self.env['subscription.mrr.reconciliation'].sudo()
        Anomaly = self.env['subscription.mrr.movement.anomaly'].sudo()
        Summary = self.env['subscription.mrr.kpi.summary'].sudo()
        Dashboard = self.env['subscription.mrr.kpi.dashboard'].sudo()
        Waterfall = self.env['subscription.mrr.waterfall'].sudo()
        Cohort = self.env['subscription.retention.cohort'].sudo()
        Forecast = self.env['subscription.revenue.forecast'].sudo()
        ChurnReason = self.env['subscription.churn.reason.summary'].sudo()
        TopPlan = self.env['subscription.plan.performance.summary'].sudo()

        Snapshot.generate_for_date(self.opening_date, company=self.company)
        Snapshot.generate_for_date(self.closing_date, company=self.company)
        Reconciliation.generate_for_period(self.opening_date, self.closing_date, company=self.company)
        Anomaly.generate_for_period(self.opening_date, self.closing_date, company=self.company)
        Summary.generate_for_period(self.opening_date, self.closing_date, company=self.company)
        for currency in (self.currency, self.other_currency):
            Dashboard.generate_for_period(self.opening_date, self.closing_date, self.company, currency)
            Waterfall.generate_for_period(self.opening_date, self.closing_date, self.company, currency)
        Cohort.generate_for_period(self.cohort_start_month, self.forecast_end_month, company=self.company)
        Forecast.generate_for_period(self.forecast_start_month, self.forecast_end_month, company=self.company)
        ChurnReason.generate_for_period(self.opening_date, self.closing_date, company=self.company)
        TopPlan.generate_for_period(self.opening_date, self.closing_date, company=self.company)

    def _count_rows(self, model_name, domain):
        return self.env[model_name].search_count(domain)

    def test_generated_analytics_stack_smoke_is_idempotent_and_scoped(self):
        monthly = self._create_subscription(
            plan=self.plan,
            price=100.0,
            next_invoice_date=self._date_in_month(self.forecast_start_month),
        )
        monthly_paused = self._create_subscription(plan=self.plan, state='paused', price=80.0)
        pro = self._create_subscription(
            plan=self.other_plan,
            price=200.0,
            next_invoice_date=self._date_in_month(self.forecast_start_month),
            subscription_end_date=self._date_in_month(self.forecast_start_month, day=20),
        )
        pro_churn = self._create_subscription(
            plan=self.other_plan,
            price=150.0,
            pending_cancellation=True,
            cancellation_effective_date=self._date_in_month(self.forecast_start_month, day=25),
        )
        alternate_currency = self._create_subscription(
            plan=self.plan,
            currency=self.other_currency,
            price=500.0,
            next_invoice_date=self._date_in_month(self.forecast_start_month),
        )
        self._create_subscription(plan=self.plan, state='cancelled', price=60.0)
        churned_with_reason = self._create_subscription(
            plan=self.plan,
            state='cancelled',
            price=70.0,
            cancellation_date=self.opening_date + relativedelta(days=5),
            cancellation_reason=self.churn_reason,
            cancellation_feedback='Smoke feedback',
        )
        no_plan = self._create_no_plan_subscription()

        self._create_movement(monthly, 'new', 100.0)
        self._create_movement(monthly_paused, 'expansion', 20.0)
        self._create_movement(pro, 'contraction', -30.0)
        self._create_movement(pro_churn, 'churn', -150.0)
        self._create_movement(alternate_currency, 'expansion', 50.0)
        self._create_movement(no_plan, 'expansion', 10.0)
        self._create_movement(churned_with_reason, 'churn', -70.0)

        self._generate_chain()
        counts_after_first_run = {
            model_name: self._count_rows(model_name, domain)
            for model_name, domain in {
                'subscription.mrr.snapshot': [('company_id', '=', self.company.id)],
                'subscription.mrr.reconciliation': [('company_id', '=', self.company.id)],
                'subscription.mrr.movement.anomaly': [('company_id', '=', self.company.id)],
                'subscription.mrr.kpi.summary': [('company_id', '=', self.company.id)],
                'subscription.mrr.kpi.dashboard': [('company_id', '=', self.company.id)],
                'subscription.mrr.waterfall': [('company_id', '=', self.company.id)],
                'subscription.retention.cohort': [('company_id', '=', self.company.id)],
                'subscription.revenue.forecast': [('company_id', '=', self.company.id)],
                'subscription.churn.reason.summary': [('company_id', '=', self.company.id)],
                'subscription.plan.performance.summary': [('company_id', '=', self.company.id)],
            }.items()
        }
        self._generate_chain()
        counts_after_second_run = {
            model_name: self._count_rows(model_name, domain)
            for model_name, domain in {
                'subscription.mrr.snapshot': [('company_id', '=', self.company.id)],
                'subscription.mrr.reconciliation': [('company_id', '=', self.company.id)],
                'subscription.mrr.movement.anomaly': [('company_id', '=', self.company.id)],
                'subscription.mrr.kpi.summary': [('company_id', '=', self.company.id)],
                'subscription.mrr.kpi.dashboard': [('company_id', '=', self.company.id)],
                'subscription.mrr.waterfall': [('company_id', '=', self.company.id)],
                'subscription.retention.cohort': [('company_id', '=', self.company.id)],
                'subscription.revenue.forecast': [('company_id', '=', self.company.id)],
                'subscription.churn.reason.summary': [('company_id', '=', self.company.id)],
                'subscription.plan.performance.summary': [('company_id', '=', self.company.id)],
            }.items()
        }

        self.assertEqual(counts_after_first_run, counts_after_second_run)
        for count in counts_after_second_run.values():
            self.assertGreater(count, 0)

        dashboard_currencies = self.env['subscription.mrr.kpi.dashboard'].search([
            ('company_id', '=', self.company.id),
        ]).mapped('currency_id')
        self.assertEqual(set(dashboard_currencies.ids), {self.currency.id, self.other_currency.id})

        waterfall_currencies = self.env['subscription.mrr.waterfall'].search([
            ('company_id', '=', self.company.id),
        ]).mapped('currency_id')
        self.assertEqual(set(waterfall_currencies.ids), {self.currency.id, self.other_currency.id})

        all_plan_forecast = self.env['subscription.revenue.forecast'].search([
            ('company_id', '=', self.company.id),
            ('currency_id', '=', self.currency.id),
            ('forecast_month', '=', self.forecast_start_month),
            ('subscription_plan_id', '=', False),
        ], limit=1)
        forecast_action = all_plan_forecast.action_view_source_subscriptions()
        forecast_sources = self.env['sale.order'].search(forecast_action['domain'])
        self.assertNotIn(('subscription_plan_id', '=', False), forecast_action['domain'])
        self.assertIn(('subscription_plan_id', '!=', False), forecast_action['domain'])
        self.assertNotIn(no_plan, forecast_sources)

        all_plan_cohort = self.env['subscription.retention.cohort'].search([
            ('company_id', '=', self.company.id),
            ('currency_id', '=', self.currency.id),
            ('cohort_month', '=', self.cohort_start_month),
            ('period_month', '=', self.cohort_start_month),
            ('subscription_plan_id', '=', False),
        ], limit=1)
        cohort_action = all_plan_cohort.action_view_subscriptions()
        cohort_sources = self.env['sale.order'].search(cohort_action['domain'])
        self.assertNotIn(('subscription_plan_id', '=', False), cohort_action['domain'])
        self.assertIn(('subscription_plan_id', '!=', False), cohort_action['domain'])
        self.assertNotIn(no_plan, cohort_sources)

        all_reason_churn = self.env['subscription.churn.reason.summary'].search([
            ('company_id', '=', self.company.id),
            ('currency_id', '=', self.currency.id),
            ('subscription_plan_id', '=', False),
            ('reason_bucket', '=', 'all_reasons'),
        ], limit=1)
        churn_action = all_reason_churn.action_view_source_subscriptions()
        churn_sources = self.env['sale.order'].search(churn_action['domain'])
        self.assertNotIn(('subscription_plan_id', '=', False), churn_action['domain'])
        self.assertIn(('subscription_plan_id', '!=', False), churn_action['domain'])
        self.assertNotIn(no_plan, churn_sources)
        self.assertIn(churned_with_reason, churn_sources)

        top_plan = self.env['subscription.plan.performance.summary'].search([
            ('company_id', '=', self.company.id),
            ('currency_id', '=', self.currency.id),
            ('subscription_plan_id', '=', self.plan.id),
        ], limit=1)
        self.assertTrue(top_plan)
        self.assertEqual(top_plan.subscription_plan_id, self.plan)
