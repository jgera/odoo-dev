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
        config_parameter='subscription_suite.deferred_revenue_account_id',
    )
    subscription_revenue_account_id = fields.Many2one(
        'account.account',
        string='Revenue Account',
        config_parameter='subscription_suite.revenue_account_id',
    )
    subscription_recognition_journal_id = fields.Many2one(
        'account.journal',
        string='Recognition Journal',
        config_parameter='subscription_suite.recognition_journal_id',
    )
    subscription_default_recognition_method = fields.Selection(
        [
            ('straight_line_daily', 'Straight-line Daily'),
            ('equal_monthly', 'Equal Monthly'),
        ],
        string='Default Recognition Method',
        config_parameter='subscription_suite.default_recognition_method',
        default='straight_line_daily',
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
