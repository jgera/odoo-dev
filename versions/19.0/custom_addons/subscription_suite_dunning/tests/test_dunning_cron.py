from unittest.mock import patch

from odoo.tests.common import TransactionCase
from odoo import fields
from odoo.exceptions import ValidationError
from odoo.exceptions import UserError
from odoo.fields import Command
from datetime import date, timedelta

class TestDunningCron(TransactionCase):

    def setUp(self):
        super(TestDunningCron, self).setUp()
        
        self.policy = self.env['subscription.dunning.policy'].create({
            'name': 'Test Policy',
            'grace_period_days': 1,
            'final_action': 'cancel',
            'final_action_delay': 3
        })

        self.template = self.env['mail.template'].create({
            'name': 'Test Dunning Template',
            'model_id': self.env.ref('sale.model_sale_order').id,
            'subject': 'Test dunning for {{ object.name }}',
            'email_from': '{{ object.company_id.email or "billing@example.com" }}',
            'email_to': '{{ object.partner_id.email or "customer@example.com" }}',
            'body_html': '<p>Recover at <t t-out="ctx.get(\'dunning_recovery_url\')"/></p>',
        })
        
        self.step_1 = self.env['subscription.dunning.policy.line'].create({
            'policy_id': self.policy.id,
            'delay_days': 1,
            'action_type': 'email',
            'email_template_id': self.template.id,
        })
        
        self.step_3 = self.env['subscription.dunning.policy.line'].create({
            'policy_id': self.policy.id,
            'delay_days': 3,
            'action_type': 'email',
            'email_template_id': self.template.id,
        })
        
        self.plan = self.env['subscription.plan'].create({
            'name': 'Dunning Plan',
            'code': 'DUNNING-PLAN',
            'dunning_policy_id': self.policy.id
        })
        
        self.sub = self.env['sale.order'].create({
            'partner_id': self.env['res.partner'].create({
                'name': 'Test Customer',
                'email': 'customer@example.com',
            }).id,
            'is_subscription': True,
            'subscription_state': 'active',
            'subscription_plan_id': self.plan.id,
        })

    def _create_payment_token(self):
        payment_method = self.env.ref('payment.payment_method_unknown')
        redirect_form = self.env['ir.ui.view'].create({
            'name': 'Dunning Retry Dummy Redirect Form',
            'type': 'qweb',
            'arch': '<form action="dummy" method="post"/>',
        })
        provider = self.env['payment.provider'].create({
            'name': 'Dunning Retry Dummy Provider',
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
        token = self.env['payment.token'].sudo().create({
            'provider_id': provider.id,
            'payment_method_id': payment_method.id,
            'payment_details': '4242',
            'partner_id': self.sub.partner_id.id,
            'provider_ref': 'dunning-retry-token',
            'active': True,
        })
        self.sub.payment_token_id = token.id
        return token

    def _create_retry_invoice(self):
        return self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.sub.partner_id.id,
            'invoice_date': fields.Date.today(),
            'subscription_id': self.sub.id,
        })

    def test_01_dunning_cron_progression(self):
        """Test the dunning cron correctly steps through the policy timeline."""
        # Force a payment failure on Day 0
        self.sub._start_dunning()
        self.assertEqual(self.sub.subscription_state, 'past_due')
        self.assertEqual(self.sub.dunning_start_date, fields.Date.today())
        
        # Day 1: Simulate 1 day elapsed, cron should execute Step 1
        self.sub.dunning_start_date = fields.Date.today() - timedelta(days=1)
        self.sub.next_dunning_date = fields.Date.today()
        self.env['sale.order']._cron_process_dunning()
        self.assertEqual(self.sub.dunning_step_id.id, self.step_1.id)
        attempt_1 = self.env['subscription.dunning.attempt'].search([
            ('subscription_id', '=', self.sub.id),
            ('policy_line_id', '=', self.step_1.id),
        ])
        self.assertEqual(len(attempt_1), 1)
        self.assertEqual(attempt_1.state, 'done')
        self.assertIn('/my/subscription/%s' % self.sub.id, attempt_1.recovery_url)
            
        # Day 2: Simulate 2 days elapsed, cron should do nothing (next_dunning_date in future)
        self.sub.dunning_start_date = fields.Date.today() - timedelta(days=2)
        # next_dunning_date was set by cron to a future date, don't override to today
        # so the cron search won't pick it up — step should stay the same
        self.env['sale.order']._cron_process_dunning()
        self.assertEqual(self.sub.dunning_step_id.id, self.step_1.id)
            
        # Day 3: Simulate 3 days elapsed, cron should execute Step 3
        self.sub.dunning_start_date = fields.Date.today() - timedelta(days=3)
        self.sub.next_dunning_date = fields.Date.today()
        self.env['sale.order']._cron_process_dunning()
        self.assertEqual(self.sub.dunning_step_id.id, self.step_3.id)
        self.assertEqual(self.sub.dunning_attempt_count, 2)
            
        # Day 6 (Step 3 + 3 delay): Final Action (Cancel)
        self.sub.dunning_start_date = fields.Date.today() - timedelta(days=6)
        self.sub.next_dunning_date = fields.Date.today()
        self.env['sale.order']._cron_process_dunning()
        self.assertEqual(self.sub.subscription_state, 'cancelled')
        final_attempt = self.env['subscription.dunning.attempt'].search([
            ('subscription_id', '=', self.sub.id),
            ('action_type', '=', 'final_cancel'),
        ])
        self.assertEqual(len(final_attempt), 1)
        self.assertEqual(final_attempt.state, 'done')

    def test_02_email_and_retry_requires_template(self):
        with self.assertRaises(ValidationError):
            self.env['subscription.dunning.policy.line'].create({
                'policy_id': self.policy.id,
                'delay_days': 5,
                'action_type': 'email_and_retry',
            })

    def test_03_dunning_payment_override_accepts_request_metadata(self):
        self.sub._start_dunning()
        tx = self.sub._auto_collect_payment(
            self.env['account.move'],
            source='portal',
            requested_by=self.env.user,
        )
        self.assertFalse(tx)
        self.assertEqual(self.sub.subscription_state, 'past_due')

    def test_04_manual_retry_from_dunning_attempt_links_payment_attempt(self):
        self.sub._start_dunning()
        invoice = self._create_retry_invoice()
        self._create_payment_token()
        attempt = self.env['subscription.dunning.attempt'].create({
            'subscription_id': self.sub.id,
            'invoice_id': invoice.id,
            'policy_id': self.policy.id,
            'policy_line_id': self.step_1.id,
            'action_type': 'email',
            'state': 'done',
            'amount_at_risk': 100.0,
        })

        class DummyTransaction:
            state = 'done'

        def fake_auto_collect(subscription, retry_invoice, source='cron', requested_by=None):
            payment_attempt = self.env['subscription.payment.attempt'].create({
                'name': 'DUNNING-MANUAL-PAY-001',
                'subscription_id': subscription.id,
                'invoice_id': retry_invoice.id,
                'source': source,
                'state': 'success',
                'amount': 100.0,
                'requested_by_id': requested_by.id,
            })
            subscription._resolve_dunning()
            self.assertEqual(source, 'manual')
            self.assertEqual(requested_by, self.env.user)
            return DummyTransaction()

        with patch.object(self.env.registry['sale.order'], '_auto_collect_payment', fake_auto_collect):
            action = attempt.action_retry_payment()

        self.assertEqual(attempt.manual_retry_count, 1)
        self.assertTrue(attempt.last_manual_retry_at)
        self.assertEqual(attempt.payment_attempt_id.name, 'DUNNING-MANUAL-PAY-001')
        self.assertEqual(action['res_model'], 'subscription.payment.attempt')
        self.assertEqual(action['res_id'], attempt.payment_attempt_id.id)
        self.assertEqual(self.sub.subscription_state, 'active')
        self.assertIn('recovered', attempt.note)

    def test_05_manual_retry_requires_eligible_attempt(self):
        invoice = self._create_retry_invoice()
        attempt = self.env['subscription.dunning.attempt'].create({
            'subscription_id': self.sub.id,
            'invoice_id': invoice.id,
            'policy_id': self.policy.id,
            'policy_line_id': self.step_1.id,
            'action_type': 'email',
            'state': 'done',
        })

        with self.assertRaises(UserError):
            attempt.action_retry_payment()

        self._create_payment_token()
        final_attempt = self.env['subscription.dunning.attempt'].create({
            'subscription_id': self.sub.id,
            'invoice_id': invoice.id,
            'policy_id': self.policy.id,
            'action_type': 'final_cancel',
            'state': 'done',
        })
        with self.assertRaises(UserError):
            final_attempt.action_retry_payment()

    def test_06_final_dunning_action_is_idempotent(self):
        self.sub._start_dunning()
        self.sub._execute_final_dunning_action(self.policy)
        first_attempt = self.env['subscription.dunning.attempt'].search([
            ('subscription_id', '=', self.sub.id),
            ('action_type', '=', 'final_cancel'),
        ])
        self.sub._execute_final_dunning_action(self.policy)
        second_attempt = self.env['subscription.dunning.attempt'].search([
            ('subscription_id', '=', self.sub.id),
            ('action_type', '=', 'final_cancel'),
        ])

        self.assertEqual(first_attempt, second_attempt)
        self.assertEqual(len(second_attempt), 1)
