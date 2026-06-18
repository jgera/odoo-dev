from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestSubscriptionRevenueForecast(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Forecast Customer'})
        self.product = self.env['product.product'].create({
            'name': 'Forecast Product',
            'list_price': 100.0,
            'type': 'service',
        })
        self.currency = self.env.company.currency_id
        self.company = self.env['res.company'].create({
            'name': 'Forecast Company',
            'currency_id': self.currency.id,
        })
        self.other_currency = self.env['res.currency'].search([('id', '!=', self.currency.id)], limit=1)
        if not self.other_currency:
            self.other_currency = self.env['res.currency'].create({
                'name': 'FCX',
                'symbol': 'F',
                'rounding': 0.01,
                'decimal_places': 2,
            })
        self.other_pricelist = self.env['product.pricelist'].create({
            'name': 'Forecast Alternate Currency',
            'currency_id': self.other_currency.id,
            'company_id': self.company.id,
        })
        self.plan = self.env['subscription.plan'].create({
            'name': 'Forecast Monthly',
            'code': 'FORECAST-MONTHLY',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.other_plan = self.env['subscription.plan'].create({
            'name': 'Forecast Pro',
            'code': 'FORECAST-PRO',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.forecast_month = fields.Date.today().replace(day=1) + relativedelta(years=6)
        self.next_month = self.forecast_month + relativedelta(months=1)

    def _date_in_month(self, month, day=10):
        return month + relativedelta(days=day - 1)

    def _create_subscription(
        self,
        plan=None,
        currency=None,
        state='active',
        next_invoice_date=False,
        subscription_end_date=False,
        pending_cancellation=False,
        cancellation_effective_date=False,
        price=100.0,
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
            'subscription_start_date': self.forecast_month - relativedelta(months=1),
            'next_invoice_date': next_invoice_date,
            'subscription_end_date': subscription_end_date,
            'pending_cancellation': pending_cancellation,
            'cancellation_effective_date': cancellation_effective_date,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'is_recurring': True,
                'price_unit': price,
                'product_uom_qty': 1.0,
            })],
        })

    def _generate(self, plan=None):
        return self.env['subscription.revenue.forecast'].sudo().generate_for_period(
            self.forecast_month,
            self.next_month,
            company=self.company,
            plan=plan,
        )

    def _row(self, rows, month=None, plan=None):
        return rows.filtered(
            lambda row: row.forecast_month == (month or self.forecast_month)
            and row.subscription_plan_id == (plan or self.plan)
        )

    def test_forecast_generation_creates_month_rows(self):
        self._create_subscription(next_invoice_date=self._date_in_month(self.forecast_month), price=100.0)

        rows = self._generate(plan=self.plan)

        self.assertEqual(len(rows), 2)
        first = self._row(rows)
        self.assertEqual(first.upcoming_invoice_count, 1)
        self.assertAlmostEqual(first.upcoming_invoice_mrr, 100.0, places=2)
        self.assertAlmostEqual(first.active_base_mrr, 100.0, places=2)
        self.assertAlmostEqual(first.net_forecast_mrr, 200.0, places=2)

    def test_upcoming_invoices_count_only_dates_inside_month(self):
        self._create_subscription(next_invoice_date=self._date_in_month(self.forecast_month), price=100.0)
        self._create_subscription(next_invoice_date=self._date_in_month(self.next_month), price=50.0)

        rows = self._generate(plan=self.plan)

        self.assertEqual(self._row(rows, self.forecast_month).upcoming_invoice_count, 1)
        self.assertEqual(self._row(rows, self.next_month).upcoming_invoice_count, 1)
        self.assertAlmostEqual(self._row(rows, self.forecast_month).upcoming_invoice_mrr, 100.0, places=2)
        self.assertAlmostEqual(self._row(rows, self.next_month).upcoming_invoice_mrr, 50.0, places=2)

    def test_renewal_due_counts_subscription_end_date(self):
        self._create_subscription(subscription_end_date=self._date_in_month(self.forecast_month), price=120.0)

        rows = self._generate(plan=self.plan)

        self.assertEqual(self._row(rows).renewal_due_count, 1)
        self.assertAlmostEqual(self._row(rows).renewal_due_mrr, 120.0, places=2)

    def test_scheduled_churn_counts_pending_cancellations(self):
        self._create_subscription(
            pending_cancellation=True,
            cancellation_effective_date=self._date_in_month(self.forecast_month),
            price=80.0,
        )

        rows = self._generate(plan=self.plan)

        self.assertEqual(self._row(rows).scheduled_churn_count, 1)
        self.assertAlmostEqual(self._row(rows).scheduled_churn_mrr, 80.0, places=2)
        self.assertAlmostEqual(self._row(rows).net_forecast_mrr, 0.0, places=2)

    def test_cancelled_and_expired_excluded_from_invoice_and_renewal(self):
        self._create_subscription(
            state='cancelled',
            next_invoice_date=self._date_in_month(self.forecast_month),
            subscription_end_date=self._date_in_month(self.forecast_month),
            price=100.0,
        )
        self._create_subscription(
            state='expired',
            next_invoice_date=self._date_in_month(self.forecast_month),
            subscription_end_date=self._date_in_month(self.forecast_month),
            price=50.0,
        )

        rows = self._generate(plan=self.plan)

        self.assertEqual(self._row(rows).upcoming_invoice_count, 0)
        self.assertEqual(self._row(rows).renewal_due_count, 0)
        self.assertAlmostEqual(self._row(rows).active_base_mrr, 0.0, places=2)

    def test_multiple_plans_and_all_plan_aggregate_are_generated(self):
        self._create_subscription(plan=self.plan, next_invoice_date=self._date_in_month(self.forecast_month), price=100.0)
        self._create_subscription(plan=self.other_plan, next_invoice_date=self._date_in_month(self.forecast_month), price=200.0)

        rows = self._generate()
        period_rows = rows.filtered(lambda row: row.forecast_month == self.forecast_month)

        self.assertEqual(len(period_rows), 3)
        self.assertAlmostEqual(self._row(rows, self.forecast_month, self.plan).active_base_mrr, 100.0, places=2)
        self.assertAlmostEqual(self._row(rows, self.forecast_month, self.other_plan).active_base_mrr, 200.0, places=2)
        all_plan_row = period_rows.filtered(lambda row: not row.subscription_plan_id)
        self.assertAlmostEqual(all_plan_row.active_base_mrr, 300.0, places=2)

    def test_multiple_currencies_remain_separated(self):
        self._create_subscription(currency=self.currency, next_invoice_date=self._date_in_month(self.forecast_month), price=100.0)
        self._create_subscription(currency=self.other_currency, next_invoice_date=self._date_in_month(self.forecast_month), price=500.0)

        rows = self._generate(plan=self.plan)
        period_rows = rows.filtered(lambda row: row.forecast_month == self.forecast_month)

        self.assertEqual(set(period_rows.mapped('currency_id').ids), {self.currency.id, self.other_currency.id})

    def test_plan_filter_limits_rows_and_drilldowns(self):
        self._create_subscription(plan=self.plan, next_invoice_date=self._date_in_month(self.forecast_month))
        self._create_subscription(plan=self.other_plan, next_invoice_date=self._date_in_month(self.forecast_month))

        rows = self._generate(plan=self.plan)
        action = rows[0].action_view_upcoming_invoices()

        self.assertEqual(set(rows.mapped('subscription_plan_id').ids), {self.plan.id})
        self.assertIn(('subscription_plan_id', '=', self.plan.id), action['domain'])

    def test_all_plan_drilldowns_omit_plan_filter_and_exclude_no_plan(self):
        self._create_subscription(plan=self.plan, next_invoice_date=self._date_in_month(self.forecast_month))
        self._create_subscription(plan=self.other_plan, next_invoice_date=self._date_in_month(self.forecast_month))
        no_plan = self._create_subscription(plan=self.plan, next_invoice_date=self._date_in_month(self.forecast_month))
        no_plan.subscription_plan_id = False

        rows = self._generate()
        all_plan_row = rows.filtered(lambda row: not row.subscription_plan_id and row.forecast_month == self.forecast_month)
        action = all_plan_row.action_view_upcoming_invoices()
        source_subscriptions = self.env['sale.order'].search(action['domain'])

        self.assertNotIn(('subscription_plan_id', '=', False), action['domain'])
        self.assertNotIn(('subscription_plan_id', '=', self.plan.id), action['domain'])
        self.assertIn(('subscription_plan_id', '!=', False), action['domain'])
        self.assertNotIn(no_plan, source_subscriptions)

    def test_rerun_is_idempotent(self):
        self._create_subscription(next_invoice_date=self._date_in_month(self.forecast_month))

        self._generate(plan=self.plan)
        self._generate(plan=self.plan)

        rows = self.env['subscription.revenue.forecast'].search([
            ('forecast_month', 'in', [self.forecast_month, self.next_month]),
            ('company_id', '=', self.company.id),
            ('currency_id', '=', self.currency.id),
            ('subscription_plan_id', '=', self.plan.id),
        ])
        self.assertEqual(len(rows), 2)

    def test_invalid_month_range_is_blocked(self):
        with self.assertRaises(ValidationError):
            self.env['subscription.revenue.forecast'].sudo().generate_for_period(
                self.next_month,
                self.forecast_month,
                company=self.company,
                plan=self.plan,
            )

    def test_generate_wizard_returns_generated_rows(self):
        self._create_subscription(next_invoice_date=self._date_in_month(self.forecast_month))
        wizard = self.env['subscription.revenue.forecast.generate.wizard'].sudo().create({
            'forecast_start_month': self.forecast_month,
            'forecast_end_month': self.next_month,
            'company_id': self.company.id,
            'subscription_plan_id': self.plan.id,
        })

        action = wizard.action_generate()

        self.assertEqual(action['res_model'], 'subscription.revenue.forecast')
        self.assertEqual(action['view_mode'], 'list,pivot,graph,form')
