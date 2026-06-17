from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class SubscriptionMrrMovementAnomaly(models.Model):
    _name = 'subscription.mrr.movement.anomaly'
    _description = 'Subscription MRR Movement Anomaly'
    _order = 'closing_date desc, opening_date desc, anomaly_type, company_id, currency_id, subscription_plan_id'

    opening_date = fields.Date(string='Opening Date', required=True, readonly=True, index=True)
    closing_date = fields.Date(string='Closing Date', required=True, readonly=True, index=True)
    bucket_key = fields.Char(string='Bucket Key', required=True, readonly=True, index=True)
    anomaly_type = fields.Selection([
        ('movement_only', 'Movement Only'),
        ('missing_plan', 'Missing Plan'),
    ], string='Anomaly Type', required=True, readonly=True, index=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True, index=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True, index=True)
    subscription_plan_id = fields.Many2one('subscription.plan', string='Subscription Plan', readonly=True, index=True)
    generated_at = fields.Datetime(string='Generated At', readonly=True)
    movement_count = fields.Integer(string='Movements', readonly=True)

    new_mrr = fields.Monetary(string='New MRR', currency_field='currency_id', readonly=True)
    expansion_mrr = fields.Monetary(string='Expansion MRR', currency_field='currency_id', readonly=True)
    contraction_mrr = fields.Monetary(string='Contraction MRR', currency_field='currency_id', readonly=True)
    churned_mrr = fields.Monetary(string='Churned MRR', currency_field='currency_id', readonly=True)
    net_movement_mrr = fields.Monetary(string='Net Movement MRR', currency_field='currency_id', readonly=True)

    _movement_anomaly_bucket_unique = models.Constraint(
        'UNIQUE(opening_date, closing_date, bucket_key)',
        'Only one movement anomaly can exist for the same date range and bucket.',
    )

    @api.constrains('opening_date', 'closing_date')
    def _check_date_range(self):
        for anomaly in self:
            if anomaly.opening_date >= anomaly.closing_date:
                raise ValidationError(_("Closing date must be after opening date."))

    @api.model
    def _check_anomaly_manager_access(self):
        if not self.env.su and not self.env.user.has_group('subscription_suite.group_subscription_manager'):
            raise AccessError(_("Only subscription managers can generate MRR movement anomalies."))

    @api.model
    def _prepare_anomaly_domain(self, opening_date, closing_date, company=None, plan=None):
        domain = [
            ('opening_date', '=', opening_date),
            ('closing_date', '=', closing_date),
        ]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        return domain

    @api.model
    def _prepare_movement_domain(self, opening_date, closing_date, company=None, plan=None):
        domain = [
            ('movement_date', '>', opening_date),
            ('movement_date', '<=', closing_date),
        ]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        return domain

    @api.model
    def _snapshot_keys(self, snapshot_date, company=None, plan=None):
        domain = [('snapshot_date', '=', snapshot_date)]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        snapshots = self.env['subscription.mrr.snapshot'].search(domain)
        return {
            (snapshot.company_id.id, snapshot.currency_id.id, snapshot.subscription_plan_id.id)
            for snapshot in snapshots
        }

    @api.model
    def _movement_key(self, movement):
        return (
            movement.company_id.id or False,
            movement.currency_id.id or False,
            movement.subscription_plan_id.id or False,
        )

    @api.model
    def _bucket_key(self, key):
        company_id, currency_id, plan_id = key
        return '%s:%s:%s' % (company_id or 'no_company', currency_id or 'no_currency', plan_id or 'no_plan')

    @api.model
    def _get_anomaly_values(self, opening_date, closing_date, company=None, plan=None):
        opening_keys = self._snapshot_keys(opening_date, company=company, plan=plan)
        closing_keys = self._snapshot_keys(closing_date, company=company, plan=plan)
        known_snapshot_keys = opening_keys | closing_keys
        buckets = defaultdict(lambda: {
            'movement_count': 0,
            'new_mrr': 0.0,
            'expansion_mrr': 0.0,
            'contraction_mrr': 0.0,
            'churned_mrr': 0.0,
            'net_movement_mrr': 0.0,
        })
        field_by_type = {
            'new': 'new_mrr',
            'expansion': 'expansion_mrr',
            'contraction': 'contraction_mrr',
            'churn': 'churned_mrr',
        }
        movements = self.env['subscription.mrr.movement'].search(
            self._prepare_movement_domain(opening_date, closing_date, company=company, plan=plan)
        )
        for movement in movements:
            key = self._movement_key(movement)
            if key in known_snapshot_keys:
                continue
            bucket = buckets[key]
            amount = movement.amount or 0.0
            bucket['movement_count'] += 1
            bucket[field_by_type[movement.movement_type]] += amount
            bucket['net_movement_mrr'] += amount

        generated_at = fields.Datetime.now()
        values = []
        for key, bucket in buckets.items():
            company_id, currency_id, plan_id = key
            values.append({
                'opening_date': opening_date,
                'closing_date': closing_date,
                'bucket_key': self._bucket_key(key),
                'anomaly_type': 'missing_plan' if not plan_id else 'movement_only',
                'company_id': company_id or False,
                'currency_id': currency_id or False,
                'subscription_plan_id': plan_id or False,
                'generated_at': generated_at,
                'movement_count': bucket['movement_count'],
                'new_mrr': bucket['new_mrr'],
                'expansion_mrr': bucket['expansion_mrr'],
                'contraction_mrr': bucket['contraction_mrr'],
                'churned_mrr': bucket['churned_mrr'],
                'net_movement_mrr': bucket['net_movement_mrr'],
            })
        return values

    @api.model
    def generate_for_period(self, opening_date, closing_date, company=None, plan=None):
        self._check_anomaly_manager_access()
        if opening_date >= closing_date:
            raise ValidationError(_("Closing date must be after opening date."))
        if isinstance(company, int):
            company = self.env['res.company'].browse(company)
        if isinstance(plan, int):
            plan = self.env['subscription.plan'].browse(plan)
        self.search(self._prepare_anomaly_domain(opening_date, closing_date, company=company, plan=plan)).unlink()
        values = self._get_anomaly_values(opening_date, closing_date, company=company, plan=plan)
        return self.create(values) if values else self.browse()

    def action_view_movements(self):
        self.ensure_one()
        domain = [
            ('movement_date', '>', self.opening_date),
            ('movement_date', '<=', self.closing_date),
        ]
        if self.company_id:
            domain.append(('company_id', '=', self.company_id.id))
        else:
            domain.append(('company_id', '=', False))
        if self.currency_id:
            domain.append(('currency_id', '=', self.currency_id.id))
        else:
            domain.append(('currency_id', '=', False))
        if self.subscription_plan_id:
            domain.append(('subscription_plan_id', '=', self.subscription_plan_id.id))
        else:
            domain.append(('subscription_plan_id', '=', False))
        return {
            'name': _('MRR Movements'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.mrr.movement',
            'view_mode': 'list,form,pivot,graph',
            'domain': domain,
        }
