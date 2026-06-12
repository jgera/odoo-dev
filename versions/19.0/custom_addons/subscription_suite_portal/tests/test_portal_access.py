from unittest.mock import patch

from odoo import fields
from odoo.addons.payment import utils as payment_utils
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tests.common import TransactionCase

class TestPortalAccess(TransactionCase):

    def setUp(self):
        super(TestPortalAccess, self).setUp()
        self.partner = self.env['res.partner'].create({'name': 'Portal Customer'})
        self.plan = self.env['subscription.plan'].create({
            'name': 'Portal Test Plan',
            'code': 'PORTAL-TEST',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.upgrade_plan = self.env['subscription.plan'].create({
            'name': 'Portal Upgrade Plan',
            'code': 'PORTAL-UPGRADE',
            'billing_interval_count': 1,
            'billing_interval_unit': 'month',
        })
        self.product = self.env['product.product'].create({
            'name': 'Portal Recovery Product',
            'type': 'service',
            'invoice_policy': 'order',
            'list_price': 75.0,
        })
        self.sub = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'is_subscription': True,
            'subscription_state': 'active',
            'subscription_plan_id': self.plan.id,
        })

    def _create_subscription_invoice(self):
        self.sub.write({
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'name': self.product.name,
                'product_uom_qty': 1.0,
                'price_unit': 75.0,
                'is_recurring': True,
            })],
        })
        self.sub.action_confirm()
        invoice = self.sub._create_invoices()[:1]
        invoice.write({'subscription_id': self.sub.id})
        invoice.action_post()
        return invoice

    def _create_payment_provider(self):
        payment_method = self.env.ref('payment.payment_method_unknown')
        redirect_form = self.env['ir.ui.view'].create({
            'name': 'Portal Payment Method Dummy Redirect Form',
            'type': 'qweb',
            'arch': '<form action="dummy" method="post"/>',
        })
        provider = self.env['payment.provider'].create({
            'name': 'Portal Payment Method Dummy Provider',
            'code': 'none',
            'state': 'test',
            'is_published': True,
            'allow_tokenization': True,
            'payment_method_ids': [Command.set([payment_method.id])],
            'redirect_form_view_id': redirect_form.id,
            'available_currency_ids': [Command.set([self.env.company.currency_id.id])],
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
            'provider_ref': 'portal-subscription-token',
            'active': True,
        })

    def test_01_subscription_is_visible(self):
        """Test that a subscription is found when searching for is_subscription."""
        subs = self.env['sale.order'].search([
            ('partner_id', '=', self.partner.id),
            ('is_subscription', '=', True),
        ])
        self.assertIn(self.sub, subs)

    def test_02_non_subscription_not_included(self):
        """Test that regular sale orders are not returned in subscription searches."""
        regular_so = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'is_subscription': False,
        })
        subs = self.env['sale.order'].search([
            ('partner_id', '=', self.partner.id),
            ('is_subscription', '=', True),
        ])
        self.assertNotIn(regular_so, subs)

    def test_03_portal_plan_change_status_data_exists(self):
        """Portal detail values can include pending plan changes and approval requests."""
        today = fields.Date.today()
        self.sub.write({
            'pending_plan_change_id': self.upgrade_plan.id,
            'pending_plan_change_date': today,
            'pending_plan_change_type': 'upgrade',
        })
        request = self.env['subscription.plan.change.request'].create({
            'subscription_id': self.sub.id,
            'current_plan_id': self.plan.id,
            'requested_plan_id': self.upgrade_plan.id,
            'requested_effective_date': today,
            'requested_timing': 'next_period',
            'change_type': 'upgrade',
            'old_mrr': 0.0,
            'new_mrr': 0.0,
        })

        portal_requests = self.env['subscription.plan.change.request'].search([
            ('subscription_id', '=', self.sub.id),
        ])

        self.assertEqual(self.sub.pending_plan_change_id, self.upgrade_plan)
        self.assertIn(request, portal_requests)

    def test_04_portal_cancellation_request_status_data_exists(self):
        """Portal detail values can include scheduled cancellation and request status."""
        today = fields.Date.today()
        reason = self.env['subscription.cancel.reason'].create({'name': 'Portal cancellation reason'})
        self.sub.write({
            'pending_cancellation': True,
            'cancellation_requested_date': today,
            'cancellation_effective_date': today,
            'cancellation_policy_applied': 'end_of_period',
            'cancellation_reason_id': reason.id,
        })
        request = self.env['subscription.cancellation.request'].create({
            'subscription_id': self.sub.id,
            'reason_id': reason.id,
            'feedback': 'Portal cancellation request',
            'requested_effective_date': today,
            'requested_policy': 'end_of_period',
        })

        portal_requests = self.env['subscription.cancellation.request'].search([
            ('subscription_id', '=', self.sub.id),
        ])

        self.assertTrue(self.sub.pending_cancellation)
        self.assertEqual(self.sub.cancellation_reason_id, reason)
        self.assertIn(request, portal_requests)

    def test_05_portal_lifecycle_request_status_data_exists(self):
        """Portal detail values can include pause/resume request status."""
        request = self.env['subscription.lifecycle.request'].create({
            'subscription_id': self.sub.id,
            'request_type': 'pause',
            'feedback': 'Portal pause request',
        })

        portal_requests = self.env['subscription.lifecycle.request'].search([
            ('subscription_id', '=', self.sub.id),
        ])

        self.assertIn(request, portal_requests)
        self.assertEqual(request.state, 'pending')
        self.assertEqual(request.request_type, 'pause')

    def test_06_portal_payment_recovery_invoice_data_exists(self):
        """Portal detail values can expose the oldest open subscription invoice."""
        invoice = self._create_subscription_invoice()
        self.sub.subscription_state = 'past_due'

        recovery_invoice = self.sub._get_portal_payment_recovery_invoice()

        self.assertEqual(recovery_invoice, invoice)
        self.assertEqual(recovery_invoice.payment_state, 'not_paid')
        self.assertEqual(recovery_invoice.subscription_id, self.sub)

    def test_06b_portal_payment_recovery_context_blocks_retry_without_token(self):
        """Portal recovery context explains when no saved method exists."""
        invoice = self._create_subscription_invoice()
        self.sub.subscription_state = 'past_due'

        recovery = self.sub._get_portal_payment_recovery_context()

        self.assertEqual(recovery['invoice'], invoice)
        self.assertEqual(recovery['state'], 'missing_payment_method')
        self.assertFalse(recovery['can_retry'])
        self.assertIn('No saved payment method', recovery['message'])

    def test_06c_portal_payment_recovery_context_allows_saved_token_retry(self):
        """Portal recovery context exposes retry availability when a saved method exists."""
        invoice = self._create_subscription_invoice()
        token = self._create_payment_token(self.partner)
        self.sub.write({
            'subscription_state': 'past_due',
            'payment_token_id': token.id,
        })

        recovery = self.sub._get_portal_payment_recovery_context()

        self.assertEqual(recovery['invoice'], invoice)
        self.assertEqual(recovery['state'], 'retry_available')
        self.assertTrue(recovery['can_retry'])

    def test_06d_portal_payment_recovery_context_is_clear_for_paid_invoice(self):
        """Portal recovery context does not expose paid invoices as recovery work."""
        invoice = self._create_subscription_invoice()
        invoice.payment_state = 'paid'
        self.sub.subscription_state = 'active'

        recovery = self.sub._get_portal_payment_recovery_context()

        self.assertFalse(recovery['invoice'])
        self.assertEqual(recovery['state'], 'clear')
        self.assertFalse(recovery['can_retry'])

    def test_07_portal_payment_retry_requires_saved_payment_method(self):
        """Portal retry cannot run token collection without a saved payment method."""
        invoice = self._create_subscription_invoice()
        self.sub.subscription_state = 'past_due'

        with self.assertRaises(UserError):
            self.sub._portal_retry_payment_recovery(invoice, self.env.user)

    def test_08_portal_available_payment_tokens_are_customer_owned(self):
        """Portal token selector only exposes active tokens owned by the customer."""
        owned_token = self._create_payment_token(self.partner)
        other_partner = self.env['res.partner'].create({'name': 'Other Portal Customer'})
        self._create_payment_token(other_partner)
        portal_user = self.env['res.users'].create({
            'name': 'Portal Token User',
            'login': 'portal-token-user@example.com',
            'partner_id': self.partner.id,
            'group_ids': [Command.set([self.env.ref('base.group_portal').id])],
        })

        tokens = self.sub._get_portal_available_payment_tokens(portal_user.partner_id)

        self.assertIn(owned_token, tokens)
        self.assertEqual(tokens.mapped('partner_id').commercial_partner_id, self.partner.commercial_partner_id)

    def test_09_portal_assign_payment_token_updates_subscription(self):
        """Portal token assignment stores the token and logs the change."""
        token = self._create_payment_token(self.partner)
        portal_user = self.env['res.users'].create({
            'name': 'Portal Assign User',
            'login': 'portal-assign-user@example.com',
            'partner_id': self.partner.id,
            'group_ids': [Command.set([self.env.ref('base.group_portal').id])],
        })

        self.sub._portal_assign_payment_token(token, portal_user)

        self.assertEqual(self.sub.payment_token_id, token)
        event = self.env['subscription.log'].search([
            ('subscription_id', '=', self.sub.id),
            ('event_type', '=', 'payment_method_updated'),
        ], limit=1)
        self.assertTrue(event)

    def test_10_portal_assign_payment_token_rejects_other_customer_token(self):
        """Portal token assignment cannot attach another customer's saved method."""
        other_partner = self.env['res.partner'].create({'name': 'Other Token Owner'})
        token = self._create_payment_token(other_partner)
        portal_user = self.env['res.users'].create({
            'name': 'Portal Reject User',
            'login': 'portal-reject-user@example.com',
            'partner_id': self.partner.id,
            'group_ids': [Command.set([self.env.ref('base.group_portal').id])],
        })

        with self.assertRaises(ValidationError):
            self.sub._portal_assign_payment_token(token, portal_user)

    def test_11_portal_payment_retry_rejects_other_customer_requester(self):
        """The payment retry helper cannot be used for another customer's subscription."""
        invoice = self._create_subscription_invoice()
        token = self._create_payment_token(self.partner)
        self.sub.write({
            'subscription_state': 'past_due',
            'payment_token_id': token.id,
        })
        other_partner = self.env['res.partner'].create({'name': 'Other Retry Requester'})
        other_user = self.env['res.users'].create({
            'name': 'Other Retry User',
            'login': 'portal-other-retry-user@example.com',
            'partner_id': other_partner.id,
            'group_ids': [Command.set([self.env.ref('base.group_portal').id])],
        })

        with self.assertRaises(ValidationError):
            self.sub._portal_retry_payment_recovery(invoice, other_user)

    def test_12_portal_payment_retry_rejects_unrelated_invoice(self):
        """Portal payment retry cannot collect payment for an invoice from another subscription."""
        token = self._create_payment_token(self.partner)
        self.sub.write({
            'subscription_state': 'past_due',
            'payment_token_id': token.id,
        })
        other_partner = self.env['res.partner'].create({'name': 'Other Invoice Owner'})
        other_sub = self.env['sale.order'].create({
            'partner_id': other_partner.id,
            'is_subscription': True,
            'subscription_state': 'past_due',
            'subscription_plan_id': self.plan.id,
        })
        other_sub.write({
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'name': self.product.name,
                'product_uom_qty': 1.0,
                'price_unit': 75.0,
                'is_recurring': True,
            })],
        })
        other_sub.action_confirm()
        other_invoice = other_sub._create_invoices()[:1]
        other_invoice.write({'subscription_id': other_sub.id})
        other_invoice.action_post()

        with self.assertRaises(ValidationError):
            self.sub._portal_retry_payment_recovery(other_invoice, self.env.user)

    def test_13_portal_payment_validation_rejects_other_customer_transaction(self):
        """Payment-method return cannot assign another customer's validation token."""
        other_partner = self.env['res.partner'].create({'name': 'Other Validation Owner'})
        token = self._create_payment_token(other_partner)
        portal_user = self.env['res.users'].create({
            'name': 'Portal Validation User',
            'login': 'portal-validation-user@example.com',
            'partner_id': self.partner.id,
            'group_ids': [Command.set([self.env.ref('base.group_portal').id])],
        })
        tx = self.env['payment.transaction'].sudo().create({
            'provider_id': token.provider_id.id,
            'token_id': token.id,
            'payment_method_id': token.payment_method_id.id,
            'operation': 'validation',
            'amount': 0.0,
            'currency_id': self.env.company.currency_id.id,
            'partner_id': other_partner.id,
            'reference': 'portal-validation-other-customer',
        })
        tx._set_done()
        access_token = payment_utils.generate_access_token(
            tx.partner_id.id,
            tx.amount,
            tx.currency_id.id,
            env=self.env,
        )

        with self.assertRaises(ValidationError):
            self.sub._portal_assign_payment_token_from_validation_transaction(
                tx,
                access_token,
                portal_user,
            )

        self.assertFalse(self.sub.payment_token_id)

    def test_14_portal_payment_validation_assigns_owned_token(self):
        """A valid payment-method validation transaction assigns the saved token."""
        token = self._create_payment_token(self.partner)
        portal_user = self.env['res.users'].create({
            'name': 'Portal Validation Owner',
            'login': 'portal-validation-owner@example.com',
            'partner_id': self.partner.id,
            'group_ids': [Command.set([self.env.ref('base.group_portal').id])],
        })
        tx = self.env['payment.transaction'].sudo().create({
            'provider_id': token.provider_id.id,
            'token_id': token.id,
            'payment_method_id': token.payment_method_id.id,
            'operation': 'validation',
            'amount': 0.0,
            'currency_id': self.env.company.currency_id.id,
            'partner_id': self.partner.id,
            'reference': 'portal-validation-owned-token',
        })
        tx._set_done()
        access_token = payment_utils.generate_access_token(
            tx.partner_id.id,
            tx.amount,
            tx.currency_id.id,
            env=self.env,
        )

        result = self.sub._portal_assign_payment_token_from_validation_transaction(
            tx,
            access_token,
            portal_user,
        )

        self.assertEqual(result, 'saved')
        self.assertEqual(self.sub.payment_token_id, token)

    def test_15_portal_payment_retry_records_pending_attempt_and_log(self):
        """A pending portal retry remains traceable through the payment attempt ledger."""
        invoice = self._create_subscription_invoice()
        token = self._create_payment_token(self.partner)
        self.sub.write({
            'subscription_state': 'past_due',
            'payment_token_id': token.id,
        })
        portal_user = self.env['res.users'].create({
            'name': 'Portal Pending Retry User',
            'login': 'portal-pending-retry@example.com',
            'partner_id': self.partner.id,
            'group_ids': [Command.set([self.env.ref('base.group_portal').id])],
        })

        def fake_send_payment_request(transactions):
            transactions._set_pending()

        with patch.object(self.env.registry['payment.transaction'], '_send_payment_request', fake_send_payment_request):
            transaction = self.sub._portal_retry_payment_recovery(invoice, portal_user)

        attempt = self.env['subscription.payment.attempt'].search([
            ('subscription_id', '=', self.sub.id),
            ('invoice_id', '=', invoice.id),
            ('source', '=', 'portal'),
        ], limit=1)
        self.assertTrue(attempt)
        self.assertEqual(attempt.requested_by_id, portal_user)
        self.assertEqual(attempt.transaction_id, transaction)
        self.assertEqual(attempt.state, 'pending')
        self.assertIn('waiting for provider confirmation', attempt.recovery_note)
        event = self.env['subscription.log'].search([
            ('subscription_id', '=', self.sub.id),
            ('event_type', '=', 'payment_pending'),
        ], limit=1)
        self.assertTrue(event)

    def test_16_portal_payment_retry_records_success_attempt_and_log(self):
        """A successful portal retry is visible from the payment attempt and subscription log."""
        invoice = self._create_subscription_invoice()
        token = self._create_payment_token(self.partner)
        self.sub.write({
            'subscription_state': 'past_due',
            'payment_token_id': token.id,
        })
        portal_user = self.env['res.users'].create({
            'name': 'Portal Success Retry User',
            'login': 'portal-success-retry@example.com',
            'partner_id': self.partner.id,
            'group_ids': [Command.set([self.env.ref('base.group_portal').id])],
        })

        def fake_send_payment_request(transactions):
            transactions._set_done()

        with patch.object(self.env.registry['payment.transaction'], '_send_payment_request', fake_send_payment_request):
            transaction = self.sub._portal_retry_payment_recovery(invoice, portal_user)

        attempt = self.env['subscription.payment.attempt'].search([
            ('subscription_id', '=', self.sub.id),
            ('invoice_id', '=', invoice.id),
            ('source', '=', 'portal'),
        ], limit=1)
        self.assertEqual(attempt.transaction_id, transaction)
        self.assertEqual(attempt.state, 'success')
        self.assertEqual(attempt.recovery_note, 'Payment was recovered successfully.')
        event = self.env['subscription.log'].search([
            ('subscription_id', '=', self.sub.id),
            ('event_type', '=', 'payment_success'),
        ], limit=1)
        self.assertTrue(event)

    def test_17_failed_portal_payment_retry_is_manager_recovery_work(self):
        """A failed portal retry appears as payment recovery work for managers."""
        invoice = self._create_subscription_invoice()
        token = self._create_payment_token(self.partner)
        self.sub.write({
            'subscription_state': 'past_due',
            'payment_token_id': token.id,
        })
        portal_user = self.env['res.users'].create({
            'name': 'Portal Failed Retry User',
            'login': 'portal-failed-retry@example.com',
            'partner_id': self.partner.id,
            'group_ids': [Command.set([self.env.ref('base.group_portal').id])],
        })

        def fake_send_payment_request(transactions):
            transactions._set_error('card declined')

        with patch.object(self.env.registry['payment.transaction'], '_send_payment_request', fake_send_payment_request):
            self.sub._portal_retry_payment_recovery(invoice, portal_user)

        attempt = self.env['subscription.payment.attempt'].search([
            ('subscription_id', '=', self.sub.id),
            ('invoice_id', '=', invoice.id),
            ('source', '=', 'portal'),
        ], limit=1)
        self.assertEqual(attempt.state, 'failed')
        self.assertTrue(attempt.recovery_required)
        self.assertIn('Customer payment retry failed', attempt.recovery_note)
        self.env.flush_all()
        operation = self.env['subscription.manager.operation'].search([
            ('source_model', '=', 'subscription.payment.attempt'),
            ('source_res_id', '=', attempt.id),
            ('operation_type', '=', 'payment_recovery'),
        ], limit=1)
        self.assertTrue(operation)
