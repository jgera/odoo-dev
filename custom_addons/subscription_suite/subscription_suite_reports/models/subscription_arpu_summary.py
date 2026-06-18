from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class SubscriptionArpuSummary(models.Model):
    _name = 'subscription.arpu.summary'
    _description = 'Subscription ARPU Summary'
    _order = 'closing_date desc, opening_date desc, company_id, currency_id, subscription_plan_id'

    opening_date = fields.Date(string='Opening Date', required=True, readonly=True, index=True)
    closing_date = fields.Date(string='Closing Date', required=True, readonly=True, index=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, readonly=True, index=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, readonly=True, index=True)
    subscription_plan_id = fields.Many2one('subscription.plan', string='Subscription Plan', readonly=True, index=True)
    bucket_key = fields.Char(string='Bucket Key', required=True, readonly=True, index=True)
    generated_at = fields.Datetime(string='Generated At', readonly=True)
    status = fields.Selection(
        [
            ('ready', 'Ready'),
            ('missing_opening_snapshot', 'Missing Opening Snapshot'),
            ('missing_closing_snapshot', 'Missing Closing Snapshot'),
        ],
        string='Status',
        required=True,
        readonly=True,
        index=True,
    )

    opening_subscription_count = fields.Integer(string='Opening Subscriptions', readonly=True)
    closing_subscription_count = fields.Integer(string='Closing Subscriptions', readonly=True)
    average_subscription_count = fields.Float(string='Average Subscriptions', digits=(16, 2), readonly=True)
    opening_mrr = fields.Monetary(string='Opening MRR', currency_field='currency_id', readonly=True)
    closing_mrr = fields.Monetary(string='Closing MRR', currency_field='currency_id', readonly=True)
    average_mrr = fields.Monetary(string='Average MRR', currency_field='currency_id', readonly=True)
    arpu = fields.Monetary(string='ARPU', currency_field='currency_id', readonly=True)

    _arpu_summary_bucket_unique = models.Constraint(
        'UNIQUE(opening_date, closing_date, bucket_key)',
        'Only one ARPU summary can exist for the same period and bucket.',
    )

    @api.constrains('opening_date', 'closing_date')
    def _check_period_dates(self):
        for summary in self:
            if summary.opening_date >= summary.closing_date:
                raise ValidationError(_("Closing date must be after opening date."))

    @api.model
    def _check_arpu_manager_access(self):
        if not self.env.su and not self.env.user.has_group('subscription_suite.group_subscription_manager'):
            raise AccessError(_("Only subscription managers can generate ARPU summaries."))

    @api.model
    def _bucket_key(self, company_id, currency_id, plan_id):
        return '%s:%s:%s' % (company_id, currency_id, plan_id or 'all_plans')

    @api.model
    def _snapshot_domain(self, snapshot_date, company=None, plan=None):
        domain = [('snapshot_date', '=', snapshot_date)]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        return domain

    @api.model
    def _prepare_existing_domain(self, opening_date, closing_date, company=None, plan=None):
        domain = [('opening_date', '=', opening_date), ('closing_date', '=', closing_date)]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        return domain

    @api.model
    def _snapshot_buckets(self, snapshot_date, company=None, plan=None):
        snapshots = self.env['subscription.mrr.snapshot'].search(
            self._snapshot_domain(snapshot_date, company=company, plan=plan)
        )
        buckets = {}
        all_plan_buckets = defaultdict(lambda: {'subscription_count': 0, 'total_recurring_mrr': 0.0})
        for snapshot in snapshots:
            key = (
                snapshot.company_id.id,
                snapshot.currency_id.id,
                snapshot.subscription_plan_id.id,
            )
            buckets[key] = {
                'subscription_count': snapshot.subscription_count,
                'total_recurring_mrr': snapshot.total_recurring_mrr,
            }
            if not plan:
                all_key = (snapshot.company_id.id, snapshot.currency_id.id, False)
                all_plan_buckets[all_key]['subscription_count'] += snapshot.subscription_count
                all_plan_buckets[all_key]['total_recurring_mrr'] += snapshot.total_recurring_mrr
        if not plan:
            buckets.update(all_plan_buckets)
        return buckets

    @api.model
    def _status_for_bucket(self, opening_bucket, closing_bucket):
        if not opening_bucket:
            return 'missing_opening_snapshot'
        if not closing_bucket:
            return 'missing_closing_snapshot'
        return 'ready'

    @api.model
    def _summary_values(self, opening_date, closing_date, company=None, plan=None):
        opening_buckets = self._snapshot_buckets(opening_date, company=company, plan=plan)
        closing_buckets = self._snapshot_buckets(closing_date, company=company, plan=plan)
        bucket_keys = set(opening_buckets) | set(closing_buckets)
        values = []
        generated_at = fields.Datetime.now()
        for company_id, currency_id, plan_id in sorted(bucket_keys):
            opening_bucket = opening_buckets.get((company_id, currency_id, plan_id))
            closing_bucket = closing_buckets.get((company_id, currency_id, plan_id))
            opening_count = opening_bucket['subscription_count'] if opening_bucket else 0
            closing_count = closing_bucket['subscription_count'] if closing_bucket else 0
            opening_mrr = opening_bucket['total_recurring_mrr'] if opening_bucket else 0.0
            closing_mrr = closing_bucket['total_recurring_mrr'] if closing_bucket else 0.0
            average_count = (opening_count + closing_count) / 2.0
            average_mrr = (opening_mrr + closing_mrr) / 2.0
            values.append({
                'opening_date': opening_date,
                'closing_date': closing_date,
                'company_id': company_id,
                'currency_id': currency_id,
                'subscription_plan_id': plan_id,
                'bucket_key': self._bucket_key(company_id, currency_id, plan_id),
                'generated_at': generated_at,
                'status': self._status_for_bucket(opening_bucket, closing_bucket),
                'opening_subscription_count': opening_count,
                'closing_subscription_count': closing_count,
                'average_subscription_count': average_count,
                'opening_mrr': opening_mrr,
                'closing_mrr': closing_mrr,
                'average_mrr': average_mrr,
                'arpu': average_count and average_mrr / average_count or 0.0,
            })
        return values

    @api.model
    def generate_for_period(self, opening_date, closing_date, company=None, plan=None):
        self._check_arpu_manager_access()
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

    def _base_snapshot_domain(self):
        self.ensure_one()
        domain = [
            ('snapshot_date', 'in', [self.opening_date, self.closing_date]),
            ('company_id', '=', self.company_id.id),
            ('currency_id', '=', self.currency_id.id),
        ]
        if self.subscription_plan_id:
            domain.append(('subscription_plan_id', '=', self.subscription_plan_id.id))
        return domain

    def _base_subscription_domain(self):
        self.ensure_one()
        domain = [
            ('is_subscription', '=', True),
            ('company_id', '=', self.company_id.id),
            ('currency_id', '=', self.currency_id.id),
            ('subscription_plan_id', '!=', False),
            ('subscription_state', 'in', list(self.env['subscription.mrr.snapshot']._get_snapshot_states())),
        ]
        if self.subscription_plan_id:
            domain.append(('subscription_plan_id', '=', self.subscription_plan_id.id))
        return domain

    def action_view_snapshots(self):
        self.ensure_one()
        return {
            'name': _('Source MRR Snapshots'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.mrr.snapshot',
            'view_mode': 'list,form,pivot,graph',
            'domain': self._base_snapshot_domain(),
        }

    def action_view_source_subscriptions(self):
        self.ensure_one()
        return {
            'name': _('Source Subscriptions'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': self._base_subscription_domain(),
        }
