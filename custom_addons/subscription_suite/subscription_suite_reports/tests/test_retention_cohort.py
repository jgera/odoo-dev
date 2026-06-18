from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestSubscriptionRetentionCohort(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Cohort Customer'})
        self.product = self.env['product.product'].create({
            'name': 'Cohort Product',
            'list_price': 100.0,
            'type': 'service',
        })
        self.currency = self.env.company.currency_id
        self.other_currency = self.env['res.currency'].search([('id', '!=', self.currency.id)], limit=1)
        if not self.other_currency:
            self.other_currency = self.env['res.currency'].create({
                'name': 'CRT',
                'symbol': 'C',
                'rounding': 0.01,
                'decimal_places': 2,
            })
        self.other_pricelist = self.env['product.pricelist'].create({
            'name': 'Cohort Alternate Currency',
            'currency_id': self.other_currency.id,
        })
        self.plan = self.env['subscription.plan'].create({
            'name': 'Cohort Monthly',
            'code': 'COHORT-MONTHLY',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.other_plan = self.env['subscription.plan'].create({
            'name': 'Cohort Pro',
            'code': 'COHORT-PRO',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        today = fields.Date.today()
        self.cohort_month = today.replace(day=1) + relativedelta(years=5)
        self.middle_month = self.cohort_month + relativedelta(months=1)
        self.end_month = self.cohort_month + relativedelta(months=2)

    def _create_subscription(
        self,
        plan=None,
        currency=None,
        start_date=None,
        trial_start_date=None,
        state='active',
        cancellation_date=False,
        price=100.0,
    ):
        return self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'currency_id': (currency or self.currency).id,
            'pricelist_id': self.other_pricelist.id if currency == self.other_currency else False,
            'is_subscription': True,
            'subscription_state': state,
            'subscription_plan_id': (plan or self.plan).id,
            'subscription_start_date': start_date,
            'trial_start_date': trial_start_date,
            'cancellation_date': cancellation_date,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'is_recurring': True,
                'price_unit': price,
                'product_uom_qty': 1.0,
            })],
        })

    def _generate(self, plan=None):
        return self.env['subscription.retention.cohort'].sudo().generate_for_period(
            self.cohort_month,
            self.end_month,
            company=self.env.company,
            plan=plan,
        )

    def _row(self, rows, period_month, plan=None):
        return rows.filtered(
            lambda row: row.period_month == period_month
            and row.subscription_plan_id == (plan or self.plan)
        )

    def test_monthly_cohort_generation_creates_period_rows(self):
        self._create_subscription(start_date=self.cohort_month + relativedelta(days=4))

        rows = self._generate(plan=self.plan)

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows.mapped('cohort_age_months'), [0, 1, 2])
        self.assertEqual(set(rows.mapped('status')), {'ready'})
        self.assertEqual(set(rows.mapped('starting_subscription_count')), {1})
        self.assertEqual(set(rows.mapped('retained_subscription_count')), {1})
        self.assertAlmostEqual(rows[0].retention_rate, 100.0, places=2)

    def test_cancelled_subscription_churns_from_cancellation_month(self):
        self._create_subscription(start_date=self.cohort_month, price=100.0)
        self._create_subscription(
            start_date=self.cohort_month,
            state='cancelled',
            cancellation_date=self.middle_month + relativedelta(days=10),
            price=50.0,
        )

        rows = self._generate(plan=self.plan)

        opening = self._row(rows, self.cohort_month)
        middle = self._row(rows, self.middle_month)
        closing = self._row(rows, self.end_month)
        self.assertEqual(opening.retained_subscription_count, 2)
        self.assertEqual(middle.retained_subscription_count, 1)
        self.assertEqual(middle.churned_subscription_count, 1)
        self.assertEqual(closing.churned_subscription_count, 1)
        self.assertAlmostEqual(middle.retention_rate, 50.0, places=2)
        self.assertAlmostEqual(middle.churned_mrr, 50.0, places=2)

    def test_cancelled_without_date_churns_only_in_generation_period(self):
        self._create_subscription(start_date=self.cohort_month, state='cancelled', price=80.0)

        rows = self._generate(plan=self.plan)

        self.assertEqual(self._row(rows, self.cohort_month).retained_subscription_count, 1)
        self.assertEqual(self._row(rows, self.middle_month).retained_subscription_count, 1)
        self.assertEqual(self._row(rows, self.end_month).churned_subscription_count, 1)

    def test_trial_start_fallback_when_subscription_start_missing(self):
        self._create_subscription(start_date=False, trial_start_date=self.cohort_month + relativedelta(days=2))

        rows = self._generate(plan=self.plan)

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows.mapped('cohort_month'), [self.cohort_month] * 3)

    def test_multiple_plans_and_all_plan_aggregate_are_generated(self):
        self._create_subscription(plan=self.plan, start_date=self.cohort_month, price=100.0)
        self._create_subscription(plan=self.other_plan, start_date=self.cohort_month, price=200.0)

        rows = self._generate()

        period_rows = rows.filtered(lambda row: row.period_month == self.cohort_month)
        self.assertEqual(len(period_rows), 3)
        plan_row = period_rows.filtered(lambda row: row.subscription_plan_id == self.plan)
        other_plan_row = period_rows.filtered(lambda row: row.subscription_plan_id == self.other_plan)
        all_plan_row = period_rows.filtered(lambda row: not row.subscription_plan_id)
        self.assertAlmostEqual(plan_row.starting_mrr, 100.0, places=2)
        self.assertAlmostEqual(other_plan_row.starting_mrr, 200.0, places=2)
        self.assertAlmostEqual(all_plan_row.starting_mrr, 300.0, places=2)

    def test_multiple_currencies_remain_separated(self):
        self._create_subscription(plan=self.plan, currency=self.currency, start_date=self.cohort_month, price=100.0)
        self._create_subscription(plan=self.plan, currency=self.other_currency, start_date=self.cohort_month, price=500.0)

        rows = self._generate(plan=self.plan)

        period_rows = rows.filtered(lambda row: row.period_month == self.cohort_month)
        self.assertEqual(set(period_rows.mapped('currency_id').ids), {self.currency.id, self.other_currency.id})
        self.assertEqual(len(period_rows), 2)

    def test_plan_filter_limits_rows_and_source_drilldown(self):
        self._create_subscription(plan=self.plan, start_date=self.cohort_month)
        self._create_subscription(plan=self.other_plan, start_date=self.cohort_month)

        rows = self._generate(plan=self.plan)
        action = rows[0].action_view_subscriptions()

        self.assertEqual(set(rows.mapped('subscription_plan_id').ids), {self.plan.id})
        self.assertIn(('subscription_plan_id', '=', self.plan.id), action['domain'])

    def test_all_plan_drilldown_omits_plan_filter(self):
        self._create_subscription(plan=self.plan, start_date=self.cohort_month)
        self._create_subscription(plan=self.other_plan, start_date=self.cohort_month)
        no_plan = self._create_subscription(plan=self.plan, start_date=self.cohort_month)
        no_plan.subscription_plan_id = False

        rows = self._generate()
        all_plan_row = rows.filtered(lambda row: not row.subscription_plan_id and row.period_month == self.cohort_month)
        action = all_plan_row.action_view_subscriptions()

        source_subscriptions = self.env['sale.order'].search(action['domain'])
        self.assertNotIn(('subscription_plan_id', '=', False), action['domain'])
        self.assertNotIn(('subscription_plan_id', '=', self.plan.id), action['domain'])
        self.assertNotIn(('subscription_plan_id', '=', self.other_plan.id), action['domain'])
        self.assertIn(('subscription_plan_id', '!=', False), action['domain'])
        self.assertNotIn(no_plan, source_subscriptions)

    def test_generation_ignores_no_plan_subscriptions(self):
        self._create_subscription(plan=self.plan, start_date=self.cohort_month)
        no_plan = self._create_subscription(plan=self.plan, start_date=self.cohort_month)
        no_plan.subscription_plan_id = False

        rows = self._generate()

        all_plan_row = rows.filtered(lambda row: not row.subscription_plan_id and row.period_month == self.cohort_month)
        self.assertEqual(all_plan_row.starting_subscription_count, 1)

    def test_rerun_is_idempotent(self):
        self._create_subscription(start_date=self.cohort_month)

        self._generate(plan=self.plan)
        self._generate(plan=self.plan)

        rows = self.env['subscription.retention.cohort'].search([
            ('cohort_month', '=', self.cohort_month),
            ('company_id', '=', self.env.company.id),
            ('currency_id', '=', self.currency.id),
            ('subscription_plan_id', '=', self.plan.id),
        ])
        self.assertEqual(len(rows), 3)

    def test_invalid_month_range_is_blocked(self):
        with self.assertRaises(ValidationError):
            self.env['subscription.retention.cohort'].sudo().generate_for_period(
                self.end_month,
                self.cohort_month,
                company=self.env.company,
                plan=self.plan,
            )

    def test_generate_wizard_returns_generated_rows(self):
        self._create_subscription(start_date=self.cohort_month)
        wizard = self.env['subscription.retention.cohort.generate.wizard'].sudo().create({
            'cohort_start_month': self.cohort_month,
            'cohort_end_month': self.end_month,
            'company_id': self.env.company.id,
            'subscription_plan_id': self.plan.id,
        })

        action = wizard.action_generate()

        self.assertEqual(action['res_model'], 'subscription.retention.cohort')
        self.assertEqual(action['view_mode'], 'list,pivot,graph,form')
