from odoo import models, api

class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    @api.depends('can_edit_wizard', 'source_amount', 'source_amount_currency', 'source_currency_id', 'company_id', 'currency_id', 'payment_date')
    def _compute_amount(self):
        super()._compute_amount()
        
        # Check system configuration
        default_zero = self.env['ir.config_parameter'].sudo().get_param('smart_payment_defaults.is_payment_zero_default')
        
        if default_zero:
            for wizard in self:
                if wizard.can_edit_wizard:
                    wizard.amount = 0.0
