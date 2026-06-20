from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models


class SubscriptionDeferredRevenueRecognitionRun(models.Model):
    _name = 'subscription.deferred.revenue.recognition.run'
    _description = 'Subscription Deferred Revenue Recognition Posting Run'
    _order = 'run_datetime desc, id desc'

    name = fields.Char(default='New', readonly=True, copy=False)
    run_datetime = fields.Datetime(default=fields.Datetime.now, readonly=True)
    company_id = fields.Many2one('res.company', required=True, readonly=True, index=True)
    cutoff_date = fields.Date(required=True, readonly=True, index=True)
    cutoff_rule = fields.Selection(
        [
            ('today', 'Today'),
            ('prior_month_end', 'Prior Month End'),
        ],
        required=True,
        readonly=True,
    )
    status = fields.Selection(
        [
            ('success', 'Success'),
            ('partial', 'Partial'),
            ('failed', 'Failed'),
            ('skipped', 'Skipped'),
        ],
        required=True,
        readonly=True,
        default='skipped',
        index=True,
    )
    created_move_count = fields.Integer(readonly=True)
    recognized_line_count = fields.Integer(readonly=True)
    skipped_schedule_count = fields.Integer(readonly=True)
    error_notes = fields.Text(readonly=True)
    move_ids = fields.Many2many(
        'account.move',
        'subscription_deferred_revenue_recognition_run_move_rel',
        'run_id',
        'move_id',
        string='Recognition Journal Entries',
        readonly=True,
    )
    line_ids = fields.Many2many(
        'subscription.deferred.revenue.line',
        'subscription_deferred_revenue_recognition_run_line_rel',
        'run_id',
        'line_id',
        string='Recognized Lines',
        readonly=True,
    )

    @api.model
    def _config_enabled(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            'subscription_suite.enable_scheduled_recognition_posting',
            'False',
        ) == 'True'

    @api.model
    def _config_cutoff_rule(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            'subscription_suite.scheduled_recognition_cutoff_rule',
            'prior_month_end',
        )

    @api.model
    def _cutoff_date_for_rule(self, rule, today=False):
        today = today or fields.Date.context_today(self)
        if rule == 'today':
            return today
        return today.replace(day=1) - relativedelta(days=1)

    @api.model
    def _recognition_config(self):
        Schedule = self.env['subscription.deferred.revenue']
        return {
            'recognition_journal': self.env['account.journal'].browse(
                Schedule._get_config_m2o('subscription_suite.recognition_journal_id')
            ),
            'deferred_revenue_account': self.env['account.account'].browse(
                Schedule._get_config_m2o('subscription_suite.deferred_revenue_account_id')
            ),
            'revenue_account': self.env['account.account'].browse(
                Schedule._get_config_m2o('subscription_suite.revenue_account_id')
            ),
        }

    @api.model
    def _create_run(self, company, cutoff_date, cutoff_rule, status, moves=False, lines=False, skipped=0, errors=False):
        moves = moves or self.env['account.move']
        lines = lines or self.env['subscription.deferred.revenue.line']
        return self.create({
            'name': _('Recognition Posting Run - %(company)s - %(date)s') % {
                'company': company.display_name,
                'date': cutoff_date,
            },
            'company_id': company.id,
            'cutoff_date': cutoff_date,
            'cutoff_rule': cutoff_rule,
            'status': status,
            'created_move_count': len(moves),
            'recognized_line_count': len(lines),
            'skipped_schedule_count': skipped,
            'error_notes': '\n'.join(errors or []),
            'move_ids': [(6, 0, moves.ids)],
            'line_ids': [(6, 0, lines.ids)],
        })

    @api.model
    def _post_company_due_lines(self, company, cutoff_date, cutoff_rule):
        config = self._recognition_config()
        Line = self.env['subscription.deferred.revenue.line']
        due_lines = Line._get_lines_for_recognition_preview(cutoff_date, company=company)
        if not due_lines:
            return self._create_run(
                company,
                cutoff_date,
                cutoff_rule,
                'skipped',
                errors=[_('No due draft recognition lines matched the cutoff.')],
            )

        lines_by_schedule = {}
        for line in due_lines:
            lines_by_schedule.setdefault(line.schedule_id, Line)
            lines_by_schedule[line.schedule_id] |= line

        moves = self.env['account.move']
        recognized_lines = Line
        skipped = 0
        errors = []
        for schedule, lines in lines_by_schedule.items():
            try:
                schedule_moves = lines._post_recognition_lines(
                    cutoff_date,
                    config['recognition_journal'],
                    config['deferred_revenue_account'],
                    config['revenue_account'],
                )
            except Exception as error:
                skipped += 1
                errors.append('%s: %s' % (schedule.display_name, error))
                continue
            moves |= schedule_moves
            recognized_lines |= lines

        if moves and errors:
            status = 'partial'
        elif moves:
            status = 'success'
        else:
            status = 'failed'
        return self._create_run(
            company,
            cutoff_date,
            cutoff_rule,
            status,
            moves=moves,
            lines=recognized_lines,
            skipped=skipped,
            errors=errors,
        )

    @api.model
    def _run_scheduled_recognition_posting(self, force=False, company=False, today=False):
        if not force and not self._config_enabled():
            return self.browse()
        cutoff_rule = self._config_cutoff_rule()
        cutoff_date = self._cutoff_date_for_rule(cutoff_rule, today=today)
        companies = company or self.env['res.company'].search([])
        runs = self.browse()
        for run_company in companies:
            runs |= self._post_company_due_lines(run_company, cutoff_date, cutoff_rule)
        return runs

    @api.model
    def _cron_post_scheduled_recognition(self):
        return self._run_scheduled_recognition_posting()

    def action_view_moves(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Recognition Journal Entries'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.move_ids.ids)],
        }

    def action_view_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Recognized Lines'),
            'res_model': 'subscription.deferred.revenue.line',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.line_ids.ids)],
        }
