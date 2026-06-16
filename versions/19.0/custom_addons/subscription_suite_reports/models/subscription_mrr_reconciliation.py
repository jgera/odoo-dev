from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class SubscriptionMrrReconciliation(models.Model):
    _name = 'subscription.mrr.reconciliation'
    _description = 'Subscription MRR Reconciliation'
    _order = 'closing_date desc, opening_date desc, company_id, currency_id, subscription_plan_id'

    opening_date = fields.Date(string='Opening Snapshot Date', required=True, readonly=True, index=True)
    closing_date = fields.Date(string='Closing Snapshot Date', required=True, readonly=True, index=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, readonly=True, index=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, readonly=True, index=True)
    subscription_plan_id = fields.Many2one(
        'subscription.plan',
        string='Subscription Plan',
        required=True,
        readonly=True,
        index=True,
    )
    generated_at = fields.Datetime(string='Generated At', readonly=True)
    status = fields.Selection([
        ('matched', 'Matched'),
        ('variance', 'Variance'),
        ('missing_opening_snapshot', 'Missing Opening Snapshot'),
        ('missing_closing_snapshot', 'Missing Closing Snapshot'),
    ], string='Status', required=True, readonly=True, index=True)

    opening_mrr = fields.Monetary(string='Opening MRR', currency_field='currency_id', readonly=True)
    closing_mrr = fields.Monetary(string='Closing MRR', currency_field='currency_id', readonly=True)
    snapshot_delta_mrr = fields.Monetary(string='Snapshot Delta', currency_field='currency_id', readonly=True)
    new_mrr = fields.Monetary(string='New MRR', currency_field='currency_id', readonly=True)
    expansion_mrr = fields.Monetary(string='Expansion MRR', currency_field='currency_id', readonly=True)
    contraction_mrr = fields.Monetary(string='Contraction MRR', currency_field='currency_id', readonly=True)
    churned_mrr = fields.Monetary(string='Churned MRR', currency_field='currency_id', readonly=True)
    net_movement_mrr = fields.Monetary(string='Net Movement MRR', currency_field='currency_id', readonly=True)
    variance_mrr = fields.Monetary(string='Variance', currency_field='currency_id', readonly=True)

    _reconciliation_bucket_unique = models.Constraint(
        'UNIQUE(opening_date, closing_date, company_id, currency_id, subscription_plan_id)',
        'Only one MRR reconciliation can exist for the same date range, company, currency, and plan.',
    )

    @api.constrains('opening_date', 'closing_date')
    def _check_date_range(self):
        for reconciliation in self:
            if reconciliation.opening_date >= reconciliation.closing_date:
                raise ValidationError(_("Closing date must be after opening date."))

    @api.model
    def _check_reconciliation_manager_access(self):
        if not self.env.su and not self.env.user.has_group('subscription_suite.group_subscription_manager'):
            raise AccessError(_("Only subscription managers can generate MRR reconciliations."))

    @api.model
    def _prepare_bucket_domain(self, opening_date, closing_date, company=None, plan=None):
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
    def _prepare_snapshot_domain(self, snapshot_date, company=None, plan=None):
        domain = [('snapshot_date', '=', snapshot_date)]
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
    def _snapshot_map(self, snapshot_date, company=None, plan=None):
        snapshots = self.env['subscription.mrr.snapshot'].search(
            self._prepare_snapshot_domain(snapshot_date, company=company, plan=plan)
        )
        return {
            (snapshot.company_id.id, snapshot.currency_id.id, snapshot.subscription_plan_id.id): snapshot
            for snapshot in snapshots
        }

    @api.model
    def _movement_buckets(self, opening_date, closing_date, company=None, plan=None):
        buckets = defaultdict(lambda: {
            'new_mrr': 0.0,
            'expansion_mrr': 0.0,
            'contraction_mrr': 0.0,
            'churned_mrr': 0.0,
            'net_movement_mrr': 0.0,
        })
        movements = self.env['subscription.mrr.movement'].search(
            self._prepare_movement_domain(opening_date, closing_date, company=company, plan=plan)
        )
        field_by_type = {
            'new': 'new_mrr',
            'expansion': 'expansion_mrr',
            'contraction': 'contraction_mrr',
            'churn': 'churned_mrr',
        }
        for movement in movements:
            if not movement.company_id or not movement.currency_id or not movement.subscription_plan_id:
                continue
            key = (movement.company_id.id, movement.currency_id.id, movement.subscription_plan_id.id)
            amount = movement.amount or 0.0
            buckets[key][field_by_type[movement.movement_type]] += amount
            buckets[key]['net_movement_mrr'] += amount
        return buckets

    @api.model
    def _get_reconciliation_values(self, opening_date, closing_date, company=None, plan=None):
        opening_snapshots = self._snapshot_map(opening_date, company=company, plan=plan)
        closing_snapshots = self._snapshot_map(closing_date, company=company, plan=plan)
        movement_buckets = self._movement_buckets(opening_date, closing_date, company=company, plan=plan)
        keys = set(opening_snapshots) | set(closing_snapshots)
        generated_at = fields.Datetime.now()
        values = []
        for key in sorted(keys):
            opening_snapshot = opening_snapshots.get(key)
            closing_snapshot = closing_snapshots.get(key)
            movement = movement_buckets.get(key, {})
            company_id, currency_id, plan_id = key
            opening_mrr = opening_snapshot.total_recurring_mrr if opening_snapshot else 0.0
            closing_mrr = closing_snapshot.total_recurring_mrr if closing_snapshot else 0.0
            snapshot_delta = closing_mrr - opening_mrr
            net_movement = movement.get('net_movement_mrr', 0.0)
            variance = snapshot_delta - net_movement
            if not opening_snapshot:
                status = 'missing_opening_snapshot'
            elif not closing_snapshot:
                status = 'missing_closing_snapshot'
            else:
                currency = self.env['res.currency'].browse(currency_id)
                status = 'matched' if currency.is_zero(variance) else 'variance'
            values.append({
                'opening_date': opening_date,
                'closing_date': closing_date,
                'company_id': company_id,
                'currency_id': currency_id,
                'subscription_plan_id': plan_id,
                'generated_at': generated_at,
                'status': status,
                'opening_mrr': opening_mrr,
                'closing_mrr': closing_mrr,
                'snapshot_delta_mrr': snapshot_delta,
                'new_mrr': movement.get('new_mrr', 0.0),
                'expansion_mrr': movement.get('expansion_mrr', 0.0),
                'contraction_mrr': movement.get('contraction_mrr', 0.0),
                'churned_mrr': movement.get('churned_mrr', 0.0),
                'net_movement_mrr': net_movement,
                'variance_mrr': variance,
            })
        return values

    @api.model
    def generate_for_period(self, opening_date, closing_date, company=None, plan=None):
        self._check_reconciliation_manager_access()
        if opening_date >= closing_date:
            raise ValidationError(_("Closing date must be after opening date."))
        if isinstance(company, int):
            company = self.env['res.company'].browse(company)
        if isinstance(plan, int):
            plan = self.env['subscription.plan'].browse(plan)
        self.search(self._prepare_bucket_domain(opening_date, closing_date, company=company, plan=plan)).unlink()
        values = self._get_reconciliation_values(opening_date, closing_date, company=company, plan=plan)
        return self.create(values) if values else self.browse()

    def action_view_snapshots(self):
        self.ensure_one()
        return {
            'name': _('MRR Snapshots'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.mrr.snapshot',
            'view_mode': 'list,form,pivot,graph',
            'domain': [
                ('snapshot_date', 'in', [self.opening_date, self.closing_date]),
                ('company_id', '=', self.company_id.id),
                ('currency_id', '=', self.currency_id.id),
                ('subscription_plan_id', '=', self.subscription_plan_id.id),
            ],
        }

    def action_view_movements(self):
        self.ensure_one()
        return {
            'name': _('MRR Movements'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.mrr.movement',
            'view_mode': 'list,form,pivot,graph',
            'domain': [
                ('movement_date', '>', self.opening_date),
                ('movement_date', '<=', self.closing_date),
                ('company_id', '=', self.company_id.id),
                ('currency_id', '=', self.currency_id.id),
                ('subscription_plan_id', '=', self.subscription_plan_id.id),
            ],
        }
