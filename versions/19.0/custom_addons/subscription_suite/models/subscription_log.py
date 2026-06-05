from odoo import models, fields

class SubscriptionLog(models.Model):
    _name = 'subscription.log'
    _description = 'Subscription Event Log'
    _order = 'create_date desc'
    _rec_name = 'event_type'

    subscription_id = fields.Many2one('sale.order', string='Subscription', required=True, ondelete='cascade', index=True)
    event_type = fields.Selection([
        ('created', 'Created'),
        ('confirmed', 'Confirmed'),
        ('trial_started', 'Trial Started'),
        ('trial_converted', 'Trial Converted'),
        ('trial_expired', 'Trial Expired'),
        ('activated', 'Activated'),
        ('paused', 'Paused'),
        ('resumed', 'Resumed'),
        ('plan_changed', 'Plan Changed'),
        ('upgraded', 'Upgraded'),
        ('downgraded', 'Downgraded'),
        ('invoice_generated', 'Invoice Generated'),
        ('payment_success', 'Payment Successful'),
        ('payment_failed', 'Payment Failed'),
        ('dunning_started', 'Dunning Started'),
        ('dunning_success', 'Dunning Recovery'),
        ('renewal_quote_created', 'Renewal Quote Created'),
        ('upsell_quote_created', 'Upsell Quote Created'),
        ('upsold', 'Upsold'),
        ('lifecycle_requested', 'Lifecycle Requested'),
        ('cancellation_requested', 'Cancellation Requested'),
        ('cancellation_scheduled', 'Cancellation Scheduled'),
        ('cancellation_reversed', 'Cancellation Reversed'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
        ('renewed', 'Renewed'),
    ], string='Event Type', required=True)
    event_date = fields.Datetime(string='Date', required=True, default=fields.Datetime.now)
    description = fields.Text(string='Description')
    old_value = fields.Text(string='Old Value')
    new_value = fields.Text(string='New Value')
    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.user)
    invoice_id = fields.Many2one('account.move', string='Invoice')
    amount = fields.Monetary(string='Amount')  # Reserved for future use (e.g. invoice amount, payment amount)
    
    currency_id = fields.Many2one('res.currency', related='subscription_id.currency_id')
    company_id = fields.Many2one('res.company', related='subscription_id.company_id')
