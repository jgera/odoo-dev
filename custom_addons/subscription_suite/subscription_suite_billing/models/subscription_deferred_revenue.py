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
    recognition_move_count = fields.Integer(compute='_compute_recognition_move_count')
    adjustment_ids = fields.One2many(
        'subscription.deferred.revenue.adjustment',
        'schedule_id',
        string='Credit Note Adjustments',
        readonly=True,
    )
    adjustment_count = fields.Integer(compute='_compute_adjustment_count')
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

    def _compute_recognition_move_count(self):
        for schedule in self:
            schedule.recognition_move_count = len(schedule.line_ids.mapped('recognition_move_id'))

    def _compute_adjustment_count(self):
        for schedule in self:
            schedule.adjustment_count = len(schedule.adjustment_ids)

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
    def _get_default_recognition_method(self, company=False):
        return self._get_company_recognition_config(company=company)['recognition_method']

    @api.model
    def _get_config_m2o(self, key):
        value = self.env['ir.config_parameter'].sudo().get_param(key)
        return int(value) if value else False

    @api.model
    def _get_company_recognition_config(self, company=False):
        company = company or self.env.company
        return {
            'recognition_method': (
                company.subscription_default_recognition_method
                or self.env['ir.config_parameter'].sudo().get_param(
                    'subscription_suite.default_recognition_method',
                    'straight_line_daily',
                )
            ),
            'recognition_journal': (
                company.subscription_recognition_journal_id
                or self.env['account.journal'].browse(
                    self._get_config_m2o('subscription_suite.recognition_journal_id')
                )
            ),
            'deferred_revenue_account': (
                company.subscription_deferred_revenue_account_id
                or self.env['account.account'].browse(
                    self._get_config_m2o('subscription_suite.deferred_revenue_account_id')
                )
            ),
            'revenue_account': (
                company.subscription_revenue_account_id
                or self.env['account.account'].browse(
                    self._get_config_m2o('subscription_suite.revenue_account_id')
                )
            ),
            'scheduled_recognition_enabled': (
                company.subscription_enable_scheduled_recognition_posting
                or self.env['ir.config_parameter'].sudo().get_param(
                    'subscription_suite.enable_scheduled_recognition_posting',
                    'False',
                ) == 'True'
            ),
            'scheduled_recognition_cutoff_rule': (
                company.subscription_scheduled_recognition_cutoff_rule
                or self.env['ir.config_parameter'].sudo().get_param(
                    'subscription_suite.scheduled_recognition_cutoff_rule',
                    'prior_month_end',
                )
            ),
        }

    @api.model
    def _validate_company_recognition_config(self, company, config=False, schedule=False):
        config = config or self._get_company_recognition_config(company=company)
        line_model = self.env['subscription.deferred.revenue.line']
        line_model._validate_recognition_configuration(
            company,
            config['recognition_journal'],
            config['deferred_revenue_account'],
            config['revenue_account'],
            schedule=schedule,
        )
        return config

    @api.model
    def _eligible_invoice_lines(self, invoice):
        lines = invoice.invoice_line_ids.filtered(
            lambda line: line.display_type not in ('line_section', 'line_note')
            and not line.exclude_from_subscription_deferred_revenue
        )
        linked_lines = lines.filtered(
            lambda line: line.sale_line_ids
            and any(sale_line.is_recurring for sale_line in line.sale_line_ids)
        )
        lines_with_sale_links = lines.filtered('sale_line_ids')
        if lines_with_sale_links:
            return linked_lines
        recurring_product_ids = set(invoice.subscription_id.order_line.filtered('is_recurring').mapped('product_id').ids)
        product_lines = lines.filtered(lambda line: line.product_id.id in recurring_product_ids)
        recurring_names = set(
            name for name in invoice.subscription_id.order_line.filtered('is_recurring').mapped('name') if name
        )
        recurring_names.update(
            name for name in invoice.subscription_id.order_line.filtered('is_recurring').mapped('product_id.name') if name
        )
        name_lines = lines.filtered(lambda line: line.name in recurring_names or line.product_id.name in recurring_names)
        if recurring_product_ids or recurring_names:
            return product_lines or name_lines
        return lines

    @api.model
    def _invoice_amount(self, invoice):
        lines = self._eligible_invoice_lines(invoice)
        line_amounts = []
        for line in lines:
            amount = line.price_subtotal
            if not amount:
                amount = line.quantity * line.price_unit * (1 - (line.discount or 0.0) / 100.0)
            if amount > 0:
                line_amounts.append(amount)
        amount = sum(line_amounts)
        invoice_lines = invoice.invoice_line_ids.filtered(
            lambda line: line.display_type not in ('line_section', 'line_note')
        )
        if invoice.currency_id.is_zero(amount) and lines == invoice_lines:
            return invoice.amount_untaxed
        return amount

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
        config = self._get_company_recognition_config(company=invoice.company_id)
        return {
            'name': _('Deferred Revenue - %s') % (invoice.name or invoice.display_name),
            'subscription_id': subscription.id,
            'invoice_id': invoice.id,
            'service_period_start': invoice.subscription_period_start,
            'service_period_end': invoice.subscription_period_end,
            'recognition_method': method or config['recognition_method'],
            'deferred_revenue_account_id': config['deferred_revenue_account'].id,
            'revenue_account_id': config['revenue_account'].id,
            'recognition_journal_id': config['recognition_journal'].id,
            'amount_total': self._invoice_amount(invoice),
        }

    @api.model
    def _configuration_block_reason(self, values, company=False):
        missing = []
        if not values.get('deferred_revenue_account_id'):
            missing.append(_('deferred revenue account'))
        if not values.get('revenue_account_id'):
            missing.append(_('revenue account'))
        if not values.get('recognition_journal_id'):
            missing.append(_('recognition journal'))
        if missing:
            return _('Missing revenue recognition configuration: %s.') % ', '.join(missing)
        try:
            self._validate_company_recognition_config(
                company or self.env.company,
                config={
                    'recognition_journal': self.env['account.journal'].browse(
                        values.get('recognition_journal_id')
                    ),
                    'deferred_revenue_account': self.env['account.account'].browse(
                        values.get('deferred_revenue_account_id')
                    ),
                    'revenue_account': self.env['account.account'].browse(
                        values.get('revenue_account_id')
                    ),
                },
            )
        except ValidationError as error:
            return str(error)
        return False

    @api.model
    def _blocked_reason_for_invoice(self, invoice, amount, values=False):
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
        config_reason = self._configuration_block_reason(values or {}, company=invoice.company_id)
        if config_reason:
            return config_reason
        return False

    @api.model
    def _sync_lines(self, schedule):
        schedule.ensure_one()
        schedule.line_ids.with_context(deferred_revenue_internal_write=True).unlink()
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
        schedule.with_context(deferred_revenue_internal_write=True).write({
            'line_ids': lines,
            'state': 'ready' if lines else 'blocked',
        })
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
            block_reason = self._blocked_reason_for_invoice(invoice, values['amount_total'], values=values)
            existing = self.search([('invoice_id', '=', invoice.id)], limit=1)
            if existing and existing.line_ids.filtered(lambda line: line.state == 'recognized'):
                schedules |= existing
                continue
            if existing and existing.state not in ('draft', 'ready', 'blocked'):
                schedules |= existing
                continue
            values.update({
                'state': 'blocked' if block_reason else 'draft',
                'block_reason': block_reason or False,
            })
            schedule = existing or self.create(values)
            if existing:
                existing.line_ids.filtered(lambda line: line.state == 'draft').with_context(
                    deferred_revenue_internal_write=True,
                ).unlink()
                existing.write(values)
            if not block_reason:
                self._sync_lines(schedule)
            if schedule.state == 'blocked':
                schedule.message_post(body=_('Deferred revenue schedule blocked: %s') % schedule.block_reason)
            elif schedule.state == 'ready':
                schedule.message_post(body=_('Deferred revenue schedule generated with %s recognition lines.') % len(schedule.line_ids))
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
            schedule.message_post(body=_('Deferred revenue schedule regenerated.'))
        return True

    def action_cancel(self):
        self._check_generate_access()
        for schedule in self:
            if schedule.line_ids.filtered(lambda line: line.state == 'recognized'):
                raise UserError(_('Schedules with recognized lines cannot be cancelled.'))
            schedule.line_ids.with_context(deferred_revenue_internal_write=True).write({'state': 'cancelled'})
            schedule.write({'state': 'cancelled'})
            schedule.message_post(body=_('Deferred revenue schedule cancelled.'))
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

    def action_preview_recognition(self):
        self._check_generate_access()
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Preview Revenue Recognition'),
            'res_model': 'subscription.deferred.revenue.preview.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_schedule_id': self.id,
                'default_company_id': self.company_id.id,
                'default_subscription_id': self.subscription_id.id,
                'default_recognition_journal_id': self.recognition_journal_id.id,
                'default_deferred_revenue_account_id': self.deferred_revenue_account_id.id,
                'default_revenue_account_id': self.revenue_account_id.id,
            },
        }

    def action_post_recognition(self):
        self._check_generate_access()
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Post Revenue Recognition'),
            'res_model': 'subscription.deferred.revenue.post.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_schedule_id': self.id,
                'default_company_id': self.company_id.id,
                'default_subscription_id': self.subscription_id.id,
                'default_recognition_journal_id': self.recognition_journal_id.id,
                'default_deferred_revenue_account_id': self.deferred_revenue_account_id.id,
                'default_revenue_account_id': self.revenue_account_id.id,
            },
        }

    def action_view_recognition_moves(self):
        self.ensure_one()
        moves = self.line_ids.mapped('recognition_move_id')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Recognition Journal Entries'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', moves.ids)],
        }

    def action_adjust_credit_notes(self):
        self._check_generate_access()
        credit_notes = self.env['account.move'].search([
            ('move_type', '=', 'out_refund'),
            ('state', '=', 'posted'),
            ('reversed_entry_id', 'in', self.mapped('invoice_id').ids),
        ])
        if not credit_notes:
            raise UserError(_('No posted credit notes are linked to these deferred revenue schedules.'))
        adjustments = self.env['subscription.deferred.revenue.adjustment'].apply_for_credit_notes(credit_notes)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Deferred Revenue Adjustments'),
            'res_model': 'subscription.deferred.revenue.adjustment',
            'view_mode': 'list,form',
            'domain': [('id', 'in', adjustments.ids)],
        }

    def action_view_adjustments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Deferred Revenue Adjustments'),
            'res_model': 'subscription.deferred.revenue.adjustment',
            'view_mode': 'list,form',
            'domain': [('schedule_id', '=', self.id)],
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
    recognition_move_id = fields.Many2one('account.move', string='Recognition Journal Entry', readonly=True, copy=False)
    company_id = fields.Many2one(related='schedule_id.company_id', store=True, readonly=True)
    currency_id = fields.Many2one(related='schedule_id.currency_id', store=True, readonly=True)

    @api.constrains('period_start', 'period_end')
    def _check_period(self):
        for line in self:
            if line.period_start >= line.period_end:
                raise ValidationError(_('Recognition line period end must be after period start.'))

    def _check_locked_schedule(self):
        if self.env.context.get('deferred_revenue_internal_write'):
            return
        locked = self.filtered(lambda line: line.schedule_id.state in ('ready', 'cancelled') or line.state == 'recognized')
        if locked:
            raise UserError(_('Recognition lines on ready, cancelled, or recognized schedules are locked.'))

    def write(self, vals):
        protected = {'period_start', 'period_end', 'amount', 'state', 'recognized_date', 'recognition_move_id', 'schedule_id'}
        if protected.intersection(vals):
            self._check_locked_schedule()
        return super().write(vals)

    def unlink(self):
        self._check_locked_schedule()
        return super().unlink()

    @api.model
    def _recognition_preview_domain(self, cutoff_date, company=False, subscription=False, schedule=False):
        domain = [
            ('state', '=', 'draft'),
            ('period_end', '<=', cutoff_date),
            ('schedule_id.state', '=', 'ready'),
        ]
        if company:
            domain.append(('company_id', '=', company.id))
        if subscription:
            domain.append(('subscription_id', '=', subscription.id))
        if schedule:
            domain.append(('schedule_id', '=', schedule.id))
        return domain

    @api.model
    def _get_lines_for_recognition_preview(self, cutoff_date, company=False, subscription=False, schedule=False):
        return self.search(self._recognition_preview_domain(
            cutoff_date,
            company=company,
            subscription=subscription,
            schedule=schedule,
        ), order='company_id, currency_id, period_end, id')

    @api.model
    def _validate_recognition_configuration(
        self,
        company,
        recognition_journal,
        deferred_revenue_account,
        revenue_account,
        schedule=False,
    ):
        missing = []
        if not recognition_journal:
            missing.append(_('recognition journal'))
        if not deferred_revenue_account:
            missing.append(_('deferred revenue account'))
        if not revenue_account:
            missing.append(_('revenue account'))
        if missing:
            raise ValidationError(_('Missing revenue recognition configuration: %s.') % ', '.join(missing))
        if recognition_journal.type != 'general':
            raise ValidationError(_('The recognition journal must be a miscellaneous/general journal.'))
        if company and recognition_journal.company_id and recognition_journal.company_id != company:
            raise ValidationError(_('The recognition journal does not belong to %s.') % company.display_name)
        account_checks = (
            (deferred_revenue_account, _('Deferred revenue account'), ('liability_current', 'liability_non_current')),
            (revenue_account, _('Revenue account'), ('income', 'income_other')),
        )
        for account, label, allowed_types in account_checks:
            if 'company_ids' in account._fields and account.company_ids and company not in account.company_ids:
                raise ValidationError(_('Recognition accounts must be available for %s.') % company.display_name)
            if 'company_id' in account._fields and account.company_id and account.company_id != company:
                raise ValidationError(_('Recognition accounts must be available for %s.') % company.display_name)
            if account.account_type not in allowed_types:
                raise ValidationError(_('%(label)s has an invalid account type for revenue recognition.') % {
                    'label': label,
                })
        if schedule and company and schedule.company_id != company:
            raise ValidationError(_('The selected schedule does not belong to %s.') % company.display_name)

    @api.model
    def _prepare_recognition_move_vals(
        self,
        schedule,
        lines,
        amount,
        balance_amount,
        posting_date,
        recognition_journal,
        deferred_revenue_account,
        revenue_account,
    ):
        name = _('Revenue recognition for %s') % (schedule.invoice_id.name or schedule.invoice_id.display_name)
        debit_currency_vals = {}
        credit_currency_vals = {}
        if schedule.currency_id != schedule.company_id.currency_id:
            debit_currency_vals = {
                'currency_id': schedule.currency_id.id,
                'amount_currency': amount,
            }
            credit_currency_vals = {
                'currency_id': schedule.currency_id.id,
                'amount_currency': -amount,
            }
        return {
            'move_type': 'entry',
            'date': posting_date,
            'journal_id': recognition_journal.id,
            'company_id': schedule.company_id.id,
            'ref': name,
            'line_ids': [
                (0, 0, {
                    'name': name,
                    'account_id': deferred_revenue_account.id,
                    'partner_id': schedule.partner_id.id,
                    'balance': balance_amount,
                    **debit_currency_vals,
                }),
                (0, 0, {
                    'name': name,
                    'account_id': revenue_account.id,
                    'partner_id': schedule.partner_id.id,
                    'balance': -balance_amount,
                    **credit_currency_vals,
                }),
            ],
        }

    def _post_recognition_lines(
        self,
        posting_date,
        recognition_journal,
        deferred_revenue_account,
        revenue_account,
    ):
        lines_by_schedule = {}
        for line in self:
            lines_by_schedule.setdefault(line.schedule_id, self.browse())
            lines_by_schedule[line.schedule_id] |= line

        moves = self.env['account.move']
        for schedule, lines in lines_by_schedule.items():
            self._validate_recognition_configuration(
                schedule.company_id,
                recognition_journal,
                deferred_revenue_account,
                revenue_account,
                schedule=schedule,
            )
            amount = schedule.currency_id.round(sum(lines.mapped('amount')))
            if schedule.currency_id.is_zero(amount) or amount < 0:
                raise ValidationError(_('Recognition amount must be positive for %s.') % schedule.display_name)
            balance_amount = schedule.currency_id._convert(
                amount,
                schedule.company_id.currency_id,
                schedule.company_id,
                posting_date,
            )
            balance_amount = schedule.company_id.currency_id.round(balance_amount)
            if schedule.company_id.currency_id.is_zero(balance_amount) or balance_amount < 0:
                raise ValidationError(_('Recognition balance amount must be positive for %s.') % schedule.display_name)
            move = self.env['account.move'].create(self._prepare_recognition_move_vals(
                schedule,
                lines,
                amount,
                balance_amount,
                posting_date,
                recognition_journal,
                deferred_revenue_account,
                revenue_account,
            ))
            move.action_post()
            lines.with_context(deferred_revenue_internal_write=True).write({
                'state': 'recognized',
                'recognized_date': posting_date,
                'recognition_move_id': move.id,
            })
            schedule.message_post(
                body=_('Posted revenue recognition journal entry %(move)s for %(amount)s.') % {
                    'move': move.display_name,
                    'amount': schedule.currency_id.format(amount),
                }
            )
            moves |= move
        return moves
