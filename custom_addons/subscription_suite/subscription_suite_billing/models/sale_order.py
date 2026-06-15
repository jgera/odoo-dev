import logging
from odoo import models, fields, api, _
from odoo.addons.payment import utils as payment_utils
from odoo.exceptions import UserError, ValidationError
from odoo.tools import consteq
from odoo.tools.float_utils import float_compare

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    proration_ids = fields.One2many('subscription.proration', 'subscription_id', string='Prorations')
    proration_count = fields.Integer(string='Proration Count', compute='_compute_proration_count')
    billing_attempt_ids = fields.One2many('subscription.billing.attempt', 'subscription_id', string='Billing Attempts')
    billing_attempt_count = fields.Integer(string='Billing Attempt Count', compute='_compute_billing_attempt_count')
    payment_attempt_ids = fields.One2many('subscription.payment.attempt', 'subscription_id', string='Payment Attempts')
    payment_attempt_count = fields.Integer(string='Payment Attempt Count', compute='_compute_payment_attempt_count')
    billing_in_progress = fields.Boolean(string='Billing in Progress', copy=False, index=True, readonly=True)
    billing_locked_at = fields.Datetime(string='Billing Locked At', copy=False, readonly=True)
    billing_locked_by_run_id = fields.Many2one('subscription.billing.run', string='Billing Locked by Run', copy=False, readonly=True)
    setup_fee_invoice_id = fields.Many2one('account.move', string='Setup Fee Invoice')
    pending_plan_change_id = fields.Many2one('subscription.plan', string='Pending Plan Change', copy=False)
    pending_plan_change_date = fields.Date(string='Pending Plan Change Date', copy=False, index=True)
    pending_plan_change_type = fields.Selection([
        ('upgrade', 'Upgrade'),
        ('downgrade', 'Downgrade'),
    ], string='Pending Plan Change Type', copy=False)
    plan_change_request_count = fields.Integer(
        string='Plan Change Requests',
        compute='_compute_plan_change_request_count',
    )

    def _compute_proration_count(self):
        for record in self:
            record.proration_count = len(record.proration_ids)

    def _compute_billing_attempt_count(self):
        for record in self:
            record.billing_attempt_count = len(record.billing_attempt_ids)

    def _compute_payment_attempt_count(self):
        for record in self:
            record.payment_attempt_count = len(record.payment_attempt_ids)

    def _compute_plan_change_request_count(self):
        grouped = self.env['subscription.plan.change.request']._read_group(
            [('subscription_id', 'in', self.ids)],
            ['subscription_id'],
            ['__count'],
        )
        counts = {subscription.id: count for subscription, count in grouped}
        for record in self:
            record.plan_change_request_count = counts.get(record.id, 0)

    def action_change_plan(self):
        self.ensure_one()
        return {
            'name': _('Change Subscription Plan'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.change.plan.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_subscription_id': self.id,
                'default_current_plan_id': self.subscription_plan_id.id,
            },
        }

    def action_change_seats(self):
        self.ensure_one()
        self._check_seat_change_allowed()
        return {
            'name': _('Change Seats'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.change.seats.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_subscription_id': self.id,
                'default_current_seat_quantity': self.seat_quantity,
                'default_new_seat_quantity': self.seat_quantity,
            },
        }

    def action_view_billing_attempts(self):
        self.ensure_one()
        return {
            'name': _('Billing Attempts'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.billing.attempt',
            'view_mode': 'list,form',
            'domain': [('subscription_id', '=', self.id)],
            'context': {'default_subscription_id': self.id},
        }

    def action_view_payment_attempts(self):
        self.ensure_one()
        return {
            'name': _('Payment Attempts'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.payment.attempt',
            'view_mode': 'list,form',
            'domain': [('subscription_id', '=', self.id)],
            'context': {'default_subscription_id': self.id},
        }

    def action_view_subscription_plan_change_requests(self):
        self.ensure_one()
        return {
            'name': _('Plan Change Requests'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.plan.change.request',
            'view_mode': 'list,form,activity',
            'domain': [('subscription_id', '=', self.id)],
            'context': {'default_subscription_id': self.id},
        }

    def _get_billing_period(self):
        self.ensure_one()
        period_end = self.next_invoice_date or fields.Date.today()
        period_start = self.last_invoice_date or self.subscription_start_date or period_end
        return period_start, period_end

    def _get_billing_idempotency_key(self, period_start, period_end):
        self.ensure_one()
        return '%s:%s:%s' % (self.id, period_start, period_end)

    def _get_or_create_billing_attempt(self, run=None):
        self.ensure_one()
        period_start, period_end = self._get_billing_period()
        idempotency_key = self._get_billing_idempotency_key(period_start, period_end)
        Attempt = self.env['subscription.billing.attempt']
        attempt = Attempt.search([('idempotency_key', '=', idempotency_key)], limit=1)
        if attempt:
            return attempt

        previous_attempts = Attempt.search_count([
            ('subscription_id', '=', self.id),
            ('period_end', '=', period_end),
        ])
        sequence = self.env['ir.sequence'].next_by_code('subscription.billing.attempt') or _('New')
        return Attempt.create({
            'name': sequence,
            'run_id': run.id if run else False,
            'subscription_id': self.id,
            'period_start': period_start,
            'period_end': period_end,
            'attempt_no': previous_attempts + 1,
            'idempotency_key': idempotency_key,
            'state': 'pending',
        })

    @api.model
    def _cron_generate_subscription_invoices(self):
        today = fields.Date.today()
        subscriptions = self.search([
            ('is_subscription', '=', True),
            ('subscription_state', '=', 'active'),
            ('state', 'in', ['sale', 'done']),
            ('next_invoice_date', '<=', today),
            ('billing_in_progress', '=', False),
        ])

        run = self.env['subscription.billing.run'].create({
            'name': self.env['ir.sequence'].next_by_code('subscription.billing.run') or _('New'),
            'run_date': today,
            'state': 'running',
            'subscription_count': len(subscriptions),
        })

        batch_size = int(self.env['ir.config_parameter'].sudo().get_param('subscription_suite.batch_size', 50))
        for i in range(0, len(subscriptions), batch_size):
            batch = subscriptions[i:i + batch_size]
            for sub in batch:
                sub.write({
                    'billing_in_progress': True,
                    'billing_locked_at': fields.Datetime.now(),
                    'billing_locked_by_run_id': run.id,
                })
                try:
                    with self.env.cr.savepoint():
                        sub._generate_subscription_invoice(billing_run=run)
                except Exception as e:
                    _logger.exception('Failed to generate invoice for subscription %s', sub.subscription_code or sub.name)
                    attempt = sub._get_or_create_billing_attempt(run=run)
                    attempt._record_failure_once(e)
                finally:
                    sub.write({
                        'billing_in_progress': False,
                        'billing_locked_at': False,
                        'billing_locked_by_run_id': False,
                    })

        run._finalize_from_attempts()
        return run

    def _generate_subscription_invoice(self, billing_run=None):
        self.ensure_one()
        if self.pending_plan_change_id and self.pending_plan_change_date and self.pending_plan_change_date <= fields.Date.today():
            self._apply_pending_plan_change()

        attempt = self._get_or_create_billing_attempt(run=billing_run)
        if billing_run and not attempt.run_id:
            attempt.run_id = billing_run.id

        if attempt.state == 'success' and attempt.invoice_id:
            return attempt.invoice_id
        if attempt.state == 'failed':
            attempt.write({
                'state': 'pending',
                'error_message': False,
                'attempt_date': fields.Datetime.now(),
                'failure_category': False,
                'retryable': False,
                'retry_exhausted': False,
                'recovery_required': False,
                'recovery_note': False,
                'next_retry_at': False,
            })

        invoiceable_lines = self.order_line.filtered(
            lambda line: not line.display_type
            and float_compare(
                line.qty_to_invoice,
                0.0,
                precision_rounding=(line.product_uom_id or line.product_id.uom_id).rounding or 0.01,
            ) > 0
        )
        if not invoiceable_lines:
            attempt.write({
                'state': 'skipped',
                'error_message': _('No invoiceable subscription lines were available.'),
            })
            return False

        try:
            invoice = super()._generate_subscription_invoice()
        except Exception as e:
            attempt._record_failure(e)
            raise

        if invoice:
            period_start = attempt.period_start
            period_end = attempt.period_end
            invoice.write({
                'subscription_period_start': period_start,
                'subscription_period_end': period_end,
            })
            attempt.write({
                'state': 'success',
                'invoice_id': invoice.id,
                'amount': invoice.amount_total,
                'error_message': False,
                'failure_category': False,
                'retryable': False,
                'retry_exhausted': False,
                'recovery_required': False,
                'recovery_note': False,
                'next_retry_at': False,
            })
        else:
            attempt.write({
                'state': 'skipped',
                'error_message': _('No invoice was generated.'),
            })
        return invoice

    def _execute_plan_change(self, new_plan, effective_date=None):
        self.ensure_one()
        effective_date = effective_date or fields.Date.today()
        
        # Calculate daily rates
        old_plan = self.subscription_plan_id
        old_mrr = self.mrr
        self._check_plan_change_allowed(old_plan, new_plan, old_mrr, effective_date=effective_date)
        if self._plan_change_requires_approval(old_plan, new_plan, old_mrr=old_mrr):
            raise ValidationError(_("This plan change requires manager approval. Use the Change Plan wizard to request approval."))
        self._clear_pending_plan_change()
        period_start = self.current_period_start or self.subscription_start_date
        period_end = self.current_period_end or self.next_invoice_date
        if not period_start or not period_end:
            period_start = effective_date
            period_end = new_plan.get_next_invoice_date(effective_date)
        
        new_mrr = new_plan._get_plan_mrr()
        old_daily_rate = old_mrr / 30
        new_daily_rate = new_mrr / 30
        
        change_type = self._get_plan_change_type(new_plan, old_mrr=old_mrr)
        
        proration = self.env['subscription.proration'].create({
            'subscription_id': self.id,
            'change_type': change_type,
            'change_date': effective_date,
            'old_plan_id': old_plan.id,
            'new_plan_id': new_plan.id,
            'period_start': period_start,
            'period_end': period_end,
            'old_daily_rate': old_daily_rate,
            'new_daily_rate': new_daily_rate,
        })
        
        proration.action_apply_proration()

        self._apply_subscription_plan(new_plan)
        new_mrr = self.mrr
        movement_type = self._get_mrr_movement_type(old_mrr, new_mrr)
        self._log_mrr_movement(
            movement_type,
            old_mrr,
            new_mrr,
            _('MRR %s from plan change: %s to %s') % (
                'expansion' if movement_type == 'expansion' else 'contraction',
                old_plan.display_name,
                new_plan.display_name,
            ),
            movement_date=effective_date,
        )
        return proration

    def _get_plan_change_type(self, new_plan, old_mrr=None):
        self.ensure_one()
        old_mrr = old_mrr if old_mrr is not None else self.mrr
        new_mrr = new_plan._get_plan_mrr()
        return 'upgrade' if self._compare_mrr(new_mrr, old_mrr) > 0 else 'downgrade'

    def _get_single_seat_line(self):
        self.ensure_one()
        seat_lines = self.order_line.filtered(
            lambda line: line.is_recurring
            and line.subscription_component_type == 'seat'
            and not line.display_type
        )
        if not seat_lines:
            raise ValidationError(_("Add one recurring seat line before changing seats."))
        if len(seat_lines) > 1:
            raise ValidationError(_("Seat changes require exactly one recurring seat line."))
        return seat_lines

    def _check_seat_change_allowed(self, new_quantity=None):
        self.ensure_one()
        if not self.is_subscription:
            raise ValidationError(_("Only subscriptions can change seats."))
        if self.state not in ('sale', 'done'):
            raise ValidationError(_("Confirm the subscription before changing seats."))
        if self.subscription_state not in ('active', 'paused', 'past_due'):
            raise ValidationError(_("Seats can only be changed on active, paused, or past-due subscriptions."))
        seat_line = self._get_single_seat_line()
        if new_quantity is not None:
            line_uom = seat_line.product_uom_id or seat_line.product_id.uom_id
            precision_rounding = line_uom.rounding or 0.01
            if float_compare(new_quantity, 1.0, precision_rounding=precision_rounding) < 0:
                raise ValidationError(_("Seat quantity must be at least 1."))
            if float_compare(
                new_quantity,
                seat_line.product_uom_qty,
                precision_rounding=precision_rounding,
            ) == 0:
                raise ValidationError(_("The new seat quantity must be different from the current quantity."))
        return seat_line

    def _monthly_equivalent_amount(self, amount):
        self.ensure_one()
        count = self.billing_interval_count or 1
        unit = self.billing_interval_unit
        if unit == 'day':
            return (amount / count) * 30
        if unit == 'week':
            return (amount / count) * 4.33
        if unit == 'month':
            return amount / count
        if unit == 'year':
            return amount / (12 * count)
        return 0.0

    def _get_mrr_after_seat_change(self, seat_line, new_quantity):
        self.ensure_one()
        new_seat_subtotal = new_quantity * seat_line.price_unit * (1 - (seat_line.discount or 0.0) / 100.0)
        new_recurring_total = self.recurring_total - seat_line.price_subtotal + new_seat_subtotal
        return self._monthly_equivalent_amount(new_recurring_total)

    def _execute_seat_change(self, new_quantity, effective_date=None):
        self.ensure_one()
        effective_date = effective_date or fields.Date.today()
        seat_line = self._check_seat_change_allowed(new_quantity=new_quantity)

        old_quantity = seat_line.product_uom_qty
        old_mrr = self.mrr
        new_mrr = self._get_mrr_after_seat_change(seat_line, new_quantity)
        period_start = self.current_period_start or self.last_invoice_date or self.subscription_start_date or effective_date
        period_end = self.current_period_end or self.next_invoice_date or self.subscription_plan_id.get_next_invoice_date(period_start)
        if effective_date < period_start:
            effective_date = period_start

        proration = self.env['subscription.proration'].create({
            'subscription_id': self.id,
            'proration_scope': 'seat_change',
            'change_type': 'upgrade' if self._compare_mrr(new_mrr, old_mrr) > 0 else 'downgrade',
            'change_date': effective_date,
            'old_plan_id': self.subscription_plan_id.id,
            'new_plan_id': self.subscription_plan_id.id,
            'old_seat_quantity': old_quantity,
            'new_seat_quantity': new_quantity,
            'period_start': period_start,
            'period_end': period_end,
            'old_daily_rate': old_mrr / 30.0,
            'new_daily_rate': new_mrr / 30.0,
        })

        seat_line.write({'product_uom_qty': new_quantity})
        self.invalidate_recordset(['seat_quantity', 'recurring_total', 'mrr'])
        proration.action_apply_proration()
        movement_type = self._get_mrr_movement_type(old_mrr, new_mrr)
        self._log_subscription_event(
            'plan_changed',
            _('Seats changed from %(old_qty)s to %(new_qty)s', old_qty=old_quantity, new_qty=new_quantity),
            old_values={'seats': old_quantity, 'mrr': old_mrr},
            new_values={'seats': new_quantity, 'mrr': new_mrr, 'effective_date': effective_date},
        )
        self._log_mrr_movement(
            movement_type,
            old_mrr,
            new_mrr,
            _('MRR %s from seat change: %s to %s seats') % (
                'expansion' if movement_type == 'expansion' else 'contraction',
                old_quantity,
                new_quantity,
            ),
            movement_date=effective_date,
        )
        return proration

    def _plan_change_requires_approval(self, old_plan, new_plan, old_mrr=None):
        self.ensure_one()
        if self.env.context.get('bypass_plan_change_approval'):
            return False
        if not old_plan or not new_plan or old_plan == new_plan:
            return False

        change_type = self._get_plan_change_type(new_plan, old_mrr=old_mrr)
        plan_policy_requires_approval = (
            (change_type == 'upgrade' and old_plan.approval_required_for_upgrade)
            or (change_type == 'downgrade' and old_plan.approval_required_for_downgrade)
        )
        if plan_policy_requires_approval:
            return True
        return not self.env.user.has_group('subscription_suite.group_subscription_manager')

    def _request_plan_change_approval(self, new_plan, effective_date=None, change_timing='immediate'):
        self.ensure_one()
        new_plan.ensure_one()
        effective_date = effective_date or self.next_invoice_date or fields.Date.today()
        old_plan = self.subscription_plan_id
        old_mrr = self.mrr
        self._check_plan_change_allowed(old_plan, new_plan, old_mrr, effective_date=effective_date)
        if not self._plan_change_requires_approval(old_plan, new_plan, old_mrr=old_mrr):
            return False

        existing_request = self.env['subscription.plan.change.request'].search([
            ('subscription_id', '=', self.id),
            ('state', '=', 'pending'),
        ], limit=1)
        if existing_request:
            raise ValidationError(_("This subscription already has a pending plan change request."))

        change_type = self._get_plan_change_type(new_plan, old_mrr=old_mrr)
        request = self.env['subscription.plan.change.request'].create({
            'subscription_id': self.id,
            'current_plan_id': old_plan.id,
            'requested_plan_id': new_plan.id,
            'requested_effective_date': effective_date,
            'requested_timing': change_timing,
            'change_type': change_type,
            'old_mrr': old_mrr,
            'new_mrr': new_plan._get_plan_mrr(),
        })
        self.sudo()._log_subscription_event(
            'plan_changed',
            _('Plan change request %(request)s created for %(plan)s', request=request.name, plan=new_plan.display_name),
            old_values={'plan': old_plan.display_name, 'mrr': old_mrr},
            new_values={
                'request_id': request.id,
                'plan': new_plan.display_name,
                'effective_date': effective_date,
                'timing': change_timing,
                'change_type': change_type,
            },
        )
        return request

    def _get_portal_plan_change_options(self):
        self.ensure_one()
        current_plan = self.subscription_plan_id
        if not current_plan:
            return self.env['subscription.plan'].browse()

        plans = current_plan.upgrade_plan_ids | current_plan.downgrade_plan_ids
        return plans.filtered(
            lambda plan: plan.active
            and plan != current_plan
            and (not plan.company_id or plan.company_id == self.company_id)
        )

    def _portal_request_plan_change(self, new_plan, requester):
        self.ensure_one()
        new_plan.ensure_one()
        requester.ensure_one()

        if not self.is_subscription:
            raise ValidationError(_("Only subscriptions can request plan changes."))
        if self.subscription_state != 'active':
            raise ValidationError(_("Only active subscriptions can request plan changes."))
        if self.pending_plan_change_id:
            raise ValidationError(_("This subscription already has a scheduled plan change."))
        if self.pending_cancellation:
            raise ValidationError(_("This subscription already has a scheduled cancellation."))
        if not self.next_invoice_date:
            raise ValidationError(_("A next invoice date is required before requesting a portal plan change."))
        if new_plan not in self._get_portal_plan_change_options():
            raise ValidationError(_("Select an allowed plan change option."))

        pending_lifecycle_request = self.env['subscription.lifecycle.request'].search([
            ('subscription_id', '=', self.id),
            ('state', '=', 'pending'),
        ], limit=1)
        if pending_lifecycle_request:
            raise ValidationError(_("This subscription already has a pending lifecycle request."))

        pending_cancellation_request = self.env['subscription.cancellation.request'].search([
            ('subscription_id', '=', self.id),
            ('state', '=', 'pending'),
        ], limit=1)
        if pending_cancellation_request:
            raise ValidationError(_("This subscription already has a pending cancellation request."))

        existing_request = self.env['subscription.plan.change.request'].search([
            ('subscription_id', '=', self.id),
            ('state', '=', 'pending'),
        ], limit=1)
        if existing_request:
            raise ValidationError(_("This subscription already has a pending plan change request."))

        old_plan = self.subscription_plan_id
        old_mrr = self.mrr
        effective_date = self.next_invoice_date
        self._check_plan_change_allowed(
            old_plan,
            new_plan,
            old_mrr,
            effective_date=effective_date,
        )
        change_type = self._get_plan_change_type(new_plan, old_mrr=old_mrr)
        plan_request = self.env['subscription.plan.change.request'].create({
            'subscription_id': self.id,
            'current_plan_id': old_plan.id,
            'requested_plan_id': new_plan.id,
            'requested_effective_date': effective_date,
            'requested_timing': 'next_period',
            'change_type': change_type,
            'requested_by_id': requester.id,
            'old_mrr': old_mrr,
            'new_mrr': new_plan._get_plan_mrr(),
        })
        self.sudo()._log_subscription_event(
            'plan_changed',
            _('Portal plan change request %(request)s created for %(plan)s', request=plan_request.name, plan=new_plan.display_name),
            old_values={'plan': old_plan.display_name, 'mrr': old_mrr},
            new_values={
                'request_id': plan_request.id,
                'plan': new_plan.display_name,
                'effective_date': effective_date,
                'timing': 'next_period',
                'change_type': change_type,
                'requested_by': requester.display_name,
            },
        )
        return plan_request

    def _clear_pending_plan_change(self):
        self.write({
            'pending_plan_change_id': False,
            'pending_plan_change_date': False,
            'pending_plan_change_type': False,
        })

    def action_cancel_pending_plan_change(self):
        for subscription in self:
            if not subscription.pending_plan_change_id:
                continue
            old_values = {
                'pending_plan_change_id': subscription.pending_plan_change_id.display_name,
                'pending_plan_change_date': subscription.pending_plan_change_date,
                'pending_plan_change_type': subscription.pending_plan_change_type,
            }
            subscription._clear_pending_plan_change()
            subscription._log_subscription_event(
                'plan_changed',
                _('Scheduled plan change cancelled'),
                old_values=old_values,
            )

    def _schedule_plan_change(self, new_plan, effective_date=None):
        self.ensure_one()
        new_plan.ensure_one()
        if not self.is_subscription:
            raise ValidationError(_("Only subscriptions can schedule plan changes."))
        if self.subscription_state != 'active':
            raise ValidationError(_("Only active subscriptions can schedule plan changes."))
        if new_plan == self.subscription_plan_id:
            raise ValidationError(_("The new plan must be different from the current plan."))

        effective_date = effective_date or self.next_invoice_date
        if not effective_date:
            raise ValidationError(_("Set a next invoice date before scheduling a next-period plan change."))

        old_mrr = self.mrr
        self._check_plan_change_allowed(
            self.subscription_plan_id,
            new_plan,
            old_mrr,
            effective_date=effective_date,
        )
        if self._plan_change_requires_approval(self.subscription_plan_id, new_plan, old_mrr=old_mrr):
            raise ValidationError(_("This plan change requires manager approval. Use the Change Plan wizard to request approval."))
        change_type = self._get_plan_change_type(new_plan, old_mrr=old_mrr)
        self.write({
            'pending_plan_change_id': new_plan.id,
            'pending_plan_change_date': effective_date,
            'pending_plan_change_type': change_type,
        })
        self._log_subscription_event(
            'plan_changed',
            _('Plan change to %(plan)s scheduled for %(date)s', plan=new_plan.display_name, date=effective_date),
            old_values={'plan': self.subscription_plan_id.display_name, 'mrr': old_mrr},
            new_values={'plan': new_plan.display_name, 'effective_date': effective_date, 'change_type': change_type},
        )
        return True

    def _apply_pending_plan_change(self):
        self.ensure_one()
        new_plan = self.pending_plan_change_id
        if not new_plan:
            return False

        effective_date = self.pending_plan_change_date or fields.Date.today()
        old_plan = self.subscription_plan_id
        old_mrr = self.mrr
        self._check_plan_change_allowed(old_plan, new_plan, old_mrr, effective_date=effective_date)
        self._apply_subscription_plan(new_plan)
        self.invalidate_recordset(['recurring_total', 'mrr'])
        new_mrr = self.mrr
        change_type = self._get_mrr_movement_type(old_mrr, new_mrr)
        self._clear_pending_plan_change()
        self._log_subscription_event(
            'plan_changed',
            _('Scheduled plan change applied from %(old_plan)s to %(new_plan)s', old_plan=old_plan.display_name, new_plan=new_plan.display_name),
            old_values={'plan': old_plan.display_name, 'mrr': old_mrr},
            new_values={'plan': new_plan.display_name, 'mrr': new_mrr, 'effective_date': effective_date},
        )
        self._log_mrr_movement(
            change_type,
            old_mrr,
            new_mrr,
            _('MRR %s from scheduled plan change: %s to %s') % (
                'expansion' if change_type == 'expansion' else 'contraction',
                old_plan.display_name,
                new_plan.display_name,
            ),
            movement_date=effective_date,
        )
        return True

    def _check_plan_change_allowed(self, old_plan, new_plan, old_mrr=None, effective_date=None):
        self.ensure_one()
        if not old_plan or not new_plan or old_plan == new_plan:
            return True

        old_mrr = old_mrr if old_mrr is not None else self.mrr
        new_mrr = new_plan._get_plan_mrr()
        comparison = self._compare_mrr(new_mrr, old_mrr)
        if comparison > 0 and old_plan.upgrade_plan_ids and new_plan not in old_plan.upgrade_plan_ids:
            raise ValidationError(
                _("Plan %(new_plan)s is not an allowed upgrade path from %(old_plan)s.") % {
                    'new_plan': new_plan.display_name,
                    'old_plan': old_plan.display_name,
                }
            )
        if comparison < 0 and old_plan.downgrade_plan_ids and new_plan not in old_plan.downgrade_plan_ids:
            raise ValidationError(
                _("Plan %(new_plan)s is not an allowed downgrade path from %(old_plan)s.") % {
                    'new_plan': new_plan.display_name,
                    'old_plan': old_plan.display_name,
                }
            )
        if comparison < 0:
            self._check_minimum_commitment(_('Downgrade'), effective_date=effective_date or fields.Date.today())
        return True

    def _create_upsell_proration(self, subscription, old_mrr, new_mrr):
        self.ensure_one()
        if not subscription.subscription_plan_id or subscription._compare_mrr(new_mrr, old_mrr) == 0:
            return False

        effective_date = self.subscription_quote_effective_date or fields.Date.today()
        period_start = subscription.current_period_start or subscription.last_invoice_date or subscription.subscription_start_date
        period_end = subscription.current_period_end or subscription.next_invoice_date
        if not period_start or not period_end or effective_date >= period_end:
            return False
        if effective_date < period_start:
            effective_date = period_start

        proration = self.env['subscription.proration'].create({
            'subscription_id': subscription.id,
            'change_type': 'upgrade' if subscription._compare_mrr(new_mrr, old_mrr) > 0 else 'downgrade',
            'change_date': effective_date,
            'old_plan_id': subscription.subscription_plan_id.id,
            'new_plan_id': subscription.subscription_plan_id.id,
            'period_start': period_start,
            'period_end': period_end,
            'old_daily_rate': old_mrr / 30.0,
            'new_daily_rate': new_mrr / 30.0,
        })
        proration.action_apply_proration()
        return proration

    def _apply_subscription_plan(self, plan):
        self.ensure_one()
        plan.ensure_one()

        recurring_lines = self.order_line.filtered('is_recurring')
        if self.state in ('sale', 'done'):
            recurring_lines.write({'product_uom_qty': 0.0})
        else:
            recurring_lines.unlink()

        order_lines = []
        for plan_line in plan.plan_line_ids:
            order_lines.append((0, 0, {
                'product_id': plan_line.product_id.id,
                'name': plan_line.description or plan_line.product_id.get_product_multiline_description_sale(),
                'product_uom_qty': plan_line.quantity,
                'price_unit': plan_line.price_unit,
                'discount': plan_line.discount,
                'is_recurring': True,
                'subscription_component_type': plan_line.subscription_component_type,
                'recurring_interval_count': plan.billing_interval_count,
                'recurring_interval_unit': plan.billing_interval_unit,
            }))

        self.write({
            'subscription_plan_id': plan.id,
            'billing_interval_count': plan.billing_interval_count,
            'billing_interval_unit': plan.billing_interval_unit,
            'order_line': order_lines,
        })

    def _get_payment_collection_token(self, invoice):
        self.ensure_one()
        primary_token = self.payment_token_id
        if not primary_token:
            return self.env['payment.token'], 'primary'
        if not invoice:
            return primary_token, 'primary'
        invoice.ensure_one()

        backup_token = self.backup_payment_token_id
        if not backup_token or not backup_token.active:
            return primary_token, 'primary'

        latest_attempt = self.env['subscription.payment.attempt'].sudo().search([
            ('subscription_id', '=', self.id),
            ('invoice_id', '=', invoice.id),
            ('state', 'in', ['failed', 'cancelled', 'error']),
        ], limit=1, order='attempt_date desc, id desc')
        latest_used_primary = (
            latest_attempt
            and latest_attempt.token_id == primary_token
            and latest_attempt.token_role in (False, 'primary')
        )
        if latest_used_primary:
            return backup_token, 'backup'
        return primary_token, 'primary'

    def _auto_collect_payment(self, invoice, source='cron', requested_by=None):
        self.ensure_one()
        token, token_role = self._get_payment_collection_token(invoice)
        if not token:
            return False

        payment_attempt = self.env['subscription.payment.attempt']._create_for_invoice(
            self,
            invoice,
            source=source,
            requested_by=requested_by,
            token=token,
            token_role=token_role,
        )
        try:
            amount = invoice.amount_residual
            if invoice.currency_id.is_zero(amount):
                amount = invoice.amount_total
            tx = self.env['payment.transaction'].create({
                'provider_id': token.provider_id.id,
                'token_id': token.id,
                'payment_method_id': token.payment_method_id.id,
                'operation': 'online_token',
                'amount': amount,
                'currency_id': invoice.currency_id.id,
                'partner_id': invoice.partner_id.id,
                'reference': invoice.name,
            })
            tx._send_payment_request()
        except Exception as error:
            payment_attempt._record_exception(error)
            self._log_subscription_event('payment_failed', _('Auto-payment failed for %s') % invoice.name)
            raise

        payment_state = payment_attempt._finalize_from_transaction(tx)
        if payment_state == 'success':
            self._log_subscription_event('payment_success', _('Auto-payment collected for %s') % invoice.name)
        elif payment_state == 'pending':
            self._log_subscription_event('payment_pending', _('Auto-payment is pending provider confirmation for %s') % invoice.name)
        else:
            self._log_subscription_event('payment_failed', _('Auto-payment failed for %s') % invoice.name)

        return tx

    def _get_payment_recovery_invoices(self):
        self.ensure_one()
        return self.env['account.move'].sudo().search([
            ('subscription_id', '=', self.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial']),
        ], order='invoice_date_due asc, invoice_date asc, id asc')

    def _get_portal_payment_recovery_invoice(self):
        self.ensure_one()
        return self._get_payment_recovery_invoices()[:1]

    def _get_latest_portal_payment_attempt(self, invoice):
        self.ensure_one()
        invoice.ensure_one()
        attempt = self.env['subscription.payment.attempt'].sudo().search([
            ('subscription_id', '=', self.id),
            ('invoice_id', '=', invoice.id),
            ('source', '=', 'portal'),
        ], limit=1, order='attempt_date desc, id desc')
        if attempt and attempt.state == 'pending' and attempt.transaction_id:
            attempt._sync_from_transaction()
        return attempt

    def _get_portal_payment_recovery_context(self):
        self.ensure_one()
        invoice = self._get_portal_payment_recovery_invoice()
        has_saved_method = bool(self.payment_token_id)
        if not invoice:
            return {
                'invoice': invoice,
                'state': 'clear',
                'has_saved_method': has_saved_method,
                'can_retry': False,
                'message': _('No payment recovery action is needed.'),
                'next_action': False,
                'payment_attempt': self.env['subscription.payment.attempt'],
            }

        payment_attempt = self._get_latest_portal_payment_attempt(invoice)
        if payment_attempt and payment_attempt.state == 'pending':
            return {
                'invoice': invoice,
                'state': 'retry_pending',
                'has_saved_method': has_saved_method,
                'can_retry': False,
                'message': _('Payment retry was submitted and is waiting for provider confirmation.'),
                'next_action': _('Open the invoice to check current payment status.'),
                'payment_attempt': payment_attempt,
            }
        if payment_attempt and payment_attempt.state in ('failed', 'cancelled', 'error') and has_saved_method:
            return {
                'invoice': invoice,
                'state': 'retry_failed',
                'has_saved_method': has_saved_method,
                'can_retry': True,
                'message': _('The last payment retry failed.'),
                'next_action': _('Retry the saved payment method or open the invoice to pay another way.'),
                'payment_attempt': payment_attempt,
            }

        if has_saved_method:
            state = 'retry_available'
            message = _('A saved payment method is available for this subscription.')
            next_action = _('Open the invoice or retry the saved payment method.')
        else:
            state = 'missing_payment_method'
            message = _('No saved payment method is assigned to this subscription.')
            next_action = _('Open the invoice to pay now, or add a saved payment method before retrying.')

        return {
            'invoice': invoice,
            'state': state,
            'has_saved_method': has_saved_method,
            'can_retry': bool(has_saved_method),
            'message': message,
            'next_action': next_action,
            'payment_attempt': payment_attempt,
        }

    def _get_portal_available_payment_tokens(self, requester_partner):
        self.ensure_one()
        requester_partner.ensure_one()
        commercial_partner = requester_partner.commercial_partner_id
        return self.env['payment.token'].sudo()._get_available_tokens(
            None,
            requester_partner.id,
            is_validation=True,
        ).filtered(
            lambda token: token.active
            and token.partner_id.commercial_partner_id == commercial_partner
        )

    def _portal_assign_payment_token(self, token, requester):
        self.ensure_one()
        token.ensure_one()
        requester.ensure_one()

        requester_partner = requester.partner_id.commercial_partner_id
        subscription_partner = self.partner_id.commercial_partner_id
        token_partner = token.partner_id.commercial_partner_id

        if not self.is_subscription:
            raise ValidationError(_('Only subscriptions can update payment methods.'))
        if requester_partner != subscription_partner:
            raise ValidationError(_('You can only update payment methods for your own subscription.'))
        if not token.active:
            raise ValidationError(_('Select an active saved payment method.'))
        if token_partner != subscription_partner:
            raise ValidationError(_('Select a payment method owned by this customer.'))

        old_token = self.payment_token_id
        self.payment_token_id = token.id
        self.sudo()._log_subscription_event(
            'payment_method_updated',
            _('Portal payment method updated by %(user)s.', user=requester.display_name),
            old_values={'payment_token': old_token.display_name if old_token else False},
            new_values={'payment_token': token.display_name, 'requested_by': requester.display_name},
        )
        return True

    def _portal_assign_payment_token_from_validation_transaction(self, transaction, access_token, requester):
        self.ensure_one()
        transaction.ensure_one()
        requester.ensure_one()

        expected_access_token = payment_utils.generate_access_token(
            transaction.partner_id.id,
            transaction.amount,
            transaction.currency_id.id,
            env=self.env,
        )
        if not access_token or not consteq(access_token, expected_access_token):
            raise ValidationError(_('Payment method validation could not be verified.'))
        if transaction.operation != 'validation':
            raise ValidationError(_('Only payment method validation transactions can update a subscription payment method.'))
        if transaction.partner_id.commercial_partner_id != requester.partner_id.commercial_partner_id:
            raise ValidationError(_('You do not have access to this payment method validation.'))
        if transaction.state == 'pending':
            return 'pending'
        if transaction.state not in ('authorized', 'done') or not transaction.token_id:
            raise ValidationError(_('Payment method was not saved. Try again or use another method.'))

        self._portal_assign_payment_token(transaction.token_id, requester)
        return 'saved'

    def _portal_retry_payment_recovery(self, invoice, requester):
        self.ensure_one()
        requester.ensure_one()
        invoice.ensure_one()

        if not self.is_subscription:
            raise ValidationError(_('Only subscriptions can retry payment recovery.'))
        if requester.partner_id.commercial_partner_id != self.partner_id.commercial_partner_id:
            raise ValidationError(_('You can only retry payments for your own subscription.'))
        if invoice.subscription_id != self:
            raise ValidationError(_('The selected invoice does not belong to this subscription.'))
        if invoice.move_type != 'out_invoice' or invoice.state != 'posted':
            raise ValidationError(_('Only posted customer invoices can be retried.'))
        if invoice.payment_state not in ['not_paid', 'partial']:
            raise ValidationError(_('This invoice does not need payment recovery.'))
        latest_attempt = self._get_latest_portal_payment_attempt(invoice)
        if latest_attempt and latest_attempt.state == 'pending':
            raise UserError(_('A payment retry is already pending provider confirmation. Open the invoice to check current status.'))
        if not self.payment_token_id:
            raise UserError(_('No saved payment method is available. Open the invoice to pay or add a payment method.'))

        transaction = self._auto_collect_payment(invoice, source='portal', requested_by=requester)
        if transaction and transaction.state == 'done':
            event_type = 'payment_success'
            description = _('Portal payment retry completed for invoice %(invoice)s by %(user)s.')
        elif transaction and transaction.state == 'pending':
            event_type = 'payment_pending'
            description = _('Portal payment retry was submitted for invoice %(invoice)s by %(user)s and is waiting for provider confirmation.')
        else:
            event_type = 'payment_failed'
            description = _('Portal payment retry failed for invoice %(invoice)s by %(user)s.')
        self._log_subscription_event(
            event_type,
            description % {'invoice': invoice.name, 'user': requester.display_name},
            new_values={
                'invoice_id': invoice.id,
                'transaction_id': transaction.id if transaction else False,
                'transaction_state': transaction.state if transaction else False,
                'requested_by': requester.display_name,
            },
        )
        return transaction

    @api.model
    def _cron_auto_collect_payments(self):
        # Scheduled job to attempt payment collection on open subscription invoices
        invoices = self.env['account.move'].search([
            ('subscription_id', '!=', False),
            ('payment_state', 'in', ['not_paid', 'partial']),
            ('state', '=', 'posted'),
        ])
        # Pre-filter to only invoices whose subscription has a payment token
        invoices = invoices.filtered(lambda inv: inv.subscription_id.payment_token_id)
        for inv in invoices:
            try:
                inv.subscription_id._auto_collect_payment(inv)
            except Exception:
                _logger.exception('Failed to auto-collect payment for invoice %s', inv.name)
