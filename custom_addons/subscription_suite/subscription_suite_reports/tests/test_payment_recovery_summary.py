from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestSubscriptionPaymentRecoverySummary(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.currency = self.company.currency_id
        self.partner = self.env['res.partner'].create({'name': 'Recovery Analytics Customer'})
        self.product = self.env['product.product'].create({
            'name': 'Recovery Analytics Product',
            'type': 'service',
            'list_price': 100.0,
        })
        self.plan = self.env['subscription.plan'].create({
            'name': 'Recovery Analytics Monthly',
            'code': 'REC-ANALYTICS-MONTHLY',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.other_plan = self.env['subscription.plan'].create({
            'name': 'Recovery Analytics Pro',
            'code': 'REC-ANALYTICS-PRO',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.other_currency = self.env['res.currency'].search([('id', '!=', self.currency.id)], limit=1)
        if not self.other_currency:
            self.other_currency = self.env['res.currency'].create({
                'name': 'RAX',
                'symbol': 'R',
                'rounding': 0.01,
                'decimal_places': 2,
            })
        self.other_pricelist = self.env['product.pricelist'].create({
            'name': 'Recovery Analytics Alternate Currency',
            'currency_id': self.other_currency.id,
            'company_id': self.company.id,
        })
        self.opening_date = fields.Date.today().replace(day=1) + relativedelta(years=10)
        self.closing_date = self.opening_date + relativedelta(days=29)
        self.attempt_date = fields.Datetime.to_datetime(self.opening_date + relativedelta(days=5))

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
            'subscription_start_date': self.opening_date - relativedelta(months=1),
            'next_invoice_date': self.opening_date + relativedelta(days=10),
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

    def _create_invoice(self, subscription):
        if subscription.state in ('draft', 'sent'):
            subscription.action_confirm()
        invoice = subscription._create_invoices()[:1]
        invoice.write({
            'subscription_id': subscription.id,
            'invoice_date': self.opening_date,
        })
        invoice.action_post()
        return invoice

    def _create_attempt_invoice(self, subscription):
        return self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': subscription.partner_id.id,
            'company_id': subscription.company_id.id,
            'currency_id': subscription.currency_id.id,
            'subscription_id': subscription.id,
            'invoice_date': self.opening_date,
        })

    def _create_attempt(self, subscription, state, source='portal', amount=100.0, recovery_required=False, invoice=False):
        invoice = invoice or self._create_attempt_invoice(subscription)
        return self.env['subscription.payment.attempt'].create({
            'name': 'REC-ATTEMPT-%s-%s' % (source, state),
            'subscription_id': subscription.id,
            'invoice_id': invoice.id,
            'source': source,
            'state': state,
            'amount': amount,
            'attempt_date': self.attempt_date,
            'recovery_required': recovery_required,
        })

    def _generate(self, plan=None, source=False):
        return self.env['subscription.payment.recovery.summary'].sudo().generate_for_period(
            self.opening_date,
            self.closing_date,
            company=self.company,
            plan=plan,
            source=source,
        )

    def test_attempt_sources_and_all_source_aggregate(self):
        failed = self._create_subscription(price=100.0)
        pending = self._create_subscription(price=80.0)
        recovered = self._create_subscription(price=60.0)
        cancelled = self._create_subscription(price=40.0)
        self._create_attempt(failed, 'failed', source='portal', amount=100.0, recovery_required=True)
        self._create_attempt(pending, 'pending', source='cron', amount=80.0)
        self._create_attempt(recovered, 'success', source='manual', amount=60.0)
        self._create_attempt(cancelled, 'cancelled', source='portal', amount=40.0, recovery_required=True)

        rows = self._generate(plan=self.plan)
        portal_row = rows.filtered(lambda row: row.recovery_source == 'portal')
        cron_row = rows.filtered(lambda row: row.recovery_source == 'cron')
        manual_row = rows.filtered(lambda row: row.recovery_source == 'manual')
        all_row = rows.filtered(lambda row: row.recovery_source == 'all')

        self.assertEqual(portal_row.failed_attempt_count, 1)
        self.assertEqual(portal_row.cancelled_error_attempt_count, 1)
        self.assertEqual(portal_row.manual_action_required_count, 2)
        self.assertAlmostEqual(portal_row.failed_amount, 140.0, places=2)
        self.assertEqual(cron_row.pending_attempt_count, 1)
        self.assertAlmostEqual(cron_row.pending_amount, 80.0, places=2)
        self.assertEqual(manual_row.recovered_attempt_count, 1)
        self.assertAlmostEqual(manual_row.recovered_amount, 60.0, places=2)
        self.assertEqual(all_row.failed_attempt_count, 1)
        self.assertEqual(all_row.pending_attempt_count, 1)
        self.assertEqual(all_row.recovered_attempt_count, 1)
        self.assertEqual(all_row.cancelled_error_attempt_count, 1)
        self.assertAlmostEqual(all_row.recovery_amount, 220.0, places=2)

    def test_open_invoices_dunning_and_at_risk_feed_all_source_row(self):
        subscription = self._create_subscription(state='past_due', price=125.0)
        invoice = self._create_invoice(subscription)
        self.env['subscription.dunning.attempt'].create({
            'subscription_id': subscription.id,
            'invoice_id': invoice.id,
            'action_type': 'final_cancel',
            'state': 'done',
            'retry_exhausted': True,
            'amount_at_risk': 125.0,
            'attempt_date': self.attempt_date,
        })
        self.env['subscription.at.risk.summary'].sudo().create({
            'as_of_date': self.opening_date,
            'lookahead_days': 30,
            'company_id': self.company.id,
            'currency_id': self.currency.id,
            'subscription_plan_id': self.plan.id,
            'subscription_id': subscription.id,
            'partner_id': self.partner.id,
            'bucket_key': 'recovery-risk:%s' % subscription.id,
            'risk_score': 80,
            'risk_bucket': 'critical',
            'mrr_at_risk': 125.0,
        })

        rows = self._generate(plan=self.plan)
        all_row = rows.filtered(lambda row: row.recovery_source == 'all')

        self.assertEqual(len(rows), 1)
        self.assertEqual(all_row.open_recovery_invoice_count, 1)
        self.assertEqual(all_row.retry_exhausted_dunning_count, 1)
        self.assertEqual(all_row.final_dunning_action_count, 1)
        self.assertEqual(all_row.at_risk_subscription_count, 1)
        self.assertAlmostEqual(all_row.recovery_amount, invoice.amount_residual, places=2)
        self.assertAlmostEqual(all_row.mrr_at_risk, 125.0, places=2)

    def test_all_source_recovery_amount_does_not_double_count_invoice_with_period_attempt(self):
        attempted = self._create_subscription(state='past_due', price=125.0)
        attempted_invoice = self._create_invoice(attempted)
        open_only = self._create_subscription(state='past_due', price=90.0)
        open_only_invoice = self._create_invoice(open_only)
        self._create_attempt(
            attempted,
            'failed',
            source='portal',
            amount=125.0,
            recovery_required=True,
            invoice=attempted_invoice,
        )

        rows = self._generate(plan=self.plan)
        portal_row = rows.filtered(lambda row: row.recovery_source == 'portal')
        all_row = rows.filtered(lambda row: row.recovery_source == 'all')

        self.assertEqual(portal_row.open_recovery_invoice_count, 0)
        self.assertAlmostEqual(portal_row.recovery_amount, 125.0, places=2)
        self.assertEqual(all_row.open_recovery_invoice_count, 1)
        self.assertAlmostEqual(all_row.recovery_amount, 125.0 + open_only_invoice.amount_residual, places=2)

    def test_plan_and_source_filter_limits_rows_and_drilldowns(self):
        wanted = self._create_subscription(plan=self.plan, price=50.0)
        other_plan = self._create_subscription(plan=self.other_plan, price=70.0)
        self._create_attempt(wanted, 'failed', source='portal', amount=50.0, recovery_required=True)
        self._create_attempt(other_plan, 'failed', source='cron', amount=70.0, recovery_required=True)

        rows = self._generate(plan=self.plan, source='portal')
        attempts_domain = rows.action_view_payment_attempts()['domain']
        subscriptions_domain = rows.action_view_subscriptions()['domain']

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.recovery_source, 'portal')
        self.assertEqual(rows.subscription_plan_id, self.plan)
        self.assertIn(('source', '=', 'portal'), attempts_domain)
        self.assertIn(('subscription_id.subscription_plan_id', '=', self.plan.id), attempts_domain)
        self.assertEqual(subscriptions_domain, [('id', 'in', [wanted.id])])

    def test_multiple_currencies_remain_separated(self):
        first = self._create_subscription(currency=self.currency, price=100.0)
        second = self._create_subscription(currency=self.other_currency, price=200.0)
        self._create_attempt(first, 'failed', source='portal', amount=100.0)
        self._create_attempt(second, 'failed', source='portal', amount=200.0)

        rows = self._generate(plan=self.plan).filtered(lambda row: row.recovery_source == 'all')

        self.assertEqual(set(rows.mapped('currency_id').ids), {self.currency.id, self.other_currency.id})
        self.assertEqual(set(round(row.failed_amount, 2) for row in rows), {100.0, 200.0})

    def test_rerun_is_idempotent_and_preserves_adjacent_scope(self):
        wanted = self._create_subscription(plan=self.plan, price=100.0)
        sentinel_subscription = self._create_subscription(plan=self.other_plan, price=75.0)
        self._create_attempt(wanted, 'failed', source='portal', amount=100.0)
        sentinel = self.env['subscription.payment.recovery.summary'].sudo().create({
            'opening_date': self.opening_date,
            'closing_date': self.closing_date,
            'company_id': self.company.id,
            'currency_id': self.currency.id,
            'subscription_plan_id': self.other_plan.id,
            'recovery_source': 'all',
            'bucket_key': 'sentinel:other-plan:all',
            'failed_attempt_count': 1,
            'failed_amount': 75.0,
            'recovery_amount': 75.0,
            'mrr_at_risk': sentinel_subscription.mrr,
        })

        self._generate(plan=self.plan)
        self._generate(plan=self.plan)

        rows = self.env['subscription.payment.recovery.summary'].search([
            ('opening_date', '=', self.opening_date),
            ('closing_date', '=', self.closing_date),
            ('company_id', '=', self.company.id),
            ('subscription_plan_id', '=', self.plan.id),
        ])
        self.assertEqual(len(rows.filtered(lambda row: row.recovery_source == 'portal')), 1)
        self.assertEqual(len(rows.filtered(lambda row: row.recovery_source == 'all')), 1)
        self.assertTrue(sentinel.exists())

    def test_invalid_period_is_blocked(self):
        with self.assertRaises(ValidationError):
            self.env['subscription.payment.recovery.summary'].sudo().generate_for_period(
                self.closing_date,
                self.opening_date,
                company=self.company,
            )

    def test_non_manager_user_cannot_generate_payment_recovery_summaries(self):
        user_env = self.env(user=self.env.ref('base.public_user'))

        with self.assertRaises(AccessError):
            user_env['subscription.payment.recovery.summary'].generate_for_period(
                self.opening_date,
                self.closing_date,
                company=self.company,
            )

    def test_generate_wizard_returns_generated_rows(self):
        subscription = self._create_subscription(price=100.0)
        self._create_attempt(subscription, 'failed', source='portal', amount=100.0)
        wizard = self.env['subscription.payment.recovery.summary.generate.wizard'].sudo().create({
            'opening_date': self.opening_date,
            'closing_date': self.closing_date,
            'company_id': self.company.id,
            'subscription_plan_id': self.plan.id,
        })

        action = wizard.action_generate()

        self.assertEqual(action['res_model'], 'subscription.payment.recovery.summary')
        self.assertEqual(action['view_mode'], 'list,pivot,graph,form')
