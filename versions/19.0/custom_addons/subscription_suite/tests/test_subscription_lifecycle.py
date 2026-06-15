from odoo.tests.common import TransactionCase
from odoo import fields
from odoo.exceptions import UserError, ValidationError
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

    def test_portal_pause_request_creates_pending_request(self):
        sub = self._create_active_subscription()

        request = sub.sudo()._portal_request_lifecycle_action(
            'pause',
            'Need a short break',
            self.env.user,
        )

        self.assertTrue(request)
        self.assertEqual(request.state, 'pending')
        self.assertEqual(request.subscription_id, sub)
        self.assertEqual(request.request_type, 'pause')
        self.assertEqual(request.feedback, 'Need a short break')
        self.assertEqual(request.requested_by_id, self.env.user)
        self.assertEqual(sub.subscription_state, 'active')

    def test_portal_pause_request_approval_pauses_subscription(self):
        sub = self._create_active_subscription()
        request = sub.sudo()._portal_request_lifecycle_action(
            'pause',
            'Pause requested',
            self.env.user,
        )

        request.with_user(self.env.ref('base.user_admin')).action_approve()
        request.invalidate_recordset()
        sub.invalidate_recordset()

        self.assertEqual(request.state, 'approved')
        self.assertEqual(sub.subscription_state, 'paused')
        self.assertEqual(sub.pause_date, fields.Date.today())

    def test_manager_lifecycle_queue_activity_and_subscription_actions(self):
        sub = self._create_active_subscription()
        request = sub.sudo()._portal_request_lifecycle_action(
            'pause',
            'Pause requested',
            self.env.user,
        )

        activity = self.env['mail.activity'].search([
            ('res_model', '=', 'subscription.lifecycle.request'),
            ('res_id', '=', request.id),
            ('summary', '=', 'Review subscription request'),
        ])
        self.assertTrue(activity)
        self.assertEqual(request.request_age_days, 0)

        action = sub.action_view_subscription_lifecycle_requests()
        self.assertEqual(action['res_model'], 'subscription.lifecycle.request')
        self.assertIn(('subscription_id', '=', sub.id), action['domain'])
        self.assertEqual(sub.lifecycle_request_count, 1)

        open_action = request.action_open_subscription()
        self.assertEqual(open_action['res_model'], 'sale.order')
        self.assertEqual(open_action['res_id'], sub.id)

        request.with_user(self.env.ref('base.user_admin')).action_approve()
        self.assertFalse(self.env['mail.activity'].search([
            ('res_model', '=', 'subscription.lifecycle.request'),
            ('res_id', '=', request.id),
            ('summary', '=', 'Review subscription request'),
        ]))

    def test_portal_resume_request_approval_resumes_subscription(self):
        sub = self._create_active_subscription()
        original_next_invoice_date = sub.next_invoice_date
        sub.action_pause_subscription()
        sub.write({'pause_date': fields.Date.today() - relativedelta(days=5)})

        request = sub.sudo()._portal_request_lifecycle_action(
            'resume',
            'Resume requested',
            self.env.user,
        )
        request.with_user(self.env.ref('base.user_admin')).action_approve()
        request.invalidate_recordset()
        sub.invalidate_recordset()

        self.assertEqual(request.state, 'approved')
        self.assertEqual(sub.subscription_state, 'active')
        self.assertEqual(sub.resume_date, fields.Date.today())
        self.assertEqual(sub.next_invoice_date, original_next_invoice_date + relativedelta(days=5))

    def test_portal_lifecycle_request_blocks_duplicate_pending_request(self):
        sub = self._create_active_subscription()
        sub.sudo()._portal_request_lifecycle_action(
            'pause',
            'First request',
            self.env.user,
        )

        with self.assertRaises(ValidationError):
            sub.sudo()._portal_request_lifecycle_action(
                'pause',
                'Second request',
                self.env.user,
            )

    def test_portal_pause_request_respects_plan_pause_policy(self):
        self.plan.pause_allowed = False
        sub = self._create_active_subscription()

        with self.assertRaises(ValidationError):
            sub.sudo()._portal_request_lifecycle_action(
                'pause',
                'Pause not allowed',
                self.env.user,
            )

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

    def test_minimum_commitment_blocks_early_cancellation(self):
        committed_plan = self.env['subscription.plan'].create({
            'name': 'Committed Monthly',
            'code': 'COMMITTED-MONTHLY',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'trial_days': 0,
            'min_commitment_periods': 3,
        })
        sub = self._create_active_subscription(plan=committed_plan)
        sub.write({
            'subscription_start_date': fields.Date.today() - relativedelta(months=1),
            'next_invoice_date': fields.Date.today() + relativedelta(days=15),
        })

        with self.assertRaises(UserError):
            sub._action_cancel(reason_id=self.cancel_reason.id)

        self.assertEqual(sub.subscription_state, 'active')

    def test_minimum_commitment_allows_cancellation_after_commitment_end(self):
        committed_plan = self.env['subscription.plan'].create({
            'name': 'Expired Commitment Monthly',
            'code': 'EXPIRED-COMMITMENT-MONTHLY',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'trial_days': 0,
            'min_commitment_periods': 3,
        })
        sub = self._create_active_subscription(plan=committed_plan)
        sub.write({
            'subscription_start_date': fields.Date.today() - relativedelta(months=4),
        })

        sub._action_cancel(reason_id=self.cancel_reason.id)

        self.assertEqual(sub.subscription_state, 'cancelled')

    def test_portal_cancellation_request_creates_pending_request(self):
        sub = self._create_active_subscription()

        request = sub.sudo()._portal_request_cancellation(
            self.cancel_reason,
            'Too expensive',
            self.env.user,
        )

        self.assertTrue(request)
        self.assertEqual(request.state, 'pending')
        self.assertEqual(request.subscription_id, sub)
        self.assertEqual(request.reason_id, self.cancel_reason)
        self.assertEqual(request.feedback, 'Too expensive')
        self.assertEqual(request.requested_policy, 'end_of_period')
        self.assertEqual(request.requested_effective_date, sub.next_invoice_date)
        self.assertEqual(request.requested_by_id, self.env.user)
        self.assertEqual(sub.subscription_state, 'active')
        self.assertFalse(sub.pending_cancellation)

    def test_portal_cancellation_request_approval_schedules_cancellation(self):
        sub = self._create_active_subscription()
        request = sub.sudo()._portal_request_cancellation(
            self.cancel_reason,
            'Cancel at renewal',
            self.env.user,
        )

        request.with_user(self.env.ref('base.user_admin')).action_approve()
        request.invalidate_recordset()
        sub.invalidate_recordset()

        self.assertEqual(request.state, 'approved')
        self.assertEqual(sub.subscription_state, 'active')
        self.assertTrue(sub.pending_cancellation)
        self.assertEqual(sub.cancellation_effective_date, request.requested_effective_date)
        self.assertEqual(sub.cancellation_reason_id, self.cancel_reason)

    def test_manager_cancellation_queue_activity_and_subscription_actions(self):
        sub = self._create_active_subscription()
        request = sub.sudo()._portal_request_cancellation(
            self.cancel_reason,
            'Cancel at renewal',
            self.env.user,
        )

        self.assertTrue(self.env['mail.activity'].search([
            ('res_model', '=', 'subscription.cancellation.request'),
            ('res_id', '=', request.id),
            ('summary', '=', 'Review subscription request'),
        ]))
        self.assertEqual(request.request_age_days, 0)

        action = sub.action_view_subscription_cancellation_requests()
        self.assertEqual(action['res_model'], 'subscription.cancellation.request')
        self.assertIn(('subscription_id', '=', sub.id), action['domain'])
        self.assertEqual(sub.cancellation_request_count, 1)

        open_action = request.action_open_subscription()
        self.assertEqual(open_action['res_model'], 'sale.order')
        self.assertEqual(open_action['res_id'], sub.id)

    def test_portal_cancellation_request_blocks_duplicate_pending_request(self):
        sub = self._create_active_subscription()
        sub.sudo()._portal_request_cancellation(
            self.cancel_reason,
            'First request',
            self.env.user,
        )

        with self.assertRaises(ValidationError):
            sub.sudo()._portal_request_cancellation(
                self.cancel_reason,
                'Second request',
                self.env.user,
            )

    def test_portal_cancellation_request_blocks_scheduled_cancellation(self):
        sub = self._create_active_subscription()
        sub._action_schedule_cancel(
            reason_id=self.cancel_reason.id,
            feedback='Already scheduled',
            effective_date=sub.next_invoice_date,
            policy='end_of_period',
        )

        with self.assertRaises(ValidationError):
            sub.sudo()._portal_request_cancellation(
                self.cancel_reason,
                'Cancel again',
                self.env.user,
            )

    def test_portal_cancellation_request_respects_minimum_commitment(self):
        committed_plan = self.env['subscription.plan'].create({
            'name': 'Portal Committed Monthly',
            'code': 'PORTAL-COMMITTED-MONTHLY',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
            'trial_days': 0,
            'min_commitment_periods': 3,
        })
        sub = self._create_active_subscription(plan=committed_plan)
        sub.write({
            'subscription_start_date': fields.Date.today() - relativedelta(months=1),
            'next_invoice_date': fields.Date.today() + relativedelta(days=15),
        })

        with self.assertRaises(UserError):
            sub.sudo()._portal_request_cancellation(
                self.cancel_reason,
                'Still committed',
                self.env.user,
            )

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

    def test_plan_and_order_lines_default_to_base_component(self):
        plan_line = self.env['subscription.plan.line'].create({
            'plan_id': self.plan.id,
            'product_id': self.product.id,
            'quantity': 1.0,
            'price_unit': 100.0,
            'description': 'Base plan line',
        })
        sub = self._create_active_subscription()

        self.assertEqual(plan_line.subscription_component_type, 'base')
        self.assertEqual(sub.order_line[:1].subscription_component_type, 'base')

    def test_seat_quantity_counts_only_recurring_seat_lines(self):
        sub = self._create_active_subscription()
        sub.write({
            'order_line': [
                (0, 0, {
                    'product_id': self.addon_product.id,
                    'name': 'User Seats',
                    'is_recurring': True,
                    'subscription_component_type': 'seat',
                    'price_unit': 12.0,
                    'product_uom_qty': 7,
                }),
                (0, 0, {
                    'product_id': self.addon_product.id,
                    'name': 'One-time onboarding',
                    'is_recurring': False,
                    'subscription_component_type': 'seat',
                    'price_unit': 20.0,
                    'product_uom_qty': 3,
                }),
            ],
        })

        self.assertEqual(sub.seat_quantity, 7.0)

    def test_renewal_quote_preserves_component_type_and_seat_quantity(self):
        sub = self._create_active_subscription()
        line = sub.order_line.filtered('is_recurring')[:1]
        line.write({
            'subscription_component_type': 'seat',
            'product_uom_qty': 5,
        })

        quote = self.env['sale.order'].browse(sub.action_renew_subscription()['res_id'])
        quote_line = quote.order_line.filtered('is_recurring')[:1]

        self.assertEqual(quote_line.subscription_component_type, 'seat')
        self.assertEqual(quote_line.product_uom_qty, 5.0)
        self.assertEqual(quote.seat_quantity, 5.0)

    def test_renewal_quote_respects_plan_policy(self):
        sub = self._create_active_subscription()
        sub.subscription_plan_id.allow_renewal_quote = False

        with self.assertRaises(UserError):
            sub.action_renew_subscription()

    def test_past_due_renewal_quote_respects_plan_policy(self):
        sub = self._create_active_subscription()
        sub.write({'subscription_state': 'past_due'})
        sub.subscription_plan_id.allow_past_due_renewal_quote = False

        with self.assertRaises(UserError):
            sub.action_renew_subscription()

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
                'subscription_component_type': 'addon',
                'price_unit': 40.0,
                'product_uom_qty': 1,
            })],
        })

        quote.action_confirm()

        addon_lines = sub.order_line.filtered(lambda line: line.product_id == self.addon_product and line.is_recurring)
        self.assertEqual(len(addon_lines), 1)
        self.assertEqual(addon_lines.subscription_component_type, 'addon')
        self.assertGreater(sub.mrr, old_mrr)
        self.assertTrue(sub.subscription_log_ids.filtered(lambda log: log.event_type == 'upsold'))
        self.assertTrue(self.env['subscription.mrr.movement'].search([
            ('subscription_id', '=', sub.id),
            ('movement_type', '=', 'expansion'),
        ]))

    def test_upsell_quote_respects_plan_policy(self):
        sub = self._create_active_subscription()
        sub.subscription_plan_id.allow_upsell_quote = False

        with self.assertRaises(UserError):
            sub.action_upsell_subscription()

    def test_past_due_upsell_quote_respects_plan_policy(self):
        sub = self._create_active_subscription()
        sub.write({'subscription_state': 'past_due'})
        sub.subscription_plan_id.allow_past_due_upsell_quote = False

        with self.assertRaises(UserError):
            sub.action_upsell_subscription()

    def test_expired_subscription_can_renew_but_not_upsell(self):
        sub = self._create_active_subscription()
        sub.write({'subscription_state': 'expired'})

        action = sub.action_renew_subscription()
        quote = self.env['sale.order'].browse(action['res_id'])

        self.assertEqual(quote.subscription_quote_type, 'renewal')
        self.assertEqual(quote.subscription_origin_id, sub)
        with self.assertRaises(UserError):
            sub.action_upsell_subscription()

    def test_subscription_quote_cannot_create_nested_quotes(self):
        sub = self._create_active_subscription()
        quote = self.env['sale.order'].browse(sub.action_renew_subscription()['res_id'])

        with self.assertRaises(UserError):
            quote.action_renew_subscription()
        with self.assertRaises(UserError):
            quote.action_upsell_subscription()
