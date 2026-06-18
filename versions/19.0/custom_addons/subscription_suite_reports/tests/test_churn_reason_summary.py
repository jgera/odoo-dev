from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestSubscriptionChurnReasonSummary(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Churn Reason Customer'})
        self.product = self.env['product.product'].create({
            'name': 'Churn Reason Product',
            'list_price': 100.0,
            'type': 'service',
        })
        self.currency = self.env.company.currency_id
        self.company = self.env['res.company'].create({
            'name': 'Churn Reason Company',
            'currency_id': self.currency.id,
        })
        self.other_currency = self.env['res.currency'].search([('id', '!=', self.currency.id)], limit=1)
        if not self.other_currency:
            self.other_currency = self.env['res.currency'].create({
                'name': 'CRX',
                'symbol': 'C',
                'rounding': 0.01,
                'decimal_places': 2,
            })
        self.other_pricelist = self.env['product.pricelist'].create({
            'name': 'Churn Reason Alternate Currency',
            'currency_id': self.other_currency.id,
            'company_id': self.company.id,
        })
        self.plan = self.env['subscription.plan'].create({
            'name': 'Churn Reason Monthly',
            'code': 'CHURN-REASON-MONTHLY',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.other_plan = self.env['subscription.plan'].create({
            'name': 'Churn Reason Pro',
            'code': 'CHURN-REASON-PRO',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.reason_price = self.env['subscription.cancel.reason'].create({'name': 'Too expensive'})
        self.reason_product = self.env['subscription.cancel.reason'].create({'name': 'Missing feature'})
        self.opening_date = fields.Date.today().replace(day=1) + relativedelta(years=8)
        self.closing_date = self.opening_date + relativedelta(months=1, days=-1)
        self.outside_date = self.closing_date + relativedelta(days=3)

    def _create_subscription(
        self,
        plan=None,
        currency=None,
        state='cancelled',
        reason=None,
        cancellation_date=None,
        feedback=False,
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
            'subscription_start_date': self.opening_date - relativedelta(months=1),
            'cancellation_date': cancellation_date or self.opening_date,
            'cancellation_reason_id': reason.id if reason else False,
            'cancellation_feedback': feedback,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'is_recurring': True,
                'price_unit': price,
                'product_uom_qty': 1.0,
            })],
        })

    def _create_churn_movement(self, subscription, amount=-100.0):
        return self.env['subscription.mrr.movement'].create({
            'name': 'Churn Movement',
            'movement_date': subscription.cancellation_date,
            'movement_type': 'churn',
            'subscription_id': subscription.id,
            'previous_mrr': abs(amount),
            'new_mrr': 0.0,
            'amount': amount,
        })

    def _generate(self, plan=None, reason=None):
        return self.env['subscription.churn.reason.summary'].sudo().generate_for_period(
            self.opening_date,
            self.closing_date,
            company=self.company,
            plan=plan,
            reason=reason,
        )

    def _specific_row(self, rows, reason=None, plan=None, currency=None):
        return rows.filtered(
            lambda row: row.reason_bucket == 'specific'
            and row.cancellation_reason_id == (reason or self.reason_price)
            and row.subscription_plan_id == (plan or self.plan)
            and row.currency_id == (currency or self.currency)
        )

    def test_generation_creates_rows_for_cancelled_and_expired_subscriptions(self):
        cancelled = self._create_subscription(reason=self.reason_price, price=100.0)
        expired = self._create_subscription(state='expired', reason=self.reason_price, price=50.0)
        self._create_churn_movement(cancelled, amount=-100.0)
        self._create_churn_movement(expired, amount=-50.0)

        row = self._specific_row(self._generate(plan=self.plan), self.reason_price)

        self.assertEqual(row.status, 'ready')
        self.assertEqual(row.churned_subscription_count, 2)
        self.assertAlmostEqual(row.churned_mrr, 150.0, places=2)
        self.assertAlmostEqual(row.average_churned_mrr, 75.0, places=2)

    def test_subscriptions_outside_period_are_excluded(self):
        self._create_subscription(reason=self.reason_price, cancellation_date=self.outside_date)

        rows = self._generate(plan=self.plan)

        self.assertFalse(rows)

    def test_non_churned_states_are_excluded(self):
        self._create_subscription(state='active', reason=self.reason_price)
        self._create_subscription(state='trial', reason=self.reason_price)
        self._create_subscription(state='paused', reason=self.reason_price)
        self._create_subscription(state='past_due', reason=self.reason_price)

        rows = self._generate(plan=self.plan)

        self.assertFalse(rows)

    def test_reason_level_rows_separate_cancellation_reasons(self):
        self._create_subscription(reason=self.reason_price, price=100.0)
        self._create_subscription(reason=self.reason_product, price=200.0)

        rows = self._generate(plan=self.plan)

        self.assertAlmostEqual(self._specific_row(rows, self.reason_price).churned_mrr, 100.0, places=2)
        self.assertAlmostEqual(self._specific_row(rows, self.reason_product).churned_mrr, 200.0, places=2)

    def test_missing_reason_rows_use_missing_reason_status(self):
        self._create_subscription(reason=False, feedback='No reason selected', price=100.0)

        row = self._generate(plan=self.plan).filtered(lambda summary: summary.reason_bucket == 'missing')

        self.assertEqual(row.status, 'missing_reason')
        self.assertFalse(row.cancellation_reason_id)
        self.assertEqual(row.feedback_count, 1)
        self.assertAlmostEqual(row.feedback_coverage, 100.0, places=2)

    def test_all_reason_rows_aggregate_without_merging_currencies(self):
        self._create_subscription(reason=self.reason_price, price=100.0)
        self._create_subscription(reason=self.reason_product, price=200.0)
        self._create_subscription(reason=self.reason_price, currency=self.other_currency, price=500.0)

        rows = self._generate(plan=self.plan)
        all_reason_rows = rows.filtered(lambda row: row.reason_bucket == 'all_reasons')

        self.assertEqual(set(all_reason_rows.mapped('currency_id').ids), {self.currency.id, self.other_currency.id})
        self.assertAlmostEqual(all_reason_rows.filtered(lambda row: row.currency_id == self.currency).churned_mrr, 300.0, places=2)
        self.assertAlmostEqual(all_reason_rows.filtered(lambda row: row.currency_id == self.other_currency).churned_mrr, 500.0, places=2)

    def test_multiple_plans_and_all_plan_aggregate_are_generated(self):
        self._create_subscription(plan=self.plan, reason=self.reason_price, price=100.0)
        self._create_subscription(plan=self.other_plan, reason=self.reason_price, price=200.0)

        rows = self._generate()
        specific_rows = rows.filtered(lambda row: row.reason_bucket == 'specific')
        all_plan_row = specific_rows.filtered(lambda row: not row.subscription_plan_id)

        self.assertAlmostEqual(self._specific_row(rows, self.reason_price, self.plan).churned_mrr, 100.0, places=2)
        self.assertAlmostEqual(self._specific_row(rows, self.reason_price, self.other_plan).churned_mrr, 200.0, places=2)
        self.assertAlmostEqual(all_plan_row.churned_mrr, 300.0, places=2)

    def test_plan_filter_limits_rows_and_drilldowns(self):
        self._create_subscription(plan=self.plan, reason=self.reason_price)
        self._create_subscription(plan=self.other_plan, reason=self.reason_price)

        row = self._specific_row(self._generate(plan=self.plan), self.reason_price)
        action = row.action_view_source_subscriptions()

        self.assertEqual(set(row.mapped('subscription_plan_id').ids), {self.plan.id})
        self.assertIn(('subscription_plan_id', '=', self.plan.id), action['domain'])

    def test_reason_filter_limits_rows_and_drilldowns(self):
        self._create_subscription(reason=self.reason_price)
        self._create_subscription(reason=self.reason_product)

        rows = self._generate(reason=self.reason_price)
        row = self._specific_row(rows, self.reason_price)
        action = row.action_view_source_subscriptions()

        self.assertEqual(set(rows.filtered(lambda summary: summary.reason_bucket == 'specific').mapped('cancellation_reason_id').ids), {self.reason_price.id})
        self.assertIn(('cancellation_reason_id', '=', self.reason_price.id), action['domain'])
        self.assertFalse(rows.filtered(lambda summary: summary.reason_bucket == 'all_reasons'))

    def test_all_reason_drilldown_omits_reason_filter(self):
        price = self._create_subscription(reason=self.reason_price)
        product = self._create_subscription(reason=self.reason_product)

        row = self._generate(plan=self.plan).filtered(lambda summary: summary.reason_bucket == 'all_reasons')
        action = row.action_view_source_subscriptions()
        source_subscriptions = self.env['sale.order'].search(action['domain'])

        self.assertNotIn(('cancellation_reason_id', '=', self.reason_price.id), action['domain'])
        self.assertIn(price, source_subscriptions)
        self.assertIn(product, source_subscriptions)

    def test_cancellation_request_drilldown_matches_summary_scope(self):
        subscription = self._create_subscription(reason=self.reason_price)
        request = self.env['subscription.cancellation.request'].create({
            'subscription_id': subscription.id,
            'reason_id': self.reason_price.id,
            'requested_effective_date': self.opening_date,
            'requested_policy': 'immediate',
        })

        row = self._specific_row(self._generate(plan=self.plan), self.reason_price)
        requests = self.env['subscription.cancellation.request'].search(row.action_view_cancellation_requests()['domain'])

        self.assertIn(request, requests)

    def test_rerun_is_idempotent(self):
        self._create_subscription(reason=self.reason_price)

        self._generate(plan=self.plan)
        self._generate(plan=self.plan)

        rows = self.env['subscription.churn.reason.summary'].search([
            ('opening_date', '=', self.opening_date),
            ('closing_date', '=', self.closing_date),
            ('company_id', '=', self.company.id),
            ('currency_id', '=', self.currency.id),
            ('subscription_plan_id', '=', self.plan.id),
            ('reason_bucket', '=', 'specific'),
            ('cancellation_reason_id', '=', self.reason_price.id),
        ])
        self.assertEqual(len(rows), 1)

    def test_scoped_rerun_preserves_adjacent_generated_rows(self):
        self._create_subscription(reason=self.reason_price)
        all_plan = self.env['subscription.churn.reason.summary'].sudo().create({
            'opening_date': self.opening_date,
            'closing_date': self.closing_date,
            'company_id': self.company.id,
            'currency_id': self.currency.id,
            'subscription_plan_id': False,
            'reason_bucket': 'all_reasons',
            'bucket_key': 'sentinel:all-plan',
            'status': 'ready',
        })
        other_reason = self.env['subscription.churn.reason.summary'].sudo().create({
            'opening_date': self.opening_date,
            'closing_date': self.closing_date,
            'company_id': self.company.id,
            'currency_id': self.currency.id,
            'subscription_plan_id': self.plan.id,
            'cancellation_reason_id': self.reason_product.id,
            'reason_bucket': 'specific',
            'bucket_key': 'sentinel:other-reason',
            'status': 'ready',
        })

        self._generate(plan=self.plan, reason=self.reason_price)

        self.assertTrue(all_plan.exists())
        self.assertTrue(other_reason.exists())

    def test_invalid_period_is_blocked(self):
        with self.assertRaises(ValidationError):
            self.env['subscription.churn.reason.summary'].sudo().generate_for_period(
                self.closing_date,
                self.opening_date,
                company=self.company,
                plan=self.plan,
            )

    def test_non_manager_user_cannot_generate_churn_reason_summaries(self):
        user_env = self.env(user=self.env.ref('base.public_user'))

        with self.assertRaises(AccessError):
            user_env['subscription.churn.reason.summary'].generate_for_period(
                self.opening_date,
                self.closing_date,
                company=self.company,
                plan=self.plan,
            )

    def test_generate_wizard_returns_generated_rows(self):
        self._create_subscription(reason=self.reason_price)
        wizard = self.env['subscription.churn.reason.summary.generate.wizard'].sudo().create({
            'opening_date': self.opening_date,
            'closing_date': self.closing_date,
            'company_id': self.company.id,
            'subscription_plan_id': self.plan.id,
            'cancellation_reason_id': self.reason_price.id,
        })

        action = wizard.action_generate()

        self.assertEqual(action['res_model'], 'subscription.churn.reason.summary')
        self.assertEqual(action['view_mode'], 'list,pivot,graph,form')
