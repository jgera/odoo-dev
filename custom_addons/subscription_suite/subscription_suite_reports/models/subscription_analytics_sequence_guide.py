from odoo import fields, models


class SubscriptionAnalyticsSequenceGuide(models.TransientModel):
    _name = 'subscription.analytics.sequence.guide'
    _description = 'Subscription Analytics Generation Sequence Guide'

    guide_text = fields.Text(
        string='Generation Sequence',
        default=lambda self: self._default_guide_text(),
        readonly=True,
    )

    def _default_guide_text(self):
        return """Generated analytics are operational report records. They are not static demo XML, accounting revenue recognition, or normalized multi-currency reporting.

Recommended generation order:
01. Generate MRR Snapshot for the opening date and closing date.
02. Generate MRR Reconciliation for the same opening and closing dates.
03. Generate MRR Movement Anomalies for the same period when auditing movement-only rows.
04. Generate MRR KPI Summary after snapshots and reconciliation exist.
05. Generate MRR KPI Dashboard from KPI summaries for one company and currency.
06. Generate MRR Waterfall from KPI summaries for the same company, currency, and period.
07. Generate Retention Cohorts for the cohort month range.
08. Generate Revenue Forecast for the forecast month range.
09. Generate ARPU Summary after opening and closing MRR snapshots exist.
10. Generate LTV Summary after ARPU summaries and retention cohorts exist.
11. Generate Churn Reasons for cancelled or expired subscriptions in the selected period.
12. Generate Top Plans after snapshots, KPI summaries, ARPU, LTV, forecasts, and churn reasons exist.
13. Generate At-Risk Subscriptions from current operational payment, dunning, renewal, and cancellation signals.
14. Generate Payment Recovery after payment attempts, open recovery invoices, dunning attempts, and optional at-risk rows exist.
15. Generate Trial Conversion for periods with trial-started subscriptions.

Review rules:
- Keep company and currency scopes explicit; generated reports do not normalize currencies.
- Scoped reruns should replace only the selected scope and preserve adjacent generated rows.
- Missing-input statuses mean an upstream generated report or source signal is absent for the selected scope.
- Use source drilldown buttons on generated rows to verify the records behind the numbers."""
