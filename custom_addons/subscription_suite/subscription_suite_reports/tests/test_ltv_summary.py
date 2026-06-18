from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestSubscriptionLtvSummary(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'LTV Customer'})
        self.product = self.env['product.product'].create({
            'name': 'LTV Product',
            'list_price': 100.0,
            'type': 'service',
        })
        self.currency = self.env.company.currency_id
        self.company = self.env['res.company'].create({
            'name': 'LTV Company',
            'currency_id': self.currency.id,
        })
        self.other_currency = self.env['res.currency'].search([('id', '!=', self.currency.id)], limit=1)
        if not self.other_currency:
            self.other_currency = self.env['res.currency'].create({
                'name': 'LTV',
                'symbol': 'L',
                'rounding': 0.01,
                'decimal_places': 2,
            })
        self.other_pricelist = self.env['product.pricelist'].create({
            'name': 'LTV Alternate Currency',
            'currency_id': self.other_currency.id,
            'company_id': self.company.id,
        })
        self.plan = self.env['subscription.plan'].create({
            'name': 'LTV Monthly',
            'code': 'LTV-MONTHLY',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.other_plan = self.env['subscription.plan'].create({
            'name': 'LTV Pro',
            'code': 'LTV-PRO',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.opening_date = fields.Date.today().replace(day=1) + relativedelta(years=7)
        self.closing_date = self.opening_date + relativedelta(months=1)
        self.cohort_start_month = self.opening_date
        self.cohort_end_month = self.closing_date

    def _create_arpu(self, plan=None, currency=None, arpu=100.0, status='ready'):
        return self.env['subscription.arpu.summary'].sudo().create({
            'opening_date': self.opening_date,
            'closing_date': self.closing_date,
            'company_id': self.company.id,
            'currency_id': (currency or self.currency).id,
            'subscription_plan_id': (plan or self.plan).id if plan is not False else False,
            'bucket_key': '%s:%s:%s' % (
                self.company.id,
                (currency or self.currency).id,
                (plan or self.plan).id if plan is not False else 'all_plans',
            ),
            'status': status,
            'arpu': arpu,
        })

    def _create_retention(self, plan=None, currency=None, starting=10, churned=2):
        return self.env['subscription.retention.cohort'].sudo().create({
            'cohort_month': self.cohort_start_month,
            'period_month': self.closing_date,
            'cohort_age_months': 1,
            'company_id': self.company.id,
            'currency_id': (currency or self.currency).id,
            'subscription_plan_id': (plan or self.plan).id if plan is not False else False,
            'bucket_key': '%s:%s:%s:%s:%s' % (
                self.company.id,
                (currency or self.currency).id,
                (plan or self.plan).id if plan is not False else 'all_plans',
                self.cohort_start_month,
                self.closing_date,
            ),
            'status': 'ready',
            'starting_subscription_count': starting,
            'retained_subscription_count': starting - churned,
            'churned_subscription_count': churned,
            'retention_rate': ((starting - churned) / starting) * 100.0 if starting else 0.0,
            'churn_rate': (churned / starting) * 100.0 if starting else 0.0,
        })

    def _create_subscription(self, plan=None, currency=None):
        currency = currency or self.currency
        return self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'currency_id': currency.id,
            'pricelist_id': self.other_pricelist.id if currency == self.other_currency else False,
            'is_subscription': True,
            'subscription_state': 'active',
            'subscription_plan_id': (plan or self.plan).id,
            'subscription_start_date': self.cohort_start_month,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'is_recurring': True,
                'price_unit': 100.0,
                'product_uom_qty': 1.0,
            })],
        })

    def _generate(self, plan=None):
        return self.env['subscription.ltv.summary'].sudo().generate_for_period(
            self.opening_date,
            self.closing_date,
            self.cohort_start_month,
            self.cohort_end_month,
            company=self.company,
            plan=plan,
        )

    def _plan_row(self, rows, plan=None, currency=None):
        return rows.filtered(
            lambda row: row.subscription_plan_id == (plan or self.plan)
            and row.currency_id == (currency or self.currency)
        )

    def test_ltv_computes_from_arpu_and_churn_rate(self):
        self._create_arpu(arpu=120.0)
        self._create_retention(starting=10, churned=2)

        row = self._plan_row(self._generate(plan=self.plan))

        self.assertEqual(row.status, 'ready')
        self.assertAlmostEqual(row.churn_rate_decimal, 0.2, places=6)
        self.assertAlmostEqual(row.churn_rate, 20.0, places=2)
        self.assertAlmostEqual(row.estimated_lifetime_months, 5.0, places=2)
        self.assertAlmostEqual(row.ltv, 600.0, places=2)

    def test_zero_churn_rate_sets_status_and_zero_ltv(self):
        self._create_arpu(arpu=100.0)
        self._create_retention(starting=10, churned=0)

        row = self._plan_row(self._generate(plan=self.plan))

        self.assertEqual(row.status, 'zero_churn_rate')
        self.assertAlmostEqual(row.estimated_lifetime_months, 0.0, places=2)
        self.assertAlmostEqual(row.ltv, 0.0, places=2)

    def test_missing_arpu_summary_status(self):
        self._create_retention(starting=10, churned=2)

        row = self._plan_row(self._generate(plan=self.plan))

        self.assertEqual(row.status, 'missing_arpu_summary')
        self.assertAlmostEqual(row.arpu, 0.0, places=2)

    def test_non_ready_arpu_summary_counts_as_missing_arpu(self):
        self._create_arpu(arpu=100.0, status='missing_opening_snapshot')
        self._create_retention(starting=10, churned=2)

        row = self._plan_row(self._generate(plan=self.plan))

        self.assertEqual(row.status, 'missing_arpu_summary')

    def test_missing_retention_cohort_status(self):
        self._create_arpu(arpu=100.0)

        row = self._plan_row(self._generate(plan=self.plan))

        self.assertEqual(row.status, 'missing_retention_cohort')
        self.assertEqual(row.starting_subscription_count, 0)

    def test_multiple_plans_create_separate_rows(self):
        self._create_arpu(plan=self.plan, arpu=100.0)
        self._create_retention(plan=self.plan, starting=10, churned=2)
        self._create_arpu(plan=self.other_plan, arpu=200.0)
        self._create_retention(plan=self.other_plan, starting=8, churned=4)

        rows = self._generate()

        self.assertAlmostEqual(self._plan_row(rows, self.plan).ltv, 500.0, places=2)
        self.assertAlmostEqual(self._plan_row(rows, self.other_plan).ltv, 400.0, places=2)

    def test_all_plan_generation_aggregates_without_merging_currencies(self):
        self._create_arpu(plan=self.plan, arpu=100.0)
        self._create_retention(plan=self.plan, starting=10, churned=2)
        self._create_arpu(plan=False, arpu=150.0)
        self._create_retention(plan=False, starting=20, churned=5)
        self._create_arpu(plan=self.plan, currency=self.other_currency, arpu=300.0)
        self._create_retention(plan=self.plan, currency=self.other_currency, starting=10, churned=5)

        rows = self._generate()
        all_plan_rows = rows.filtered(lambda row: not row.subscription_plan_id)

        self.assertEqual(set(rows.mapped('currency_id').ids), {self.currency.id, self.other_currency.id})
        self.assertAlmostEqual(all_plan_rows.ltv, 600.0, places=2)

    def test_plan_filter_limits_rows_and_drilldowns(self):
        self._create_arpu(plan=self.plan, arpu=100.0)
        self._create_retention(plan=self.plan, starting=10, churned=2)
        self._create_arpu(plan=self.other_plan, arpu=200.0)
        self._create_retention(plan=self.other_plan, starting=10, churned=5)
        self._create_subscription(plan=self.plan)
        self._create_subscription(plan=self.other_plan)

        row = self._plan_row(self._generate(plan=self.plan))

        self.assertEqual(set(row.mapped('subscription_plan_id').ids), {self.plan.id})
        self.assertIn(('subscription_plan_id', '=', self.plan.id), row.action_view_arpu_summaries()['domain'])
        self.assertIn(('subscription_plan_id', '=', self.plan.id), row.action_view_retention_cohorts()['domain'])
        self.assertIn(('subscription_plan_id', '=', self.plan.id), row.action_view_source_subscriptions()['domain'])

    def test_all_plan_drilldowns_omit_specific_plan_and_exclude_no_plan(self):
        self._create_arpu(plan=False, arpu=100.0)
        self._create_retention(plan=False, starting=10, churned=2)
        plan_subscription = self._create_subscription(plan=self.plan)
        other_subscription = self._create_subscription(plan=self.other_plan)
        no_plan = self._create_subscription(plan=self.plan)
        no_plan.subscription_plan_id = False

        all_plan_row = self._generate().filtered(lambda row: not row.subscription_plan_id)
        action = all_plan_row.action_view_source_subscriptions()
        source_subscriptions = self.env['sale.order'].search(action['domain'])

        self.assertNotIn(('subscription_plan_id', '=', False), action['domain'])
        self.assertNotIn(('subscription_plan_id', '=', self.plan.id), action['domain'])
        self.assertIn(('subscription_plan_id', '!=', False), action['domain'])
        self.assertIn(plan_subscription, source_subscriptions)
        self.assertIn(other_subscription, source_subscriptions)
        self.assertNotIn(no_plan, source_subscriptions)

    def test_rerun_is_idempotent(self):
        self._create_arpu(arpu=100.0)
        self._create_retention(starting=10, churned=2)

        self._generate(plan=self.plan)
        self._generate(plan=self.plan)

        rows = self.env['subscription.ltv.summary'].search([
            ('opening_date', '=', self.opening_date),
            ('closing_date', '=', self.closing_date),
            ('cohort_start_month', '=', self.cohort_start_month),
            ('cohort_end_month', '=', self.cohort_end_month),
            ('company_id', '=', self.company.id),
            ('currency_id', '=', self.currency.id),
            ('subscription_plan_id', '=', self.plan.id),
        ])
        self.assertEqual(len(rows), 1)

    def test_scoped_rerun_preserves_adjacent_generated_rows(self):
        self._create_arpu(arpu=100.0)
        self._create_retention(starting=10, churned=2)
        all_plan = self.env['subscription.ltv.summary'].sudo().create({
            'opening_date': self.opening_date,
            'closing_date': self.closing_date,
            'cohort_start_month': self.cohort_start_month,
            'cohort_end_month': self.cohort_end_month,
            'company_id': self.company.id,
            'currency_id': self.currency.id,
            'subscription_plan_id': False,
            'bucket_key': 'sentinel:all',
            'status': 'ready',
        })
        other_plan = self.env['subscription.ltv.summary'].sudo().create({
            'opening_date': self.opening_date,
            'closing_date': self.closing_date,
            'cohort_start_month': self.cohort_start_month,
            'cohort_end_month': self.cohort_end_month,
            'company_id': self.company.id,
            'currency_id': self.currency.id,
            'subscription_plan_id': self.other_plan.id,
            'bucket_key': 'sentinel:other',
            'status': 'ready',
        })

        self._generate(plan=self.plan)

        self.assertTrue(all_plan.exists())
        self.assertTrue(other_plan.exists())

    def test_invalid_ranges_are_blocked(self):
        with self.assertRaises(ValidationError):
            self.env['subscription.ltv.summary'].sudo().generate_for_period(
                self.closing_date,
                self.opening_date,
                self.cohort_start_month,
                self.cohort_end_month,
                company=self.company,
                plan=self.plan,
            )
        with self.assertRaises(ValidationError):
            self.env['subscription.ltv.summary'].sudo().generate_for_period(
                self.opening_date,
                self.closing_date,
                self.cohort_end_month,
                self.cohort_start_month,
                company=self.company,
                plan=self.plan,
            )

    def test_non_manager_user_cannot_generate_ltv_summaries(self):
        user_env = self.env(user=self.env.ref('base.public_user'))

        with self.assertRaises(AccessError):
            user_env['subscription.ltv.summary'].generate_for_period(
                self.opening_date,
                self.closing_date,
                self.cohort_start_month,
                self.cohort_end_month,
                company=self.company,
                plan=self.plan,
            )

    def test_generate_wizard_returns_generated_rows(self):
        self._create_arpu(arpu=100.0)
        self._create_retention(starting=10, churned=2)
        wizard = self.env['subscription.ltv.summary.generate.wizard'].sudo().create({
            'opening_date': self.opening_date,
            'closing_date': self.closing_date,
            'cohort_start_month': self.cohort_start_month,
            'cohort_end_month': self.cohort_end_month,
            'company_id': self.company.id,
            'subscription_plan_id': self.plan.id,
        })

        action = wizard.action_generate()

        self.assertEqual(action['res_model'], 'subscription.ltv.summary')
        self.assertEqual(action['view_mode'], 'list,pivot,graph,form')
