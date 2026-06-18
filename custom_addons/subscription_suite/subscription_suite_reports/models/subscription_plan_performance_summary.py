from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class SubscriptionPlanPerformanceSummary(models.Model):
    _name = 'subscription.plan.performance.summary'
    _description = 'Subscription Plan Performance Summary'
    _order = 'closing_mrr desc, net_new_mrr desc, closing_date desc, company_id, currency_id, subscription_plan_id'

    opening_date = fields.Date(string='Opening Date', required=True, readonly=True, index=True)
    closing_date = fields.Date(string='Closing Date', required=True, readonly=True, index=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, readonly=True, index=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, readonly=True, index=True)
    subscription_plan_id = fields.Many2one('subscription.plan', string='Subscription Plan', required=True, readonly=True, index=True)
    bucket_key = fields.Char(string='Bucket Key', required=True, readonly=True, index=True)
    generated_at = fields.Datetime(string='Generated At', readonly=True)
    status = fields.Selection(
        [
            ('ready', 'Ready'),
            ('missing_snapshot', 'Missing Snapshot'),
            ('missing_kpi_summary', 'Missing KPI Summary'),
            ('missing_arpu_summary', 'Missing ARPU Summary'),
            ('missing_ltv_summary', 'Missing LTV Summary'),
            ('missing_forecast', 'Missing Forecast'),
        ],
        string='Status',
        required=True,
        readonly=True,
        index=True,
    )

    opening_mrr = fields.Monetary(string='Opening MRR', currency_field='currency_id', readonly=True)
    closing_mrr = fields.Monetary(string='Closing MRR', currency_field='currency_id', readonly=True)
    arr = fields.Monetary(string='ARR', currency_field='currency_id', readonly=True)
    net_new_mrr = fields.Monetary(string='Net New MRR', currency_field='currency_id', readonly=True)
    arpu = fields.Monetary(string='ARPU', currency_field='currency_id', readonly=True)
    ltv = fields.Monetary(string='LTV', currency_field='currency_id', readonly=True)

    subscription_count = fields.Integer(string='Subscriptions', readonly=True)
    trial_count = fields.Integer(string='Trial Subscriptions', readonly=True)
    active_count = fields.Integer(string='Active Subscriptions', readonly=True)
    paused_count = fields.Integer(string='Paused Subscriptions', readonly=True)
    past_due_count = fields.Integer(string='Past Due Subscriptions', readonly=True)
    cancelled_count = fields.Integer(string='Cancelled Subscriptions', readonly=True)
    expired_count = fields.Integer(string='Expired Subscriptions', readonly=True)

    churned_subscription_count = fields.Integer(string='Churned Subscriptions', readonly=True)
    churned_mrr = fields.Monetary(string='Churned MRR', currency_field='currency_id', readonly=True)
    feedback_coverage = fields.Float(string='Feedback Coverage (%)', readonly=True)
    upcoming_invoice_mrr = fields.Monetary(string='Upcoming Invoice MRR', currency_field='currency_id', readonly=True)
    scheduled_churn_mrr = fields.Monetary(string='Scheduled Churn MRR', currency_field='currency_id', readonly=True)
    net_forecast_mrr = fields.Monetary(string='Net Forecast MRR', currency_field='currency_id', readonly=True)

    _plan_performance_summary_bucket_unique = models.Constraint(
        'UNIQUE(opening_date, closing_date, bucket_key)',
        'Only one top plan summary can exist for the same period and bucket.',
    )

    @api.constrains('opening_date', 'closing_date')
    def _check_period_dates(self):
        for summary in self:
            if summary.opening_date >= summary.closing_date:
                raise ValidationError(_("Closing date must be after opening date."))

    @api.model
    def _check_top_plan_manager_access(self):
        if not self.env.su and not self.env.user.has_group('subscription_suite.group_subscription_manager'):
            raise AccessError(_("Only subscription managers can generate top plan summaries."))

    @api.model
    def _month_start(self, value):
        value = fields.Date.to_date(value)
        return value.replace(day=1)

    @api.model
    def _bucket_key(self, company_id, currency_id, plan_id):
        return '%s:%s:%s' % (company_id, currency_id, plan_id)

    @api.model
    def _prepare_existing_domain(self, opening_date, closing_date, company=None, plan=None):
        domain = [('opening_date', '=', opening_date), ('closing_date', '=', closing_date)]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        return domain

    @api.model
    def _period_domain(self, opening_date, closing_date, company=None, plan=None):
        domain = [('opening_date', '=', opening_date), ('closing_date', '=', closing_date)]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        return domain

    @api.model
    def _snapshot_buckets(self, snapshot_date, company=None, plan=None):
        domain = [('snapshot_date', '=', snapshot_date)]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        return {
            (snapshot.company_id.id, snapshot.currency_id.id, snapshot.subscription_plan_id.id): snapshot
            for snapshot in self.env['subscription.mrr.snapshot'].search(domain)
        }

    @api.model
    def _record_buckets(self, model_name, domain):
        return {
            (record.company_id.id, record.currency_id.id, record.subscription_plan_id.id): record
            for record in self.env[model_name].search(domain)
            if record.subscription_plan_id
        }

    @api.model
    def _forecast_buckets(self, opening_date, closing_date, company=None, plan=None):
        domain = [
            ('forecast_month', '>=', self._month_start(opening_date)),
            ('forecast_month', '<=', self._month_start(closing_date)),
            ('subscription_plan_id', '!=', False),
        ]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        buckets = defaultdict(lambda: {
            'upcoming_invoice_mrr': 0.0,
            'scheduled_churn_mrr': 0.0,
            'net_forecast_mrr': 0.0,
        })
        for forecast in self.env['subscription.revenue.forecast'].search(domain):
            key = (forecast.company_id.id, forecast.currency_id.id, forecast.subscription_plan_id.id)
            buckets[key]['upcoming_invoice_mrr'] += forecast.upcoming_invoice_mrr
            buckets[key]['scheduled_churn_mrr'] += forecast.scheduled_churn_mrr
            buckets[key]['net_forecast_mrr'] += forecast.net_forecast_mrr
        return buckets

    @api.model
    def _churn_reason_buckets(self, opening_date, closing_date, company=None, plan=None):
        domain = [
            ('opening_date', '=', opening_date),
            ('closing_date', '=', closing_date),
            ('reason_bucket', '=', 'all_reasons'),
            ('subscription_plan_id', '!=', False),
        ]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        return {
            (summary.company_id.id, summary.currency_id.id, summary.subscription_plan_id.id): summary
            for summary in self.env['subscription.churn.reason.summary'].search(domain)
        }

    @api.model
    def _status_for_bucket(self, opening_snapshot, closing_snapshot, kpi, arpu, ltv, forecast):
        if not opening_snapshot or not closing_snapshot:
            return 'missing_snapshot'
        if not kpi or kpi.status != 'ready':
            return 'missing_kpi_summary'
        if not arpu or arpu.status != 'ready':
            return 'missing_arpu_summary'
        if not ltv or ltv.status != 'ready':
            return 'missing_ltv_summary'
        if not forecast:
            return 'missing_forecast'
        return 'ready'

    @api.model
    def _summary_values(self, opening_date, closing_date, company=None, plan=None):
        opening_snapshots = self._snapshot_buckets(opening_date, company=company, plan=plan)
        closing_snapshots = self._snapshot_buckets(closing_date, company=company, plan=plan)
        kpis = self._record_buckets(
            'subscription.mrr.kpi.summary',
            self._period_domain(opening_date, closing_date, company=company, plan=plan),
        )
        arpus = self._record_buckets(
            'subscription.arpu.summary',
            self._period_domain(opening_date, closing_date, company=company, plan=plan),
        )
        ltvs = self._record_buckets(
            'subscription.ltv.summary',
            self._period_domain(opening_date, closing_date, company=company, plan=plan),
        )
        forecasts = self._forecast_buckets(opening_date, closing_date, company=company, plan=plan)
        churn_reasons = self._churn_reason_buckets(opening_date, closing_date, company=company, plan=plan)
        bucket_keys = set(opening_snapshots) | set(closing_snapshots) | set(kpis) | set(arpus) | set(ltvs) | set(forecasts)
        values = []
        generated_at = fields.Datetime.now()
        for key in sorted(bucket_keys):
            company_id, currency_id, plan_id = key
            opening_snapshot = opening_snapshots.get(key)
            closing_snapshot = closing_snapshots.get(key)
            kpi = kpis.get(key)
            arpu = arpus.get(key)
            ltv = ltvs.get(key)
            forecast = forecasts.get(key)
            churn_reason = churn_reasons.get(key)
            values.append({
                'opening_date': opening_date,
                'closing_date': closing_date,
                'company_id': company_id,
                'currency_id': currency_id,
                'subscription_plan_id': plan_id,
                'bucket_key': self._bucket_key(company_id, currency_id, plan_id),
                'generated_at': generated_at,
                'status': self._status_for_bucket(opening_snapshot, closing_snapshot, kpi, arpu, ltv, forecast),
                'opening_mrr': opening_snapshot.total_recurring_mrr if opening_snapshot else 0.0,
                'closing_mrr': closing_snapshot.total_recurring_mrr if closing_snapshot else 0.0,
                'arr': closing_snapshot.arr if closing_snapshot else 0.0,
                'net_new_mrr': kpi.net_new_mrr if kpi else 0.0,
                'arpu': arpu.arpu if arpu else 0.0,
                'ltv': ltv.ltv if ltv else 0.0,
                'subscription_count': closing_snapshot.subscription_count if closing_snapshot else 0,
                'trial_count': closing_snapshot.trial_count if closing_snapshot else 0,
                'active_count': closing_snapshot.active_count if closing_snapshot else 0,
                'paused_count': closing_snapshot.paused_count if closing_snapshot else 0,
                'past_due_count': closing_snapshot.past_due_count if closing_snapshot else 0,
                'cancelled_count': closing_snapshot.cancelled_count if closing_snapshot else 0,
                'expired_count': closing_snapshot.expired_count if closing_snapshot else 0,
                'churned_subscription_count': churn_reason.churned_subscription_count if churn_reason else 0,
                'churned_mrr': churn_reason.churned_mrr if churn_reason else 0.0,
                'feedback_coverage': churn_reason.feedback_coverage if churn_reason else 0.0,
                'upcoming_invoice_mrr': forecast['upcoming_invoice_mrr'] if forecast else 0.0,
                'scheduled_churn_mrr': forecast['scheduled_churn_mrr'] if forecast else 0.0,
                'net_forecast_mrr': forecast['net_forecast_mrr'] if forecast else 0.0,
            })
        return values

    @api.model
    def generate_for_period(self, opening_date, closing_date, company=None, plan=None):
        self._check_top_plan_manager_access()
        opening_date = fields.Date.to_date(opening_date)
        closing_date = fields.Date.to_date(closing_date)
        if opening_date >= closing_date:
            raise ValidationError(_("Closing date must be after opening date."))
        if isinstance(company, int):
            company = self.env['res.company'].browse(company)
        if isinstance(plan, int):
            plan = self.env['subscription.plan'].browse(plan)
        self.search(self._prepare_existing_domain(opening_date, closing_date, company=company, plan=plan)).unlink()
        values = self._summary_values(opening_date, closing_date, company=company, plan=plan)
        return self.create(values) if values else self.browse()

    def _source_domain(self, model_name):
        self.ensure_one()
        domain = [
            ('company_id', '=', self.company_id.id),
            ('currency_id', '=', self.currency_id.id),
            ('subscription_plan_id', '=', self.subscription_plan_id.id),
        ]
        if model_name == 'subscription.mrr.snapshot':
            domain.append(('snapshot_date', 'in', [self.opening_date, self.closing_date]))
        elif model_name == 'subscription.revenue.forecast':
            domain += [
                ('forecast_month', '>=', self._month_start(self.opening_date)),
                ('forecast_month', '<=', self._month_start(self.closing_date)),
            ]
        else:
            domain += [('opening_date', '=', self.opening_date), ('closing_date', '=', self.closing_date)]
        return domain

    def _subscription_domain(self):
        self.ensure_one()
        return [
            ('is_subscription', '=', True),
            ('company_id', '=', self.company_id.id),
            ('currency_id', '=', self.currency_id.id),
            ('subscription_plan_id', '=', self.subscription_plan_id.id),
            ('subscription_state', 'in', list(self.env['subscription.mrr.snapshot']._get_snapshot_states())),
        ]

    def _action_for_source(self, name, model_name, view_mode='list,form,pivot,graph'):
        self.ensure_one()
        return {
            'name': name,
            'type': 'ir.actions.act_window',
            'res_model': model_name,
            'view_mode': view_mode,
            'domain': self._source_domain(model_name),
        }

    def action_view_snapshots(self):
        return self._action_for_source(_('Source MRR Snapshots'), 'subscription.mrr.snapshot')

    def action_view_kpi_summaries(self):
        return self._action_for_source(_('Source MRR KPI Summaries'), 'subscription.mrr.kpi.summary')

    def action_view_arpu_summaries(self):
        return self._action_for_source(_('Source ARPU Summaries'), 'subscription.arpu.summary')

    def action_view_ltv_summaries(self):
        return self._action_for_source(_('Source LTV Summaries'), 'subscription.ltv.summary')

    def action_view_churn_reason_summaries(self):
        return self._action_for_source(_('Source Churn Reason Summaries'), 'subscription.churn.reason.summary')

    def action_view_forecasts(self):
        return self._action_for_source(_('Source Revenue Forecasts'), 'subscription.revenue.forecast')

    def action_view_source_subscriptions(self):
        self.ensure_one()
        return {
            'name': _('Source Subscriptions'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': self._subscription_domain(),
        }
