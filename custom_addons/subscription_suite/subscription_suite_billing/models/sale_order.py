import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    proration_ids = fields.One2many('subscription.proration', 'subscription_id', string='Prorations')
    proration_count = fields.Integer(string='Proration Count', compute='_compute_proration_count')
    billing_attempt_ids = fields.One2many('subscription.billing.attempt', 'subscription_id', string='Billing Attempts')
    billing_attempt_count = fields.Integer(string='Billing Attempt Count', compute='_compute_billing_attempt_count')
    billing_in_progress = fields.Boolean(string='Billing in Progress', copy=False, index=True, readonly=True)
    billing_locked_at = fields.Datetime(string='Billing Locked At', copy=False, readonly=True)
    billing_locked_by_run_id = fields.Many2one('subscription.billing.run', string='Billing Locked by Run', copy=False, readonly=True)
    setup_fee_invoice_id = fields.Many2one('account.move', string='Setup Fee Invoice')

    def _compute_proration_count(self):
        for record in self:
            record.proration_count = len(record.proration_ids)

    def _compute_billing_attempt_count(self):
        for record in self:
            record.billing_attempt_count = len(record.billing_attempt_ids)

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

        invoiceable_lines = self.order_line.filtered(lambda line: not line.display_type and line.qty_to_invoice > 0)
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
        self._check_plan_change_allowed(old_plan, new_plan, old_mrr)
        period_start = self.current_period_start or self.subscription_start_date
        period_end = self.current_period_end or self.next_invoice_date
        if not period_start or not period_end:
            period_start = effective_date
            period_end = new_plan.get_next_invoice_date(effective_date)
        
        new_mrr = new_plan._get_plan_mrr()
        old_daily_rate = old_mrr / 30
        new_daily_rate = new_mrr / 30
        
        change_type = 'upgrade' if new_mrr > old_mrr else 'downgrade'
        
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
        movement_type = 'expansion' if new_mrr > old_mrr else 'contraction'
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

    def _check_plan_change_allowed(self, old_plan, new_plan, old_mrr=None):
        self.ensure_one()
        if not old_plan or not new_plan or old_plan == new_plan:
            return True

        old_mrr = old_mrr if old_mrr is not None else self.mrr
        new_mrr = new_plan._get_plan_mrr()
        if new_mrr > old_mrr and old_plan.upgrade_plan_ids and new_plan not in old_plan.upgrade_plan_ids:
            raise ValidationError(
                _("Plan %(new_plan)s is not an allowed upgrade path from %(old_plan)s.") % {
                    'new_plan': new_plan.display_name,
                    'old_plan': old_plan.display_name,
                }
            )
        if new_mrr < old_mrr and old_plan.downgrade_plan_ids and new_plan not in old_plan.downgrade_plan_ids:
            raise ValidationError(
                _("Plan %(new_plan)s is not an allowed downgrade path from %(old_plan)s.") % {
                    'new_plan': new_plan.display_name,
                    'old_plan': old_plan.display_name,
                }
            )
        return True

    def _create_upsell_proration(self, subscription, old_mrr, new_mrr):
        self.ensure_one()
        if not subscription.subscription_plan_id or new_mrr == old_mrr:
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
            'change_type': 'upgrade' if new_mrr > old_mrr else 'downgrade',
            'change_date': effective_date,
            'old_plan_id': subscription.subscription_plan_id.id,
            'new_plan_id': subscription.subscription_plan_id.id,
            'period_start': period_start,
            'period_end': period_end,
            'old_daily_rate': old_mrr / 30.0,
            'new_daily_rate': new_mrr / 30.0,
            'state': 'applied',
        })
        return proration

    def _apply_subscription_plan(self, plan):
        self.ensure_one()
        plan.ensure_one()

        self.order_line.filtered('is_recurring').unlink()
        order_lines = []
        for plan_line in plan.plan_line_ids:
            order_lines.append((0, 0, {
                'product_id': plan_line.product_id.id,
                'name': plan_line.description or plan_line.product_id.get_product_multiline_description_sale(),
                'product_uom_qty': plan_line.quantity,
                'price_unit': plan_line.price_unit,
                'discount': plan_line.discount,
                'is_recurring': True,
                'recurring_interval_count': plan.billing_interval_count,
                'recurring_interval_unit': plan.billing_interval_unit,
            }))

        self.write({
            'subscription_plan_id': plan.id,
            'billing_interval_count': plan.billing_interval_count,
            'billing_interval_unit': plan.billing_interval_unit,
            'order_line': order_lines,
        })

    def _auto_collect_payment(self, invoice):
        self.ensure_one()
        token = self.payment_token_id
        if not token:
            return False
            
        tx = self.env['payment.transaction'].create({
            'provider_id': token.provider_id.id,
            'token_id': token.id,
            'amount': invoice.amount_total,
            'currency_id': invoice.currency_id.id,
            'partner_id': invoice.partner_id.id,
            'reference': invoice.name,
        })
        tx._send_payment_request()
        
        if tx.state == 'done':
            self._log_subscription_event('payment_success', f'Auto-payment collected for {invoice.name}')
        else:
            self._log_subscription_event('payment_failed', f'Auto-payment failed for {invoice.name}')
            
        return tx

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
