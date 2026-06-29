import base64
import csv
import hashlib
import io
from collections import defaultdict

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.tools.float_utils import float_compare


TEMPLATE_COLUMNS = {
    'plans': [
        'code', 'name', 'billing_interval_count', 'billing_interval_unit',
        'trial_days', 'currency', 'auto_renew', 'allow_renewal_quote',
        'allow_upsell_quote', 'allow_past_due_renewal_quote',
        'allow_past_due_upsell_quote', 'cancellation_policy', 'pause_allowed',
        'max_pause_days', 'min_commitment_periods',
    ],
    'plan_lines': [
        'plan_code', 'line_reference', 'product_default_code', 'component_type',
        'quantity', 'price_unit', 'discount', 'promo_discount',
        'promo_start_date', 'promo_end_date', 'pricing_model',
    ],
    'plan_line_tiers': [
        'plan_code', 'line_reference', 'sequence', 'min_quantity',
        'max_quantity', 'price_unit',
    ],
    'subscriptions': [
        'external_reference', 'partner_ref', 'plan_code', 'state',
        'subscription_start_date', 'trial_start_date', 'trial_end_date',
        'subscription_end_date', 'next_invoice_date', 'last_invoice_date',
        'billing_interval_count', 'billing_interval_unit', 'salesperson_login',
        'pricelist_name', 'currency',
    ],
    'subscription_lines': [
        'subscription_reference', 'line_reference', 'product_default_code',
        'quantity', 'price_unit', 'discount', 'is_recurring', 'component_type',
        'pricing_model',
    ],
    'subscription_line_tiers': [
        'subscription_reference', 'line_reference', 'sequence', 'min_quantity',
        'max_quantity', 'price_unit',
    ],
    'payment_assignments': [
        'subscription_reference', 'role', 'provider_code', 'provider_reference',
    ],
    'usage_events': [
        'external_reference', 'subscription_reference', 'meter_code',
        'event_date', 'quantity',
    ],
}

REQUIRED_COLUMNS = {
    'plans': {'code', 'name', 'billing_interval_count', 'billing_interval_unit', 'currency'},
    'plan_lines': {'plan_code', 'line_reference', 'product_default_code'},
    'plan_line_tiers': {'plan_code', 'line_reference', 'min_quantity', 'price_unit'},
    'subscriptions': {
        'external_reference', 'partner_ref', 'plan_code', 'state',
        'pricelist_name', 'currency',
    },
    'subscription_lines': {
        'subscription_reference', 'line_reference', 'product_default_code',
    },
    'subscription_line_tiers': {
        'subscription_reference', 'line_reference', 'min_quantity', 'price_unit',
    },
    'payment_assignments': {
        'subscription_reference', 'role', 'provider_code', 'provider_reference',
    },
    'usage_events': {
        'external_reference', 'subscription_reference', 'meter_code',
        'event_date', 'quantity',
    },
}


