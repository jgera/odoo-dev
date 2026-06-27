from odoo import _, fields, models


class SubscriptionOperationRun(models.Model):
    _inherit = 'subscription.operation.run'

    snapshot_ids = fields.Many2many(
        'subscription.mrr.snapshot',
        'subscription_operation_run_mrr_snapshot_rel',
        'operation_run_id',
        'snapshot_id',
        readonly=True,
    )

    def action_view_snapshots(self):
        return self._open_records(
            'subscription.mrr.snapshot',
            self.snapshot_ids,
            _('MRR Snapshots'),
        )
