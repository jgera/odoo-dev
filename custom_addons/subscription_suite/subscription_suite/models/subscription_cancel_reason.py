from odoo import models, fields

class SubscriptionCancelReason(models.Model):
    _name = 'subscription.cancel.reason'
    _description = 'Subscription Cancellation Reason'
    _order = 'sequence, id'

    name = fields.Char(string='Reason', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)
