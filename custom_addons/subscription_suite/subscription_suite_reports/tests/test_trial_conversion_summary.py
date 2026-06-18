from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestSubscriptionTrialConversionSummary(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.currency = self.company.currency_id
        self.partner = self.env['res.partner'].create({'name': 'Trial Analytics Customer'})
        self.product = self.env['product.product'].create({
            'name': 'Trial Analytics Product',
            'type': 'service',
            'list_price': 100.0,
        })
        self.plan = self.env['subscription.plan'].create({
            'name': 'Trial Analytics Monthly',
            'code': 'TRIAL-ANALYTICS-MONTHLY',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'trial_days': 14,
        })
        self.other_plan = self.env['subscription.plan'].create({
            'name': 'Trial Analytics Pro',
            'code': 'TRIAL-ANALYTICS-PRO',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'trial_days': 14,
        })
        self.other_currency = self.env['res.currency'].search([('id', '!=', self.currency.id)], limit=1)
        if not self.other_currency:
            self.other_currency = self.env['res.currency'].create({
                'name': 'TAX',
                'symbol': 'T',
                'rounding': 0.01,
                'decimal_places': 2,
            })
        self.other_pricelist = self.env['product.pricelist'].create({
            'name': 'Trial Analytics Alternate Currency',
            'currency_id': self.other_currency.id,
            'company_id': self.company.id,
        })
        self.opening_date = fields.Date.today().replace(day=1) + relativedelta(years=10)
        self.closing_date = self.opening_date + relativedelta(days=29)

    def _create_subscription(
        self,
        plan=None,
        currency=None,
        state='trial',
        price=100.0,
        trial_start_date=None,
        trial_end_date=None,
        subscription_start_date=False,
    ):
        currency = currency or self.currency
        trial_start_date = trial_start_date if trial_start_date is not None else self.opening_date
        return self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'currency_id': currency.id,
            'pricelist_id': self.other_pricelist.id if currency == self.other_currency else False,
            'is_subscription': True,
            'subscription_state': state,
            'subscription_plan_id': (plan or self.plan).id,
            'trial_start_date': trial_start_date,
            'trial_end_date': trial_end_date,
            'subscription_start_date': subscription_start_date,
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'name': self.product.name,
                'product_uom_qty': 1.0,
                'price_unit': price,
                'is_recurring': True,
            })],
        })

    def _generate(self, plan=None):
        return self.env['subscription.trial.conversion.summary'].sudo().generate_for_period(
            self.opening_date,
            self.closing_date,
            company=self.company,
            plan=plan,
        )

    def test_trial_funnel_metrics_and_rates(self):
        self._create_subscription(
            state='active',
            price=100.0,
            trial_start_date=self.opening_date,
            subscription_start_date=self.opening_date + relativedelta(days=10),
        )
        self._create_subscription(
            state='expired',
            price=80.0,
            trial_start_date=self.opening_date + relativedelta(days=1),
            trial_end_date=self.opening_date + relativedelta(days=15),
        )
        self._create_subscription(
            state='trial',
            price=60.0,
            trial_start_date=self.opening_date + relativedelta(days=2),
            trial_end_date=self.closing_date + relativedelta(days=5),
        )

        rows = self._generate(plan=self.plan)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.trials_started_count, 3)
        self.assertEqual(rows.trials_converted_count, 1)
        self.assertEqual(rows.trials_expired_count, 1)
        self.assertEqual(rows.active_trial_count, 1)
        self.assertAlmostEqual(rows.converted_mrr, 100.0, places=2)
        self.assertAlmostEqual(rows.active_trial_mrr, 60.0, places=2)
        self.assertAlmostEqual(rows.conversion_rate, 33.333333, places=4)
        self.assertAlmostEqual(rows.expiry_rate, 33.333333, places=4)
        self.assertAlmostEqual(rows.average_trial_length_days, (10.0 + 14.0 + 32.0) / 3.0, places=4)

    def test_trials_outside_period_are_excluded_and_zero_safe(self):
        self._create_subscription(
            state='active',
            trial_start_date=self.opening_date - relativedelta(days=1),
            subscription_start_date=self.opening_date + relativedelta(days=2),
        )

        rows = self._generate(plan=self.plan)

        self.assertFalse(rows)

    def test_multiple_plans_create_plan_and_all_plan_rows(self):
        self._create_subscription(plan=self.plan, state='trial', price=50.0)
        self._create_subscription(plan=self.other_plan, state='trial', price=70.0)

        rows = self._generate()

        self.assertEqual(set(rows.mapped('subscription_plan_id').ids), {self.plan.id, self.other_plan.id})
        all_plan = rows.filtered(lambda row: not row.subscription_plan_id)
        self.assertEqual(len(all_plan), 1)
        self.assertEqual(all_plan.trials_started_count, 2)

    def test_multiple_currencies_remain_separated(self):
        self._create_subscription(currency=self.currency, state='trial', price=50.0)
        self._create_subscription(currency=self.other_currency, state='trial', price=70.0)

        rows = self._generate().filtered(lambda row: not row.subscription_plan_id)

        self.assertEqual(set(rows.mapped('currency_id').ids), {self.currency.id, self.other_currency.id})

    def test_plan_filter_limits_rows_and_drilldowns(self):
        wanted = self._create_subscription(plan=self.plan, state='trial')
        other = self._create_subscription(plan=self.other_plan, state='trial')

        rows = self._generate(plan=self.plan)
        action = rows.action_view_active_trials()
        sources = self.env['sale.order'].search(action['domain'])

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.subscription_plan_id, self.plan)
        self.assertIn(wanted, sources)
        self.assertNotIn(other, sources)
        self.assertIn(('subscription_plan_id', '=', self.plan.id), action['domain'])

    def test_rerun_is_idempotent_and_preserves_adjacent_scope(self):
        self._create_subscription(plan=self.plan, state='trial')
        sentinel = self.env['subscription.trial.conversion.summary'].sudo().create({
            'opening_date': self.opening_date,
            'closing_date': self.closing_date,
            'company_id': self.company.id,
            'currency_id': self.currency.id,
            'subscription_plan_id': self.other_plan.id,
            'bucket_key': 'sentinel:trial:other-plan',
            'trials_started_count': 1,
        })

        self._generate(plan=self.plan)
        self._generate(plan=self.plan)

        rows = self.env['subscription.trial.conversion.summary'].search([
            ('opening_date', '=', self.opening_date),
            ('closing_date', '=', self.closing_date),
            ('company_id', '=', self.company.id),
            ('subscription_plan_id', '=', self.plan.id),
        ])
        self.assertEqual(len(rows), 1)
        self.assertTrue(sentinel.exists())

    def test_invalid_period_is_blocked(self):
        with self.assertRaises(ValidationError):
            self.env['subscription.trial.conversion.summary'].sudo().generate_for_period(
                self.closing_date,
                self.opening_date,
                company=self.company,
            )

    def test_non_manager_user_cannot_generate_trial_conversion_summaries(self):
        user_env = self.env(user=self.env.ref('base.public_user'))

        with self.assertRaises(AccessError):
            user_env['subscription.trial.conversion.summary'].generate_for_period(
                self.opening_date,
                self.closing_date,
                company=self.company,
            )

    def test_generate_wizard_returns_generated_rows(self):
        self._create_subscription(state='trial')
        wizard = self.env['subscription.trial.conversion.summary.generate.wizard'].sudo().create({
            'opening_date': self.opening_date,
            'closing_date': self.closing_date,
            'company_id': self.company.id,
            'subscription_plan_id': self.plan.id,
        })

        action = wizard.action_generate()

        self.assertEqual(action['res_model'], 'subscription.trial.conversion.summary')
        self.assertEqual(action['view_mode'], 'list,pivot,graph,form')
