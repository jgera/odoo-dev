from odoo import models, fields, api

class SubscriptionPlanLine(models.Model):
    _name = 'subscription.plan.line'
    _description = 'Subscription Plan Line'
    _order = 'sequence, id'

    plan_id = fields.Many2one('subscription.plan', string='Plan', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    product_id = fields.Many2one('product.product', string='Product', required=True, domain=[('type', '=', 'service')])
    quantity = fields.Float(string='Quantity', default=1.0, required=True)
    uom_id = fields.Many2one('uom.uom', related='product_id.uom_id', string='Unit of Measure')
    price_unit = fields.Monetary(string='Unit Price', help="Leave empty to use product price")
    discount = fields.Float(string='Discount (%)', default=0.0)
    description = fields.Text(string='Description', translate=True)
    
    currency_id = fields.Many2one('res.currency', related='plan_id.currency_id')
    company_id = fields.Many2one('res.company', related='plan_id.company_id')

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.description = self.product_id.get_product_multiline_description_sale()
            if not self.price_unit:
                self.price_unit = self.product_id.list_price
