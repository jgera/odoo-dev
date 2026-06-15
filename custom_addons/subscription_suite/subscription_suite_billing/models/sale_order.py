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
    pending_seat_quantity = fields.Float(string='Pending Seat Quantity', copy=False)
    pending_seat_change_date = fields.Date(string='Pending Seat Change Date', copy=False, index=True)
    pending_addon_change_operation = fields.Selection([
        ('add', 'Add'),
        ('remove', 'Remove'),
    ], string='Pending Add-on Operation', copy=False)
    pending_addon_product_id = fields.Many2one('product.product', string='Pending Add-on Product', copy=False)
    pending_addon_line_id = fields.Many2one('sale.order.line', string='Pending Add-on Line', copy=False)
    pending_addon_quantity = fields.Float(string='Pending Add-on Quantity', copy=False)
    pending_addon_price_unit = fields.Monetary(string='Pending Add-on Unit Price', copy=False)
    pending_addon_discount = fields.Float(string='Pending Add-on Discount (%)', copy=False)
    pending_addon_change_date = fields.Date(string='Pending Add-on Change Date', copy=False, index=True)
    usage_summary_ids = fields.One2many('subscription.usage.summary', 'subscription_id', string='Usage Summaries')
    usage_summary_count = fields.Integer(string='Usage Summary Count', compute='_compute_usage_summary_count')
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

    def _compute_usage_summary_count(self):
        for record in self:
            record.usage_summary_count = len(record.usage_summary_ids)

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

    def action_cancel_pending_seat_change(self):
        for subscription in self:
            if not subscription.pending_seat_change_date:
                continue
            old_values = {
                'pending_seat_quantity': subscription.pending_seat_quantity,
                'pending_seat_change_date': subscription.pending_seat_change_date,
            }
            subscription._clear_pending_seat_change()
            subscription._log_subscription_event(
                'plan_changed',
                _('Scheduled seat change cancelled'),
                old_values=old_values,
            )

    def action_change_addons(self):
        self.ensure_one()
        self._check_addon_change_allowed()
        return {
            'name': _('Change Add-ons'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.change.addons.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_subscription_id': self.id,
            },
        }

    def action_cancel_pending_addon_change(self):
        for subscription in self:
            if not subscription.pending_addon_change_date:
                continue
            old_values = {
                'pending_addon_change_operation': subscription.pending_addon_change_operation,
                'pending_addon_product_id': subscription.pending_addon_product_id.display_name,
                'pending_addon_line_id': subscription.pending_addon_line_id.display_name,
                'pending_addon_quantity': subscription.pending_addon_quantity,
                'pending_addon_change_date': subscription.pending_addon_change_date,
            }
            subscription._clear_pending_addon_change()
            subscription._log_subscription_event(
                'plan_changed',
                _('Scheduled add-on change cancelled'),
                old_values=old_values,
            )

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

    def action_view_usage_summaries(self):
        self.ensure_one()
        return {
            'name': _('Usage Summaries'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.usage.summary',
            'view_mode': 'list,form',
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
        if self.pending_seat_change_date and self.pending_seat_change_date <= fields.Date.today():
            self._apply_pending_seat_change()
        if self.pending_addon_change_date and self.pending_addon_change_date <= fields.Date.today():
            self._apply_pending_addon_change()
        self._refresh_subscription_line_discounts()

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

        usage_summaries = self._prepare_usage_summaries_for_invoice(attempt.period_start, attempt.period_end)
        try:
            invoice = super()._generate_subscription_invoice()
            if invoice:
                self._append_usage_invoice_lines(invoice, usage_summaries)
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
            self._mark_usage_summaries_invoiced(invoice, usage_summaries)
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

    def _get_plan_usage_lines(self):
        self.ensure_one()
        if not self.subscription_plan_id:
            return self.env['subscription.plan.usage.line']
        return self.subscription_plan_id.usage_line_ids.filtered(lambda line: line.meter_id.active)

    def _get_or_create_usage_summary(self, usage_line, period_start, period_end):
        self.ensure_one()
        usage_line.ensure_one()
        Summary = self.env['subscription.usage.summary']
        summary = Summary.search([
            ('subscription_id', '=', self.id),
            ('meter_id', '=', usage_line.meter_id.id),
            ('period_start', '=', period_start),
            ('period_end', '=', period_end),
        ], limit=1)
        Event = self.env['subscription.usage.event']
        domain = [
            ('subscription_id', '=', self.id),
            ('meter_id', '=', usage_line.meter_id.id),
            ('state', '=', 'ready'),
            ('event_date', '>=', period_start),
            ('event_date', '<', period_end),
            ('summary_id', '=', False),
        ]
        new_events = Event.search(domain)
        if summary and not summary.invoice_id:
            events = summary.event_ids.filtered(lambda event: event.state == 'ready') | new_events
        elif summary:
            return summary
        else:
            events = new_events

        if not summary and not events:
            return Summary

        used_quantity = sum(events.mapped('quantity'))
        precision_rounding = usage_line.meter_id.uom_id.rounding or 0.01
        billable_quantity = 0.0
        if float_compare(used_quantity, usage_line.included_quantity, precision_rounding=precision_rounding) > 0:
            billable_quantity = used_quantity - usage_line.included_quantity
        amount = billable_quantity * usage_line.overage_price_unit
        values = {
            'subscription_id': self.id,
            'meter_id': usage_line.meter_id.id,
            'period_start': period_start,
            'period_end': period_end,
            'included_quantity': usage_line.included_quantity,
            'used_quantity': used_quantity,
            'billable_quantity': billable_quantity,
            'overage_product_id': usage_line.overage_product_id.id,
            'overage_price_unit': usage_line.overage_price_unit,
            'amount': amount,
        }
        if summary:
            summary.write(values)
        else:
            summary = Summary.create(values)
        if new_events:
            new_events.write({'summary_id': summary.id})
        return summary

    def _prepare_usage_summaries_for_invoice(self, period_start, period_end):
        self.ensure_one()
        if not period_start or not period_end or period_start >= period_end:
            return self.env['subscription.usage.summary']
        summaries = self.env['subscription.usage.summary']
        for usage_line in self._get_plan_usage_lines():
            summaries |= self._get_or_create_usage_summary(usage_line, period_start, period_end)
        return summaries.filtered(lambda summary: not summary.invoice_id)

    def _append_usage_invoice_lines(self, invoice, usage_summaries):
        self.ensure_one()
        invoice.ensure_one()
        created_lines = self.env['account.move.line']
        for summary in usage_summaries:
            precision_rounding = summary.meter_id.uom_id.rounding or 0.01
            if (
                summary.invoice_line_id
                or float_compare(summary.billable_quantity, 0.0, precision_rounding=precision_rounding) <= 0
            ):
                continue
            product = summary.overage_product_id
            account = product.property_account_income_id or product.categ_id.property_account_income_categ_id
            if not account and hasattr(product, '_get_product_accounts'):
                account = product._get_product_accounts().get('income')
            if not account:
                raise ValidationError(
                    _("Configure an income account on usage overage product %s or its product category.")
                    % product.display_name
                )
            taxes = product.taxes_id.filtered(lambda tax: not tax.company_id or tax.company_id == invoice.company_id)
            created_lines |= self.env['account.move.line'].create({
                'move_id': invoice.id,
                'product_id': product.id,
                'name': _('Usage overage: %(meter)s (%(start)s to %(end)s)') % {
                    'meter': summary.meter_id.display_name,
                    'start': summary.period_start,
                    'end': summary.period_end,
                },
                'quantity': summary.billable_quantity,
                'price_unit': summary.overage_price_unit,
                'account_id': account.id,
                'tax_ids': [(6, 0, taxes.ids)],
                'currency_id': invoice.currency_id.id,
                'usage_summary_id': summary.id,
            })
        return created_lines

    def _mark_usage_summaries_invoiced(self, invoice, usage_summaries):
        self.ensure_one()
        invoice.ensure_one()
        for summary in usage_summaries:
            invoice_line = invoice.invoice_line_ids.filtered(lambda line: line.usage_summary_id == summary)[:1]
            summary.write({
                'invoice_id': invoice.id,
                'invoice_line_id': invoice_line.id if invoice_line else False,
            })
            summary.event_ids.filtered(lambda event: event.state == 'ready').with_context(
                allow_usage_state_change=True,
            ).write({'state': 'invoiced'})

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
        new_seat_subtotal = seat_line._get_subscription_discounted_total(quantity=new_quantity)
        new_recurring_total = self.recurring_total - seat_line.price_subtotal + new_seat_subtotal
        return self._monthly_equivalent_amount(new_recurring_total)

    def _get_seat_change_write_values(self, seat_line, new_quantity):
        self.ensure_one()
        values = {'product_uom_qty': new_quantity}
        if seat_line.subscription_pricing_model != 'flat':
            values['price_unit'] = seat_line._get_effective_price_unit(quantity=new_quantity)
        return values

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

        seat_line.write(self._get_seat_change_write_values(seat_line, new_quantity))
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

    def _clear_pending_seat_change(self):
        self.write({
            'pending_seat_quantity': 0.0,
            'pending_seat_change_date': False,
        })

    def _schedule_seat_change(self, new_quantity, effective_date=None):
        self.ensure_one()
        effective_date = effective_date or self.next_invoice_date
        if not effective_date:
            raise ValidationError(_("Set a next invoice date before scheduling a next-period seat change."))
        seat_line = self._check_seat_change_allowed(new_quantity=new_quantity)
        old_quantity = seat_line.product_uom_qty
        old_mrr = self.mrr
        new_mrr = self._get_mrr_after_seat_change(seat_line, new_quantity)
        self.write({
            'pending_seat_quantity': new_quantity,
            'pending_seat_change_date': effective_date,
        })
        self._log_subscription_event(
            'plan_changed',
            _('Seat change from %(old_qty)s to %(new_qty)s scheduled for %(date)s', old_qty=old_quantity, new_qty=new_quantity, date=effective_date),
            old_values={'seats': old_quantity, 'mrr': old_mrr},
            new_values={'seats': new_quantity, 'mrr': new_mrr, 'effective_date': effective_date, 'timing': 'next_period'},
        )
        return True

    def _apply_pending_seat_change(self):
        self.ensure_one()
        if not self.pending_seat_change_date:
            return False
        new_quantity = self.pending_seat_quantity
        effective_date = self.pending_seat_change_date
        seat_line = self._check_seat_change_allowed()
        old_quantity = seat_line.product_uom_qty
        line_uom = seat_line.product_uom_id or seat_line.product_id.uom_id
        if float_compare(new_quantity, old_quantity, precision_rounding=line_uom.rounding or 0.01) == 0:
            self._clear_pending_seat_change()
            self._log_subscription_event(
                'plan_changed',
                _('Scheduled seat change skipped because the subscription already has %(qty)s seats', qty=old_quantity),
                old_values={'seats': old_quantity},
                new_values={'seats': old_quantity, 'effective_date': effective_date, 'timing': 'next_period'},
            )
            return False
        old_mrr = self.mrr
        new_mrr = self._get_mrr_after_seat_change(seat_line, new_quantity)
        seat_line.write(self._get_seat_change_write_values(seat_line, new_quantity))
        self.invalidate_recordset(['seat_quantity', 'recurring_total', 'mrr'])
        self._clear_pending_seat_change()
        movement_type = self._get_mrr_movement_type(old_mrr, new_mrr)
        self._log_subscription_event(
            'plan_changed',
            _('Scheduled seat change applied from %(old_qty)s to %(new_qty)s', old_qty=old_quantity, new_qty=new_quantity),
            old_values={'seats': old_quantity, 'mrr': old_mrr},
            new_values={'seats': new_quantity, 'mrr': new_mrr, 'effective_date': effective_date, 'timing': 'next_period'},
        )
        self._log_mrr_movement(
            movement_type,
            old_mrr,
            new_mrr,
            _('MRR %s from scheduled seat change: %s to %s seats') % (
                'expansion' if movement_type == 'expansion' else 'contraction',
                old_quantity,
                new_quantity,
            ),
            movement_date=effective_date,
        )
        return True

    def _get_addon_lines(self, product=None):
        self.ensure_one()
        addon_lines = self.order_line.filtered(
            lambda line: line.is_recurring
            and line.subscription_component_type == 'addon'
            and not line.display_type
            and line.product_id
        )
        if product:
            addon_lines = addon_lines.filtered(lambda line: line.product_id == product)
        return addon_lines

    def _check_addon_change_allowed(self):
        self.ensure_one()
        if not self.is_subscription:
            raise ValidationError(_("Only subscriptions can change add-ons."))
        if self.subscription_quote_type:
            raise ValidationError(_("Subscription quotations cannot change add-ons."))
        if self.state not in ('sale', 'done'):
            raise ValidationError(_("Confirm the subscription before changing add-ons."))
        if self.subscription_state not in ('active', 'paused', 'past_due'):
            raise ValidationError(_("Add-ons can only be changed on active, paused, or past-due subscriptions."))
        return True

    def _check_addon_quantity(self, quantity, product=None, line=None, operation='add'):
        precision_rounding = 0.01
        if line:
            line_uom = line.product_uom_id or line.product_id.uom_id
            precision_rounding = line_uom.rounding or precision_rounding
        elif product and product.uom_id:
            precision_rounding = product.uom_id.rounding or precision_rounding
        if float_compare(quantity, 1.0, precision_rounding=precision_rounding) < 0:
            raise ValidationError(_("Add-on quantity must be at least 1."))
        if operation == 'remove' and line and float_compare(quantity, line.product_uom_qty, precision_rounding=precision_rounding) > 0:
            raise ValidationError(_("Cannot remove more add-on quantity than the subscription currently has."))
        return precision_rounding

    def _get_mrr_after_addon_change(self, addon_line=None, product=None, quantity=0.0, price_unit=0.0, discount=0.0, operation='add'):
        self.ensure_one()
        recurring_total = self.recurring_total
        if operation == 'add':
            if addon_line:
                old_subtotal = addon_line.price_subtotal
                new_quantity = addon_line.product_uom_qty + quantity
                new_subtotal = new_quantity * addon_line.price_unit * (1 - (addon_line.discount or 0.0) / 100.0)
                recurring_total = recurring_total - old_subtotal + new_subtotal
            else:
                recurring_total += quantity * price_unit * (1 - (discount or 0.0) / 100.0)
        else:
            old_subtotal = addon_line.price_subtotal
            new_quantity = max(0.0, addon_line.product_uom_qty - quantity)
            new_subtotal = new_quantity * addon_line.price_unit * (1 - (addon_line.discount or 0.0) / 100.0)
            recurring_total = recurring_total - old_subtotal + new_subtotal
        return self._monthly_equivalent_amount(recurring_total)

    def _prepare_addon_line_values(self, product, quantity, price_unit=None, discount=0.0):
        self.ensure_one()
        product.ensure_one()
        return {
            'product_id': product.id,
            'name': product.get_product_multiline_description_sale(),
            'product_uom_qty': quantity,
            'price_unit': price_unit if price_unit is not None else product.list_price,
            'discount': discount,
            'is_recurring': True,
            'subscription_component_type': 'addon',
            'subscription_base_discount': discount,
            'recurring_interval_count': self.billing_interval_count,
            'recurring_interval_unit': self.billing_interval_unit,
        }

    def _apply_addon_line_change(self, operation, product=None, quantity=0.0, price_unit=None, discount=0.0, addon_line=None):
        self.ensure_one()
        if operation == 'add':
            addon_lines = self._get_addon_lines(product)
            addon_line = addon_line or addon_lines[:1]
            if addon_line:
                addon_line.write({'product_uom_qty': addon_line.product_uom_qty + quantity})
            else:
                self.write({'order_line': [(0, 0, self._prepare_addon_line_values(product, quantity, price_unit, discount))]})
                addon_line = self._get_addon_lines(product)[:1]
        else:
            addon_line.ensure_one()
            remaining_quantity = max(0.0, addon_line.product_uom_qty - quantity)
            addon_line.write({'product_uom_qty': remaining_quantity})
        self.invalidate_recordset(['recurring_total', 'mrr'])
        return addon_line

    def _create_addon_proration(self, addon_line, product, old_quantity, new_quantity, old_mrr, new_mrr, effective_date):
        self.ensure_one()
        period_start = self.current_period_start or self.last_invoice_date or self.subscription_start_date or effective_date
        period_end = self.current_period_end or self.next_invoice_date or self.subscription_plan_id.get_next_invoice_date(period_start)
        if effective_date < period_start:
            effective_date = period_start
        if not period_start or not period_end or effective_date >= period_end:
            return False
        if self._compare_mrr(new_mrr, old_mrr) == 0:
            return False
        proration = self.env['subscription.proration'].create({
            'subscription_id': self.id,
            'proration_scope': 'addon_change',
            'change_type': 'upgrade' if self._compare_mrr(new_mrr, old_mrr) > 0 else 'downgrade',
            'change_date': effective_date,
            'old_plan_id': self.subscription_plan_id.id,
            'new_plan_id': self.subscription_plan_id.id,
            'addon_product_id': product.id,
            'old_addon_quantity': old_quantity,
            'new_addon_quantity': new_quantity,
            'period_start': period_start,
            'period_end': period_end,
            'old_daily_rate': old_mrr / 30.0,
            'new_daily_rate': new_mrr / 30.0,
        })
        proration.action_apply_proration()
        return proration

    def _execute_addon_change(self, operation, product=None, quantity=0.0, price_unit=None, discount=0.0, addon_line=None, effective_date=None):
        self.ensure_one()
        effective_date = effective_date or fields.Date.today()
        self._check_addon_change_allowed()
        if operation not in ('add', 'remove'):
            raise ValidationError(_("Unsupported add-on operation."))
        if operation == 'add':
            if not product:
                raise ValidationError(_("Select an add-on product to add."))
            product.ensure_one()
            addon_line = self._get_addon_lines(product)[:1]
            self._check_addon_quantity(quantity, product=product, line=addon_line, operation=operation)
            old_quantity = addon_line.product_uom_qty if addon_line else 0.0
            old_mrr = self.mrr
            new_mrr = self._get_mrr_after_addon_change(addon_line=addon_line, product=product, quantity=quantity, price_unit=price_unit, discount=discount, operation=operation)
            changed_line = self._apply_addon_line_change(operation, product=product, quantity=quantity, price_unit=price_unit, discount=discount, addon_line=addon_line)
            new_quantity = old_quantity + quantity
        else:
            if not addon_line:
                raise ValidationError(_("Select an existing add-on line to remove."))
            addon_line.ensure_one()
            product = addon_line.product_id
            self._check_addon_quantity(quantity, line=addon_line, operation=operation)
            old_quantity = addon_line.product_uom_qty
            old_mrr = self.mrr
            new_mrr = self._get_mrr_after_addon_change(addon_line=addon_line, quantity=quantity, operation=operation)
            changed_line = self._apply_addon_line_change(operation, quantity=quantity, addon_line=addon_line)
            new_quantity = max(0.0, old_quantity - quantity)

        proration = self._create_addon_proration(changed_line, product, old_quantity, new_quantity, old_mrr, new_mrr, effective_date)
        movement_type = self._get_mrr_movement_type(old_mrr, new_mrr)
        operation_label = _('added') if operation == 'add' else _('removed')
        self._log_subscription_event(
            'plan_changed',
            _('Add-on %(product)s %(operation)s: %(old_qty)s to %(new_qty)s', product=product.display_name, operation=operation_label, old_qty=old_quantity, new_qty=new_quantity),
            old_values={'addon': product.display_name, 'quantity': old_quantity, 'mrr': old_mrr},
            new_values={'addon': product.display_name, 'quantity': new_quantity, 'mrr': new_mrr, 'effective_date': effective_date, 'proration_id': proration.id if proration else False},
        )
        self._log_mrr_movement(
            movement_type,
            old_mrr,
            new_mrr,
            _('MRR %s from add-on change: %s') % (
                'expansion' if movement_type == 'expansion' else 'contraction',
                product.display_name,
            ),
            movement_date=effective_date,
        )
        return proration

    def _clear_pending_addon_change(self):
        self.write({
            'pending_addon_change_operation': False,
            'pending_addon_product_id': False,
            'pending_addon_line_id': False,
            'pending_addon_quantity': 0.0,
            'pending_addon_price_unit': 0.0,
            'pending_addon_discount': 0.0,
            'pending_addon_change_date': False,
        })

    def _schedule_addon_change(self, operation, product=None, quantity=0.0, price_unit=None, discount=0.0, addon_line=None, effective_date=None):
        self.ensure_one()
        self._check_addon_change_allowed()
        effective_date = effective_date or self.next_invoice_date
        if not effective_date:
            raise ValidationError(_("Set a next invoice date before scheduling a next-period add-on change."))
        if operation == 'add':
            if not product:
                raise ValidationError(_("Select an add-on product to add."))
            product.ensure_one()
            self._check_addon_quantity(quantity, product=product, operation=operation)
        elif operation == 'remove':
            if not addon_line:
                raise ValidationError(_("Select an existing add-on line to remove."))
            addon_line.ensure_one()
            product = addon_line.product_id
            self._check_addon_quantity(quantity, line=addon_line, operation=operation)
        else:
            raise ValidationError(_("Unsupported add-on operation."))
        self.write({
            'pending_addon_change_operation': operation,
            'pending_addon_product_id': product.id,
            'pending_addon_line_id': addon_line.id if addon_line else False,
            'pending_addon_quantity': quantity,
            'pending_addon_price_unit': price_unit if price_unit is not None else product.list_price,
            'pending_addon_discount': discount,
            'pending_addon_change_date': effective_date,
        })
        self._log_subscription_event(
            'plan_changed',
            _('Add-on %(product)s %(operation)s scheduled for %(date)s', product=product.display_name, operation=operation, date=effective_date),
            new_values={'addon': product.display_name, 'quantity': quantity, 'effective_date': effective_date, 'timing': 'next_period'},
        )
        return True

    def _apply_pending_addon_change(self):
        self.ensure_one()
        if not self.pending_addon_change_date:
            return False
        operation = self.pending_addon_change_operation
        product = self.pending_addon_product_id
        addon_line = self.pending_addon_line_id
        quantity = self.pending_addon_quantity
        price_unit = self.pending_addon_price_unit
        discount = self.pending_addon_discount
        effective_date = self.pending_addon_change_date
        self._execute_addon_change(
            operation,
            product=product,
            quantity=quantity,
            price_unit=price_unit,
            discount=discount,
            addon_line=addon_line,
            effective_date=effective_date,
        )
        self._clear_pending_addon_change()
        return True

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

        order_lines = [
            (0, 0, plan_line._prepare_sale_order_line_values(plan))
            for plan_line in plan.plan_line_ids
        ]

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
