from odoo import _, fields, models


class SubscriptionBillingRun(models.Model):
    _name = 'subscription.billing.run'
    _description = 'Subscription Billing Run'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'started_at desc, id desc'

    name = fields.Char(string='Reference', required=True, copy=False, default=lambda self: _('New'))
    run_date = fields.Date(string='Run Date', required=True, default=fields.Date.context_today, index=True)
    started_at = fields.Datetime(string='Started At', default=fields.Datetime.now, readonly=True)
    finished_at = fields.Datetime(string='Finished At', readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('running', 'Running'),
        ('done', 'Done'),
        ('done_with_errors', 'Done with Errors'),
    ], string='Status', default='draft', required=True, tracking=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', readonly=True)

    attempt_ids = fields.One2many('subscription.billing.attempt', 'run_id', string='Billing Attempts')
    subscription_count = fields.Integer(string='Subscriptions', readonly=True)
    success_count = fields.Integer(string='Successful', readonly=True)
    failed_count = fields.Integer(string='Failed', readonly=True)
    skipped_count = fields.Integer(string='Skipped', readonly=True)
    total_amount = fields.Monetary(string='Total Amount', currency_field='currency_id', readonly=True)
    log = fields.Text(string='Log', readonly=True)

    def _finalize_from_attempts(self):
        for run in self:
            attempts = run.attempt_ids
            success_attempts = attempts.filtered(lambda attempt: attempt.state == 'success')
            failed_attempts = attempts.filtered(lambda attempt: attempt.state == 'failed')
            skipped_attempts = attempts.filtered(lambda attempt: attempt.state == 'skipped')
            run.write({
                'state': 'done_with_errors' if failed_attempts else 'done',
                'finished_at': fields.Datetime.now(),
                'subscription_count': len(attempts.mapped('subscription_id')),
                'success_count': len(success_attempts),
                'failed_count': len(failed_attempts),
                'skipped_count': len(skipped_attempts),
                'total_amount': sum(success_attempts.mapped('amount')),
            })

    def action_view_attempts(self):
        self.ensure_one()
        return {
            'name': _('Billing Attempts'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.billing.attempt',
            'view_mode': 'list,form',
            'domain': [('run_id', '=', self.id)],
            'context': {'default_run_id': self.id},
        }
