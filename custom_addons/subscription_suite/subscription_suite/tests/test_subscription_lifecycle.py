from odoo.tests.common import TransactionCase
from odoo import fields
from dateutil.relativedelta import relativedelta

class TestSubscriptionLifecycle(TransactionCase):

    def setUp(self):
        super(TestSubscriptionLifecycle, self).setUp()
        self.partner = self.env['res.partner'].create({'name': 'Test Customer'})
        self.product = self.env['product.product'].create({
            'name': 'Basic Sub',
            'list_price': 100.0,
            'type': 'service'
        })
        self.addon_product = self.env['product.product'].create({
            'name': 'Support Add-on',
            'list_price': 40.0,
            'type': 'service'
        })
        
        self.plan = self.env['subscription.plan'].create({
            'name': 'Monthly Basic',
            'code': 'MONTHLY-BASIC',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'trial_days': 0
        })
        
        self.trial_plan = self.env['subscription.plan'].create({
            'name': 'Monthly Trial',
            'code': 'MONTHLY-TRIAL',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'trial_days': 14
        })
        self.cancel_reason = self.env['subscription.cancel.reason'].create({
            'name': 'No longer needed',
        })

    def _create_active_subscription(self, plan=None):
        plan = plan or self.plan
        sub = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'is_subscription': True,
            'subscription_state': 'active',
            'subscription_plan_id': plan.id,
            'subscription_start_date': fields.Date.today(),
            'next_invoice_date': fields.Date.today() + relativedelta(days=20),
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'is_recurring': True,
                'price_unit': 100.0,
                'product_uom_qty': 1,
            })],
        })
        sub.action_confirm()
        return sub

    def test_01_confirm_standard_subscription(self):
        """Test confirming a subscription without a trial immediately activates it."""
        sub = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'is_subscription': True,
            'subscription_plan_id': self.plan.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'is_recurring': True,
                'price_unit': 100.0,
                'product_uom_qty': 1,
            })]
        })
        
        self.assertEqual(sub.subscription_state, 'draft')
        sub.action_confirm_subscription()
        self.assertEqual(sub.subscription_state, 'active')
        self.assertEqual(sub.subscription_start_date, fields.Date.today())
        self.assertEqual(sub.next_invoice_date, fields.Date.today())

    def test_02_confirm_trial_subscription(self):
        """Test confirming a subscription with a trial enters trial mode."""
        sub = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'is_subscription': True,
            'subscription_plan_id': self.trial_plan.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'is_recurring': True,
                'price_unit': 100.0,
                'product_uom_qty': 1,
            })]
        })
        
        sub.action_confirm_subscription()
        self.assertEqual(sub.subscription_state, 'trial')
        self.assertEqual(sub.trial_start_date, fields.Date.today())
        expected_end = fields.Date.today() + relativedelta(days=14)
        self.assertEqual(sub.trial_end_date, expected_end)
        
    def test_03_trial_conversion(self):
        """Test converting a trial to an active subscription."""
        sub = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'is_subscription': True,
            'subscription_state': 'trial',
            'subscription_plan_id': self.trial_plan.id,
        })
        
        sub.action_trial_convert()
        self.assertEqual(sub.subscription_state, 'active')
        self.assertEqual(sub.subscription_start_date, fields.Date.today())

    def test_pause_resume_extends_next_invoice_date_by_paused_days(self):
        sub = self._create_active_subscription()
        original_next_invoice_date = sub.next_invoice_date

        sub.action_pause_subscription()
        sub.write({'pause_date': fields.Date.today() - relativedelta(days=10)})
        sub.action_resume_subscription()

        self.assertEqual(sub.subscription_state, 'active')
        self.assertEqual(sub.resume_date, fields.Date.today())
        self.assertEqual(sub.next_invoice_date, original_next_invoice_date + relativedelta(days=10))

    def test_end_of_period_cancellation_is_scheduled_then_processed(self):
        sub = self._create_active_subscription()
        effective_date = sub.next_invoice_date
        wizard = self.env['subscription.close.wizard'].create({
            'subscription_id': sub.id,
            'cancel_reason_id': self.cancel_reason.id,
            'feedback': 'Cancelling at renewal',
            'cancel_date': effective_date,
        })

        wizard.action_cancel()

        self.assertEqual(sub.subscription_state, 'active')
        self.assertTrue(sub.pending_cancellation)
        self.assertEqual(sub.cancellation_effective_date, effective_date)
        self.assertEqual(sub.cancellation_policy_applied, 'end_of_period')

        sub.write({'cancellation_effective_date': fields.Date.today()})
        self.env['sale.order']._cron_process_scheduled_cancellations()

        self.assertEqual(sub.subscription_state, 'cancelled')
        self.assertFalse(sub.pending_cancellation)
        self.assertEqual(sub.cancellation_date, fields.Date.today())
        self.assertEqual(sub.cancellation_reason_id, self.cancel_reason)

    def test_scheduled_cancellation_can_be_reversed(self):
        sub = self._create_active_subscription()
        sub._action_schedule_cancel(
            reason_id=self.cancel_reason.id,
            feedback='Changed mind',
            effective_date=sub.next_invoice_date,
            policy='end_of_period',
        )

        sub.action_reverse_scheduled_cancellation()

        self.assertEqual(sub.subscription_state, 'active')
        self.assertFalse(sub.pending_cancellation)
        self.assertFalse(sub.cancellation_effective_date)
        self.assertFalse(sub.cancellation_reason_id)

    def test_immediate_cancellation_policy_cancels_now(self):
        immediate_plan = self.env['subscription.plan'].create({
            'name': 'Immediate Cancel Plan',
            'code': 'IMMEDIATE-CANCEL',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'trial_days': 0,
            'cancellation_policy': 'immediate',
        })
        sub = self._create_active_subscription(plan=immediate_plan)
        wizard = self.env['subscription.close.wizard'].create({
            'subscription_id': sub.id,
            'cancel_reason_id': self.cancel_reason.id,
            'feedback': 'Cancel today',
            'cancel_date': fields.Date.today(),
        })

        wizard.action_cancel()

        self.assertEqual(sub.subscription_state, 'cancelled')
        self.assertFalse(sub.pending_cancellation)
        self.assertEqual(sub.cancellation_date, fields.Date.today())

    def test_renewal_quote_creation_and_confirmation_extends_subscription(self):
        sub = self._create_active_subscription()

        action = sub.action_renew_subscription()
        quote = self.env['sale.order'].browse(action['res_id'])

        self.assertEqual(quote.subscription_quote_type, 'renewal')
        self.assertEqual(quote.subscription_origin_id, sub)
        self.assertFalse(quote.is_subscription)
        self.assertEqual(len(quote.order_line.filtered('is_recurring')), 1)
        self.assertEqual(quote.subscription_start_date, sub.next_invoice_date)

        quote.action_confirm()

        self.assertEqual(sub.subscription_end_date, quote.subscription_end_date)
        self.assertTrue(sub.subscription_log_ids.filtered(lambda log: log.event_type == 'renewed'))

    def test_upsell_quote_confirmation_adds_recurring_line_and_logs_mrr(self):
        sub = self._create_active_subscription()
        old_mrr = sub.mrr

        action = sub.action_upsell_subscription()
        quote = self.env['sale.order'].browse(action['res_id'])
        quote.write({
            'order_line': [(0, 0, {
                'product_id': self.addon_product.id,
                'name': 'Support Add-on',
                'is_recurring': True,
                'price_unit': 40.0,
                'product_uom_qty': 1,
            })],
        })

        quote.action_confirm()

        addon_lines = sub.order_line.filtered(lambda line: line.product_id == self.addon_product and line.is_recurring)
        self.assertEqual(len(addon_lines), 1)
        self.assertGreater(sub.mrr, old_mrr)
        self.assertTrue(sub.subscription_log_ids.filtered(lambda log: log.event_type == 'upsold'))
        self.assertTrue(self.env['subscription.mrr.movement'].search([
            ('subscription_id', '=', sub.id),
            ('movement_type', '=', 'expansion'),
        ]))
