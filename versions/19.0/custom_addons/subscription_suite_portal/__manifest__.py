{
    'name': 'Subscription Suite - Portal',
    'version': '19.0.1.0.0',
    'category': 'Sales/Subscriptions',
    'summary': 'Customer portal for viewing subscriptions',
    'description': """
Subscription Suite - Portal
===========================
Odoo 19 Community Edition only.

Allows customers to:
* View active subscriptions
* See billing history
    """,
    'author': 'Subscription Suite Contributors',
    'website': 'https://github.com/subscription-suite',
    'license': 'LGPL-3',
    'depends': ['subscription_suite', 'portal'],
    'data': [
        'views/portal_templates.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
