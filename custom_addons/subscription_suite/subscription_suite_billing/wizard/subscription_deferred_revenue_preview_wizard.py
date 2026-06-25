from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class SubscriptionDeferredRevenuePreviewWizard(models.TransientModel):
    _name = 'subscription.deferred.revenue.preview.wizard'
    _description = 'Preview Subscription Revenue Recognition'

    cutoff_date = fields.Date(default=fields.Date.context_today, required=True)
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
        default=lambda self: self.env['subscription.deferred.revenue']._get_company_recognition_config()[
            'recognition_journal'
        ],
    )
    deferred_revenue_account_id = fields.Many2one(
        'account.account',
        string='Deferred Revenue Account',
        default=lambda self: self.env['subscription.deferred.revenue']._get_company_recognition_config()[
            'deferred_revenue_account'
        ],
    )
    revenue_account_id = fields.Many2one(
        'account.account',
        default=lambda self: self.env['subscription.deferred.revenue']._get_company_recognition_config()[
            'revenue_account'
        ],
    )
    line_ids = fields.One2many(
        'subscription.deferred.revenue.preview.line',
        'wizard_id',
        string='Preview Lines',
        readonly=True,
    )
    preview_summary = fields.Html(compute='_compute_preview_summary')

    def _check_preview_access(self):
        if not self.env.user.has_group('subscription_suite.group_subscription_manager'):
            raise AccessError(_('Only subscription managers can preview revenue recognition.'))

    def _validate_preview_configuration(self):
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
        self.env['subscription.deferred.revenue.line']._validate_recognition_configuration(
            self.company_id,
            self.recognition_journal_id,
            self.deferred_revenue_account_id,
            self.revenue_account_id,
            schedule=self.schedule_id,
        )
        if self.schedule_id:
            if self.subscription_id and self.schedule_id.subscription_id != self.subscription_id:
                raise ValidationError(_('The selected schedule does not belong to the selected subscription.'))

    @api.depends('line_ids.amount', 'line_ids.company_id', 'line_ids.currency_id')
    def _compute_preview_summary(self):
        for wizard in self:
            if not wizard.line_ids:
                wizard.preview_summary = _('<p>No due recognition lines match the current preview filters.</p>')
                continue
            totals = defaultdict(float)
            for line in wizard.line_ids:
                totals[(line.company_id, line.currency_id)] += line.amount
            rows = []
            for (company, currency), amount in sorted(
                totals.items(),
                key=lambda item: (item[0][0].display_name, item[0][1].name),
            ):
                rows.append(
                    '<tr><td>%s</td><td>%s</td><td class="text-end">%s</td></tr>' % (
                        company.display_name,
                        currency.name,
                        currency.format(amount),
                    )
                )
            wizard.preview_summary = _(
                '<table class="table table-sm"><thead><tr><th>Company</th><th>Currency</th><th class="text-end">Amount</th></tr></thead><tbody>%s</tbody></table>'
            ) % ''.join(rows)

    def action_preview(self):
        self.ensure_one()
        self._check_preview_access()
        self._validate_preview_configuration()
        self.line_ids.unlink()
        due_lines = self.env['subscription.deferred.revenue.line']._get_lines_for_recognition_preview(
            self.cutoff_date,
            company=self.company_id,
            subscription=self.subscription_id,
            schedule=self.schedule_id,
        )
        preview_lines = []
        for line in due_lines:
            preview_lines.append((0, 0, {
                'schedule_line_id': line.id,
                'schedule_id': line.schedule_id.id,
                'invoice_id': line.invoice_id.id,
                'subscription_id': line.subscription_id.id,
                'partner_id': line.partner_id.id,
                'period_start': line.period_start,
                'period_end': line.period_end,
                'amount': line.amount,
                'company_id': line.company_id.id,
                'currency_id': line.currency_id.id,
                'recognition_journal_id': self.recognition_journal_id.id,
                'debit_account_id': self.deferred_revenue_account_id.id,
                'credit_account_id': self.revenue_account_id.id,
            }))
        self.write({'line_ids': preview_lines})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Preview Revenue Recognition'),
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }


class SubscriptionDeferredRevenuePreviewLine(models.TransientModel):
    _name = 'subscription.deferred.revenue.preview.line'
    _description = 'Subscription Revenue Recognition Preview Line'
    _order = 'company_id, currency_id, period_end, id'

    wizard_id = fields.Many2one(
        'subscription.deferred.revenue.preview.wizard',
        required=True,
        ondelete='cascade',
    )
    schedule_line_id = fields.Many2one('subscription.deferred.revenue.line', readonly=True)
    schedule_id = fields.Many2one('subscription.deferred.revenue', readonly=True)
    invoice_id = fields.Many2one('account.move', readonly=True)
    subscription_id = fields.Many2one('sale.order', readonly=True)
    partner_id = fields.Many2one('res.partner', readonly=True)
    period_start = fields.Date(readonly=True)
    period_end = fields.Date(readonly=True)
    amount = fields.Monetary(currency_field='currency_id', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    currency_id = fields.Many2one('res.currency', readonly=True)
    recognition_journal_id = fields.Many2one('account.journal', readonly=True)
    debit_account_id = fields.Many2one('account.account', readonly=True)
    credit_account_id = fields.Many2one('account.account', readonly=True)
