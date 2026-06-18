from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestSubscriptionArpuSummary(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'ARPU Customer'})
        self.currency = self.env.company.currency_id
        self.company = self.env['res.company'].create({
            'name': 'ARPU Company',
            'currency_id': self.currency.id,
        })
        self.other_currency = self.env['res.currency'].search([('id', '!=', self.currency.id)], limit=1)
        if not self.other_currency:
            self.other_currency = self.env['res.currency'].create({
                'name': 'APX',
                'symbol': 'A',
                'rounding': 0.01,
                'decimal_places': 2,
            })
        self.other_pricelist = self.env['product.pricelist'].create({
            'name': 'ARPU Alternate Currency',
            'currency_id': self.other_currency.id,
            'company_id': self.company.id,
        })
        self.plan = self.env['subscription.plan'].create({
            'name': 'ARPU Monthly',
            'code': 'ARPU-MONTHLY',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.other_plan = self.env['subscription.plan'].create({
            'name': 'ARPU Pro',
            'code': 'ARPU-PRO',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.product = self.env['product.product'].create({
            'name': 'ARPU Product',
            'list_price': 100.0,
            'type': 'service',
        })
        self.opening_date = fields.Date.today() - relativedelta(months=1)
        self.closing_date = fields.Date.today()

    def _create_snapshot(self, snapshot_date, plan=None, currency=None, count=1, mrr=100.0):
        return self.env['subscription.mrr.snapshot'].sudo().create({
            'snapshot_date': snapshot_date,
            'company_id': self.company.id,
            'currency_id': (currency or self.currency).id,
            'subscription_plan_id': (plan or self.plan).id,
            'subscription_count': count,
            'active_count': count,
            'active_mrr': mrr,
            'total_recurring_mrr': mrr,
            'arr': mrr * 12,
        })

    def _create_subscription(self, plan=None, currency=None, state='active', price=100.0):
        currency = currency or self.currency
        return self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'currency_id': currency.id,
            'pricelist_id': self.other_pricelist.id if currency == self.other_currency else False,
            'is_subscription': True,
            'subscription_state': state,
            'subscription_plan_id': (plan or self.plan).id,
            'subscription_start_date': self.opening_date,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'is_recurring': True,
                'price_unit': price,
                'product_uom_qty': 1.0,
            })],
        })

    def _generate(self, plan=None):
        return self.env['subscription.arpu.summary'].sudo().generate_for_period(
            self.opening_date,
            self.closing_date,
            company=self.company,
            plan=plan,
        )

    def _plan_row(self, rows, plan=None, currency=None):
        return rows.filtered(
            lambda row: row.subscription_plan_id == (plan or self.plan)
            and row.currency_id == (currency or self.currency)
        )

    def test_arpu_computes_from_snapshot_counts_and_mrr(self):
        self._create_snapshot(self.opening_date, count=2, mrr=200.0)
        self._create_snapshot(self.closing_date, count=4, mrr=600.0)

        rows = self._generate(plan=self.plan)
        row = self._plan_row(rows)

        self.assertEqual(row.status, 'ready')
        self.assertEqual(row.opening_subscription_count, 2)
        self.assertEqual(row.closing_subscription_count, 4)
        self.assertAlmostEqual(row.average_subscription_count, 3.0, places=2)
        self.assertAlmostEqual(row.average_mrr, 400.0, places=2)
        self.assertAlmostEqual(row.arpu, 133.333333, places=2)

    def test_zero_subscription_count_keeps_arpu_zero_safe(self):
        self._create_snapshot(self.opening_date, count=0, mrr=0.0)
        self._create_snapshot(self.closing_date, count=0, mrr=0.0)

        row = self._plan_row(self._generate(plan=self.plan))

        self.assertEqual(row.status, 'ready')
        self.assertAlmostEqual(row.average_subscription_count, 0.0, places=2)
        self.assertAlmostEqual(row.arpu, 0.0, places=2)

    def test_missing_opening_snapshot_status(self):
        self._create_snapshot(self.closing_date, count=3, mrr=300.0)

        row = self._plan_row(self._generate(plan=self.plan))

        self.assertEqual(row.status, 'missing_opening_snapshot')
        self.assertEqual(row.opening_subscription_count, 0)
        self.assertEqual(row.closing_subscription_count, 3)

    def test_missing_closing_snapshot_status(self):
        self._create_snapshot(self.opening_date, count=3, mrr=300.0)

        row = self._plan_row(self._generate(plan=self.plan))

        self.assertEqual(row.status, 'missing_closing_snapshot')
        self.assertEqual(row.opening_subscription_count, 3)
        self.assertEqual(row.closing_subscription_count, 0)

    def test_multiple_plans_create_separate_rows(self):
        self._create_snapshot(self.opening_date, plan=self.plan, count=1, mrr=100.0)
        self._create_snapshot(self.closing_date, plan=self.plan, count=1, mrr=100.0)
        self._create_snapshot(self.opening_date, plan=self.other_plan, count=2, mrr=300.0)
        self._create_snapshot(self.closing_date, plan=self.other_plan, count=2, mrr=300.0)

        rows = self._generate()

        self.assertEqual(len(rows.filtered(lambda row: row.subscription_plan_id)), 2)
        self.assertAlmostEqual(self._plan_row(rows, self.plan).arpu, 100.0, places=2)
        self.assertAlmostEqual(self._plan_row(rows, self.other_plan).arpu, 150.0, places=2)

    def test_all_plan_generation_aggregates_without_merging_currencies(self):
        self._create_snapshot(self.opening_date, plan=self.plan, count=1, mrr=100.0)
        self._create_snapshot(self.closing_date, plan=self.plan, count=1, mrr=100.0)
        self._create_snapshot(self.opening_date, plan=self.other_plan, count=3, mrr=600.0)
        self._create_snapshot(self.closing_date, plan=self.other_plan, count=3, mrr=600.0)
        self._create_snapshot(self.opening_date, plan=self.plan, currency=self.other_currency, count=2, mrr=500.0)
        self._create_snapshot(self.closing_date, plan=self.plan, currency=self.other_currency, count=2, mrr=500.0)

        rows = self._generate()
        all_plan_rows = rows.filtered(lambda row: not row.subscription_plan_id)

        self.assertEqual(set(all_plan_rows.mapped('currency_id').ids), {self.currency.id, self.other_currency.id})
        same_currency_all_plan = all_plan_rows.filtered(lambda row: row.currency_id == self.currency)
        other_currency_all_plan = all_plan_rows.filtered(lambda row: row.currency_id == self.other_currency)
        self.assertAlmostEqual(same_currency_all_plan.arpu, 175.0, places=2)
        self.assertAlmostEqual(other_currency_all_plan.arpu, 250.0, places=2)

    def test_plan_filter_limits_rows_and_drilldowns(self):
        self._create_snapshot(self.opening_date, plan=self.plan, count=1, mrr=100.0)
        self._create_snapshot(self.closing_date, plan=self.plan, count=1, mrr=100.0)
        self._create_snapshot(self.opening_date, plan=self.other_plan, count=1, mrr=200.0)
        self._create_snapshot(self.closing_date, plan=self.other_plan, count=1, mrr=200.0)
        self._create_subscription(plan=self.plan)
        self._create_subscription(plan=self.other_plan)

        row = self._plan_row(self._generate(plan=self.plan))
        snapshot_action = row.action_view_snapshots()
        subscription_action = row.action_view_source_subscriptions()

        self.assertEqual(row.subscription_plan_id, self.plan)
        self.assertIn(('subscription_plan_id', '=', self.plan.id), snapshot_action['domain'])
        self.assertIn(('subscription_plan_id', '=', self.plan.id), subscription_action['domain'])

    def test_all_plan_drilldowns_omit_specific_plan_and_exclude_no_plan(self):
        self._create_snapshot(self.opening_date, plan=self.plan, count=1, mrr=100.0)
        self._create_snapshot(self.closing_date, plan=self.plan, count=1, mrr=100.0)
        self._create_snapshot(self.opening_date, plan=self.other_plan, count=1, mrr=200.0)
        self._create_snapshot(self.closing_date, plan=self.other_plan, count=1, mrr=200.0)
        plan_subscription = self._create_subscription(plan=self.plan)
        other_subscription = self._create_subscription(plan=self.other_plan)
        no_plan = self._create_subscription(plan=self.plan)
        no_plan.subscription_plan_id = False

        all_plan_row = self._generate().filtered(lambda row: not row.subscription_plan_id and row.currency_id == self.currency)
        snapshot_action = all_plan_row.action_view_snapshots()
        subscription_action = all_plan_row.action_view_source_subscriptions()
        source_subscriptions = self.env['sale.order'].search(subscription_action['domain'])

        self.assertNotIn(('subscription_plan_id', '=', False), snapshot_action['domain'])
        self.assertNotIn(('subscription_plan_id', '=', self.plan.id), snapshot_action['domain'])
        self.assertNotIn(('subscription_plan_id', '=', self.plan.id), subscription_action['domain'])
        self.assertIn(('subscription_plan_id', '!=', False), subscription_action['domain'])
        self.assertIn(plan_subscription, source_subscriptions)
        self.assertIn(other_subscription, source_subscriptions)
        self.assertNotIn(no_plan, source_subscriptions)

    def test_rerun_is_idempotent(self):
        self._create_snapshot(self.opening_date, count=1, mrr=100.0)
        self._create_snapshot(self.closing_date, count=1, mrr=100.0)

        self._generate(plan=self.plan)
        self._generate(plan=self.plan)

        rows = self.env['subscription.arpu.summary'].search([
            ('opening_date', '=', self.opening_date),
            ('closing_date', '=', self.closing_date),
            ('company_id', '=', self.company.id),
            ('currency_id', '=', self.currency.id),
            ('subscription_plan_id', '=', self.plan.id),
        ])
        self.assertEqual(len(rows), 1)

    def test_scoped_rerun_preserves_adjacent_generated_rows(self):
        self._create_snapshot(self.opening_date, plan=self.plan, count=1, mrr=100.0)
        self._create_snapshot(self.closing_date, plan=self.plan, count=1, mrr=100.0)
        all_plan = self.env['subscription.arpu.summary'].sudo().create({
            'opening_date': self.opening_date,
            'closing_date': self.closing_date,
            'company_id': self.company.id,
            'currency_id': self.currency.id,
            'subscription_plan_id': False,
            'bucket_key': 'sentinel:all',
            'status': 'ready',
        })
        other_plan = self.env['subscription.arpu.summary'].sudo().create({
            'opening_date': self.opening_date,
            'closing_date': self.closing_date,
            'company_id': self.company.id,
            'currency_id': self.currency.id,
            'subscription_plan_id': self.other_plan.id,
            'bucket_key': 'sentinel:other',
            'status': 'ready',
        })

        self._generate(plan=self.plan)

        self.assertTrue(all_plan.exists())
        self.assertTrue(other_plan.exists())

    def test_invalid_period_is_blocked(self):
        with self.assertRaises(ValidationError):
            self.env['subscription.arpu.summary'].sudo().generate_for_period(
                self.closing_date,
                self.opening_date,
                company=self.company,
                plan=self.plan,
            )

    def test_non_manager_user_cannot_generate_arpu_summaries(self):
        user_env = self.env(user=self.env.ref('base.public_user'))

        with self.assertRaises(AccessError):
            user_env['subscription.arpu.summary'].generate_for_period(
                self.opening_date,
                self.closing_date,
                company=self.company,
                plan=self.plan,
            )

    def test_generate_wizard_returns_generated_rows(self):
        self._create_snapshot(self.opening_date, count=1, mrr=100.0)
        self._create_snapshot(self.closing_date, count=1, mrr=100.0)
        wizard = self.env['subscription.arpu.summary.generate.wizard'].sudo().create({
            'opening_date': self.opening_date,
            'closing_date': self.closing_date,
            'company_id': self.company.id,
            'subscription_plan_id': self.plan.id,
        })

        action = wizard.action_generate()

        self.assertEqual(action['res_model'], 'subscription.arpu.summary')
        self.assertEqual(action['view_mode'], 'list,pivot,graph,form')
