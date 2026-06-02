from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    is_payment_zero_default = fields.Boolean(
        string="Default Payment to 0.0",
        config_parameter='smart_payment_defaults.is_payment_zero_default',
        help="If checked, the register payment wizard will default to 0.0 instead of the total balance."
    )
