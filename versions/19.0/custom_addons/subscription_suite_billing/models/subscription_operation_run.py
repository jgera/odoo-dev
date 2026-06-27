from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class SubscriptionOperationRun(models.Model):
    _name = 'subscription.operation.run'
    _description = 'Subscription Operational Run'
    _order = 'started_at desc, id desc'

    name = fields.Char(required=True, readonly=True, copy=False)
    operation_type = fields.Selection(
        [
            ('recurring_billing', 'Recurring Billing'),
            ('billing_retry', 'Billing Retry'),
            ('payment_collection', 'Payment Collection'),
            ('dunning', 'Dunning'),
            ('dunning_retry', 'Dunning Retry'),
            ('revenue_recognition', 'Revenue Recognition'),
            ('mrr_snapshot', 'MRR Snapshot'),
        ],
        required=True,
        readonly=True,
        index=True,
    )
    trigger = fields.Selection(
        [('cron', 'Scheduled'), ('manual', 'Manual')],
        required=True,
        default='cron',
        readonly=True,
        index=True,
    )
    state = fields.Selection(
        [
            ('running', 'Running'),
            ('success', 'Success'),
            ('partial', 'Partial'),
            ('failed', 'Failed'),
            ('skipped', 'Skipped'),
        ],
        required=True,
        default='running',
        readonly=True,
        index=True,
    )
    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company,
        readonly=True,
        index=True,
    )
    started_at = fields.Datetime(required=True, default=fields.Datetime.now, readonly=True, index=True)
    finished_at = fields.Datetime(readonly=True, index=True)
    duration_seconds = fields.Float(readonly=True)
    processed_count = fields.Integer(readonly=True)
    success_count = fields.Integer(readonly=True)
    failed_count = fields.Integer(readonly=True)
    skipped_count = fields.Integer(readonly=True)
    error_summary = fields.Text(readonly=True)
    reviewed = fields.Boolean(readonly=True, index=True)
    reviewed_by_id = fields.Many2one('res.users', readonly=True)
    reviewed_at = fields.Datetime(readonly=True)
    billing_run_ids = fields.Many2many(
        'subscription.billing.run',
        'subscription_operation_run_billing_run_rel',
        'operation_run_id',
        'billing_run_id',
        readonly=True,
    )
    billing_attempt_ids = fields.Many2many(
        'subscription.billing.attempt',
        'subscription_operation_run_billing_attempt_rel',
        'operation_run_id',
        'billing_attempt_id',
        readonly=True,
    )
    payment_attempt_ids = fields.Many2many(
        'subscription.payment.attempt',
        'subscription_operation_run_payment_attempt_rel',
        'operation_run_id',
        'payment_attempt_id',
        readonly=True,
    )
    recognition_run_ids = fields.Many2many(
        'subscription.deferred.revenue.recognition.run',
        'subscription_operation_run_recognition_run_rel',
        'operation_run_id',
        'recognition_run_id',
        readonly=True,
    )

    @api.model
    def _start_run(self, operation_type, company=False, trigger='cron'):
        company = company or self.env.company
        label = dict(self._fields['operation_type'].selection).get(operation_type, operation_type)
        return self.sudo().create({
            'name': _('%(operation)s - %(company)s - %(date)s') % {
                'operation': label,
                'company': company.display_name,
                'date': fields.Datetime.now(),
            },
            'operation_type': operation_type,
            'trigger': trigger,
            'company_id': company.id,
        })

    def _finish_run(
        self,
        processed=0,
        succeeded=0,
        failed=0,
        skipped=0,
        errors=False,
        state=False,
        **links,
    ):
        self.ensure_one()
        if not state:
            if failed and succeeded:
                state = 'partial'
            elif failed:
                state = 'failed'
            elif not processed:
                state = 'skipped'
            else:
                state = 'success'
        finished_at = fields.Datetime.now()
        duration = (finished_at - self.started_at).total_seconds() if self.started_at else 0.0
        values = {
            'state': state,
            'finished_at': finished_at,
            'duration_seconds': duration,
            'processed_count': processed,
            'success_count': succeeded,
            'failed_count': failed,
            'skipped_count': skipped,
            'error_summary': '\n'.join(errors or []),
        }
        for field_name, records in links.items():
            if field_name in self._fields and records:
                values[field_name] = [(6, 0, records.ids)]
        self.sudo().write(values)
        return self

    def _open_records(self, model, records, name):
        self.ensure_one()
        return {
            'name': name,
            'type': 'ir.actions.act_window',
            'res_model': model,
            'view_mode': 'list,form',
            'domain': [('id', 'in', records.ids)],
        }

    def action_view_billing_runs(self):
        return self._open_records('subscription.billing.run', self.billing_run_ids, _('Billing Runs'))

    def action_view_billing_attempts(self):
        return self._open_records('subscription.billing.attempt', self.billing_attempt_ids, _('Billing Attempts'))

    def action_view_payment_attempts(self):
        return self._open_records('subscription.payment.attempt', self.payment_attempt_ids, _('Payment Attempts'))

    def action_view_recognition_runs(self):
        return self._open_records(
            'subscription.deferred.revenue.recognition.run',
            self.recognition_run_ids,
            _('Recognition Runs'),
        )

    def action_mark_reviewed(self):
        self._check_manager()
        self.filtered(lambda run: run.state in ['failed', 'partial']).sudo().write({
            'reviewed': True,
            'reviewed_by_id': self.env.user.id,
            'reviewed_at': fields.Datetime.now(),
        })
        return True

    def action_reopen_review(self):
        self._check_manager()
        self.sudo().write({
            'reviewed': False,
            'reviewed_by_id': False,
            'reviewed_at': False,
        })
        return True

    @api.model
    def _check_manager(self):
        if not self.env.user.has_group('subscription_suite.group_subscription_manager'):
            raise AccessError(_('Only subscription managers can manage operational run retention.'))

    @api.model
    def _cron_cleanup_operation_runs(self):
        cutoff_now = fields.Datetime.now()
        removed = 0
        for company in self.env['res.company'].sudo().search([
            ('subscription_operation_cleanup_enabled', '=', True),
        ]):
            retention_days = max(company.subscription_operation_retention_days, 1)
            cutoff = cutoff_now - timedelta(days=retention_days)
            old_runs = self.sudo().search([
                ('company_id', '=', company.id),
                ('state', 'in', ['success', 'skipped']),
                ('finished_at', '<', cutoff),
            ])
            removed += len(old_runs)
            old_runs.unlink()
        return removed

    @api.model
    def action_cleanup_operation_runs(self):
        self._check_manager()
        return self._cron_cleanup_operation_runs()

    @api.model
    def _cron_send_daily_digest(self):
        yesterday = fields.Date.context_today(self) - timedelta(days=1)
        start = fields.Datetime.to_datetime(yesterday)
        end = start + timedelta(days=1)
        mails = self.env['mail.mail']
        for company in self.env['res.company'].sudo().search([
            ('subscription_operation_digest_enabled', '=', True),
        ]):
            recipients = company.subscription_operation_digest_recipient_ids.filtered(
                lambda user: user.active and user.email
            )
            if not recipients:
                continue
            runs = self.sudo().search([
                ('company_id', '=', company.id),
                ('state', 'in', ['partial', 'failed']),
                ('reviewed', '=', False),
                ('started_at', '>=', start),
                ('started_at', '<', end),
            ])
            payment_attempts = self.env['subscription.payment.attempt'].sudo().search([
                ('company_id', '=', company.id),
                ('state', 'in', ['failed', 'error', 'cancelled']),
                ('attempt_date', '>=', start),
                ('attempt_date', '<', end),
            ])
            dunning_attempts = self.env['subscription.dunning.attempt'] if 'subscription.dunning.attempt' in self.env else False
            exhausted = dunning_attempts.sudo().search([
                ('company_id', '=', company.id),
                ('retry_exhausted', '=', True),
                ('write_date', '>=', start),
                ('write_date', '<', end),
            ]) if dunning_attempts else self.env['subscription.payment.attempt'].browse()
            if not runs and not payment_attempts and not exhausted:
                continue
            body = _(
                '<p>Subscription operations requiring review for %(date)s:</p>'
                '<ul><li>Failed or partial runs: %(runs)s</li>'
                '<li>Failed payment attempts: %(payments)s</li>'
                '<li>Retry-exhausted dunning attempts: %(dunning)s</li></ul>'
            ) % {
                'date': yesterday,
                'runs': len(runs),
                'payments': len(payment_attempts),
                'dunning': len(exhausted),
            }
            mail = self.env['mail.mail'].sudo().create({
                'subject': _('Subscription Operations Digest - %s') % yesterday,
                'body_html': body,
                'email_to': ','.join(recipients.mapped('email')),
                'email_from': company.email or self.env.user.email_formatted,
            })
            mails |= mail
        return mails
