from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    subscription_billing_retry_max_attempts = fields.Integer(
        string='Max Billing Retry Attempts',
        config_parameter='subscription_suite.billing_retry_max_attempts',
        default=3,
    )
    subscription_billing_retry_batch_size = fields.Integer(
        string='Billing Retry Batch Size',
        config_parameter='subscription_suite.billing_retry_batch_size',
        default=50,
    )
    subscription_billing_retry_delay_hours = fields.Integer(
        string='Billing Retry Delay',
        config_parameter='subscription_suite.billing_retry_delay_hours',
        default=1,
    )
    subscription_deferred_revenue_account_id = fields.Many2one(
        'account.account',
        string='Deferred Revenue Account',
        related='company_id.subscription_deferred_revenue_account_id',
        readonly=False,
    )
    subscription_revenue_account_id = fields.Many2one(
        'account.account',
        string='Revenue Account',
        related='company_id.subscription_revenue_account_id',
        readonly=False,
    )
    subscription_recognition_journal_id = fields.Many2one(
        'account.journal',
        string='Recognition Journal',
        related='company_id.subscription_recognition_journal_id',
        readonly=False,
    )
    subscription_default_recognition_method = fields.Selection(
        string='Default Recognition Method',
        related='company_id.subscription_default_recognition_method',
        readonly=False,
    )
    subscription_enable_scheduled_recognition_posting = fields.Boolean(
        string='Enable Scheduled Recognition Posting',
        related='company_id.subscription_enable_scheduled_recognition_posting',
        readonly=False,
    )
    subscription_scheduled_recognition_cutoff_rule = fields.Selection(
        string='Scheduled Recognition Cutoff',
        related='company_id.subscription_scheduled_recognition_cutoff_rule',
        readonly=False,
    )
    subscription_operation_digest_enabled = fields.Boolean(
        related='company_id.subscription_operation_digest_enabled',
        readonly=False,
    )
    subscription_operation_digest_recipient_ids = fields.Many2many(
        related='company_id.subscription_operation_digest_recipient_ids',
        readonly=False,
    )
    subscription_operation_cleanup_enabled = fields.Boolean(
        related='company_id.subscription_operation_cleanup_enabled',
        readonly=False,
    )
    subscription_operation_retention_days = fields.Integer(
        related='company_id.subscription_operation_retention_days',
        readonly=False,
    )

    @api.constrains(
        'subscription_billing_retry_max_attempts',
        'subscription_billing_retry_batch_size',
        'subscription_billing_retry_delay_hours',
    )
    def _check_subscription_billing_retry_values(self):
        for settings in self:
            if settings.subscription_billing_retry_max_attempts < 1:
                raise ValidationError(_('Max billing retry attempts must be at least 1.'))
            if settings.subscription_billing_retry_batch_size < 1:
                raise ValidationError(_('Billing retry batch size must be at least 1.'))
            if settings.subscription_billing_retry_delay_hours < 1:
                raise ValidationError(_('Billing retry delay must be at least 1 hour.'))
            if settings.subscription_operation_retention_days < 1:
                raise ValidationError(_('Operation run retention must be at least 1 day.'))
