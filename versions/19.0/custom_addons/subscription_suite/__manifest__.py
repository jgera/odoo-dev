{
    'name': 'Subscription Suite',
    'version': '19.0.1.0.0',
    'category': 'Sales/Subscriptions',
    'summary': 'Complete subscription management suite',
    'description': """
Subscription Suite
==================
Odoo 19 Community Edition only.

Core module for subscription management. Features include:
* Subscription Plans with flexible billing intervals
* Subscription Lifecycle (Draft, Trial, Active, Paused, Cancelled, Expired)
* Automated recurring invoicing
* Customer Portal integration
    """,
    'author': 'Subscription Suite Contributors',
    'website': 'https://github.com/subscription-suite',
    'license': 'LGPL-3',
    'depends': ['sale_management', 'account', 'payment', 'mail', 'portal'],
    'data': [
        'security/subscription_security.xml',
        'security/ir.model.access.csv',
        'security/subscription_record_rules.xml',
        'data/sequence_data.xml',
        'data/cron_data.xml',
        'views/subscription_cancel_reason_views.xml',
        'views/subscription_plan_views.xml',
        'views/sale_order_views.xml',
        'wizard/subscription_close_wizard_views.xml',
        'views/menu_views.xml',
    ],
    'demo': [
        'demo/subscription_demo.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
