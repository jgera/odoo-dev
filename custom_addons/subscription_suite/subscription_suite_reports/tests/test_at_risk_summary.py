from dateutil.relativedelta import relativedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestSubscriptionAtRiskSummary(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'At-Risk Customer'})
        self.product = self.env['product.product'].create({
            'name': 'At-Risk Subscription Product',
            'type': 'service',
            'list_price': 100.0,
        })
        self.currency = self.env.company.currency_id
        self.company = self.env.company
        self.other_currency = self.env['res.currency'].search([('id', '!=', self.currency.id)], limit=1)
        if not self.other_currency:
            self.other_currency = self.env['res.currency'].create({
                'name': 'ARX',
                'symbol': 'A',
                'rounding': 0.01,
                'decimal_places': 2,
            })
        self.other_pricelist = self.env['product.pricelist'].create({
            'name': 'At-Risk Alternate Currency',
            'currency_id': self.other_currency.id,
            'company_id': self.company.id,
        })
        self.plan = self.env['subscription.plan'].create({
            'name': 'At-Risk Monthly',
            'code': 'AT-RISK-MONTHLY',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.other_plan = self.env['subscription.plan'].create({
            'name': 'At-Risk Pro',
            'code': 'AT-RISK-PRO',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.as_of_date = fields.Date.today().replace(day=1) + relativedelta(years=10)

    def _create_subscription(
        self,
        plan=None,
        currency=None,
        state='active',
        price=100.0,
        next_invoice_date=False,
        subscription_end_date=False,
        pending_cancellation=False,
        cancellation_effective_date=False,
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
            'subscription_start_date': self.as_of_date - relativedelta(months=1),
            'next_invoice_date': next_invoice_date,
            'subscription_end_date': subscription_end_date,
            'pending_cancellation': pending_cancellation,
            'cancellation_effective_date': cancellation_effective_date,
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

    def _create_subscription_invoice(self, subscription):
        if subscription.state in ('draft', 'sent'):
            subscription.action_confirm()
        invoice = subscription._create_invoices()[:1]
        invoice.write({'subscription_id': subscription.id})
        invoice.action_post()
        return invoice

    def _create_payment_provider(self):
        payment_method = self.env.ref('payment.payment_method_unknown')
        redirect_form = self.env['ir.ui.view'].create({
            'name': 'At-Risk Dummy Redirect Form',
            'type': 'qweb',
            'arch': '<form action="dummy" method="post"/>',
        })
        provider = self.env['payment.provider'].create({
            'name': 'At-Risk Dummy Provider',
            'code': 'none',
            'state': 'test',
            'is_published': True,
            'allow_tokenization': True,
            'payment_method_ids': [Command.set([payment_method.id])],
            'redirect_form_view_id': redirect_form.id,
            'available_currency_ids': [Command.set([self.currency.id])],
        })
        payment_method.write({
            'active': True,
            'support_tokenization': True,
        })
        return provider

    def _create_payment_token(self, partner=None):
        provider = self._create_payment_provider()
        payment_method = provider.payment_method_ids[:1]
        return self.env['payment.token'].sudo().create({
            'provider_id': provider.id,
            'payment_method_id': payment_method.id,
            'payment_details': '4242',
            'partner_id': (partner or self.partner).id,
            'provider_ref': 'at-risk-token-%s' % fields.Datetime.now(),
            'active': True,
        })

    def _generate(self, plan=None, lookahead_days=30):
        return self.env['subscription.at.risk.summary'].sudo().generate_for_date(
            self.as_of_date,
            lookahead_days=lookahead_days,
            company=self.company,
            plan=plan,
        )

    def test_past_due_recovery_and_dunning_signals_create_critical_row(self):
        subscription = self._create_subscription(state='past_due', price=125.0)
        invoice = self._create_subscription_invoice(subscription)
        self.env['subscription.payment.attempt'].create({
            'name': 'AT-RISK-PAY-002',
            'subscription_id': subscription.id,
            'invoice_id': invoice.id,
            'source': 'cron',
            'state': 'pending',
            'amount': 125.0,
        })
        failed_attempt = self.env['subscription.payment.attempt'].create({
            'name': 'AT-RISK-PAY-001',
            'subscription_id': subscription.id,
            'invoice_id': invoice.id,
            'source': 'portal',
            'state': 'failed',
            'amount': 125.0,
            'recovery_required': True,
        })
        final_dunning = self.env['subscription.dunning.attempt'].create({
            'subscription_id': subscription.id,
            'invoice_id': invoice.id,
            'action_type': 'final_cancel',
            'state': 'done',
            'retry_exhausted': True,
            'amount_at_risk': 125.0,
        })

        row = self._generate(plan=self.plan)

        self.assertEqual(row.subscription_id, subscription)
        self.assertEqual(row.risk_bucket, 'critical')
        self.assertEqual(row.risk_score, 130)
        self.assertAlmostEqual(row.mrr_at_risk, 125.0, places=2)
        self.assertTrue(row.is_past_due)
        self.assertTrue(row.has_open_recovery_invoice)
        self.assertTrue(row.missing_primary_payment_method)
        self.assertEqual(row.open_recovery_invoice_count, 1)
        self.assertEqual(row.failed_payment_attempt_count, 1)
        self.assertEqual(row.pending_payment_attempt_count, 1)
        self.assertEqual(row.retry_exhausted_dunning_attempt_count, 1)
        self.assertEqual(row.final_dunning_action_count, 1)
        self.assertEqual(row.latest_payment_attempt_id, failed_attempt)
        self.assertEqual(row.latest_dunning_attempt_id, final_dunning)

    def test_pending_cancellation_upcoming_invoice_and_renewal_score(self):
        subscription = self._create_subscription(
            state='active',
            next_invoice_date=self.as_of_date + relativedelta(days=5),
            subscription_end_date=self.as_of_date + relativedelta(days=20),
            pending_cancellation=True,
            cancellation_effective_date=self.as_of_date + relativedelta(days=25),
            price=90.0,
        )

        row = self._generate(plan=self.plan)

        self.assertEqual(row.subscription_id, subscription)
        self.assertEqual(row.risk_score, 65)
        self.assertEqual(row.risk_bucket, 'high')
        self.assertTrue(row.has_pending_cancellation)
        self.assertTrue(row.scheduled_churn_within_period)
        self.assertTrue(row.upcoming_invoice_within_period)
        self.assertTrue(row.renewal_due_within_period)
        self.assertTrue(row.missing_primary_payment_method)

    def test_no_risk_cancelled_expired_quotes_and_non_subscriptions_are_excluded(self):
        self._create_subscription(state='active', price=50.0)
        self._create_subscription(state='cancelled', next_invoice_date=self.as_of_date, price=50.0)
        self._create_subscription(state='expired', next_invoice_date=self.as_of_date, price=50.0)
        quote = self._create_subscription(state='active', next_invoice_date=self.as_of_date, price=50.0)
        quote.subscription_quote_type = 'renewal'
        self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'company_id': self.company.id,
            'is_subscription': False,
            'subscription_plan_id': self.plan.id,
        })

        rows = self._generate(plan=self.plan)

        self.assertFalse(rows)

    def test_multiple_currencies_and_plans_remain_separated(self):
        subscriptions = (
            self._create_subscription(plan=self.plan, currency=self.currency, state='past_due', price=100.0)
            | self._create_subscription(plan=self.plan, currency=self.other_currency, state='past_due', price=200.0)
            | self._create_subscription(plan=self.other_plan, currency=self.currency, state='past_due', price=300.0)
        )

        rows = self._generate()
        rows = rows.filtered(lambda row: row.subscription_id in subscriptions)

        self.assertEqual(set(rows.mapped('currency_id').ids), {self.currency.id, self.other_currency.id})
        self.assertEqual(set(rows.mapped('subscription_plan_id').ids), {self.plan.id, self.other_plan.id})

    def test_plan_filter_limits_rows_and_drilldowns(self):
        wanted = self._create_subscription(plan=self.plan, state='past_due')
        other = self._create_subscription(plan=self.other_plan, state='past_due')

        rows = self._generate(plan=self.plan)
        subscription_action = rows.action_view_subscription()
        attempts_domain = rows.action_view_payment_attempts()['domain']

        self.assertEqual(rows.subscription_id, wanted)
        self.assertNotEqual(rows.subscription_id, other)
        self.assertEqual(subscription_action['res_id'], wanted.id)
        self.assertIn(('subscription_id', '=', wanted.id), attempts_domain)

    def test_rerun_is_idempotent_and_preserves_adjacent_scope(self):
        self._create_subscription(plan=self.plan, state='past_due')
        sentinel_subscription = self._create_subscription(plan=self.other_plan, state='past_due')
        sentinel = self.env['subscription.at.risk.summary'].sudo().create({
            'as_of_date': self.as_of_date,
            'lookahead_days': 30,
            'company_id': self.company.id,
            'currency_id': self.currency.id,
            'subscription_plan_id': self.other_plan.id,
            'subscription_id': sentinel_subscription.id,
            'partner_id': self.partner.id,
            'bucket_key': 'sentinel:other-plan',
            'risk_score': 1,
            'risk_bucket': 'low',
        })

        self._generate(plan=self.plan)
        self._generate(plan=self.plan)

        rows = self.env['subscription.at.risk.summary'].search([
            ('as_of_date', '=', self.as_of_date),
            ('lookahead_days', '=', 30),
            ('company_id', '=', self.company.id),
            ('subscription_plan_id', '=', self.plan.id),
        ])
        self.assertEqual(len(rows), 1)
        self.assertTrue(sentinel.exists())

    def test_negative_lookahead_is_blocked(self):
        with self.assertRaises(ValidationError):
            self.env['subscription.at.risk.summary'].sudo().generate_for_date(
                self.as_of_date,
                lookahead_days=-1,
                company=self.company,
            )

    def test_non_manager_user_cannot_generate_at_risk_summaries(self):
        user_env = self.env(user=self.env.ref('base.public_user'))

        with self.assertRaises(AccessError):
            user_env['subscription.at.risk.summary'].generate_for_date(
                self.as_of_date,
                lookahead_days=30,
                company=self.company,
            )

    def test_generate_wizard_returns_generated_rows(self):
        self._create_subscription(state='past_due')
        wizard = self.env['subscription.at.risk.summary.generate.wizard'].sudo().create({
            'as_of_date': self.as_of_date,
            'lookahead_days': 30,
            'company_id': self.company.id,
            'subscription_plan_id': self.plan.id,
        })

        action = wizard.action_generate()

        self.assertEqual(action['res_model'], 'subscription.at.risk.summary')
        self.assertEqual(action['view_mode'], 'list,pivot,graph,form')
