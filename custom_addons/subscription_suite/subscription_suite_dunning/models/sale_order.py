import logging
from odoo import models, fields, api, _
from datetime import timedelta

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dunning_start_date = fields.Date(string='Dunning Start Date', copy=False)
    next_dunning_date = fields.Date(string='Next Dunning Date', copy=False)
    dunning_step_id = fields.Many2one('subscription.dunning.policy.line', string='Last Dunning Step', copy=False)

    def _auto_collect_payment(self, invoice):
        # Override to trigger dunning on failure or resolve on success
        tx = super()._auto_collect_payment(invoice)
        if tx:
            if tx.state == 'done':
                self._resolve_dunning()
            elif tx.state in ['error', 'cancel']:
                self._start_dunning()
        else:
            self._start_dunning()
        return tx

    def _start_dunning(self):
        self.ensure_one()
        if self.subscription_state != 'past_due':
            self.subscription_state = 'past_due'
            self.dunning_start_date = fields.Date.today()
            
            policy = self.subscription_plan_id.dunning_policy_id
            if policy:
                self.next_dunning_date = self.dunning_start_date + timedelta(days=policy.grace_period_days)
            else:
                self.next_dunning_date = False
                
            self._log_subscription_event('dunning_started', 'Payment failed, subscription entered dunning')

    def _resolve_dunning(self):
        self.ensure_one()
        if self.subscription_state == 'past_due':
            self.subscription_state = 'active'
            self.dunning_start_date = False
            self.next_dunning_date = False
            self.dunning_step_id = False
            self._log_subscription_event('dunning_success', 'Payment successful, subscription recovered')

    @api.model
    def _cron_process_dunning(self):
        today = fields.Date.today()
        subscriptions = self.search([
            ('is_subscription', '=', True),
            ('subscription_state', '=', 'past_due'),
            ('next_dunning_date', '<=', today),
            ('subscription_plan_id.dunning_policy_id', '!=', False)
        ])
        
        for sub in subscriptions:
            policy = sub.subscription_plan_id.dunning_policy_id
            
            # Find the next step to execute
            next_step = False
            days_since_start = (today - sub.dunning_start_date).days
            
            # Get all steps ordered by delay_days
            steps = policy.line_ids
            current_delay = sub.dunning_step_id.delay_days if sub.dunning_step_id else 0
            for step in steps:
                if current_delay < step.delay_days <= days_since_start:
                    next_step = step
                    break
                        
            if next_step:
                # Execute step
                if next_step.action_type == 'email' and next_step.email_template_id:
                    next_step.email_template_id.send_mail(sub.id, force_send=True)
                    sub._log_subscription_event('dunning_step', f'Sent dunning email (Step: {next_step.delay_days} days)')
                
                sub.dunning_step_id = next_step.id
                
                # Determine next dunning date
                future_steps = steps.filtered(lambda s: s.delay_days > next_step.delay_days)
                if future_steps:
                    next_delay = future_steps[0].delay_days - next_step.delay_days
                    sub.next_dunning_date = today + timedelta(days=next_delay)
                else:
                    # No more steps, schedule final action
                    sub.next_dunning_date = today + timedelta(days=policy.final_action_delay)
            else:
                # Check for final action
                if steps:
                    last_step = steps[-1]
                    if sub.dunning_step_id and sub.dunning_step_id.id == last_step.id:
                        if days_since_start >= last_step.delay_days + policy.final_action_delay:
                            sub._execute_final_dunning_action(policy)

    def _execute_final_dunning_action(self, policy):
        self.ensure_one()
        if policy.final_action == 'cancel':
            self._action_cancel(feedback="Automated cancellation due to failed dunning")
        elif policy.final_action == 'pause':
            self.subscription_state = 'paused'
            self.pause_date = fields.Date.today()
            self._log_subscription_event('paused', 'Automated pause due to failed dunning')
        
        self.next_dunning_date = False
