from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class TestSubscriptionMrrWaterfall(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Waterfall Customer'})
        self.product = self.env['product.product'].create({
            'name': 'Waterfall Product',
            'list_price': 100.0,
            'type': 'service',
        })
        self.currency = self.env.company.currency_id
        self.other_currency = self.env['res.currency'].search([('id', '!=', self.currency.id)], limit=1)
        if not self.other_currency:
            self.other_currency = self.env['res.currency'].create({
                'name': 'WTF',
                'symbol': 'W',
                'rounding': 0.01,
                'decimal_places': 2,
            })
        self.plan = self.env['subscription.plan'].create({
            'name': 'Waterfall Monthly',
            'code': 'WATERFALL-MONTHLY',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.other_plan = self.env['subscription.plan'].create({
            'name': 'Waterfall Pro',
            'code': 'WATERFALL-PRO',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.opening_date = fields.Date.today() - relativedelta(days=30)
        self.closing_date = fields.Date.today()

    def _create_subscription(self, plan=None, currency=None):
        return self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'currency_id': (currency or self.currency).id,
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
    ):
        currency = currency or self.currency
        plan = plan or self.plan
        net = new + expansion + contraction + churn
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
            'variance_mrr': (closing - opening) - net,
            'nrr': ((opening + expansion + contraction + churn) / opening) * 100.0 if opening else 0.0,
            'grr': ((opening + contraction + churn) / opening) * 100.0 if opening else 0.0,
        })

    def _create_snapshot(self, snapshot_date, amount, plan=None, currency=None):
        return self.env['subscription.mrr.snapshot'].sudo().create({
            'snapshot_date': snapshot_date,
            'company_id': self.env.company.id,
            'currency_id': (currency or self.currency).id,
            'subscription_plan_id': (plan or self.plan).id,
            'subscription_count': 1,
            'active_count': 1,
            'active_mrr': amount,
            'total_recurring_mrr': amount,
            'arr': amount * 12,
        })

    def _create_movement(self, movement_type, amount, plan=None, currency=None):
        return self.env['subscription.mrr.movement'].create({
            'name': '%s Waterfall movement' % movement_type,
            'movement_date': self.closing_date,
            'movement_type': movement_type,
            'subscription_id': self._create_subscription(plan=plan, currency=currency).id,
            'previous_mrr': 0.0,
            'new_mrr': amount,
            'amount': amount,
        })

    def _generate(self, plan=None, currency=None):
        return self.env['subscription.mrr.waterfall'].sudo().generate_for_period(
            self.opening_date,
            self.closing_date,
            company=self.env.company,
            currency=currency or self.currency,
            plan=plan,
        )

    def _row(self, rows, bucket_type):
        return rows.filtered(lambda row: row.bucket_type == bucket_type)

    def test_waterfall_creates_ordered_buckets_and_reconciles(self):
        self._create_summary(opening=100.0, closing=125.0, new=5.0, expansion=30.0, contraction=-5.0, churn=-5.0)

        rows = self._generate(plan=self.plan)

        self.assertEqual(rows.mapped('bucket_type'), ['opening', 'new', 'expansion', 'contraction', 'churn', 'closing'])
        self.assertEqual(set(rows.mapped('status')), {'ready'})
        self.assertAlmostEqual(self._row(rows, 'opening').ending_mrr, 100.0, places=2)
        self.assertAlmostEqual(self._row(rows, 'new').ending_mrr, 105.0, places=2)
        self.assertAlmostEqual(self._row(rows, 'expansion').ending_mrr, 135.0, places=2)
        self.assertAlmostEqual(self._row(rows, 'contraction').ending_mrr, 130.0, places=2)
        self.assertAlmostEqual(self._row(rows, 'churn').ending_mrr, 125.0, places=2)
        self.assertAlmostEqual(self._row(rows, 'closing').amount, 125.0, places=2)
        self.assertAlmostEqual(self._row(rows, 'closing').expected_closing_mrr, 125.0, places=2)
        self.assertAlmostEqual(self._row(rows, 'closing').actual_closing_mrr, 125.0, places=2)
        self.assertAlmostEqual(self._row(rows, 'closing').variance_mrr, 0.0, places=2)

    def test_waterfall_variance_status_when_movement_math_does_not_match_closing(self):
        self._create_summary(opening=100.0, closing=140.0, new=5.0, expansion=30.0, contraction=-5.0, churn=-5.0)

        rows = self._generate(plan=self.plan)

        self.assertEqual(set(rows.mapped('status')), {'variance'})
        self.assertAlmostEqual(self._row(rows, 'closing').expected_closing_mrr, 125.0, places=2)
        self.assertAlmostEqual(self._row(rows, 'closing').actual_closing_mrr, 140.0, places=2)
        self.assertAlmostEqual(self._row(rows, 'closing').variance_mrr, 15.0, places=2)

    def test_waterfall_aggregates_multiple_plans(self):
        self._create_summary(plan=self.plan, opening=100.0, closing=125.0, new=5.0, expansion=30.0, contraction=-5.0, churn=-5.0)
        self._create_summary(plan=self.other_plan, opening=200.0, closing=250.0, new=10.0, expansion=40.0, contraction=0.0, churn=0.0)

        rows = self._generate()

        self.assertFalse(rows[0].subscription_plan_id)
        self.assertEqual(self._row(rows, 'opening').source_count, 2)
        self.assertAlmostEqual(self._row(rows, 'opening').amount, 300.0, places=2)
        self.assertAlmostEqual(self._row(rows, 'closing').amount, 375.0, places=2)
        self.assertAlmostEqual(self._row(rows, 'churn').amount, -5.0, places=2)

    def test_waterfall_plan_filter_limits_values(self):
        self._create_summary(plan=self.plan, opening=100.0, closing=125.0)
        self._create_summary(plan=self.other_plan, opening=200.0, closing=250.0)

        rows = self._generate(plan=self.plan)

        self.assertEqual(rows.mapped('subscription_plan_id'), self.plan)
        self.assertAlmostEqual(self._row(rows, 'opening').amount, 100.0, places=2)
        self.assertAlmostEqual(self._row(rows, 'closing').amount, 125.0, places=2)

    def test_waterfall_keeps_currency_separate(self):
        self._create_summary(plan=self.plan, currency=self.currency, opening=100.0, closing=125.0)
        self._create_summary(plan=self.other_plan, currency=self.other_currency, opening=500.0, closing=600.0)

        rows = self._generate(currency=self.currency)

        self.assertEqual(rows.mapped('currency_id'), self.currency)
        self.assertAlmostEqual(self._row(rows, 'opening').amount, 100.0, places=2)
        self.assertAlmostEqual(self._row(rows, 'closing').amount, 125.0, places=2)

    def test_waterfall_missing_kpi_summary_status(self):
        rows = self._generate(plan=self.plan)

        self.assertEqual(set(rows.mapped('status')), {'missing_kpi_summary'})
        self.assertEqual(sum(rows.mapped('source_count')), 0)
        self.assertAlmostEqual(sum(rows.mapped('amount')), 0.0, places=2)

    def test_waterfall_missing_inputs_status(self):
        self._create_summary(status='missing_reconciliation')

        rows = self._generate(plan=self.plan)

        self.assertEqual(set(rows.mapped('status')), {'missing_inputs'})
        self.assertEqual(self._row(rows, 'opening').source_count, 1)

    def test_waterfall_rerun_is_idempotent(self):
        self._create_summary()

        self._generate(plan=self.plan)
        self._generate(plan=self.plan)

        rows = self.env['subscription.mrr.waterfall'].search([
            ('opening_date', '=', self.opening_date),
            ('closing_date', '=', self.closing_date),
            ('company_id', '=', self.env.company.id),
            ('currency_id', '=', self.currency.id),
            ('subscription_plan_id', '=', self.plan.id),
        ])
        self.assertEqual(len(rows), 6)

    def test_waterfall_drilldowns_filter_sources(self):
        self._create_summary()
        self._create_snapshot(self.opening_date, 100.0)
        self._create_snapshot(self.closing_date, 125.0)
        self._create_movement('expansion', 30.0)
        rows = self._generate(plan=self.plan)

        opening_action = self._row(rows, 'opening').action_view_sources()
        expansion_action = self._row(rows, 'expansion').action_view_sources()
        summary_action = self._row(rows, 'new').action_view_kpi_summaries()

        self.assertEqual(opening_action['res_model'], 'subscription.mrr.snapshot')
        self.assertIn(('subscription_plan_id', '=', self.plan.id), opening_action['domain'])
        self.assertEqual(expansion_action['res_model'], 'subscription.mrr.movement')
        self.assertIn(('movement_type', '=', 'expansion'), expansion_action['domain'])
        self.assertIn(('subscription_plan_id', '=', self.plan.id), expansion_action['domain'])
        self.assertEqual(summary_action['res_model'], 'subscription.mrr.kpi.summary')
        self.assertIn(('subscription_plan_id', '=', self.plan.id), summary_action['domain'])

    def test_all_plan_waterfall_drilldowns_do_not_filter_false_plan(self):
        self._create_summary(plan=self.plan)
        self._create_summary(plan=self.other_plan, opening=200.0, closing=250.0)
        self._create_snapshot(self.opening_date, 100.0, plan=self.plan)
        self._create_snapshot(self.opening_date, 200.0, plan=self.other_plan)
        self._create_movement('expansion', 30.0, plan=self.plan)
        self._create_movement('expansion', 50.0, plan=self.other_plan)
        rows = self._generate()

        snapshot_action = self._row(rows, 'opening').action_view_sources()
        movement_action = self._row(rows, 'expansion').action_view_sources()
        summary_action = self._row(rows, 'new').action_view_kpi_summaries()

        self.assertNotIn(('subscription_plan_id', '=', False), snapshot_action['domain'])
        self.assertNotIn(('subscription_plan_id', '=', False), movement_action['domain'])
        self.assertNotIn(('subscription_plan_id', '=', False), summary_action['domain'])
        self.assertNotIn(('subscription_plan_id', '=', self.plan.id), snapshot_action['domain'])
        self.assertNotIn(('subscription_plan_id', '=', self.plan.id), movement_action['domain'])
        self.assertNotIn(('subscription_plan_id', '=', self.plan.id), summary_action['domain'])

    def test_generate_wizard_returns_generated_rows(self):
        self._create_summary()
        wizard = self.env['subscription.mrr.waterfall.generate.wizard'].sudo().create({
            'opening_date': self.opening_date,
            'closing_date': self.closing_date,
            'company_id': self.env.company.id,
            'currency_id': self.currency.id,
            'subscription_plan_id': self.plan.id,
        })

        action = wizard.action_generate()

        self.assertEqual(action['res_model'], 'subscription.mrr.waterfall')
        self.assertEqual(action['view_mode'], 'list,graph,form')
