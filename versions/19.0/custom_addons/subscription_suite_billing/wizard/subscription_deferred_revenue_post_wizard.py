from collections import defaultdict

from odoo import _, fields, models
from odoo.exceptions import AccessError, ValidationError


class SubscriptionDeferredRevenuePostWizard(models.TransientModel):
    _name = 'subscription.deferred.revenue.post.wizard'
    _description = 'Post Subscription Revenue Recognition'

    cutoff_date = fields.Date(default=fields.Date.context_today, required=True)
    posting_date = fields.Date(default=fields.Date.context_today, required=True)
    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
    )
    subscription_id = fields.Many2one(
        'sale.order',
        domain=[('is_subscription', '=', True)],
    )
    schedule_id = fields.Many2one(
        'subscription.deferred.revenue',
        domain=[('state', '=', 'ready')],
    )
    recognition_journal_id = fields.Many2one(
        'account.journal',
        default=lambda self: self.env['subscription.deferred.revenue']._get_config_m2o(
            'subscription_suite.recognition_journal_id'
        ),
    )
    deferred_revenue_account_id = fields.Many2one(
        'account.account',
        string='Deferred Revenue Account',
        default=lambda self: self.env['subscription.deferred.revenue']._get_config_m2o(
            'subscription_suite.deferred_revenue_account_id'
        ),
    )
    revenue_account_id = fields.Many2one(
        'account.account',
        default=lambda self: self.env['subscription.deferred.revenue']._get_config_m2o(
            'subscription_suite.revenue_account_id'
        ),
    )

    def _check_post_access(self):
        if not self.env.user.has_group('subscription_suite.group_subscription_manager'):
            raise AccessError(_('Only subscription managers can post revenue recognition.'))

    def _validate_post_configuration(self):
        self.ensure_one()
        missing = []
        if not self.recognition_journal_id:
            missing.append(_('recognition journal'))
        if not self.deferred_revenue_account_id:
            missing.append(_('deferred revenue account'))
        if not self.revenue_account_id:
            missing.append(_('revenue account'))
        if missing:
            raise ValidationError(_('Missing revenue recognition configuration: %s.') % ', '.join(missing))
        if self.company_id and self.recognition_journal_id.company_id != self.company_id:
            raise ValidationError(_('The recognition journal does not belong to the selected company.'))
        for account in (self.deferred_revenue_account_id, self.revenue_account_id):
            if 'company_ids' in account._fields and account.company_ids and self.company_id not in account.company_ids:
                raise ValidationError(_('Recognition accounts must be available for the selected company.'))
            if 'company_id' in account._fields and account.company_id and account.company_id != self.company_id:
                raise ValidationError(_('Recognition accounts must be available for the selected company.'))
        if self.schedule_id:
            if self.company_id and self.schedule_id.company_id != self.company_id:
                raise ValidationError(_('The selected schedule does not belong to the selected company.'))
            if self.subscription_id and self.schedule_id.subscription_id != self.subscription_id:
                raise ValidationError(_('The selected schedule does not belong to the selected subscription.'))

    def _get_due_lines(self):
        self.ensure_one()
        return self.env['subscription.deferred.revenue.line']._get_lines_for_recognition_preview(
            self.cutoff_date,
            company=self.company_id,
            subscription=self.subscription_id,
            schedule=self.schedule_id,
        )

    def _validate_schedule_configuration(self, schedule):
        if self.recognition_journal_id.company_id != schedule.company_id:
            raise ValidationError(_('The recognition journal does not belong to %s.') % schedule.company_id.display_name)
        for account in (self.deferred_revenue_account_id, self.revenue_account_id):
            if 'company_ids' in account._fields and account.company_ids and schedule.company_id not in account.company_ids:
                raise ValidationError(_('Recognition accounts must be available for %s.') % schedule.company_id.display_name)
            if 'company_id' in account._fields and account.company_id and account.company_id != schedule.company_id:
                raise ValidationError(_('Recognition accounts must be available for %s.') % schedule.company_id.display_name)

    def _prepare_move_vals(self, schedule, lines, amount, balance_amount):
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
            'date': self.posting_date,
            'journal_id': self.recognition_journal_id.id,
            'company_id': schedule.company_id.id,
            'ref': name,
            'line_ids': [
                (0, 0, {
                    'name': name,
                    'account_id': self.deferred_revenue_account_id.id,
                    'partner_id': schedule.partner_id.id,
                    'balance': balance_amount,
                    **debit_currency_vals,
                }),
                (0, 0, {
                    'name': name,
                    'account_id': self.revenue_account_id.id,
                    'partner_id': schedule.partner_id.id,
                    'balance': -balance_amount,
                    **credit_currency_vals,
                }),
            ],
        }

    def action_post_recognition(self):
        self.ensure_one()
        self._check_post_access()
        self._validate_post_configuration()
        due_lines = self._get_due_lines()
        if not due_lines:
            raise ValidationError(_('No due draft recognition lines match the current posting filters.'))

        lines_by_schedule = defaultdict(lambda: self.env['subscription.deferred.revenue.line'])
        for line in due_lines:
            lines_by_schedule[line.schedule_id] |= line

        moves = self.env['account.move']
        for schedule, lines in lines_by_schedule.items():
            self._validate_schedule_configuration(schedule)
            amount = schedule.currency_id.round(sum(lines.mapped('amount')))
            if schedule.currency_id.is_zero(amount) or amount < 0:
                raise ValidationError(_('Recognition amount must be positive for %s.') % schedule.display_name)
            balance_amount = schedule.currency_id._convert(
                amount,
                schedule.company_id.currency_id,
                schedule.company_id,
                self.posting_date,
            )
            balance_amount = schedule.company_id.currency_id.round(balance_amount)
            if schedule.company_id.currency_id.is_zero(balance_amount) or balance_amount < 0:
                raise ValidationError(_('Recognition balance amount must be positive for %s.') % schedule.display_name)
            move = self.env['account.move'].create(self._prepare_move_vals(schedule, lines, amount, balance_amount))
            move.action_post()
            lines.with_context(deferred_revenue_internal_write=True).write({
                'state': 'recognized',
                'recognized_date': self.posting_date,
                'recognition_move_id': move.id,
            })
            schedule.message_post(
                body=_('Posted revenue recognition journal entry %(move)s for %(amount)s.') % {
                    'move': move.display_name,
                    'amount': schedule.currency_id.format(amount),
                }
            )
            moves |= move

        return {
            'type': 'ir.actions.act_window',
            'name': _('Recognition Journal Entries'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', moves.ids)],
        }