class SubscriptionDataOperation(models.Model):
    _name = 'subscription.data.operation'
    _description = 'Subscription Data Operation'
    _order = 'started_at desc, id desc'

    name = fields.Char(required=True, readonly=True)
    operation_type = fields.Selection(
        [(key, key.replace('_', ' ').title()) for key in TEMPLATE_COLUMNS]
        + [('mrr_backfill', 'MRR Movement Backfill'), ('billing_attempt_backfill', 'Billing Attempt Backfill')],
        required=True,
        readonly=True,
        index=True,
    )
    mode = fields.Selection(
        [('validate', 'Validate Only'), ('apply', 'Apply')],
        required=True,
        readonly=True,
        index=True,
    )
    state = fields.Selection(
        [('running', 'Running'), ('success', 'Success'), ('partial', 'Partial'), ('failed', 'Failed')],
        required=True,
        default='running',
        readonly=True,
        index=True,
    )
    company_id = fields.Many2one('res.company', required=True, readonly=True, index=True)
    source_filename = fields.Char(readonly=True)
    source_hash = fields.Char(readonly=True, index=True)
    validation_run_id = fields.Many2one('subscription.data.operation', readonly=True)
    started_at = fields.Datetime(default=fields.Datetime.now, required=True, readonly=True)
    finished_at = fields.Datetime(readonly=True)
    date_from = fields.Date(readonly=True)
    date_to = fields.Date(readonly=True)
    processed_count = fields.Integer(readonly=True)
    created_count = fields.Integer(readonly=True)
    updated_count = fields.Integer(readonly=True)
    skipped_count = fields.Integer(readonly=True)
    failed_count = fields.Integer(readonly=True)
    warning_count = fields.Integer(readonly=True)
    schema_error = fields.Text(readonly=True)
    error_report = fields.Binary(readonly=True, attachment=True)
    error_report_filename = fields.Char(readonly=True)
    line_ids = fields.One2many('subscription.data.operation.line', 'operation_id', readonly=True)
    operation_run_id = fields.Many2one('subscription.operation.run', readonly=True)

    @api.model
    def _check_manager(self):
        if not self.env.user.has_group('subscription_suite.group_subscription_manager'):
            raise AccessError(_('Only subscription managers can run data operations.'))

    @api.model
    def _parse_csv(self, content, template_type):
        try:
            text = base64.b64decode(content).decode('utf-8-sig')
        except (ValueError, UnicodeDecodeError) as error:
            raise ValidationError(_('The import must be a valid UTF-8 CSV file: %s') % error) from error
        reader = csv.DictReader(io.StringIO(text))
        headers = reader.fieldnames or []
        unknown = set(headers) - set(TEMPLATE_COLUMNS[template_type])
        missing = REQUIRED_COLUMNS[template_type] - set(headers)
        if unknown or missing:
            messages = []
            if missing:
                messages.append(_('Missing columns: %s') % ', '.join(sorted(missing)))
            if unknown:
                messages.append(_('Unknown columns: %s') % ', '.join(sorted(unknown)))
            raise ValidationError('; '.join(messages))
        return [
            {
                key: (row.get(key) or '').strip()
                for key in TEMPLATE_COLUMNS[template_type]
            }
            for row in reader
            if any((value or '').strip() for value in row.values())
        ]

    @api.model
    def _bool(self, value, default=False):
        if value == '':
            return default
        normalized = value.lower()
        if normalized in ('1', 'true', 'yes', 'y'):
            return True
        if normalized in ('0', 'false', 'no', 'n'):
            return False
        raise ValidationError(_('Invalid boolean value: %s') % value)

    @api.model
    def _int(self, value, default=0):
        try:
            return int(value) if value != '' else default
        except ValueError as error:
            raise ValidationError(_('Invalid integer value: %s') % value) from error

    @api.model
    def _float(self, value, default=0.0):
        try:
            return float(value) if value != '' else default
        except ValueError as error:
            raise ValidationError(_('Invalid numeric value: %s') % value) from error

    @api.model
    def _date(self, value):
        if not value:
            return False
        try:
            return fields.Date.to_date(value)
        except (TypeError, ValueError) as error:
            raise ValidationError(_('Invalid date %(value)s; use YYYY-MM-DD.') % {'value': value}) from error

    def _unique(self, model, domain, label):
        records = self.env[model].search(domain, limit=2)
        if not records:
            raise ValidationError(_('%s was not found.') % label)
        if len(records) > 1:
            raise ValidationError(_('%s is ambiguous.') % label)
        return records

    def _currency(self, code):
        return self._unique('res.currency', [('name', '=', code.upper()), ('active', '=', True)], _('Currency %s') % code)

    def _plan(self, code):
        return self._unique(
            'subscription.plan',
            [('code', '=', code), ('company_id', '=', self.company_id.id)],
            _('Plan %s') % code,
        )

    def _subscription(self, reference):
        return self._unique(
            'sale.order',
            [
                ('subscription_import_reference', '=', reference),
                ('company_id', '=', self.company_id.id),
                ('is_subscription', '=', True),
            ],
            _('Subscription %s') % reference,
        )

    def _product(self, code):
        return self._unique(
            'product.product',
            [
                ('default_code', '=', code),
                ('type', '=', 'service'),
                '|',
                ('company_id', '=', False),
                ('company_id', '=', self.company_id.id),
            ],
            _('Service product %s') % code,
        )

    def _partner(self, reference):
        return self._unique(
            'res.partner',
            [
                ('ref', '=', reference),
                '|',
                ('company_id', '=', False),
                ('company_id', '=', self.company_id.id),
            ],
            _('Partner %s') % reference,
        )

    def _selection(self, model, field_name, value):
        allowed = dict(self.env[model]._fields[field_name].selection)
        if value not in allowed:
            raise ValidationError(_('Invalid %(field)s value: %(value)s') % {
                'field': field_name,
                'value': value,
            })
        return value

    def _upsert(self, record, model, values, apply, preserve_fields=False):
        if not apply:
            return record, 'validated'
        if record:
            updates = {
                key: value for key, value in values.items()
                if key not in (preserve_fields or set())
            }
            record.write(updates)
            return record, 'updated'
        return self.env[model].create(values), 'created'

    def _handle_plans(self, row, apply):
        code = row['code'].strip().upper()
        currency = self._currency(row['currency'])
        values = {
            'code': code,
            'name': row['name'],
            'company_id': self.company_id.id,
            'currency_id': currency.id,
            'billing_interval_count': self._int(row['billing_interval_count'], 1),
            'billing_interval_unit': self._selection('subscription.plan', 'billing_interval_unit', row['billing_interval_unit']),
            'trial_days': self._int(row['trial_days']),
            'auto_renew': self._bool(row['auto_renew'], True),
            'allow_renewal_quote': self._bool(row['allow_renewal_quote'], True),
            'allow_upsell_quote': self._bool(row['allow_upsell_quote'], True),
            'allow_past_due_renewal_quote': self._bool(row['allow_past_due_renewal_quote'], True),
            'allow_past_due_upsell_quote': self._bool(row['allow_past_due_upsell_quote'], True),
            'cancellation_policy': self._selection(
                'subscription.plan', 'cancellation_policy', row['cancellation_policy'] or 'end_of_period'
            ),
            'pause_allowed': self._bool(row['pause_allowed'], True),
            'max_pause_days': self._int(row['max_pause_days']),
            'min_commitment_periods': self._int(row['min_commitment_periods']),
        }
        record = self.env['subscription.plan'].search([
            ('code', '=', code), ('company_id', '=', self.company_id.id),
        ], limit=1)
        column_fields = {
            'name': 'name', 'billing_interval_count': 'billing_interval_count',
            'billing_interval_unit': 'billing_interval_unit', 'trial_days': 'trial_days',
            'auto_renew': 'auto_renew', 'allow_renewal_quote': 'allow_renewal_quote',
            'allow_upsell_quote': 'allow_upsell_quote',
            'allow_past_due_renewal_quote': 'allow_past_due_renewal_quote',
            'allow_past_due_upsell_quote': 'allow_past_due_upsell_quote',
            'cancellation_policy': 'cancellation_policy', 'pause_allowed': 'pause_allowed',
            'max_pause_days': 'max_pause_days', 'min_commitment_periods': 'min_commitment_periods',
        }
        preserve = {field for column, field in column_fields.items() if not row[column]}
        return (*self._upsert(record, 'subscription.plan', values, apply, preserve), code)

    def _handle_plan_lines(self, row, apply):
        plan = self._plan(row['plan_code'].strip().upper())
        product = self._product(row['product_default_code'])
        reference = row['line_reference']
        pricing_model = row['pricing_model'] or 'flat'
        self._selection('subscription.plan.line', 'subscription_pricing_model', pricing_model)
        values = {
            'plan_id': plan.id,
            'import_reference': reference,
            'product_id': product.id,
            'subscription_component_type': self._selection(
                'subscription.plan.line', 'subscription_component_type', row['component_type'] or 'base'
            ),
            'quantity': self._float(row['quantity'], 1.0),
            'price_unit': self._float(row['price_unit'], product.lst_price),
            'discount': self._float(row['discount']),
            'subscription_promo_discount': self._float(row['promo_discount']),
            'subscription_promo_discount_start_date': self._date(row['promo_start_date']),
            'subscription_promo_discount_end_date': self._date(row['promo_end_date']),
            'subscription_pricing_model': pricing_model,
        }
        record = self.env['subscription.plan.line'].search([
            ('plan_id', '=', plan.id), ('import_reference', '=', reference),
        ], limit=1)
        column_fields = {
            'component_type': 'subscription_component_type', 'quantity': 'quantity',
            'price_unit': 'price_unit', 'discount': 'discount',
            'promo_discount': 'subscription_promo_discount',
            'promo_start_date': 'subscription_promo_discount_start_date',
            'promo_end_date': 'subscription_promo_discount_end_date',
            'pricing_model': 'subscription_pricing_model',
        }
        preserve = {field for column, field in column_fields.items() if not row[column]}
        return (*self._upsert(record, 'subscription.plan.line', values, apply, preserve), '%s/%s' % (plan.code, reference))

    def _handle_subscriptions(self, row, apply):
        reference = row['external_reference']
        partner = self._partner(row['partner_ref'])
        plan = self._plan(row['plan_code'].strip().upper())
        currency = self._currency(row['currency'])
        pricelist = self._unique(
            'product.pricelist',
            [
                ('name', '=', row['pricelist_name']),
                ('currency_id', '=', currency.id),
                '|',
                ('company_id', '=', False),
                ('company_id', '=', self.company_id.id),
            ],
            _('Pricelist %s') % row['pricelist_name'],
        )
        user = False
        if row['salesperson_login']:
            user = self._unique('res.users', [('login', '=', row['salesperson_login'])], _('User %s') % row['salesperson_login'])
            if self.company_id not in user.company_ids:
                raise ValidationError(_('Salesperson is not allowed in the selected company.'))
        values = {
            'partner_id': partner.id,
            'company_id': self.company_id.id,
            'pricelist_id': pricelist.id,
            'is_subscription': True,
            'subscription_import_reference': reference,
            'subscription_plan_id': plan.id,
            'subscription_state': self._selection('sale.order', 'subscription_state', row['state']),
            'subscription_start_date': self._date(row['subscription_start_date']),
            'trial_start_date': self._date(row['trial_start_date']),
            'trial_end_date': self._date(row['trial_end_date']),
            'subscription_end_date': self._date(row['subscription_end_date']),
            'next_invoice_date': self._date(row['next_invoice_date']),
            'last_invoice_date': self._date(row['last_invoice_date']),
            'billing_interval_count': self._int(row['billing_interval_count'], plan.billing_interval_count),
            'billing_interval_unit': self._selection(
                'sale.order', 'billing_interval_unit', row['billing_interval_unit'] or plan.billing_interval_unit
            ),
            'user_id': user.id if user else False,
        }
        record = self.env['sale.order'].search([
            ('subscription_import_reference', '=', reference),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        column_fields = {
            'subscription_start_date': 'subscription_start_date',
            'trial_start_date': 'trial_start_date', 'trial_end_date': 'trial_end_date',
            'subscription_end_date': 'subscription_end_date',
            'next_invoice_date': 'next_invoice_date', 'last_invoice_date': 'last_invoice_date',
            'billing_interval_count': 'billing_interval_count',
            'billing_interval_unit': 'billing_interval_unit',
            'salesperson_login': 'user_id',
        }
        preserve = {field for column, field in column_fields.items() if not row[column]}
        return (*self._upsert(record, 'sale.order', values, apply, preserve), reference)

    def _handle_subscription_lines(self, row, apply):
        subscription = self._subscription(row['subscription_reference'])
        product = self._product(row['product_default_code'])
        reference = row['line_reference']
        pricing_model = row['pricing_model'] or 'flat'
        values = {
            'order_id': subscription.id,
            'subscription_import_reference': reference,
            'product_id': product.id,
            'name': product.get_product_multiline_description_sale(),
            'product_uom_qty': self._float(row['quantity'], 1.0),
            'price_unit': self._float(row['price_unit'], product.lst_price),
            'discount': self._float(row['discount']),
            'is_recurring': self._bool(row['is_recurring'], True),
            'subscription_component_type': self._selection(
                'sale.order.line', 'subscription_component_type', row['component_type'] or 'base'
            ),
            'subscription_pricing_model': self._selection(
                'sale.order.line', 'subscription_pricing_model', pricing_model
            ),
        }
        record = self.env['sale.order.line'].search([
            ('order_id', '=', subscription.id),
            ('subscription_import_reference', '=', reference),
        ], limit=1)
        column_fields = {
            'quantity': 'product_uom_qty', 'price_unit': 'price_unit',
            'discount': 'discount', 'is_recurring': 'is_recurring',
            'component_type': 'subscription_component_type',
            'pricing_model': 'subscription_pricing_model',
        }
        preserve = {field for column, field in column_fields.items() if not row[column]}
        return (*self._upsert(record, 'sale.order.line', values, apply, preserve), '%s/%s' % (row['subscription_reference'], reference))

    def _handle_payment_assignments(self, row, apply):
        subscription = self._subscription(row['subscription_reference'])
        role = row['role']
        if role not in ('primary', 'backup'):
            raise ValidationError(_('Payment role must be primary or backup.'))
        tokens = self.env['payment.token'].search([
            ('provider_code', '=', row['provider_code']),
            ('provider_ref', '=', row['provider_reference']),
            ('active', '=', True),
            ('company_id', '=', self.company_id.id),
            ('partner_id.commercial_partner_id', '=', subscription.partner_id.commercial_partner_id.id),
        ], limit=2)
        if len(tokens) != 1:
            raise ValidationError(_('An active, customer-owned payment token could not be resolved uniquely.'))
        field_name = 'payment_token_id' if role == 'primary' else 'backup_payment_token_id'
        if apply:
            subscription.write({field_name: tokens.id})
        return subscription, 'updated' if apply else 'validated', '%s/%s' % (row['subscription_reference'], role)

    def _handle_usage_events(self, row, apply):
        reference = row['external_reference']
        subscription = self._subscription(row['subscription_reference'])
        meter = self._unique(
            'subscription.usage.meter',
            [('code', '=', row['meter_code'].upper()), ('company_id', '=', self.company_id.id)],
            _('Usage meter %s') % row['meter_code'],
        )
        quantity = self._float(row['quantity'])
        if float_compare(quantity, 0.0, precision_rounding=meter.uom_id.rounding or 0.01) <= 0:
            raise ValidationError(_('Usage quantity must be positive.'))
        values = {
            'external_reference': reference,
            'subscription_id': subscription.id,
            'meter_id': meter.id,
            'event_date': self._date(row['event_date']),
            'quantity': quantity,
        }
        record = self.env['subscription.usage.event'].search([
            ('external_reference', '=', reference), ('company_id', '=', self.company_id.id),
        ], limit=1)
        return (*self._upsert(record, 'subscription.usage.event', values, apply), reference)

    def _tier_parent(self, template_type, row):
        if template_type == 'plan_line_tiers':
            plan = self._plan(row['plan_code'].strip().upper())
            parent = self._unique(
                'subscription.plan.line',
                [('plan_id', '=', plan.id), ('import_reference', '=', row['line_reference'])],
                _('Plan line %s') % row['line_reference'],
            )
            return parent, 'tier_ids', 'subscription.plan.line.tier'
        subscription = self._subscription(row['subscription_reference'])
        parent = self._unique(
            'sale.order.line',
            [('order_id', '=', subscription.id), ('subscription_import_reference', '=', row['line_reference'])],
            _('Subscription line %s') % row['line_reference'],
        )
        return parent, 'subscription_tier_ids', 'subscription.sale.order.line.tier'

    def _process_tier_rows(self, rows, apply):
        grouped = defaultdict(list)
        for row_number, row in enumerate(rows, start=2):
            parent, field_name, model = self._tier_parent(self.operation_type, row)
            grouped[(parent, field_name, model)].append((row_number, row))
        results = []
        for (parent, field_name, model), group_rows in grouped.items():
            tiers = []
            for row_number, row in sorted(group_rows, key=lambda item: self._int(item[1]['sequence'], 10)):
                minimum = self._float(row['min_quantity'])
                maximum = self._float(row['max_quantity']) if row['max_quantity'] else False
                price = self._float(row['price_unit'])
                if minimum <= 0 or price <= 0 or (maximum and maximum <= minimum):
                    raise ValidationError(_('Tier quantities and prices must be positive and ordered.'))
                tiers.append({
                    'sequence': self._int(row['sequence'], 10),
                    'min_quantity': minimum,
                    'max_quantity': maximum,
                    'price_unit': price,
                })
            if not tiers or tiers[-1]['max_quantity']:
                raise ValidationError(_('The final pricing tier must be open-ended.'))
            if tiers[0]['min_quantity'] != 1.0:
                raise ValidationError(_('The first pricing tier must start at quantity 1.'))
            for previous, current in zip(tiers, tiers[1:]):
                if previous['max_quantity'] != current['min_quantity']:
                    raise ValidationError(_('Pricing tiers must be contiguous without gaps or overlaps.'))
            if apply:
                parent.write({field_name: [Command.clear()] + [Command.create(values) for values in tiers]})
            for row_number, row in group_rows:
                reference = row.get('plan_code') or row.get('subscription_reference')
                results.append((row_number, row, parent, 'updated' if apply else 'validated', reference))
        return results

    def _result_line(self, row_number, reference, outcome, message=False, target=False):
        return {
            'operation_id': self.id,
            'row_number': row_number,
            'external_reference': reference,
            'outcome': outcome,
            'message': message,
            'target_model': target._name if target else False,
            'target_res_id': target.id if target else 0,
        }

    def _finish(self):
        outcomes = self.line_ids.mapped('outcome')
        counts = {name: outcomes.count(name) for name in set(outcomes)}
        failed = counts.get('failed', 0)
        succeeded = sum(counts.get(name, 0) for name in ('validated', 'created', 'updated'))
        state = 'partial' if failed and succeeded else 'failed' if failed else 'success'
        error_rows = self.line_ids.filtered(lambda line: line.outcome in ('failed', 'warning'))
        output = io.StringIO()
        writer = csv.writer(output, lineterminator='\n')
        writer.writerow(['row_number', 'external_reference', 'outcome', 'message'])
        for line in error_rows:
            writer.writerow([line.row_number, line.external_reference or '', line.outcome, line.message or ''])
        values = {
            'state': state,
            'finished_at': fields.Datetime.now(),
            'processed_count': len(self.line_ids),
            'created_count': counts.get('created', 0),
            'updated_count': counts.get('updated', 0),
            'skipped_count': counts.get('skipped', 0),
            'failed_count': failed,
            'warning_count': counts.get('warning', 0),
        }
        if error_rows:
            values.update({
                'error_report': base64.b64encode(output.getvalue().encode()),
                'error_report_filename': '%s-errors.csv' % self.name.replace('/', '-'),
            })
        self.write(values)
        self.operation_run_id._finish_run(
            processed=values['processed_count'],
            succeeded=succeeded,
            failed=failed,
            skipped=values['skipped_count'] + values['warning_count'],
            errors=error_rows.mapped('message'),
            state='partial' if state == 'partial' else 'failed' if state == 'failed' else False,
        )
        return self

    @api.model
    def execute_csv(self, template_type, mode, company, filename, content, validation_run=False):
        self._check_manager()
        digest = hashlib.sha256(base64.b64decode(content)).hexdigest()
        operation_run = self.env['subscription.operation.run']._start_run(
            'data_import', company=company, trigger='manual'
        )
        operation = self.create({
            'name': _('Import %(type)s - %(date)s') % {'type': template_type, 'date': fields.Datetime.now()},
            'operation_type': template_type,
            'mode': mode,
            'company_id': company.id,
            'source_filename': filename,
            'source_hash': digest,
            'validation_run_id': validation_run.id if validation_run else False,
            'operation_run_id': operation_run.id,
        })
        try:
            rows = self._parse_csv(content, template_type)
            if mode == 'apply':
                if not validation_run:
                    raise ValidationError(_('Apply mode requires a prior validation run.'))
                if (
                    validation_run.mode != 'validate'
                    or validation_run.operation_type != template_type
                    or validation_run.company_id != company
                    or validation_run.source_hash != digest
                    or validation_run.schema_error
                ):
                    raise ValidationError(_('The selected validation run does not match this file and scope.'))
        except Exception as error:
            operation.write({
                'state': 'failed',
                'finished_at': fields.Datetime.now(),
                'schema_error': str(error),
                'failed_count': 1,
            })
            operation_run._finish_run(processed=1, failed=1, errors=[str(error)])
            return operation
        apply = mode == 'apply'
        if template_type in ('plan_line_tiers', 'subscription_line_tiers'):
            try:
                processed = operation._process_tier_rows(rows, apply)
                operation.line_ids = [Command.create(operation._result_line(
                    row_number, reference, outcome, target=target
                )) for row_number, row, target, outcome, reference in processed]
            except Exception as error:
                operation.line_ids = [Command.create(operation._result_line(
                    0, False, 'failed', str(error)
                ))]
            return operation._finish()
        handler = getattr(operation, '_handle_%s' % template_type)
        lines = []
        for row_number, row in enumerate(rows, start=2):
            reference = next((row.get(key) for key in (
                'external_reference', 'subscription_reference', 'plan_code', 'code'
            ) if row.get(key)), False)
            try:
                with self.env.cr.savepoint():
                    target, outcome, reference = handler(row, apply)
                    lines.append(Command.create(operation._result_line(
                        row_number, reference, outcome, target=target
                    )))
            except Exception as error:
                lines.append(Command.create(operation._result_line(
                    row_number, reference, 'failed', str(error)
                )))
        operation.line_ids = lines
        return operation._finish()

    @api.model
    def execute_mrr_backfill(self, mode, company):
        self._check_manager()
        operation_run = self.env['subscription.operation.run']._start_run(
            'mrr_backfill', company=company, trigger='manual'
        )
        operation = self.create({
            'name': _('MRR Backfill - %s') % fields.Datetime.now(),
            'operation_type': 'mrr_backfill',
            'mode': mode,
            'company_id': company.id,
            'operation_run_id': operation_run.id,
        })
        subscriptions = self.env['sale.order'].search([
            ('company_id', '=', company.id),
            ('is_subscription', '=', True),
        ])
        lines = []
        for number, subscription in enumerate(subscriptions, start=1):
            outcome = 'validated'
            message = False
            target = False
            try:
                if subscription.subscription_state not in ('trial', 'active', 'paused', 'past_due'):
                    outcome, message = 'warning', _('Historical cancelled or expired state was not reconstructed.')
                elif float_compare(subscription.mrr, 0.0, precision_rounding=subscription.currency_id.rounding) <= 0:
                    outcome, message = 'skipped', _('Subscription has no positive MRR.')
                elif self.env['subscription.mrr.movement'].search_count([('subscription_id', '=', subscription.id)]):
                    outcome, message = 'skipped', _('Subscription already has MRR movement history.')
                else:
                    key = 'mrr-backfill:%s' % subscription.id
                    values = {
                        'name': _('Imported opening MRR'),
                        'movement_date': (
                            subscription.subscription_start_date
                            or subscription.trial_start_date
                            or fields.Date.to_date(subscription.create_date)
                        ),
                        'movement_type': 'new',
                        'subscription_id': subscription.id,
                        'previous_mrr': 0.0,
                        'new_mrr': subscription.mrr,
                        'amount': subscription.mrr,
                        'backfill_key': key,
                    }
                    if mode == 'apply':
                        target = self.env['subscription.mrr.movement'].create(values)
                        outcome = 'created'
            except Exception as error:
                outcome, message = 'failed', str(error)
            lines.append(Command.create(operation._result_line(
                number, subscription.subscription_import_reference or subscription.subscription_code,
                outcome, message, target
            )))
        operation.line_ids = lines
        return operation._finish()

    @api.model
    def execute_billing_attempt_backfill(self, mode, company, date_from, date_to):
        self._check_manager()
        operation_run = self.env['subscription.operation.run']._start_run(
            'billing_attempt_backfill', company=company, trigger='manual'
        )
        operation = self.create({
            'name': _('Billing Attempt Backfill - %s') % fields.Datetime.now(),
            'operation_type': 'billing_attempt_backfill',
            'mode': mode,
            'company_id': company.id,
            'date_from': date_from,
            'date_to': date_to,
            'operation_run_id': operation_run.id,
        })
        invoices = self.env['account.move'].search([
            ('company_id', '=', company.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('subscription_id', '!=', False),
            ('invoice_date', '>=', date_from),
            ('invoice_date', '<=', date_to),
        ], order='invoice_date, id')
        lines = []
        for number, invoice in enumerate(invoices, start=1):
            outcome, message, target = 'validated', False, False
            try:
                if not invoice.subscription_period_start or not invoice.subscription_period_end:
                    outcome, message = 'warning', _('Invoice is missing a subscription service period.')
                elif invoice.amount_untaxed <= 0:
                    outcome, message = 'skipped', _('Invoice has no positive untaxed amount.')
                else:
                    subscription = invoice.subscription_id
                    key = subscription._get_billing_idempotency_key(
                        invoice.subscription_period_start, invoice.subscription_period_end
                    )
                    existing = self.env['subscription.billing.attempt'].search([
                        ('idempotency_key', '=', key),
                    ], limit=1)
                    same_period_invoices = self.env['account.move'].search_count([
                        ('subscription_id', '=', subscription.id),
                        ('move_type', '=', 'out_invoice'),
                        ('state', '=', 'posted'),
                        ('subscription_period_start', '=', invoice.subscription_period_start),
                        ('subscription_period_end', '=', invoice.subscription_period_end),
                    ])
                    if existing:
                        outcome, message, target = 'skipped', _('Billing attempt already exists.'), existing
                    elif same_period_invoices > 1:
                        outcome, message = 'warning', _('Multiple posted invoices share this subscription period.')
                    elif mode == 'apply':
                        target = self.env['subscription.billing.attempt'].create({
                            'name': self.env['ir.sequence'].next_by_code('subscription.billing.attempt') or _('New'),
                            'subscription_id': subscription.id,
                            'invoice_id': invoice.id,
                            'period_start': invoice.subscription_period_start,
                            'period_end': invoice.subscription_period_end,
                            'idempotency_key': key,
                            'state': 'success',
                            'amount': invoice.amount_untaxed,
                        })
                        outcome = 'created'
            except Exception as error:
                outcome, message = 'failed', str(error)
            lines.append(Command.create(operation._result_line(
                number, invoice.name, outcome, message, target
            )))
        operation.line_ids = lines
        return operation._finish()

    def action_view_lines(self):
        self.ensure_one()
        return {
            'name': _('Data Operation Rows'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.data.operation.line',
            'view_mode': 'list,form',
            'domain': [('operation_id', '=', self.id)],
        }


class SubscriptionDataOperationLine(models.Model):
    _name = 'subscription.data.operation.line'
    _description = 'Subscription Data Operation Row'
    _order = 'row_number, id'

    operation_id = fields.Many2one('subscription.data.operation', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='operation_id.company_id', store=True, index=True)
    row_number = fields.Integer(readonly=True)
    external_reference = fields.Char(readonly=True, index=True)
    outcome = fields.Selection(
        [
            ('validated', 'Validated'), ('created', 'Created'), ('updated', 'Updated'),
            ('skipped', 'Skipped'), ('warning', 'Warning'), ('failed', 'Failed'),
        ],
        required=True,
        readonly=True,
        index=True,
    )
    message = fields.Text(readonly=True)
    target_model = fields.Char(readonly=True)
    target_res_id = fields.Integer(readonly=True)

    def action_open_target(self):
        self.ensure_one()
        if not self.target_model or not self.target_res_id:
            return False
        return {
            'name': _('Imported Record'),
            'type': 'ir.actions.act_window',
            'res_model': self.target_model,
            'res_id': self.target_res_id,
            'view_mode': 'form',
        }
