from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class SubscriptionAtRiskSummary(models.Model):
    _name = 'subscription.at.risk.summary'
    _description = 'Subscription At-Risk Summary'
    _order = 'risk_score desc, mrr_at_risk desc, as_of_date desc, subscription_id'

    as_of_date = fields.Date(string='As Of Date', required=True, readonly=True, index=True)
    lookahead_days = fields.Integer(string='Lookahead Days', required=True, readonly=True, index=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, readonly=True, index=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, readonly=True, index=True)
    subscription_plan_id = fields.Many2one('subscription.plan', string='Subscription Plan', required=True, readonly=True, index=True)
    subscription_id = fields.Many2one('sale.order', string='Subscription', required=True, readonly=True, index=True)
    partner_id = fields.Many2one('res.partner', string='Customer', required=True, readonly=True, index=True)
    bucket_key = fields.Char(string='Bucket Key', required=True, readonly=True, index=True)
    generated_at = fields.Datetime(string='Generated At', readonly=True)

    risk_score = fields.Integer(string='Risk Score', readonly=True, index=True)
    risk_bucket = fields.Selection(
        [
            ('low', 'Low'),
            ('medium', 'Medium'),
            ('high', 'High'),
            ('critical', 'Critical'),
        ],
        string='Risk Bucket',
        required=True,
        readonly=True,
        index=True,
    )
    mrr_at_risk = fields.Monetary(string='MRR at Risk', currency_field='currency_id', readonly=True)

    is_past_due = fields.Boolean(string='Past Due', readonly=True, index=True)
    has_pending_cancellation = fields.Boolean(string='Pending Cancellation', readonly=True, index=True)
    scheduled_churn_within_period = fields.Boolean(string='Scheduled Churn in Lookahead', readonly=True, index=True)
    has_open_recovery_invoice = fields.Boolean(string='Open Recovery Invoice', readonly=True, index=True)
    missing_primary_payment_method = fields.Boolean(string='Missing Primary Payment Method', readonly=True, index=True)
    upcoming_invoice_within_period = fields.Boolean(string='Upcoming Invoice in Lookahead', readonly=True, index=True)
    renewal_due_within_period = fields.Boolean(string='Renewal Due in Lookahead', readonly=True, index=True)

    open_recovery_invoice_count = fields.Integer(string='Open Recovery Invoices', readonly=True)
    failed_payment_attempt_count = fields.Integer(string='Failed Payment Attempts', readonly=True)
    pending_payment_attempt_count = fields.Integer(string='Pending Payment Attempts', readonly=True)
    active_dunning_attempt_count = fields.Integer(string='Active Dunning Attempts', readonly=True)
    failed_dunning_attempt_count = fields.Integer(string='Failed Dunning Attempts', readonly=True)
    retry_exhausted_dunning_attempt_count = fields.Integer(string='Retry Exhausted Attempts', readonly=True)
    final_dunning_action_count = fields.Integer(string='Final Dunning Actions', readonly=True)

    latest_payment_attempt_id = fields.Many2one('subscription.payment.attempt', string='Latest Payment Attempt', readonly=True)
    latest_dunning_attempt_id = fields.Many2one('subscription.dunning.attempt', string='Latest Dunning Attempt', readonly=True)

    _at_risk_summary_bucket_unique = models.Constraint(
        'UNIQUE(as_of_date, lookahead_days, bucket_key)',
        'Only one at-risk summary can exist for the same date, lookahead, and subscription.',
    )

    @api.constrains('lookahead_days')
    def _check_lookahead_days(self):
        for summary in self:
            if summary.lookahead_days < 0:
                raise ValidationError(_("Lookahead days cannot be negative."))

    @api.model
    def _check_at_risk_manager_access(self):
        if not self.env.su and not self.env.user.has_group('subscription_suite.group_subscription_manager'):
            raise AccessError(_("Only subscription managers can generate at-risk subscription summaries."))

    @api.model
    def _bucket_key(self, subscription):
        return '%s:%s:%s:%s' % (
            subscription.company_id.id,
            subscription.currency_id.id,
            subscription.subscription_plan_id.id,
            subscription.id,
        )

    @api.model
    def _risk_bucket(self, score):
        if score >= 70:
            return 'critical'
        if score >= 45:
            return 'high'
        if score >= 20:
            return 'medium'
        return 'low'

    @api.model
    def _scope_domain(self, as_of_date, lookahead_days, company=None, plan=None):
        domain = [('as_of_date', '=', as_of_date), ('lookahead_days', '=', lookahead_days)]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        return domain

    @api.model
    def _subscription_domain(self, company=None, plan=None):
        domain = [
            ('is_subscription', '=', True),
            ('subscription_state', 'in', ['trial', 'active', 'paused', 'past_due']),
            ('subscription_plan_id', '!=', False),
            ('subscription_quote_type', '=', False),
        ]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        return domain

    @api.model
    def _date_in_period(self, value, start_date, end_date):
        value = fields.Date.to_date(value)
        return bool(value and start_date <= value <= end_date)

    @api.model
    def _open_invoice_domain(self, subscription):
        return [
            ('subscription_id', '=', subscription.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial']),
        ]

    @api.model
    def _payment_attempt_domain(self, subscription):
        return [
            ('subscription_id', '=', subscription.id),
            ('source', 'in', ['portal', 'cron']),
        ]

    @api.model
    def _dunning_attempt_domain(self, subscription):
        return [('subscription_id', '=', subscription.id)]

    @api.model
    def _risk_values_for_subscription(self, subscription, as_of_date, lookahead_days, generated_at):
        period_end = as_of_date + relativedelta(days=lookahead_days)
        PaymentAttempt = self.env['subscription.payment.attempt'].sudo()
        DunningAttempt = self.env['subscription.dunning.attempt'].sudo()
        AccountMove = self.env['account.move'].sudo()

        open_invoices = AccountMove.search(self._open_invoice_domain(subscription))
        payment_attempts = PaymentAttempt.search(self._payment_attempt_domain(subscription))
        failed_payment_attempts = payment_attempts.filtered(lambda attempt: attempt.state in ('failed', 'error', 'cancelled'))
        pending_payment_attempts = payment_attempts.filtered(lambda attempt: attempt.state == 'pending')
        dunning_attempts = DunningAttempt.search(self._dunning_attempt_domain(subscription))
        failed_dunning_attempts = dunning_attempts.filtered(lambda attempt: attempt.state == 'failed')
        active_dunning_attempts = dunning_attempts.filtered(lambda attempt: attempt.state in ('pending', 'sent', 'done'))
        retry_exhausted_attempts = dunning_attempts.filtered(lambda attempt: attempt.retry_exhausted)
        final_dunning_attempts = dunning_attempts.filtered(lambda attempt: attempt.action_type in ('final_cancel', 'final_pause', 'final_none'))

        is_past_due = subscription.subscription_state == 'past_due'
        has_open_recovery_invoice = bool(open_invoices)
        upcoming_invoice = self._date_in_period(subscription.next_invoice_date, as_of_date, period_end)
        renewal_due = self._date_in_period(subscription.subscription_end_date, as_of_date, period_end)
        scheduled_churn = bool(
            subscription.pending_cancellation
            and self._date_in_period(subscription.cancellation_effective_date, as_of_date, period_end)
        )
        missing_payment = bool(
            not subscription.payment_token_id
            and (is_past_due or has_open_recovery_invoice or upcoming_invoice)
        )

        score = 0
        if is_past_due:
            score += 40
        if has_open_recovery_invoice:
            score += 25
        if failed_payment_attempts:
            score += 20
        if retry_exhausted_attempts or final_dunning_attempts:
            score += 30
        if subscription.pending_cancellation or scheduled_churn:
            score += 35
        if missing_payment:
            score += 15
        if renewal_due:
            score += 10
        if upcoming_invoice:
            score += 5

        if score <= 0:
            return False

        latest_payment_attempt = payment_attempts[:1]
        latest_dunning_attempt = dunning_attempts[:1]
        return {
            'as_of_date': as_of_date,
            'lookahead_days': lookahead_days,
            'company_id': subscription.company_id.id,
            'currency_id': subscription.currency_id.id,
            'subscription_plan_id': subscription.subscription_plan_id.id,
            'subscription_id': subscription.id,
            'partner_id': subscription.partner_id.id,
            'bucket_key': self._bucket_key(subscription),
            'generated_at': generated_at,
            'risk_score': score,
            'risk_bucket': self._risk_bucket(score),
            'mrr_at_risk': subscription.mrr,
            'is_past_due': is_past_due,
            'has_pending_cancellation': bool(subscription.pending_cancellation),
            'scheduled_churn_within_period': scheduled_churn,
            'has_open_recovery_invoice': has_open_recovery_invoice,
            'missing_primary_payment_method': missing_payment,
            'upcoming_invoice_within_period': upcoming_invoice,
            'renewal_due_within_period': renewal_due,
            'open_recovery_invoice_count': len(open_invoices),
            'failed_payment_attempt_count': len(failed_payment_attempts),
            'pending_payment_attempt_count': len(pending_payment_attempts),
            'active_dunning_attempt_count': len(active_dunning_attempts),
            'failed_dunning_attempt_count': len(failed_dunning_attempts),
            'retry_exhausted_dunning_attempt_count': len(retry_exhausted_attempts),
            'final_dunning_action_count': len(final_dunning_attempts),
            'latest_payment_attempt_id': latest_payment_attempt.id if latest_payment_attempt else False,
            'latest_dunning_attempt_id': latest_dunning_attempt.id if latest_dunning_attempt else False,
        }

    @api.model
    def generate_for_date(self, as_of_date=None, lookahead_days=30, company=None, plan=None):
        self._check_at_risk_manager_access()
        as_of_date = fields.Date.to_date(as_of_date or fields.Date.context_today(self))
        lookahead_days = int(lookahead_days or 0)
        if lookahead_days < 0:
            raise ValidationError(_("Lookahead days cannot be negative."))
        if isinstance(company, int):
            company = self.env['res.company'].browse(company)
        if isinstance(plan, int):
            plan = self.env['subscription.plan'].browse(plan)

        self.search(self._scope_domain(as_of_date, lookahead_days, company=company, plan=plan)).unlink()
        generated_at = fields.Datetime.now()
        values = []
        for subscription in self.env['sale.order'].search(self._subscription_domain(company=company, plan=plan)):
            risk_values = self._risk_values_for_subscription(subscription, as_of_date, lookahead_days, generated_at)
            if risk_values:
                values.append(risk_values)
        return self.create(values) if values else self.browse()

    def _subscription_scope_domain(self):
        self.ensure_one()
        return [('id', '=', self.subscription_id.id)]

    def _invoice_domain(self):
        self.ensure_one()
        return self._open_invoice_domain(self.subscription_id)

    def _payment_attempt_scope_domain(self):
        self.ensure_one()
        return self._payment_attempt_domain(self.subscription_id)

    def _dunning_attempt_scope_domain(self):
        self.ensure_one()
        return self._dunning_attempt_domain(self.subscription_id)

    def action_view_subscription(self):
        self.ensure_one()
        return {
            'name': _('Subscription'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.subscription_id.id,
            'view_mode': 'form',
        }

    def action_view_open_invoices(self):
        self.ensure_one()
        return {
            'name': _('Open Recovery Invoices'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': self._invoice_domain(),
        }

    def action_view_payment_attempts(self):
        self.ensure_one()
        return {
            'name': _('Payment Attempts'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.payment.attempt',
            'view_mode': 'list,form',
            'domain': self._payment_attempt_scope_domain(),
        }

    def action_view_dunning_attempts(self):
        self.ensure_one()
        return {
            'name': _('Dunning Attempts'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.dunning.attempt',
            'view_mode': 'list,form',
            'domain': self._dunning_attempt_scope_domain(),
        }

    def action_view_cancellation_requests(self):
        self.ensure_one()
        return {
            'name': _('Cancellation Requests'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.cancellation.request',
            'view_mode': 'list,form',
            'domain': [('subscription_id', '=', self.subscription_id.id)],
        }
