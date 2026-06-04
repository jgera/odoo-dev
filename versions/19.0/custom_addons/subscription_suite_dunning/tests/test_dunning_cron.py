from odoo.tests.common import TransactionCase
from odoo import fields
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
        
        self.step_1 = self.env['subscription.dunning.policy.line'].create({
            'policy_id': self.policy.id,
            'delay_days': 1,
            'action_type': 'email'
        })
        
        self.step_3 = self.env['subscription.dunning.policy.line'].create({
            'policy_id': self.policy.id,
            'delay_days': 3,
            'action_type': 'email'
        })
        
        self.plan = self.env['subscription.plan'].create({
            'name': 'Dunning Plan',
            'code': 'DUNNING-PLAN',
            'dunning_policy_id': self.policy.id
        })
        
        self.sub = self.env['sale.order'].create({
            'partner_id': self.env['res.partner'].create({'name': 'Test Customer'}).id,
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
            
        # Day 6 (Step 3 + 3 delay): Final Action (Cancel)
        self.sub.dunning_start_date = fields.Date.today() - timedelta(days=6)
        self.sub.next_dunning_date = fields.Date.today()
        self.env['sale.order']._cron_process_dunning()
        self.assertEqual(self.sub.subscription_state, 'cancelled')
