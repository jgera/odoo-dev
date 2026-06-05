from odoo.tests.common import TransactionCase
from odoo import fields
from odoo.exceptions import ValidationError
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
