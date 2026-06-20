from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class SubscriptionDeferredRevenueReconciliation(models.Model):
    _name = 'subscription.deferred.revenue.reconciliation'
    _description = 'Subscription Deferred Revenue Reconciliation'
    _order = 'closing_date desc, company_id, currency_id, subscription_plan_id, id desc'

    opening_date = fields.Date(required=True, readonly=True, index=True)
    closing_date = fields.Date(required=True, readonly=True, index=True)
    generated_at = fields.Datetime(default=fields.Datetime.now, readonly=True)
    company_id = fields.Many2one('res.company', required=True, readonly=True, index=True)
    currency_id = fields.Many2one('res.currency', required=True, readonly=True, index=True)
    subscription_plan_id = fields.Many2one('subscription.plan', string='Plan', readonly=True, index=True)
    bucket_key = fields.Char(required=True, readonly=True, index=True)
    status = fields.Selection(
        [
            ('ready', 'Ready'),
            ('variance', 'Variance'),
            ('missing_schedule', 'Missing Schedule'),
            ('missing_journal_entry', 'Missing Journal Entry'),
            ('blocked_schedule', 'Blocked Schedule'),
        ],
        default='ready',
        required=True,
        readonly=True,
        index=True,
    )

    invoice_deferred_amount = fields.Monetary(currency_field='currency_id', readonly=True)
    schedule_amount = fields.Monetary(currency_field='currency_id', readonly=True)
    recognized_line_amount = fields.Monetary(currency_field='currency_id', readonly=True)
    posted_journal_amount = fields.Monetary(currency_field='currency_id', readonly=True)
    credit_note_adjustment_amount = fields.Monetary(currency_field='currency_id', readonly=True)
    remaining_deferred_amount = fields.Monetary(currency_field='currency_id', readonly=True)
    variance_amount = fields.Monetary(currency_field='currency_id', readonly=True)

    invoice_count = fields.Integer(readonly=True)
    schedule_count = fields.Integer(readonly=True)
    recognized_line_count = fields.Integer(readonly=True)
    recognition_move_count = fields.Integer(readonly=True)
    adjustment_count = fields.Integer(readonly=True)

    invoice_ids = fields.Many2many(
        'account.move',
        'subscription_deferred_revenue_reconciliation_invoice_rel',
        'reconciliation_id',
        'invoice_id',
        string='Source Invoices',
        readonly=True,
    )
    schedule_ids = fields.Many2many(
        'subscription.deferred.revenue',
        'subscription_deferred_revenue_reconciliation_schedule_rel',
        'reconciliation_id',
        'schedule_id',
        string='Source Schedules',
        readonly=True,
    )
    recognition_line_ids = fields.Many2many(
        'subscription.deferred.revenue.line',
        'subscription_deferred_revenue_reconciliation_line_rel',
        'reconciliation_id',
        'line_id',
        string='Recognized Lines',
        readonly=True,
    )
    recognition_move_ids = fields.Many2many(
        'account.move',
        'subscription_deferred_revenue_reconciliation_move_rel',
        'reconciliation_id',
        'move_id',
        string='Recognition Journal Entries',
        readonly=True,
    )
    credit_note_ids = fields.Many2many(
        'account.move',
        'subscription_deferred_revenue_reconciliation_credit_rel',
        'reconciliation_id',
        'credit_note_id',
        string='Credit Notes',
        readonly=True,
    )
    adjustment_ids = fields.Many2many(
        'subscription.deferred.revenue.adjustment',
        'subscription_deferred_revenue_reconciliation_adjustment_rel',
        'reconciliation_id',
        'adjustment_id',
        string='Credit Note Adjustments',
        readonly=True,
    )

    _unique_bucket_key = models.Constraint(
        'unique(bucket_key)',
        'A deferred revenue reconciliation already exists for this generated bucket.',
    )

    @api.model
    def _check_generate_access(self):
        if not self.env.user.has_group('subscription_suite.group_subscription_manager'):
            raise AccessError(_('Only subscription managers can generate deferred revenue reconciliations.'))

    @api.model
    def _validate_period(self, opening_date, closing_date):
        if not opening_date or not closing_date:
            raise ValidationError(_('Opening date and closing date are required.'))
        if closing_date < opening_date:
            raise ValidationError(_('Closing date must be on or after opening date.'))

    @api.model
    def _bucket_key(self, opening_date, closing_date, company, currency, plan=False):
        plan_id = plan.id if plan else 0
        return '%s:%s:%s:%s:%s' % (opening_date, closing_date, company.id, currency.id, plan_id)

    @api.model
    def _period_domain(self, field_name, opening_date, closing_date):
        return [(field_name, '>=', opening_date), (field_name, '<=', closing_date)]

    @api.model
    def _plan_domain(self, plan):
        return [('subscription_plan_id', '=', plan.id)] if plan else []

    @api.model
    def _subscription_plan_domain(self, plan):
        return [('subscription_id.subscription_plan_id', '=', plan.id)] if plan else []

    @api.model
    def _clear_generation_scope(self, opening_date, closing_date, company=False, plan=False):
        domain = [
            ('opening_date', '=', opening_date),
            ('closing_date', '=', closing_date),
        ]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        self.search(domain).sudo().unlink()

    @api.model
    def _source_invoices(self, opening_date, closing_date, company=False, plan=False):
        domain = [
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('subscription_id', '!=', False),
            *self._period_domain('invoice_date', opening_date, closing_date),
        ]
        if company:
            domain.append(('company_id', '=', company.id))
        domain += self._subscription_plan_domain(plan)
        return self.env['account.move'].search(domain)

    @api.model
    def _source_recognized_lines(self, opening_date, closing_date, company=False, plan=False):
        domain = [
            ('state', '=', 'recognized'),
            *self._period_domain('recognized_date', opening_date, closing_date),
        ]
        if company:
            domain.append(('company_id', '=', company.id))
        domain += self._plan_domain(plan)
        return self.env['subscription.deferred.revenue.line'].search(domain)

    @api.model
    def _source_adjustments(self, opening_date, closing_date, company=False, plan=False):
        domain = [
            ('state', '=', 'applied'),
            *self._period_domain('adjustment_date', opening_date, closing_date),
        ]
        if company:
            domain.append(('company_id', '=', company.id))
        domain += self._plan_domain(plan)
        return self.env['subscription.deferred.revenue.adjustment'].search(domain)

    @api.model
    def _source_schedules(self, invoices, recognized_lines, adjustments, opening_date, closing_date, company=False, plan=False):
        invoice_schedule_domain = [
            ('invoice_id', 'in', invoices.ids),
        ]
        period_schedule_domain = [
            ('invoice_date', '>=', opening_date),
            ('invoice_date', '<=', closing_date),
        ]
        if company:
            invoice_schedule_domain.append(('company_id', '=', company.id))
            period_schedule_domain.append(('company_id', '=', company.id))
        invoice_schedule_domain += self._plan_domain(plan)
        period_schedule_domain += self._plan_domain(plan)

        schedules = self.env['subscription.deferred.revenue'].search(invoice_schedule_domain)
        schedules |= self.env['subscription.deferred.revenue'].search(period_schedule_domain)
        schedules |= recognized_lines.mapped('schedule_id')
        schedules |= adjustments.mapped('schedule_id')
        return schedules

    @api.model
    def _bucket_for_record(self, record):
        return (
            record.company_id.id,
            record.currency_id.id,
            record.subscription_plan_id.id or 0,
        )

    @api.model
    def _sum_invoice_amount(self, invoices):
        scheduler = self.env['subscription.deferred.revenue']
        total = 0.0
        for invoice in invoices:
            total += scheduler._invoice_amount(invoice)
        return invoices[:1].currency_id.round(total) if invoices else 0.0

    @api.model
    def _posted_move_amount(self, moves, currency):
        total = 0.0
        for move in moves.filtered(lambda rec: rec.state == 'posted'):
            debit = sum(move.line_ids.mapped('debit'))
            credit = sum(move.line_ids.mapped('credit'))
            total += max(debit, credit)
        return currency.round(total)

    @api.model
    def _effective_remaining_amount(self, schedules, currency):
        total = 0.0
        for schedule in schedules.filtered(lambda rec: rec.state != 'cancelled'):
            total += sum(schedule.line_ids.filtered(lambda line: line.state == 'draft').mapped('amount'))
        return currency.round(total)

    @api.model
    def _status_for_bucket(self, currency, bucket):
        if bucket['blocked_schedules']:
            return 'blocked_schedule'
        if bucket['missing_schedule_invoices']:
            return 'missing_schedule'
        if bucket['missing_journal_lines']:
            return 'missing_journal_entry'
        if currency.compare_amounts(bucket['variance_amount'], 0.0):
            return 'variance'
        return 'ready'

    @api.model
    def _prepare_bucket_values(self, opening_date, closing_date, company, currency, plan, bucket):
        invoices = bucket['invoices']
        schedules = bucket['schedules']
        recognized_lines = bucket['recognized_lines']
        moves = recognized_lines.mapped('recognition_move_id').filtered(lambda move: move.state == 'posted')
        adjustments = bucket['adjustments']
        credit_notes = adjustments.mapped('credit_note_id')

        invoice_amount = self._sum_invoice_amount(invoices)
        schedule_amount = currency.round(sum(schedules.filtered(lambda rec: rec.state != 'cancelled').mapped('amount_total')))
        recognized_amount = currency.round(sum(recognized_lines.mapped('amount')))
        posted_amount = self._posted_move_amount(moves, currency)
        adjustment_amount = currency.round(sum(adjustments.mapped('amount_total')))
        reversal_amount = currency.round(sum(adjustments.mapped('recognized_reversal_amount')))
        remaining_amount = self._effective_remaining_amount(schedules, currency)
        variance = currency.round(
            (schedule_amount - adjustment_amount) - ((posted_amount - reversal_amount) + remaining_amount)
        )
        bucket['variance_amount'] = variance

        return {
            'opening_date': opening_date,
            'closing_date': closing_date,
            'generated_at': fields.Datetime.now(),
            'company_id': company.id,
            'currency_id': currency.id,
            'subscription_plan_id': plan.id if plan else False,
            'bucket_key': self._bucket_key(opening_date, closing_date, company, currency, plan=plan),
            'status': self._status_for_bucket(currency, bucket),
            'invoice_deferred_amount': invoice_amount,
            'schedule_amount': schedule_amount,
            'recognized_line_amount': recognized_amount,
            'posted_journal_amount': posted_amount,
            'credit_note_adjustment_amount': adjustment_amount,
            'remaining_deferred_amount': remaining_amount,
            'variance_amount': variance,
            'invoice_count': len(invoices),
            'schedule_count': len(schedules),
            'recognized_line_count': len(recognized_lines),
            'recognition_move_count': len(moves),
            'adjustment_count': len(adjustments),
            'invoice_ids': [(6, 0, invoices.ids)],
            'schedule_ids': [(6, 0, schedules.ids)],
            'recognition_line_ids': [(6, 0, recognized_lines.ids)],
            'recognition_move_ids': [(6, 0, moves.ids)],
            'credit_note_ids': [(6, 0, credit_notes.ids)],
            'adjustment_ids': [(6, 0, adjustments.ids)],
        }

    @api.model
    def generate_reconciliation(self, opening_date, closing_date, company=False, plan=False):
        self._check_generate_access()
        self._validate_period(opening_date, closing_date)
        self._clear_generation_scope(opening_date, closing_date, company=company, plan=plan)

        invoices = self._source_invoices(opening_date, closing_date, company=company, plan=plan)
        recognized_lines = self._source_recognized_lines(opening_date, closing_date, company=company, plan=plan)
        adjustments = self._source_adjustments(opening_date, closing_date, company=company, plan=plan)
        schedules = self._source_schedules(
            invoices,
            recognized_lines,
            adjustments,
            opening_date,
            closing_date,
            company=company,
            plan=plan,
        )

        bucket_data = defaultdict(lambda: {
            'invoices': self.env['account.move'],
            'schedules': self.env['subscription.deferred.revenue'],
            'recognized_lines': self.env['subscription.deferred.revenue.line'],
            'adjustments': self.env['subscription.deferred.revenue.adjustment'],
            'missing_schedule_invoices': self.env['account.move'],
            'missing_journal_lines': self.env['subscription.deferred.revenue.line'],
            'blocked_schedules': self.env['subscription.deferred.revenue'],
            'variance_amount': 0.0,
        })

        for invoice in invoices:
            key = self._bucket_for_record(invoice.subscription_id)
            bucket = bucket_data[key]
            bucket['invoices'] |= invoice
            if not schedules.filtered(lambda schedule: schedule.invoice_id == invoice):
                bucket['missing_schedule_invoices'] |= invoice

        for schedule in schedules:
            key = self._bucket_for_record(schedule)
            bucket = bucket_data[key]
            bucket['schedules'] |= schedule
            if schedule.state == 'blocked':
                bucket['blocked_schedules'] |= schedule

        for line in recognized_lines:
            key = self._bucket_for_record(line)
            bucket = bucket_data[key]
            bucket['recognized_lines'] |= line
            bucket['schedules'] |= line.schedule_id
            if not line.recognition_move_id or line.recognition_move_id.state != 'posted':
                bucket['missing_journal_lines'] |= line

        for adjustment in adjustments:
            key = self._bucket_for_record(adjustment)
            bucket = bucket_data[key]
            bucket['adjustments'] |= adjustment
            bucket['schedules'] |= adjustment.schedule_id

        records = self.browse()
        Company = self.env['res.company']
        Currency = self.env['res.currency']
        Plan = self.env['subscription.plan']
        for company_id, currency_id, plan_id in bucket_data:
            values = self._prepare_bucket_values(
                opening_date,
                closing_date,
                Company.browse(company_id),
                Currency.browse(currency_id),
                Plan.browse(plan_id) if plan_id else Plan,
                bucket_data[(company_id, currency_id, plan_id)],
            )
            records |= self.create(values)
        return records

    def _action_for_records(self, name, model, records, view_mode='list,form'):
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': model,
            'view_mode': view_mode,
            'domain': [('id', 'in', records.ids)],
        }

    def action_view_invoices(self):
        self.ensure_one()
        return self._action_for_records(_('Source Invoices'), 'account.move', self.invoice_ids)

    def action_view_schedules(self):
        self.ensure_one()
        return self._action_for_records(_('Deferred Revenue Schedules'), 'subscription.deferred.revenue', self.schedule_ids)

    def action_view_recognition_lines(self):
        self.ensure_one()
        return self._action_for_records(
            _('Recognized Revenue Lines'),
            'subscription.deferred.revenue.line',
            self.recognition_line_ids,
        )

    def action_view_recognition_moves(self):
        self.ensure_one()
        return self._action_for_records(_('Recognition Journal Entries'), 'account.move', self.recognition_move_ids)

    def action_view_credit_notes(self):
        self.ensure_one()
        return self._action_for_records(_('Credit Notes'), 'account.move', self.credit_note_ids)

    def action_view_adjustments(self):
        self.ensure_one()
        return self._action_for_records(
            _('Deferred Revenue Adjustments'),
            'subscription.deferred.revenue.adjustment',
            self.adjustment_ids,
        )
