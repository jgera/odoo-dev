from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class SubscriptionDeferredRevenue(models.Model):
    _name = 'subscription.deferred.revenue'
    _description = 'Subscription Deferred Revenue Schedule'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'invoice_date desc, id desc'

    name = fields.Char(default='New', readonly=True, copy=False)
    subscription_id = fields.Many2one(
        'sale.order',
        string='Subscription',
        required=True,
        readonly=True,
        index=True,
        ondelete='cascade',
    )
    invoice_id = fields.Many2one(
        'account.move',
        string='Invoice',
        required=True,
        readonly=True,
        index=True,
        ondelete='cascade',
    )
    partner_id = fields.Many2one(related='invoice_id.partner_id', store=True, readonly=True)
    subscription_plan_id = fields.Many2one(
        related='subscription_id.subscription_plan_id',
        string='Plan',
        store=True,
        readonly=True,
    )
    invoice_date = fields.Date(related='invoice_id.invoice_date', store=True, readonly=True)
    service_period_start = fields.Date(readonly=True)
    service_period_end = fields.Date(readonly=True)
    recognition_method = fields.Selection(
        [
            ('straight_line_daily', 'Straight-line Daily'),
            ('equal_monthly', 'Equal Monthly'),
        ],
        required=True,
        default='straight_line_daily',
        readonly=True,
    )
    deferred_revenue_account_id = fields.Many2one('account.account', readonly=True)
    revenue_account_id = fields.Many2one('account.account', readonly=True)
    recognition_journal_id = fields.Many2one('account.journal', readonly=True)
    amount_total = fields.Monetary(currency_field='currency_id', readonly=True)
    recognized_amount = fields.Monetary(
        currency_field='currency_id',
        compute='_compute_amounts',
        store=True,
        readonly=True,
    )
    remaining_amount = fields.Monetary(
        currency_field='currency_id',
        compute='_compute_amounts',
        store=True,
        readonly=True,
    )
    line_ids = fields.One2many(
        'subscription.deferred.revenue.line',
        'schedule_id',
        string='Recognition Lines',
        readonly=True,
        copy=False,
    )
    line_count = fields.Integer(compute='_compute_line_count')
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('ready', 'Ready'),
            ('blocked', 'Blocked'),
            ('cancelled', 'Cancelled'),
        ],
        default='draft',
        required=True,
        tracking=True,
    )
    block_reason = fields.Text(readonly=True)
    company_id = fields.Many2one(related='invoice_id.company_id', store=True, readonly=True)
    currency_id = fields.Many2one(related='invoice_id.currency_id', store=True, readonly=True)

    _unique_invoice_schedule = models.Constraint(
        'unique(invoice_id)',
        'A deferred revenue schedule already exists for this invoice.',
    )

    @api.depends('line_ids.amount', 'line_ids.state', 'amount_total')
    def _compute_amounts(self):
        for schedule in self:
            recognized = sum(schedule.line_ids.filtered(lambda line: line.state == 'recognized').mapped('amount'))
            schedule.recognized_amount = recognized
            schedule.remaining_amount = schedule.amount_total - recognized

    def _compute_line_count(self):
        for schedule in self:
            schedule.line_count = len(schedule.line_ids)

    @api.constrains('service_period_start', 'service_period_end')
    def _check_service_period(self):
        for schedule in self:
            if schedule.state != 'blocked' and schedule.service_period_start and schedule.service_period_end:
                if schedule.service_period_start >= schedule.service_period_end:
                    raise ValidationError(_('Service period end must be after service period start.'))

    def _check_generate_access(self):
        if not self.env.user.has_group('subscription_suite.group_subscription_manager'):
            raise AccessError(_('Only subscription managers can generate deferred revenue schedules.'))

    @api.model
    def _get_default_recognition_method(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            'subscription_suite.default_recognition_method',
            'straight_line_daily',
        )

    @api.model
    def _get_config_m2o(self, key):
        value = self.env['ir.config_parameter'].sudo().get_param(key)
        return int(value) if value else False

    @api.model
    def _invoice_amount(self, invoice):
        if invoice.amount_untaxed > 0:
            return invoice.amount_untaxed
        lines = invoice.invoice_line_ids.filtered(lambda line: not line.display_type)
        return sum(amount for amount in lines.mapped('price_subtotal') if amount > 0)

    @api.model
    def _month_segments(self, period_start, period_end):
        segments = []
        cursor = period_start
        while cursor < period_end:
            month_end = (cursor.replace(day=1) + relativedelta(months=1))
            segment_end = min(month_end, period_end)
            segments.append((cursor, segment_end))
            cursor = segment_end
        return segments

    @api.model
    def _allocation_amounts(self, amount, period_start, period_end, method, currency):
        segments = self._month_segments(period_start, period_end)
        if not segments:
            return []
        total_days = (period_end - period_start).days
        if total_days <= 0:
            return []
        amounts = []
        allocated = 0.0
        for index, (line_start, line_end) in enumerate(segments):
            if index == len(segments) - 1:
                line_amount = currency.round(amount - allocated)
            elif method == 'equal_monthly':
                line_amount = currency.round(amount / len(segments))
                allocated += line_amount
            else:
                line_days = (line_end - line_start).days
                line_amount = currency.round(amount * line_days / total_days)
                allocated += line_amount
            amounts.append((line_start, line_end, line_amount))
        return amounts

    @api.model
    def _prepare_schedule_values(self, invoice, method=False):
        subscription = invoice.subscription_id
        return {
            'name': _('Deferred Revenue - %s') % (invoice.name or invoice.display_name),
            'subscription_id': subscription.id,
            'invoice_id': invoice.id,
            'service_period_start': invoice.subscription_period_start,
            'service_period_end': invoice.subscription_period_end,
            'recognition_method': method or self._get_default_recognition_method(),
            'deferred_revenue_account_id': self._get_config_m2o('subscription_suite.deferred_revenue_account_id'),
            'revenue_account_id': self._get_config_m2o('subscription_suite.revenue_account_id'),
            'recognition_journal_id': self._get_config_m2o('subscription_suite.recognition_journal_id'),
            'amount_total': self._invoice_amount(invoice),
        }

    @api.model
    def _blocked_reason_for_invoice(self, invoice, amount):
        if invoice.move_type != 'out_invoice':
            return _('Only customer invoices are supported in this foundation slice.')
        if invoice.state != 'posted':
            return _('Only posted subscription invoices can generate deferred revenue schedules.')
        if not invoice.subscription_id:
            return _('Invoice is not linked to a subscription.')
        if not invoice.subscription_period_start or not invoice.subscription_period_end:
            return _('Invoice is missing subscription service period dates.')
        if invoice.subscription_period_start >= invoice.subscription_period_end:
            return _('Invoice subscription service period is invalid.')
        if invoice.currency_id.is_zero(amount) or amount < 0:
            return _('Invoice has no positive tax-excluded subscription amount to recognize.')
        return False

    @api.model
    def _sync_lines(self, schedule):
        schedule.ensure_one()
        schedule.line_ids.unlink()
        if schedule.state == 'blocked':
            return schedule
        lines = []
        for sequence, (period_start, period_end, amount) in enumerate(
            self._allocation_amounts(
                schedule.amount_total,
                schedule.service_period_start,
                schedule.service_period_end,
                schedule.recognition_method,
                schedule.currency_id,
            ),
            start=1,
        ):
            lines.append((0, 0, {
                'sequence': sequence,
                'period_start': period_start,
                'period_end': period_end,
                'amount': amount,
                'state': 'draft',
            }))
        schedule.write({'line_ids': lines, 'state': 'ready' if lines else 'blocked'})
        if not lines:
            schedule.write({'block_reason': _('No recognition periods could be generated.')})
        return schedule

    @api.model
    def generate_for_invoices(self, invoices, method=False):
        self._check_generate_access()
        schedules = self.browse()
        for invoice in invoices.sudo():
            if not invoice.subscription_id:
                continue
            values = self._prepare_schedule_values(invoice, method=method)
            block_reason = self._blocked_reason_for_invoice(invoice, values['amount_total'])
            existing = self.search([('invoice_id', '=', invoice.id)], limit=1)
            if existing and existing.state not in ('draft', 'ready', 'blocked'):
                schedules |= existing
                continue
            values.update({
                'state': 'blocked' if block_reason else 'draft',
                'block_reason': block_reason or False,
            })
            schedule = existing or self.create(values)
            if existing:
                existing.line_ids.filtered(lambda line: line.state == 'draft').unlink()
                existing.write(values)
            if not block_reason:
                self._sync_lines(schedule)
            schedules |= schedule
        return schedules

    def action_regenerate_lines(self):
        self._check_generate_access()
        for schedule in self:
            if schedule.state == 'cancelled':
                raise UserError(_('Cancelled schedules cannot be regenerated.'))
            if schedule.line_ids.filtered(lambda line: line.state == 'recognized'):
                raise UserError(_('Schedules with recognized lines cannot be regenerated in this foundation slice.'))
            schedule.write({'state': 'draft', 'block_reason': False})
            self._sync_lines(schedule)
        return True

    def action_cancel(self):
        self._check_generate_access()
        for schedule in self:
            if schedule.line_ids.filtered(lambda line: line.state == 'recognized'):
                raise UserError(_('Schedules with recognized lines cannot be cancelled.'))
            schedule.line_ids.write({'state': 'cancelled'})
            schedule.write({'state': 'cancelled'})
        return True

    def action_view_invoice(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoice'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.invoice_id.id,
        }

    def action_view_subscription(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Subscription'),
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': self.subscription_id.id,
        }


