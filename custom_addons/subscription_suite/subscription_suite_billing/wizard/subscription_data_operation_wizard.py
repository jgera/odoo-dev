from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..models.subscription_data_operation import TEMPLATE_COLUMNS


class SubscriptionDataOperationWizard(models.TransientModel):
    _name = 'subscription.data.operation.wizard'
    _description = 'Subscription Data Operation Wizard'

    operation_type = fields.Selection(
        [(key, key.replace('_', ' ').title()) for key in TEMPLATE_COLUMNS]
        + [('mrr_backfill', 'MRR Movement Backfill'), ('billing_attempt_backfill', 'Billing Attempt Backfill')],
        required=True,
    )
    mode = fields.Selection(
        [('validate', 'Validate Only'), ('apply', 'Apply')],
        default='validate',
        required=True,
    )
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    source_file = fields.Binary(attachment=False)
    source_filename = fields.Char()
    validation_run_id = fields.Many2one(
        'subscription.data.operation',
        domain="[('mode', '=', 'validate'), ('operation_type', '=', operation_type), ('company_id', '=', company_id)]",
    )
    date_from = fields.Date()
    date_to = fields.Date()

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError(_('Start date must not be after end date.'))

    def action_execute(self):
        self.ensure_one()
        Operation = self.env['subscription.data.operation']
        if self.operation_type in TEMPLATE_COLUMNS:
            if not self.source_file or not self.source_filename:
                raise ValidationError(_('Select a UTF-8 CSV file.'))
            operation = Operation.execute_csv(
                self.operation_type,
                self.mode,
                self.company_id,
                self.source_filename,
                self.source_file,
                validation_run=self.validation_run_id,
            )
        elif self.operation_type == 'mrr_backfill':
            operation = Operation.execute_mrr_backfill(self.mode, self.company_id)
        else:
            if not self.date_from or not self.date_to:
                raise ValidationError(_('Billing attempt backfill requires a date range.'))
            operation = Operation.execute_billing_attempt_backfill(
                self.mode, self.company_id, self.date_from, self.date_to
            )
        return {
            'name': _('Subscription Data Operation'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.data.operation',
            'res_id': operation.id,
            'view_mode': 'form',
        }
