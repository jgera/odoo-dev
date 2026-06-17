from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class SubscriptionMrrKpiSummary(models.Model):
    _name = 'subscription.mrr.kpi.summary'
    _description = 'Subscription MRR KPI Summary'
    _order = 'closing_date desc, opening_date desc, company_id, currency_id, subscription_plan_id'

    opening_date = fields.Date(string='Opening Date', required=True, readonly=True, index=True)
    closing_date = fields.Date(string='Closing Date', required=True, readonly=True, index=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, readonly=True, index=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, readonly=True, index=True)
    subscription_plan_id = fields.Many2one('subscription.plan', string='Subscription Plan', readonly=True, index=True)
    bucket_key = fields.Char(string='Bucket Key', required=True, readonly=True, index=True)
    generated_at = fields.Datetime(string='Generated At', readonly=True)
    status = fields.Selection([
        ('ready', 'Ready'),
        ('missing_opening_snapshot', 'Missing Opening Snapshot'),
        ('missing_closing_snapshot', 'Missing Closing Snapshot'),
        ('missing_reconciliation', 'Missing Reconciliation'),
    ], string='Status', required=True, readonly=True, index=True)

    opening_mrr = fields.Monetary(string='Opening MRR', currency_field='currency_id', readonly=True)
    closing_mrr = fields.Monetary(string='Closing MRR', currency_field='currency_id', readonly=True)
    snapshot_delta_mrr = fields.Monetary(string='Snapshot Delta', currency_field='currency_id', readonly=True)
    new_mrr = fields.Monetary(string='New MRR', currency_field='currency_id', readonly=True)
    expansion_mrr = fields.Monetary(string='Expansion MRR', currency_field='currency_id', readonly=True)
    contraction_mrr = fields.Monetary(string='Contraction MRR', currency_field='currency_id', readonly=True)
    churned_mrr = fields.Monetary(string='Churned MRR', currency_field='currency_id', readonly=True)
    net_new_mrr = fields.Monetary(string='Net New MRR', currency_field='currency_id', readonly=True)
    nrr = fields.Float(string='NRR (%)', readonly=True)
    grr = fields.Float(string='GRR (%)', readonly=True)
    variance_mrr = fields.Monetary(string='Reconciliation Variance', currency_field='currency_id', readonly=True)

    _kpi_summary_bucket_unique = models.Constraint(
        'UNIQUE(opening_date, closing_date, bucket_key)',
        'Only one MRR KPI summary can exist for the same date range and bucket.',
    )

    @api.constrains('opening_date', 'closing_date')
    def _check_date_range(self):
        for summary in self:
            if summary.opening_date >= summary.closing_date:
                raise ValidationError(_("Closing date must be after opening date."))

    @api.model
    def _check_kpi_manager_access(self):
        if not self.env.su and not self.env.user.has_group('subscription_suite.group_subscription_manager'):
            raise AccessError(_("Only subscription managers can generate MRR KPI summaries."))

    @api.model
    def _bucket_key(self, company_id, currency_id, plan_id):
        return '%s:%s:%s' % (company_id or 'no_company', currency_id or 'no_currency', plan_id or 'all_plans')

    @api.model
    def _prepare_summary_domain(self, opening_date, closing_date, company=None, plan=None):
        domain = [('opening_date', '=', opening_date), ('closing_date', '=', closing_date)]
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
    def _snapshot_buckets(self, snapshot_date, company=None, plan=None):
        buckets = {}
        for snapshot in self.env['subscription.mrr.snapshot'].search(
            self._prepare_snapshot_domain(snapshot_date, company=company, plan=plan)
        ):
            key = (snapshot.company_id.id, snapshot.currency_id.id, snapshot.subscription_plan_id.id)
            buckets[key] = snapshot
        return buckets

    @api.model
    def _reconciliation_buckets(self, opening_date, closing_date, company=None, plan=None):
        domain = [('opening_date', '=', opening_date), ('closing_date', '=', closing_date)]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        buckets = {}
        for reconciliation in self.env['subscription.mrr.reconciliation'].search(domain):
            key = (
                reconciliation.company_id.id,
                reconciliation.currency_id.id,
                reconciliation.subscription_plan_id.id,
            )
            buckets[key] = reconciliation
        return buckets

    @api.model
    def _movement_buckets(self, opening_date, closing_date, company=None, plan=None):
        domain = [('movement_date', '>', opening_date), ('movement_date', '<=', closing_date)]
        if company:
            domain.append(('company_id', '=', company.id))
        if plan:
            domain.append(('subscription_plan_id', '=', plan.id))
        buckets = defaultdict(lambda: {
            'new_mrr': 0.0,
            'expansion_mrr': 0.0,
            'contraction_mrr': 0.0,
            'churned_mrr': 0.0,
            'net_new_mrr': 0.0,
        })
        field_by_type = {
            'new': 'new_mrr',
            'expansion': 'expansion_mrr',
            'contraction': 'contraction_mrr',
            'churn': 'churned_mrr',
        }
        for movement in self.env['subscription.mrr.movement'].search(domain):
            if not movement.company_id or not movement.currency_id or not movement.subscription_plan_id:
                continue
            key = (movement.company_id.id, movement.currency_id.id, movement.subscription_plan_id.id)
            amount = movement.amount or 0.0
            buckets[key][field_by_type[movement.movement_type]] += amount
            buckets[key]['net_new_mrr'] += amount
        return buckets

    @api.model
    def _get_kpi_values(self, opening_date, closing_date, company=None, plan=None):
        opening_snapshots = self._snapshot_buckets(opening_date, company=company, plan=plan)
        closing_snapshots = self._snapshot_buckets(closing_date, company=company, plan=plan)
        reconciliations = self._reconciliation_buckets(opening_date, closing_date, company=company, plan=plan)
        movement_buckets = self._movement_buckets(opening_date, closing_date, company=company, plan=plan)
        keys = set(opening_snapshots) | set(closing_snapshots) | set(reconciliations) | set(movement_buckets)
        generated_at = fields.Datetime.now()
        values = []
        for key in sorted(keys):
            company_id, currency_id, plan_id = key
            opening_snapshot = opening_snapshots.get(key)
            closing_snapshot = closing_snapshots.get(key)
            reconciliation = reconciliations.get(key)
            opening_mrr = opening_snapshot.total_recurring_mrr if opening_snapshot else 0.0
            closing_mrr = closing_snapshot.total_recurring_mrr if closing_snapshot else 0.0
            snapshot_delta = closing_mrr - opening_mrr

            if reconciliation:
                new_mrr = reconciliation.new_mrr
                expansion_mrr = reconciliation.expansion_mrr
                contraction_mrr = reconciliation.contraction_mrr
                churned_mrr = reconciliation.churned_mrr
                net_new_mrr = reconciliation.net_movement_mrr
                variance_mrr = reconciliation.variance_mrr
            else:
                movement = movement_buckets.get(key, {})
                new_mrr = movement.get('new_mrr', 0.0)
                expansion_mrr = movement.get('expansion_mrr', 0.0)
                contraction_mrr = movement.get('contraction_mrr', 0.0)
                churned_mrr = movement.get('churned_mrr', 0.0)
                net_new_mrr = movement.get('net_new_mrr', 0.0)
                variance_mrr = snapshot_delta - net_new_mrr

            if not opening_snapshot:
                status = 'missing_opening_snapshot'
            elif not closing_snapshot:
                status = 'missing_closing_snapshot'
            elif not reconciliation:
                status = 'missing_reconciliation'
            else:
                status = 'ready'

            nrr = 0.0
            grr = 0.0
            if opening_mrr:
                nrr = ((opening_mrr + expansion_mrr + contraction_mrr + churned_mrr) / opening_mrr) * 100.0
                grr = ((opening_mrr + contraction_mrr + churned_mrr) / opening_mrr) * 100.0

            values.append({
                'opening_date': opening_date,
                'closing_date': closing_date,
                'company_id': company_id,
                'currency_id': currency_id,
                'subscription_plan_id': plan_id,
                'bucket_key': self._bucket_key(company_id, currency_id, plan_id),
                'generated_at': generated_at,
                'status': status,
                'opening_mrr': opening_mrr,
                'closing_mrr': closing_mrr,
                'snapshot_delta_mrr': snapshot_delta,
                'new_mrr': new_mrr,
                'expansion_mrr': expansion_mrr,
                'contraction_mrr': contraction_mrr,
                'churned_mrr': churned_mrr,
                'net_new_mrr': net_new_mrr,
                'variance_mrr': variance_mrr,
                'nrr': nrr,
                'grr': grr,
            })
        return values

    @api.model
    def generate_for_period(self, opening_date, closing_date, company=None, plan=None):
        self._check_kpi_manager_access()
        if opening_date >= closing_date:
            raise ValidationError(_("Closing date must be after opening date."))
        if isinstance(company, int):
            company = self.env['res.company'].browse(company)
        if isinstance(plan, int):
            plan = self.env['subscription.plan'].browse(plan)
        self.search(self._prepare_summary_domain(opening_date, closing_date, company=company, plan=plan)).unlink()
        values = self._get_kpi_values(opening_date, closing_date, company=company, plan=plan)
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

    def action_view_reconciliation(self):
        self.ensure_one()
        return {
            'name': _('MRR Reconciliation'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.mrr.reconciliation',
            'view_mode': 'list,form,pivot,graph',
            'domain': [
                ('opening_date', '=', self.opening_date),
                ('closing_date', '=', self.closing_date),
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
