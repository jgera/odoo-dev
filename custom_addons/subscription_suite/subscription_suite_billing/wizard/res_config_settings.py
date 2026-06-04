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
