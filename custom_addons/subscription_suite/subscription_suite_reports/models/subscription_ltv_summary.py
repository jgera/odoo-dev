from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class SubscriptionLtvSummary(models.Model):
    _name = 'subscription.ltv.summary'
    _description = 'Subscription LTV Summary'
    _order = 'closing_date desc, opening_date desc, cohort_end_month desc, company_id, currency_id, subscription_plan_id'

    opening_date = fields.Date(string='Opening Date', required=True, readonly=True, index=True)
    closing_date = fields.Date(string='Closing Date', required=True, readonly=True, index=True)
    cohort_start_month = fields.Date(string='Cohort Start Month', required=True, readonly=True, index=True)
    cohort_end_month = fields.Date(string='Cohort End Month', required=True, readonly=True, index=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, readonly=True, index=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, readonly=True, index=True)
    subscription_plan_id = fields.Many2one('subscription.plan', string='Subscription Plan', readonly=True, index=True)
    bucket_key = fields.Char(string='Bucket Key', required=True, readonly=True, index=True)
    generated_at = fields.Datetime(string='Generated At', readonly=True)
    status = fields.Selection(
        [
            ('ready', 'Ready'),
            ('missing_arpu_summary', 'Missing ARPU Summary'),
            ('missing_retention_cohort', 'Missing Retention Cohort'),
            ('zero_churn_rate', 'Zero Churn Rate'),
        ],
        string='Status',
        required=True,
        readonly=True,
        index=True,
    )

    arpu = fields.Monetary(string='ARPU', currency_field='currency_id', readonly=True)
    starting_subscription_count = fields.Integer(string='Starting Subscriptions', readonly=True)
    churned_subscription_count = fields.Integer(string='Churned Subscriptions', readonly=True)
    churn_rate = fields.Float(string='Churn Rate (%)', readonly=True)
    churn_rate_decimal = fields.Float(string='Churn Rate Decimal', digits=(16, 6), readonly=True)
    estimated_lifetime_months = fields.Float(string='Estimated Lifetime Months', digits=(16, 2), readonly=True)
    ltv = fields.Monetary(string='LTV', currency_field='currency_id', readonly=True)

    _ltv_summary_bucket_unique = models.Constraint(
        'UNIQUE(opening_date, closing_date, cohort_start_month, cohort_end_month, bucket_key)',
        'Only one LTV summary can exist for the same period, cohort range, and bucket.',
    )

    @api.constrains('opening_date', 'closing_date', 'cohort_start_month', 'cohort_end_month')
    def _check_periods(self):
        for summary in self:
            if summary.opening_date >= summary.closing_date:
                raise ValidationError(_("Closing date must be after opening date."))
            if summary.cohort_start_month > summary.cohort_end_month:
                raise ValidationError(_("Cohort end month must be on or after cohort start month."))
            if summary.cohort_start_month != self._month_start(summary.cohort_start_month):
                raise ValidationError(_("Cohort start month must be the first day of a month."))
            if summary.cohort_end_month != self._month_start(summary.cohort_end_month):
                raise ValidationError(_("Cohort end month must be the first day of a month."))

    @api.model
    def _check_ltv_manager_access(self):
        if not self.env.su and not self.env.user.has_group('subscription_suite.group_subscription_manager'):
            raise AccessError(_("Only subscription managers can generate LTV summaries."))

    @api.model
    def _month_start(self, value):
        value = fields.Date.to_date(value)
        return value.replace(day=1)

    @api.model
    def _month_end(self, value):
        return self._month_start(value) + relativedelta(months=1, days=-1)

    @api.model
    def _bucket_key(self, company_id, currency_id, plan_id):
        return '%s:%s:%s' % (company_id, currency_id, plan_id or 'all_plans')

    @api.model
    def _prepare_existing_domain(self, opening_date, closing_date, cohort_start_month, cohort_end_month, company=None, plan=None):
        domain = [
            ('opening_date', '=', opening_date),
            ('closing_date', '=', closing_date),
            ('cohort_start_month', '=', cohort_start_month),
            ('cohort_end_month', '=', cohort_end_month),
        ]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        return domain

    @api.model
    def _arpu_buckets(self, opening_date, closing_date, company=None, plan=None):
        domain = [('opening_date', '=', opening_date), ('closing_date', '=', closing_date)]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        buckets = {}
        for summary in self.env['subscription.arpu.summary'].search(domain):
            key = (
                summary.company_id.id,
                summary.currency_id.id,
                summary.subscription_plan_id.id or False,
            )
            buckets[key] = {
                'arpu': summary.arpu,
                'status': summary.status,
            }
        return buckets

    @api.model
    def _retention_buckets(self, cohort_start_month, cohort_end_month, closing_date, company=None, plan=None):
        closing_month = self._month_start(closing_date)
        domain = [
            ('cohort_month', '>=', cohort_start_month),
            ('cohort_month', '<=', cohort_end_month),
            ('period_month', '=', closing_month),
        ]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        buckets = defaultdict(lambda: {'starting_subscription_count': 0, 'churned_subscription_count': 0})
        for cohort in self.env['subscription.retention.cohort'].search(domain):
            key = (
                cohort.company_id.id,
                cohort.currency_id.id,
                cohort.subscription_plan_id.id or False,
            )
            buckets[key]['starting_subscription_count'] += cohort.starting_subscription_count
            buckets[key]['churned_subscription_count'] += cohort.churned_subscription_count
        return buckets

    @api.model
    def _status_for_bucket(self, arpu_bucket, retention_bucket, churn_rate_decimal):
        if not arpu_bucket or arpu_bucket.get('status') != 'ready':
            return 'missing_arpu_summary'
        if not retention_bucket:
            return 'missing_retention_cohort'
        if not churn_rate_decimal:
            return 'zero_churn_rate'
        return 'ready'

    @api.model
    def _summary_values(self, opening_date, closing_date, cohort_start_month, cohort_end_month, company=None, plan=None):
        arpu_buckets = self._arpu_buckets(opening_date, closing_date, company=company, plan=plan)
        retention_buckets = self._retention_buckets(
            cohort_start_month,
            cohort_end_month,
            closing_date,
            company=company,
            plan=plan,
        )
        bucket_keys = set(arpu_buckets) | set(retention_buckets)
        values = []
        generated_at = fields.Datetime.now()
        for company_id, currency_id, plan_id in sorted(bucket_keys):
            arpu_bucket = arpu_buckets.get((company_id, currency_id, plan_id))
            retention_bucket = retention_buckets.get((company_id, currency_id, plan_id))
            starting_count = retention_bucket['starting_subscription_count'] if retention_bucket else 0
            churned_count = retention_bucket['churned_subscription_count'] if retention_bucket else 0
            churn_rate_decimal = (churned_count / starting_count) if starting_count else 0.0
            churn_rate = churn_rate_decimal * 100.0
            status = self._status_for_bucket(arpu_bucket, retention_bucket, churn_rate_decimal)
            arpu = arpu_bucket['arpu'] if arpu_bucket else 0.0
            estimated_lifetime_months = 1.0 / churn_rate_decimal if status == 'ready' else 0.0
            ltv = arpu / churn_rate_decimal if status == 'ready' else 0.0
            values.append({
                'opening_date': opening_date,
                'closing_date': closing_date,
                'cohort_start_month': cohort_start_month,
                'cohort_end_month': cohort_end_month,
                'company_id': company_id,
                'currency_id': currency_id,
                'subscription_plan_id': plan_id,
                'bucket_key': self._bucket_key(company_id, currency_id, plan_id),
                'generated_at': generated_at,
                'status': status,
                'arpu': arpu,
                'starting_subscription_count': starting_count,
                'churned_subscription_count': churned_count,
                'churn_rate': churn_rate,
                'churn_rate_decimal': churn_rate_decimal,
                'estimated_lifetime_months': estimated_lifetime_months,
                'ltv': ltv,
            })
        return values

    @api.model
    def generate_for_period(self, opening_date, closing_date, cohort_start_month, cohort_end_month, company=None, plan=None):
        self._check_ltv_manager_access()
        opening_date = fields.Date.to_date(opening_date)
        closing_date = fields.Date.to_date(closing_date)
        cohort_start_month = self._month_start(cohort_start_month)
        cohort_end_month = self._month_start(cohort_end_month)
        if opening_date >= closing_date:
            raise ValidationError(_("Closing date must be after opening date."))
        if cohort_start_month > cohort_end_month:
            raise ValidationError(_("Cohort end month must be on or after cohort start month."))
        if isinstance(company, int):
            company = self.env['res.company'].browse(company)
        if isinstance(plan, int):
            plan = self.env['subscription.plan'].browse(plan)
        self.search(
            self._prepare_existing_domain(
                opening_date,
                closing_date,
                cohort_start_month,
                cohort_end_month,
                company=company,
                plan=plan,
            )
        ).unlink()
        values = self._summary_values(
            opening_date,
            closing_date,
            cohort_start_month,
            cohort_end_month,
            company=company,
            plan=plan,
        )
        return self.create(values) if values else self.browse()

    def _arpu_domain(self):
        self.ensure_one()
        domain = [
            ('opening_date', '=', self.opening_date),
            ('closing_date', '=', self.closing_date),
            ('company_id', '=', self.company_id.id),
            ('currency_id', '=', self.currency_id.id),
        ]
        if self.subscription_plan_id:
            domain.append(('subscription_plan_id', '=', self.subscription_plan_id.id))
        return domain

    def _retention_domain(self):
        self.ensure_one()
        domain = [
            ('cohort_month', '>=', self.cohort_start_month),
            ('cohort_month', '<=', self.cohort_end_month),
            ('period_month', '=', self._month_start(self.closing_date)),
            ('company_id', '=', self.company_id.id),
            ('currency_id', '=', self.currency_id.id),
        ]
        if self.subscription_plan_id:
            domain.append(('subscription_plan_id', '=', self.subscription_plan_id.id))
        return domain

    def _source_subscription_domain(self):
        self.ensure_one()
        domain = [
            ('is_subscription', '=', True),
            ('company_id', '=', self.company_id.id),
            ('currency_id', '=', self.currency_id.id),
            ('subscription_plan_id', '!=', False),
            '|',
            '&',
            ('subscription_start_date', '>=', self.cohort_start_month),
            ('subscription_start_date', '<=', self._month_end(self.cohort_end_month)),
            '&',
            ('subscription_start_date', '=', False),
            '&',
            ('trial_start_date', '>=', self.cohort_start_month),
            ('trial_start_date', '<=', self._month_end(self.cohort_end_month)),
        ]
        if self.subscription_plan_id:
            domain.append(('subscription_plan_id', '=', self.subscription_plan_id.id))
        return domain

    def action_view_arpu_summaries(self):
        self.ensure_one()
        return {
            'name': _('Source ARPU Summaries'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.arpu.summary',
            'view_mode': 'list,form,pivot,graph',
            'domain': self._arpu_domain(),
        }

    def action_view_retention_cohorts(self):
        self.ensure_one()
        return {
            'name': _('Source Retention Cohorts'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.retention.cohort',
            'view_mode': 'list,form,pivot,graph',
            'domain': self._retention_domain(),
        }

    def action_view_source_subscriptions(self):
        self.ensure_one()
        return {
            'name': _('Source Subscriptions'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': self._source_subscription_domain(),
        }
