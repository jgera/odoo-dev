from odoo import _, fields, models


class SubscriptionOperationRun(models.Model):
    _inherit = 'subscription.operation.run'

    dunning_attempt_ids = fields.Many2many(
        'subscription.dunning.attempt',
        'subscription_operation_run_dunning_attempt_rel',
        'operation_run_id',
        'dunning_attempt_id',
        readonly=True,
    )

    def action_view_dunning_attempts(self):
        return self._open_records(
            'subscription.dunning.attempt',
            self.dunning_attempt_ids,
            _('Dunning Attempts'),
        )
