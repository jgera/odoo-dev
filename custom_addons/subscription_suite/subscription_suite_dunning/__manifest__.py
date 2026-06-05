{
    'name': 'Subscription Suite - Dunning & Recovery',
    'version': '19.0.1.0.0',
    'category': 'Sales/Subscriptions',
    'summary': 'Automated collections and failed payment recovery',
    'description': """
Subscription Suite - Dunning
============================
Odoo 19 Community Edition only.

Handles failed payments and collections:
* Configurable dunning policies
* Automated email reminders
* Subscription pausing and cancellation rules
    """,
    'author': 'Subscription Suite Contributors',
    'website': 'https://github.com/subscription-suite',
    'license': 'LGPL-3',
    'depends': ['subscription_suite_billing'],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'data/email_templates.xml',
        'data/cron_data.xml',
        'data/default_dunning_policy.xml',
        'views/dunning_attempt_views.xml',
        'views/subscription_manager_operation_dashboard_views.xml',
        'views/dunning_policy_views.xml',
        'views/subscription_plan_views.xml',
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