class SubscriptionDeferredRevenueLine(models.Model):
    _name = 'subscription.deferred.revenue.line'
    _description = 'Subscription Deferred Revenue Schedule Line'
    _order = 'schedule_id, sequence, period_start'

    schedule_id = fields.Many2one(
        'subscription.deferred.revenue',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(default=10)
    subscription_id = fields.Many2one(related='schedule_id.subscription_id', store=True, readonly=True)
    invoice_id = fields.Many2one(related='schedule_id.invoice_id', store=True, readonly=True)
    partner_id = fields.Many2one(related='schedule_id.partner_id', store=True, readonly=True)
    subscription_plan_id = fields.Many2one(related='schedule_id.subscription_plan_id', store=True, readonly=True)
    period_start = fields.Date(required=True)
    period_end = fields.Date(required=True)
    amount = fields.Monetary(currency_field='currency_id', required=True)
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('recognized', 'Recognized'),
            ('cancelled', 'Cancelled'),
        ],
        default='draft',
        required=True,
    )
    recognized_date = fields.Date(readonly=True)
    company_id = fields.Many2one(related='schedule_id.company_id', store=True, readonly=True)
    currency_id = fields.Many2one(related='schedule_id.currency_id', store=True, readonly=True)

    @api.constrains('period_start', 'period_end')
    def _check_period(self):
        for line in self:
            if line.period_start >= line.period_end:
                raise ValidationError(_('Recognition line period end must be after period start.'))
