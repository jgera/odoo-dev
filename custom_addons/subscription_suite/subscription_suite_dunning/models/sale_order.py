import logging
from odoo import models, fields, api, _
from datetime import timedelta

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dunning_start_date = fields.Date(string='Dunning Start Date', copy=False, index=True)
    next_dunning_date = fields.Date(string='Next Dunning Date', copy=False, index=True)
    dunning_step_id = fields.Many2one('subscription.dunning.policy.line', string='Last Dunning Step', copy=False, index=True)
    dunning_attempt_ids = fields.One2many('subscription.dunning.attempt', 'subscription_id', string='Dunning Attempts')
    dunning_attempt_count = fields.Integer(string='Dunning Count', compute='_compute_dunning_attempt_count')

    def _compute_dunning_attempt_count(self):
        grouped = self.env['subscription.dunning.attempt']._read_group(
            [('subscription_id', 'in', self.ids)],
            ['subscription_id'],
            ['__count'],
        )
        counts = {subscription.id: count for subscription, count in grouped}
        for order in self:
            order.dunning_attempt_count = counts.get(order.id, 0)

    def action_view_subscription_dunning_attempts(self):
        self.ensure_one()
        return {
            'name': _('Dunning Attempts'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.dunning.attempt',
            'view_mode': 'list,form',
            'domain': [('subscription_id', '=', self.id)],
            'context': {'default_subscription_id': self.id},
        }

    def _auto_collect_payment(self, invoice, source='cron', requested_by=None):
        # Override to trigger dunning on failure or resolve on success
        tx = super()._auto_collect_payment(invoice, source=source, requested_by=requested_by)
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

    def _get_dunning_recovery_url(self):
        self.ensure_one()
        return '%s/my/subscription/%s' % (self.get_base_url(), self.id)

    def _get_dunning_recovery_invoice(self):
        self.ensure_one()
        if hasattr(self, '_get_portal_payment_recovery_invoice'):
            return self._get_portal_payment_recovery_invoice()
        return self.env['account.move'].sudo().search([
            ('subscription_id', '=', self.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial']),
        ], order='invoice_date_due asc, invoice_date asc, id asc', limit=1)

    def _prepare_dunning_attempt_values(self, policy, step=False, invoice=False, action_type=False):
        self.ensure_one()
        today = fields.Date.today()
        days_since_start = (today - self.dunning_start_date).days if self.dunning_start_date else 0
        action_type = action_type or (step.action_type if step else 'final_none')
        return {
            'subscription_id': self.id,
            'invoice_id': invoice.id if invoice else False,
            'policy_id': policy.id if policy else False,
            'policy_line_id': step.id if step else False,
            'email_template_id': step.email_template_id.id if step and step.email_template_id else False,
            'action_type': action_type,
            'days_since_start': days_since_start,
            'amount_at_risk': invoice.amount_residual if invoice else 0.0,
            'recovery_url': self._get_dunning_recovery_url(),
            'state': 'pending',
            'auto_retry_enabled': bool(
                step
                and step.action_type == 'email_and_retry'
                and step.max_auto_retries
                and invoice
                and self.payment_token_id
            ),
            'max_auto_retries': step.max_auto_retries if step and step.action_type == 'email_and_retry' else 0,
            'next_auto_retry_at': (
                fields.Datetime.add(fields.Datetime.now(), hours=step.retry_delay_hours)
                if step
                and step.action_type == 'email_and_retry'
                and step.max_auto_retries
                and invoice
                and self.payment_token_id
                else False
            ),
        }

    def _create_dunning_attempt(self, policy, step=False, invoice=False, action_type=False):
        return self.env['subscription.dunning.attempt'].create(
            self._prepare_dunning_attempt_values(policy, step=step, invoice=invoice, action_type=action_type)
        )

    def _execute_dunning_step(self, policy, step):
        self.ensure_one()
        invoice = self._get_dunning_recovery_invoice()
        attempt = self._create_dunning_attempt(policy, step=step, invoice=invoice)
        try:
            mail_id = False
            if step.email_template_id:
                force_send = not self.env.context.get('subscription_suite_benchmark_queue_dunning_mail')
                mail_id = step.email_template_id.with_context(
                    dunning_recovery_url=attempt.recovery_url,
                    dunning_attempt_id=attempt.id,
                ).send_mail(self.id, force_send=force_send)
                attempt.write({'mail_mail_id': mail_id or False, 'state': 'sent'})

            values = {
                'state': 'done',
                'completed_at': fields.Datetime.now(),
                'note': _('Dunning step executed.'),
            }
            if attempt.auto_retry_enabled:
                values['note'] = _('Dunning step executed. Automatic payment retry scheduled.')
            attempt.write(values)
            self._log_subscription_event('dunning_step', _('Sent dunning email (Step: %s days)') % step.delay_days)
        except Exception as error:
            attempt.mark_failed(error)
            _logger.exception('Failed to execute dunning step for subscription %s', self.name)
        return attempt

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
        batch_size = int(self.env['ir.config_parameter'].sudo().get_param('subscription_suite.dunning_batch_size', 100))
        subscriptions = self.search([
            ('is_subscription', '=', True),
            ('subscription_state', '=', 'past_due'),
            ('next_dunning_date', '<=', today),
            ('subscription_plan_id.dunning_policy_id', '!=', False)
        ], limit=batch_size, order='next_dunning_date asc, id asc')
        
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
                attempt = sub._execute_dunning_step(policy, next_step)
                if attempt.state == 'failed':
                    continue
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
        existing_attempt = self.env['subscription.dunning.attempt'].search([
            ('subscription_id', '=', self.id),
            ('policy_id', '=', policy.id),
            ('action_type', '=', 'final_%s' % policy.final_action),
            ('state', '!=', 'failed'),
        ], limit=1)
        if existing_attempt:
            self.next_dunning_date = False
            return existing_attempt

        invoice = self._get_dunning_recovery_invoice()
        attempt = self._create_dunning_attempt(
            policy,
            invoice=invoice,
            action_type='final_%s' % policy.final_action,
        )
        try:
            if policy.final_action == 'cancel':
                self._action_cancel(feedback="Automated cancellation due to failed dunning")
                attempt.mark_done(_('Automated cancellation due to failed dunning.'))
            elif policy.final_action == 'pause':
                self.subscription_state = 'paused'
                self.pause_date = fields.Date.today()
                self._log_subscription_event('paused', 'Automated pause due to failed dunning')
                attempt.mark_done(_('Automated pause due to failed dunning.'))
            else:
                attempt.mark_done(_('No final action configured.'), state='skipped')
        except Exception as error:
            attempt.mark_failed(error)
            _logger.exception('Failed to execute final dunning action for subscription %s', self.name)
            raise
        
        self.next_dunning_date = False
        return attempt
