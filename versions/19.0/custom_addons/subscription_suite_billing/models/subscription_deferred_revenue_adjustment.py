from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class SubscriptionDeferredRevenueAdjustment(models.Model):
    _name = 'subscription.deferred.revenue.adjustment'
    _description = 'Subscription Deferred Revenue Credit Note Adjustment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'adjustment_date desc, id desc'

    name = fields.Char(default='New', readonly=True, copy=False)
    schedule_id = fields.Many2one(
        'subscription.deferred.revenue',
        readonly=True,
        index=True,
        ondelete='cascade',
    )
    source_invoice_id = fields.Many2one(
        'account.move',
        string='Source Invoice',
        readonly=True,
        index=True,
    )
    credit_note_id = fields.Many2one(
        'account.move',
        string='Credit Note',
        required=True,
        readonly=True,
        index=True,
    )
    subscription_id = fields.Many2one(related='schedule_id.subscription_id', store=True, readonly=True, index=True)
    partner_id = fields.Many2one(related='schedule_id.partner_id', store=True, readonly=True)
    subscription_plan_id = fields.Many2one(related='schedule_id.subscription_plan_id', store=True, readonly=True, index=True)
    company_id = fields.Many2one(related='schedule_id.company_id', store=True, readonly=True, index=True)
    currency_id = fields.Many2one(related='schedule_id.currency_id', store=True, readonly=True, index=True)
    adjustment_date = fields.Date(related='credit_note_id.invoice_date', store=True, readonly=True, index=True)
    service_period_start = fields.Date(readonly=True, index=True)
    service_period_end = fields.Date(readonly=True, index=True)
    amount_total = fields.Monetary(currency_field='currency_id', readonly=True)
    draft_adjusted_amount = fields.Monetary(currency_field='currency_id', readonly=True)
    recognized_reversal_amount = fields.Monetary(currency_field='currency_id', readonly=True)
    state = fields.Selection(
        [
            ('applied', 'Applied'),
            ('blocked', 'Blocked'),
        ],
        default='applied',
        required=True,
        readonly=True,
        tracking=True,
        index=True,
    )
    block_reason = fields.Text(readonly=True)
    adjusted_line_ids = fields.Many2many(
        'subscription.deferred.revenue.line',
        'subscription_deferred_revenue_adjustment_line_rel',
        'adjustment_id',
        'line_id',
        string='Adjusted Recognition Lines',
        readonly=True,
    )
    reversal_move_ids = fields.Many2many(
        'account.move',
        'subscription_deferred_revenue_adjustment_move_rel',
        'adjustment_id',
        'move_id',
        string='Reversal Journal Entries',
        readonly=True,
    )

    _unique_credit_note_adjustment = models.Constraint(
        'unique(credit_note_id)',
        'A deferred revenue adjustment already exists for this credit note.',
    )

    def _check_adjust_access(self):
        if not self.env.user.has_group('subscription_suite.group_subscription_manager'):
            raise AccessError(_('Only subscription managers can adjust deferred revenue for credit notes.'))

    @api.model
    def _credit_note_amount(self, credit_note):
        amount = abs(self.env['subscription.deferred.revenue']._invoice_amount(credit_note))
        if credit_note.currency_id.is_zero(amount):
            amount = abs(credit_note.amount_untaxed)
        return credit_note.currency_id.round(amount)

    @api.model
    def _blocked_reason_for_credit_note(self, credit_note):
        if credit_note.move_type != 'out_refund':
            return _('Only posted customer credit notes can adjust deferred revenue.')
        if credit_note.state != 'posted':
            return _('Only posted customer credit notes can adjust deferred revenue.')
        if not credit_note.reversed_entry_id:
            return _('Credit note is not linked to an original subscription invoice.')
        if not credit_note.subscription_period_start or not credit_note.subscription_period_end:
            return _('Credit note is missing subscription service period dates.')
        if credit_note.subscription_period_start >= credit_note.subscription_period_end:
            return _('Credit note subscription service period is invalid.')
        return False

    @api.model
    def _get_source_schedule(self, credit_note):
        return self.env['subscription.deferred.revenue'].search([
            ('invoice_id', '=', credit_note.reversed_entry_id.id),
        ], limit=1)

    @api.model
    def _remaining_adjustable_amount(self, schedule):
        applied = self.search([
            ('schedule_id', '=', schedule.id),
            ('state', '=', 'applied'),
        ])
        adjusted = sum(applied.mapped('amount_total'))
        return schedule.currency_id.round(schedule.amount_total - adjusted)

    @api.model
    def _overlapping_lines(self, schedule, period_start, period_end):
        return schedule.line_ids.filtered(
            lambda line: line.period_start < period_end
            and line.period_end > period_start
            and line.state in ('draft', 'recognized')
        ).sorted('period_start')

    def _prepare_reversal_move_vals(self, source_move, schedule, amount):
        company_currency = schedule.company_id.currency_id
        balance_amount = schedule.currency_id._convert(
            amount,
            company_currency,
            schedule.company_id,
            self.adjustment_date or fields.Date.context_today(self),
        )
        balance_amount = company_currency.round(balance_amount)
        name = _('Deferred revenue reversal for %s') % (self.credit_note_id.name or self.credit_note_id.display_name)
        debit_currency_vals = {}
        credit_currency_vals = {}
        if schedule.currency_id != company_currency:
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
            'date': self.adjustment_date or fields.Date.context_today(self),
            'journal_id': schedule.recognition_journal_id.id,
            'company_id': schedule.company_id.id,
            'ref': name,
            'reversed_entry_id': source_move.id,
            'line_ids': [
                (0, 0, {
                    'name': name,
                    'account_id': schedule.revenue_account_id.id,
                    'partner_id': schedule.partner_id.id,
                    'balance': balance_amount,
                    **debit_currency_vals,
                }),
                (0, 0, {
                    'name': name,
                    'account_id': schedule.deferred_revenue_account_id.id,
                    'partner_id': schedule.partner_id.id,
                    'balance': -balance_amount,
                    **credit_currency_vals,
                }),
            ],
        }

    def _apply_to_draft_lines(self, amount):
        self.ensure_one()
        remaining = amount
        adjusted_lines = self.env['subscription.deferred.revenue.line']
        draft_adjusted = 0.0
        draft_lines = self._overlapping_lines(
            self.schedule_id,
            self.service_period_start,
            self.service_period_end,
        ).filtered(lambda line: line.state == 'draft')
        for line in draft_lines:
            if self.currency_id.is_zero(remaining):
                break
            line_amount = self.currency_id.round(line.amount)
            if self.currency_id.compare_amounts(line_amount, remaining) <= 0:
                line.with_context(deferred_revenue_internal_write=True).write({'state': 'cancelled'})
                draft_adjusted += line_amount
                remaining = self.currency_id.round(remaining - line_amount)
            else:
                line.with_context(deferred_revenue_internal_write=True).write({
                    'amount': self.currency_id.round(line_amount - remaining),
                })
                draft_adjusted += remaining
                remaining = 0.0
            adjusted_lines |= line
        return remaining, self.currency_id.round(draft_adjusted), adjusted_lines

    def _apply_to_recognized_lines(self, amount):
        self.ensure_one()
        remaining = amount
        reversed_amount = 0.0
        adjusted_lines = self.env['subscription.deferred.revenue.line']
        moves = self.env['account.move']
        recognized_lines = self._overlapping_lines(
            self.schedule_id,
            self.service_period_start,
            self.service_period_end,
        ).filtered(lambda line: line.state == 'recognized' and line.recognition_move_id)
        by_move = defaultdict(lambda: self.env['subscription.deferred.revenue.line'])
        for line in recognized_lines:
            by_move[line.recognition_move_id] |= line
        for source_move, lines in by_move.items():
            if self.currency_id.is_zero(remaining):
                break
            move_amount = min(sum(lines.mapped('amount')), remaining)
            move_amount = self.currency_id.round(move_amount)
            if self.currency_id.is_zero(move_amount):
                continue
            reversal = self.env['account.move'].create(
                self._prepare_reversal_move_vals(source_move, self.schedule_id, move_amount)
            )
            reversal.action_post()
            reversed_amount += move_amount
            remaining = self.currency_id.round(remaining - move_amount)
            adjusted_lines |= lines
            moves |= reversal
        return remaining, self.currency_id.round(reversed_amount), adjusted_lines, moves

    def action_view_credit_note(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Credit Note'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.credit_note_id.id,
        }

    def action_view_reversal_moves(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Deferred Revenue Reversal Entries'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.reversal_move_ids.ids)],
        }

    @api.model
    def apply_for_credit_notes(self, credit_notes):
        self._check_adjust_access()
        adjustments = self.browse()
        for credit_note in credit_notes.sudo():
            existing = self.search([('credit_note_id', '=', credit_note.id)], limit=1)
            if existing:
                adjustments |= existing
                continue

            block_reason = self._blocked_reason_for_credit_note(credit_note)
            schedule = self._get_source_schedule(credit_note) if not block_reason else self.env['subscription.deferred.revenue']
            if not block_reason and not schedule:
                block_reason = _('Original invoice does not have a deferred revenue schedule.')
            if not block_reason and schedule.state in ('blocked', 'cancelled'):
                block_reason = _('Original deferred revenue schedule is blocked or cancelled.')

            amount = self._credit_note_amount(credit_note)
            if not block_reason and credit_note.currency_id.is_zero(amount):
                block_reason = _('Credit note has no positive tax-excluded subscription amount to adjust.')
            if not block_reason and credit_note.currency_id != schedule.currency_id:
                block_reason = _('Credit note currency does not match the original deferred revenue schedule.')
            if not block_reason and credit_note.company_id != schedule.company_id:
                block_reason = _('Credit note company does not match the original deferred revenue schedule.')
            if not block_reason:
                remaining_adjustable = self._remaining_adjustable_amount(schedule)
                if schedule.currency_id.compare_amounts(amount, remaining_adjustable) > 0:
                    block_reason = _('Credit note amount exceeds the remaining adjustable deferred revenue.')
            if not block_reason:
                overlapping_lines = self._overlapping_lines(
                    schedule,
                    credit_note.subscription_period_start,
                    credit_note.subscription_period_end,
                )
                overlapping_amount = schedule.currency_id.round(sum(overlapping_lines.mapped('amount')))
                if schedule.currency_id.compare_amounts(amount, overlapping_amount) > 0:
                    block_reason = _('Credit note service period does not match enough deferred revenue lines to adjust.')
                elif overlapping_lines.filtered(lambda line: line.state == 'recognized' and not line.recognition_move_id):
                    block_reason = _('Recognized deferred revenue lines are missing recognition journal entry links.')

            values = {
                'name': _('Deferred Revenue Adjustment - %s') % (credit_note.name or credit_note.display_name),
                'schedule_id': schedule.id if schedule else False,
                'source_invoice_id': credit_note.reversed_entry_id.id if credit_note.reversed_entry_id else False,
                'credit_note_id': credit_note.id,
                'service_period_start': credit_note.subscription_period_start,
                'service_period_end': credit_note.subscription_period_end,
                'amount_total': amount,
                'state': 'blocked' if block_reason else 'applied',
                'block_reason': block_reason or False,
            }
            if block_reason:
                adjustment = self.create(values)
                adjustment.message_post(body=_('Deferred revenue credit-note adjustment blocked: %s') % block_reason)
                adjustments |= adjustment
                continue

            adjustment = self.create(values)
            remaining, draft_amount, draft_lines = adjustment._apply_to_draft_lines(amount)
            remaining, reversal_amount, recognized_lines, reversal_moves = adjustment._apply_to_recognized_lines(remaining)
            adjustment.write({
                'draft_adjusted_amount': draft_amount,
                'recognized_reversal_amount': reversal_amount,
                'adjusted_line_ids': [(6, 0, (draft_lines | recognized_lines).ids)],
                'reversal_move_ids': [(6, 0, reversal_moves.ids)],
            })
            schedule.message_post(
                body=_(
                    'Applied deferred revenue credit-note adjustment %(adjustment)s for %(amount)s. '
                    'Draft adjustment: %(draft)s. Recognition reversal: %(reversal)s.'
                ) % {
                    'adjustment': adjustment.display_name,
                    'amount': schedule.currency_id.format(amount),
                    'draft': schedule.currency_id.format(draft_amount),
                    'reversal': schedule.currency_id.format(reversal_amount),
                }
            )
            adjustments |= adjustment
        return adjustments
