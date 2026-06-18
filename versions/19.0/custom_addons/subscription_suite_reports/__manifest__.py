{
    'name': 'Subscription Suite - Reporting & KPIs',
    'version': '19.0.1.0.0',
    'category': 'Sales/Subscriptions',
    'summary': 'Dashboards and analytics for subscriptions',
    'description': """
Subscription Suite - Reports
============================
Odoo 19 Community Edition only.

Provides analytics:
* MRR and ARR tracking
* Churn analysis
* New vs Expansion revenue
    """,
    'author': 'Subscription Suite Contributors',
    'website': 'https://github.com/subscription-suite',
    'license': 'LGPL-3',
    'depends': ['subscription_suite', 'subscription_suite_billing', 'subscription_suite_dunning'],
    'data': [
        'security/report_security.xml',
        'security/ir.model.access.csv',
        'data/cron_data.xml',
        'views/subscription_report_views.xml',
        'views/mrr_movement_views.xml',
        'views/subscription_mrr_snapshot_views.xml',
        'views/subscription_mrr_reconciliation_views.xml',
        'views/subscription_mrr_movement_anomaly_views.xml',
        'views/subscription_mrr_kpi_summary_views.xml',
        'views/subscription_mrr_kpi_dashboard_views.xml',
        'views/subscription_mrr_waterfall_views.xml',
        'views/subscription_retention_cohort_views.xml',
        'views/subscription_revenue_forecast_views.xml',
        'views/subscription_arpu_summary_views.xml',
        'views/subscription_ltv_summary_views.xml',
        'views/subscription_churn_reason_summary_views.xml',
        'views/subscription_plan_performance_summary_views.xml',
        'views/subscription_at_risk_summary_views.xml',
        'views/subscription_payment_recovery_summary_views.xml',
        'views/subscription_trial_conversion_summary_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
