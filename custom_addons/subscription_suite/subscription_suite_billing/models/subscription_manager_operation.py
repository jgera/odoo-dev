from odoo import _, api, fields, models, tools


class SubscriptionManagerOperation(models.Model):
    _name = 'subscription.manager.operation'
    _description = 'Subscription Manager Operation'
    _auto = False
    _order = 'priority desc, event_date asc, id asc'

    name = fields.Char(readonly=True)
    operation_type = fields.Selection([
        ('plan_change', 'Plan Change'),
        ('lifecycle', 'Lifecycle'),
        ('cancellation', 'Cancellation'),
        ('billing_recovery', 'Billing Recovery'),
    ], string='Type', readonly=True)
    action_state = fields.Selection([
        ('pending', 'Pending'),
        ('failed', 'Failed'),
    ], string='Action State', readonly=True)
    priority = fields.Selection([
        ('normal', 'Normal'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ], readonly=True)
    event_date = fields.Datetime(string='Date', readonly=True)
    age_days = fields.Integer(string='Age (Days)', compute='_compute_age_days')
    subscription_id = fields.Many2one('sale.order', string='Subscription', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    amount = fields.Monetary(string='Amount', currency_field='currency_id', readonly=True)
    source_model = fields.Char(readonly=True)
    source_res_id = fields.Integer(readonly=True)
    source_reference = fields.Char(string='Source', readonly=True)
    note = fields.Text(readonly=True)

    @api.depends('event_date')
    def _compute_age_days(self):
        now = fields.Datetime.now()
        for operation in self:
            event_date = fields.Datetime.to_datetime(operation.event_date) if operation.event_date else False
            operation.age_days = (now - event_date).days if event_date else 0

    def action_open_source(self):
        self.ensure_one()
        if not self.source_model or not self.source_res_id:
            return False
        return {
            'name': self.source_reference or self.name,
            'type': 'ir.actions.act_window',
            'res_model': self.source_model,
            'res_id': self.source_res_id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_subscription(self):
        self.ensure_one()
        return {
            'name': _('Subscription'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.subscription_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    request.id * 10 + 1 AS id,
                    request.name AS name,
                    'plan_change'::varchar AS operation_type,
                    'pending'::varchar AS action_state,
                    CASE
                        WHEN request.change_type = 'downgrade' THEN 'high'
                        ELSE 'normal'
                    END::varchar AS priority,
                    request.requested_on AS event_date,
                    request.subscription_id AS subscription_id,
                    request.partner_id AS partner_id,
                    request.company_id AS company_id,
                    request.currency_id AS currency_id,
                    request.new_mrr - request.old_mrr AS amount,
                    'subscription.plan.change.request'::varchar AS source_model,
                    request.id AS source_res_id,
                    request.name AS source_reference,
                    concat('Pending ', request.change_type, ' request for manager approval.') AS note
                FROM subscription_plan_change_request request
                WHERE request.state = 'pending'

                UNION ALL

                SELECT
                    request.id * 10 + 2 AS id,
                    request.name AS name,
                    'lifecycle'::varchar AS operation_type,
                    'pending'::varchar AS action_state,
                    'normal'::varchar AS priority,
                    request.requested_on AS event_date,
                    request.subscription_id AS subscription_id,
                    request.partner_id AS partner_id,
                    request.company_id AS company_id,
                    subscription.currency_id AS currency_id,
                    0.0 AS amount,
                    'subscription.lifecycle.request'::varchar AS source_model,
                    request.id AS source_res_id,
                    request.name AS source_reference,
                    concat('Pending ', request.request_type, ' request for manager approval.') AS note
                FROM subscription_lifecycle_request request
                JOIN sale_order subscription ON subscription.id = request.subscription_id
                WHERE request.state = 'pending'

                UNION ALL

                SELECT
                    request.id * 10 + 3 AS id,
                    request.name AS name,
                    'cancellation'::varchar AS operation_type,
                    'pending'::varchar AS action_state,
                    'high'::varchar AS priority,
                    request.requested_on AS event_date,
                    request.subscription_id AS subscription_id,
                    request.partner_id AS partner_id,
                    request.company_id AS company_id,
                    subscription.currency_id AS currency_id,
                    0.0 AS amount,
                    'subscription.cancellation.request'::varchar AS source_model,
                    request.id AS source_res_id,
                    request.name AS source_reference,
                    'Pending cancellation request for manager approval.' AS note
                FROM subscription_cancellation_request request
                JOIN sale_order subscription ON subscription.id = request.subscription_id
                WHERE request.state = 'pending'

                UNION ALL

                SELECT
                    attempt.id * 10 + 4 AS id,
                    attempt.name AS name,
                    'billing_recovery'::varchar AS operation_type,
                    'failed'::varchar AS action_state,
                    CASE
                        WHEN attempt.recovery_required OR attempt.retry_exhausted THEN 'critical'
                        ELSE 'high'
                    END::varchar AS priority,
                    COALESCE(attempt.last_failure_at, attempt.attempt_date) AS event_date,
                    attempt.subscription_id AS subscription_id,
                    attempt.partner_id AS partner_id,
                    attempt.company_id AS company_id,
                    attempt.currency_id AS currency_id,
                    attempt.amount AS amount,
                    'subscription.billing.attempt'::varchar AS source_model,
                    attempt.id AS source_res_id,
                    attempt.name AS source_reference,
                    COALESCE(attempt.recovery_note, attempt.last_failure_message, attempt.error_message) AS note
                FROM subscription_billing_attempt attempt
                WHERE attempt.state = 'failed'
                  AND (attempt.recovery_required = true OR attempt.retryable = true OR attempt.retry_exhausted = true)
            )
        """ % self._table)
