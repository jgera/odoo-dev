from odoo import _, fields, models


class SubscriptionMrrSnapshotGenerateWizard(models.TransientModel):
    _name = 'subscription.mrr.snapshot.generate.wizard'
    _description = 'Generate MRR Snapshot'

    snapshot_date = fields.Date(
        string='Snapshot Date',
        required=True,
        default=fields.Date.context_today,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        help="Leave empty to regenerate snapshots for all accessible companies.",
    )

    def action_generate_snapshot(self):
        self.ensure_one()
        Snapshot = self.env['subscription.mrr.snapshot']
        snapshots = Snapshot.generate_for_date(self.snapshot_date, company=self.company_id)
        domain = [('snapshot_date', '=', self.snapshot_date)]
        if self.company_id:
            domain.append(('company_id', '=', self.company_id.id))
        return {
            'name': _('MRR Snapshots'),
            'type': 'ir.actions.act_window',
            'res_model': 'subscription.mrr.snapshot',
            'view_mode': 'pivot,graph,list,form',
            'domain': domain,
            'context': {'search_default_group_plan_id': 1},
            'target': 'current',
        }
