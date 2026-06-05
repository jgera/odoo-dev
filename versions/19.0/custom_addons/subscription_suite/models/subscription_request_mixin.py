from odoo import _, api, fields, models


class SubscriptionRequestMixin(models.AbstractModel):
    _name = 'subscription.request.mixin'
    _description = 'Subscription Request Manager Workflow'

    request_age_days = fields.Integer(string='Age (Days)', compute='_compute_request_age_days')

    @api.depends('requested_on')
    def _compute_request_age_days(self):
        now = fields.Datetime.now()
        for request in self:
            requested_on = fields.Datetime.to_datetime(request.requested_on) if request.requested_on else False
            request.request_age_days = (now - requested_on).days if requested_on else 0

    def _get_manager_review_user(self):
        self.ensure_one()
        group = self.env.ref('subscription_suite.group_subscription_manager', raise_if_not_found=False)
        if not group:
            return self.env['res.users']
        group = group.sudo()

        request_sudo = self.sudo()
        subscription_user = request_sudo.subscription_id.user_id
        if subscription_user and subscription_user in group.user_ids:
            return subscription_user

        managers = group.user_ids.filtered(lambda user: user.active)
        if request_sudo.company_id:
            company_managers = managers.filtered(lambda user: request_sudo.company_id in user.company_ids)
            managers = company_managers or managers
        return managers[:1]

    def _schedule_manager_review_activity(self):
        for request in self.filtered(lambda req: req.state == 'pending'):
            review_user = request._get_manager_review_user()
            if not review_user:
                continue
            existing_activity = request.activity_search(
                ['mail.mail_activity_data_todo'],
                user_id=review_user.id,
                only_automated=True,
            )
            if existing_activity:
                continue
            request.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=review_user.id,
                summary=_('Review subscription request'),
                note=_('Review and approve or reject this subscription request.'),
                date_deadline=fields.Date.context_today(request),
            )

    def _close_manager_review_activity(self, feedback):
        self.activity_feedback(
            ['mail.mail_activity_data_todo'],
            feedback=feedback,
            only_automated=True,
        )

    def action_open_subscription(self):
        self.ensure_one()
        return {
            'name': self.subscription_id.display_name,
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.subscription_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
