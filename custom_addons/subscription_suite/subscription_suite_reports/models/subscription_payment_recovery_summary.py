from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class SubscriptionPaymentRecoverySummary(models.Model):
    _name = 'subscription.payment.recovery.summary'
    _description = 'Subscription Payment Recovery Summary'
    _order = 'closing_date desc, company_id, currency_id, subscription_plan_id, recovery_source'

    opening_date = fields.Date(string='Opening Date', required=True, readonly=True, index=True)
    closing_date = fields.Date(string='Closing Date', required=True, readonly=True, index=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, readonly=True, index=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, readonly=True, index=True)
    subscription_plan_id = fields.Many2one('subscription.plan', string='Subscription Plan', readonly=True, index=True)
    recovery_source = fields.Selection(
        [
            ('portal', 'Portal'),
            ('cron', 'Cron'),
            ('manual', 'Manual'),
            ('all', 'All Sources'),
        ],
        string='Recovery Source',
        required=True,
        readonly=True,
        index=True,
    )
    bucket_key = fields.Char(string='Bucket Key', required=True, readonly=True, index=True)
    status = fields.Selection([('ready', 'Ready')], string='Status', required=True, readonly=True, default='ready')
    generated_at = fields.Datetime(string='Generated At', readonly=True)

    failed_attempt_count = fields.Integer(string='Failed Attempts', readonly=True)
    pending_attempt_count = fields.Integer(string='Pending Attempts', readonly=True)
    recovered_attempt_count = fields.Integer(string='Recovered Attempts', readonly=True)
    cancelled_error_attempt_count = fields.Integer(string='Cancelled/Error Attempts', readonly=True)
    manual_action_required_count = fields.Integer(string='Manual Action Required', readonly=True)
    retry_exhausted_dunning_count = fields.Integer(string='Retry Exhausted', readonly=True)
    final_dunning_action_count = fields.Integer(string='Final Dunning Actions', readonly=True)
    open_recovery_invoice_count = fields.Integer(string='Open Recovery Invoices', readonly=True)
    at_risk_subscription_count = fields.Integer(string='At-Risk Subscriptions', readonly=True)

    recovery_amount = fields.Monetary(string='Recovery Amount', currency_field='currency_id', readonly=True)
    recovered_amount = fields.Monetary(string='Recovered Amount', currency_field='currency_id', readonly=True)
    pending_amount = fields.Monetary(string='Pending Amount', currency_field='currency_id', readonly=True)
    failed_amount = fields.Monetary(string='Failed Amount', currency_field='currency_id', readonly=True)
    mrr_at_risk = fields.Monetary(string='MRR at Risk', currency_field='currency_id', readonly=True)

    _payment_recovery_summary_bucket_unique = models.Constraint(
        'UNIQUE(opening_date, closing_date, bucket_key)',
        'Only one payment recovery summary can exist for the same period and bucket.',
    )

    @api.constrains('opening_date', 'closing_date')
    def _check_period(self):
        for summary in self:
            if summary.opening_date and summary.closing_date and summary.opening_date > summary.closing_date:
                raise ValidationError(_("Opening date must be on or before closing date."))

    @api.model
    def _check_payment_recovery_manager_access(self):
        if not self.env.su and not self.env.user.has_group('subscription_suite.group_subscription_manager'):
            raise AccessError(_("Only subscription managers can generate payment recovery summaries."))

    @api.model
    def _bucket_key(self, company, currency, plan, source):
        return '%s:%s:%s:%s' % (
            company.id,
            currency.id,
            plan.id if plan else 'all-plans',
            source,
        )

    @api.model
    def _period_attempt_domain(self, opening_date, closing_date):
        start_dt = fields.Datetime.to_datetime(opening_date)
        end_dt = fields.Datetime.to_datetime(closing_date + relativedelta(days=1))
        return [('attempt_date', '>=', start_dt), ('attempt_date', '<', end_dt)]

    @api.model
    def _period_date_domain(self, field_name, opening_date, closing_date):
        return [(field_name, '>=', opening_date), (field_name, '<=', closing_date)]

    @api.model
    def _scope_domain(self, opening_date, closing_date, company=None, plan=None, source=False):
        domain = [('opening_date', '=', opening_date), ('closing_date', '=', closing_date)]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        if source:
            domain.append(('recovery_source', '=', source))
        return domain

    @api.model
    def _subscription_scope_domain(self, company=None, plan=None, currency=None):
        domain = [
            ('is_subscription', '=', True),
            ('subscription_quote_type', '=', False),
            ('subscription_plan_id', '!=', False),
        ]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        if currency:
            domain.append(('currency_id', '=', currency.id))
        return domain

    @api.model
    def _open_invoice_domain(self, opening_date, closing_date, company=None, plan=None, currency=None):
        domain = [
            ('subscription_id', '!=', False),
            ('subscription_id.subscription_plan_id', '!=', False),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial']),
            ('invoice_date', '<=', closing_date),
        ]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_id.subscription_plan_id', '=', plan.id))
        if currency:
            domain.append(('currency_id', '=', currency.id))
        return domain

    @api.model
    def _bucket_plans_for_subscription(self, subscription, plan_filter=False):
        if plan_filter:
            return [plan_filter] if subscription.subscription_plan_id == plan_filter else []
        return [subscription.subscription_plan_id, False]

    @api.model
    def _empty_bucket(self, opening_date, closing_date, company, currency, plan, source, generated_at):
        return {
            'opening_date': opening_date,
            'closing_date': closing_date,
            'company_id': company.id,
            'currency_id': currency.id,
            'subscription_plan_id': plan.id if plan else False,
            'recovery_source': source,
            'bucket_key': self._bucket_key(company, currency, plan, source),
            'status': 'ready',
            'generated_at': generated_at,
            'failed_attempt_count': 0,
            'pending_attempt_count': 0,
            'recovered_attempt_count': 0,
            'cancelled_error_attempt_count': 0,
            'manual_action_required_count': 0,
            'retry_exhausted_dunning_count': 0,
            'final_dunning_action_count': 0,
            'open_recovery_invoice_count': 0,
            'at_risk_subscription_count': 0,
            'recovery_amount': 0.0,
            'recovered_amount': 0.0,
            'pending_amount': 0.0,
            'failed_amount': 0.0,
            'mrr_at_risk': 0.0,
            '_mrr_subscription_ids': {},
            '_at_risk_subscription_ids': set(),
            '_attempt_invoice_ids': set(),
        }

    @api.model
    def _get_bucket(self, buckets, opening_date, closing_date, generated_at, company, currency, plan, source):
        key = self._bucket_key(company, currency, plan, source)
        if key not in buckets:
            buckets[key] = self._empty_bucket(opening_date, closing_date, company, currency, plan, source, generated_at)
        return buckets[key]

    @api.model
    def _add_mrr_at_risk(self, bucket, subscription, amount=False):
        bucket['_mrr_subscription_ids'][subscription.id] = amount if amount is not False else subscription.mrr

    @api.model
    def _attempt_domain(self, opening_date, closing_date, company=None, plan=None, source=False, currency=None):
        domain = self._period_attempt_domain(opening_date, closing_date) + [
            ('subscription_id', '!=', False),
            ('subscription_id.subscription_plan_id', '!=', False),
        ]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_id.subscription_plan_id', '=', plan.id))
        if source and source != 'all':
            domain.append(('source', '=', source))
        if currency:
            domain.append(('currency_id', '=', currency.id))
        return domain

    @api.model
    def _dunning_domain(self, opening_date, closing_date, company=None, plan=None, currency=None):
        domain = self._period_attempt_domain(opening_date, closing_date) + [
            ('subscription_id', '!=', False),
            ('subscription_id.subscription_plan_id', '!=', False),
        ]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_id.subscription_plan_id', '=', plan.id))
        if currency:
            domain.append(('currency_id', '=', currency.id))
        return domain

    @api.model
    def _at_risk_domain(self, opening_date, closing_date, company=None, plan=None, currency=None):
        domain = self._period_date_domain('as_of_date', opening_date, closing_date)
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        if currency:
            domain.append(('currency_id', '=', currency.id))
        return domain

    @api.model
    def generate_for_period(self, opening_date, closing_date, company=None, plan=None, source=False):
        self._check_payment_recovery_manager_access()
        opening_date = fields.Date.to_date(opening_date)
        closing_date = fields.Date.to_date(closing_date)
        if not opening_date or not closing_date:
            raise ValidationError(_("Opening and closing dates are required."))
        if opening_date > closing_date:
            raise ValidationError(_("Opening date must be on or before closing date."))
        if isinstance(company, int):
            company = self.env['res.company'].browse(company)
        if isinstance(plan, int):
            plan = self.env['subscription.plan'].browse(plan)
        if source and source not in dict(self._fields['recovery_source'].selection):
            raise ValidationError(_("Unsupported recovery source: %s") % source)

        self.search(self._scope_domain(opening_date, closing_date, company=company, plan=plan, source=source)).unlink()

        generated_at = fields.Datetime.now()
        buckets = {}
        PaymentAttempt = self.env['subscription.payment.attempt'].sudo()
        AccountMove = self.env['account.move'].sudo()
        DunningAttempt = self.env['subscription.dunning.attempt'].sudo()
        AtRiskSummary = self.env['subscription.at.risk.summary'].sudo()

        attempt_domain = self._attempt_domain(opening_date, closing_date, company=company, plan=plan, source=source)
        for attempt in PaymentAttempt.search(attempt_domain):
            subscription = attempt.subscription_id
            if not subscription or not subscription.subscription_plan_id:
                continue
            row_sources = []
            if source == 'all':
                row_sources = ['all']
            elif source:
                row_sources = [source]
            else:
                row_sources = [attempt.source, 'all']
            for bucket_plan in self._bucket_plans_for_subscription(subscription, plan_filter=plan):
                for row_source in row_sources:
                    bucket = self._get_bucket(
                        buckets,
                        opening_date,
                        closing_date,
                        generated_at,
                        attempt.company_id,
                        attempt.currency_id,
                        bucket_plan,
                        row_source,
                    )
                    amount = attempt.amount or 0.0
                    if attempt.invoice_id:
                        bucket['_attempt_invoice_ids'].add(attempt.invoice_id.id)
                    if attempt.state == 'success':
                        bucket['recovered_attempt_count'] += 1
                        bucket['recovered_amount'] += amount
                    elif attempt.state == 'pending':
                        bucket['pending_attempt_count'] += 1
                        bucket['pending_amount'] += amount
                        bucket['recovery_amount'] += amount
                        self._add_mrr_at_risk(bucket, subscription)
                    elif attempt.state == 'failed':
                        bucket['failed_attempt_count'] += 1
                        bucket['failed_amount'] += amount
                        bucket['recovery_amount'] += amount
                        self._add_mrr_at_risk(bucket, subscription)
                    elif attempt.state in ('cancelled', 'error'):
                        bucket['cancelled_error_attempt_count'] += 1
                        bucket['failed_amount'] += amount
                        bucket['recovery_amount'] += amount
                        self._add_mrr_at_risk(bucket, subscription)
                    if attempt.recovery_required and attempt.state in ('failed', 'cancelled', 'error'):
                        bucket['manual_action_required_count'] += 1
                        self._add_mrr_at_risk(bucket, subscription)

        if not source or source == 'all':
            for invoice in AccountMove.search(self._open_invoice_domain(opening_date, closing_date, company=company, plan=plan)):
                subscription = invoice.subscription_id
                if not subscription or not subscription.subscription_plan_id:
                    continue
                for bucket_plan in self._bucket_plans_for_subscription(subscription, plan_filter=plan):
                    bucket = self._get_bucket(
                        buckets,
                        opening_date,
                        closing_date,
                        generated_at,
                        invoice.company_id,
                        invoice.currency_id,
                        bucket_plan,
                        'all',
                    )
                    if invoice.id in bucket['_attempt_invoice_ids']:
                        continue
                    bucket['open_recovery_invoice_count'] += 1
                    bucket['recovery_amount'] += invoice.amount_residual or 0.0
                    self._add_mrr_at_risk(bucket, subscription)

            dunning_domain = self._dunning_domain(opening_date, closing_date, company=company, plan=plan)
            for dunning in DunningAttempt.search(dunning_domain):
                subscription = dunning.subscription_id
                if not subscription or not subscription.subscription_plan_id:
                    continue
                for bucket_plan in self._bucket_plans_for_subscription(subscription, plan_filter=plan):
                    bucket = self._get_bucket(
                        buckets,
                        opening_date,
                        closing_date,
                        generated_at,
                        dunning.company_id,
                        dunning.currency_id,
                        bucket_plan,
                        'all',
                    )
                    if dunning.retry_exhausted:
                        bucket['retry_exhausted_dunning_count'] += 1
                        self._add_mrr_at_risk(bucket, subscription)
                    if dunning.action_type in ('final_cancel', 'final_pause', 'final_none'):
                        bucket['final_dunning_action_count'] += 1
                        self._add_mrr_at_risk(bucket, subscription)

            at_risk_domain = self._at_risk_domain(opening_date, closing_date, company=company, plan=plan)
            for risk in AtRiskSummary.search(at_risk_domain):
                subscription = risk.subscription_id
                if not subscription or not subscription.subscription_plan_id:
                    continue
                for bucket_plan in self._bucket_plans_for_subscription(subscription, plan_filter=plan):
                    bucket = self._get_bucket(
                        buckets,
                        opening_date,
                        closing_date,
                        generated_at,
                        risk.company_id,
                        risk.currency_id,
                        bucket_plan,
                        'all',
                    )
                    if subscription.id not in bucket['_at_risk_subscription_ids']:
                        bucket['_at_risk_subscription_ids'].add(subscription.id)
                        bucket['at_risk_subscription_count'] += 1
                    self._add_mrr_at_risk(bucket, subscription, risk.mrr_at_risk)

        values = []
        for bucket in buckets.values():
            bucket['mrr_at_risk'] = sum(bucket.pop('_mrr_subscription_ids').values())
            bucket.pop('_at_risk_subscription_ids')
            bucket.pop('_attempt_invoice_ids')
            if any(
                bucket[field_name]
                for field_name in (
                    'failed_attempt_count',
                    'pending_attempt_count',
                    'recovered_attempt_count',
                    'cancelled_error_attempt_count',
                    'manual_action_required_count',
                    'retry_exhausted_dunning_count',
                    'final_dunning_action_count',
                    'open_recovery_invoice_count',
                    'at_risk_subscription_count',
                )
            ):
                values.append(bucket)
        return self.create(values) if values else self.browse()

    def _plan_domain(self):
        self.ensure_one()
        return [('subscription_plan_id', '=', self.subscription_plan_id.id)] if self.subscription_plan_id else [
            ('subscription_plan_id', '!=', False)
        ]

    def _base_subscription_domain(self):
        self.ensure_one()
        domain = [
            ('is_subscription', '=', True),
            ('subscription_quote_type', '=', False),
            ('company_id', '=', self.company_id.id),
            ('currency_id', '=', self.currency_id.id),
        ] + self._plan_domain()
        return domain

    def _source_subscription_ids(self):
        self.ensure_one()
        subscriptions = self.env['sale.order'].sudo().browse()
        attempts = self.env['subscription.payment.attempt'].sudo().search(
            self._attempt_domain(
                self.opening_date,
                self.closing_date,
                company=self.company_id,
                plan=self.subscription_plan_id,
                source=False if self.recovery_source == 'all' else self.recovery_source,
                currency=self.currency_id,
            )
        )
        subscriptions |= attempts.mapped('subscription_id')
        if self.recovery_source == 'all':
            invoices = self.env['account.move'].sudo().search(
                self._open_invoice_domain(
                    self.opening_date,
                    self.closing_date,
                    company=self.company_id,
                    plan=self.subscription_plan_id,
                    currency=self.currency_id,
                )
            )
            dunning = self.env['subscription.dunning.attempt'].sudo().search(
                self._dunning_domain(
                    self.opening_date,
                    self.closing_date,
                    company=self.company_id,
                    plan=self.subscription_plan_id,
                    currency=self.currency_id,
                )
            )
            risks = self.env['subscription.at.risk.summary'].sudo().search(
                self._at_risk_domain(
                    self.opening_date,
                    self.closing_date,
                    company=self.company_id,
                    plan=self.subscription_plan_id,
                    currency=self.currency_id,
                )
            )
            subscriptions |= invoices.mapped('subscription_id') | dunning.mapped('subscription_id') | risks.mapped('subscription_id')
        return subscriptions.ids

    def action_view_payment_attempts(self):
        self.ensure_one()
        return {
            'name': _('Payment Attempts'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.payment.attempt',
            'view_mode': 'list,form',
            'domain': self._attempt_domain(
                self.opening_date,
                self.closing_date,
                company=self.company_id,
                plan=self.subscription_plan_id,
                source=False if self.recovery_source == 'all' else self.recovery_source,
                currency=self.currency_id,
            ),
        }

    def action_view_open_invoices(self):
        self.ensure_one()
        return {
            'name': _('Open Recovery Invoices'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': self._open_invoice_domain(
                self.opening_date,
                self.closing_date,
                company=self.company_id,
                plan=self.subscription_plan_id,
                currency=self.currency_id,
            ),
        }

    def action_view_subscriptions(self):
        self.ensure_one()
        return {
            'name': _('Recovery Subscriptions'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self._source_subscription_ids())],
        }

    def action_view_dunning_attempts(self):
        self.ensure_one()
        return {
            'name': _('Dunning Attempts'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.dunning.attempt',
            'view_mode': 'list,form',
            'domain': self._dunning_domain(
                self.opening_date,
                self.closing_date,
                company=self.company_id,
                plan=self.subscription_plan_id,
                currency=self.currency_id,
            ),
        }

    def action_view_at_risk_summaries(self):
        self.ensure_one()
        return {
            'name': _('At-Risk Subscriptions'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.at.risk.summary',
            'view_mode': 'list,form',
            'domain': self._at_risk_domain(
                self.opening_date,
                self.closing_date,
                company=self.company_id,
                plan=self.subscription_plan_id,
                currency=self.currency_id,
            ),
        }
