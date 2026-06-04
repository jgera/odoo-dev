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
    'depends': ['subscription_suite'],
    'data': [
        'security/report_security.xml',
        'security/ir.model.access.csv',
        'views/subscription_report_views.xml',
        'views/mrr_movement_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
