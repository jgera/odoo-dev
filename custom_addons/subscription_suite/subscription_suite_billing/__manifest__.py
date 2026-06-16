{
    'name': 'Subscription Suite - Billing & Proration',
    'version': '19.0.1.0.0',
    'category': 'Sales/Subscriptions',
    'summary': 'Advanced billing, proration, and auto-payments for subscriptions',
    'description': """
Subscription Suite - Billing
============================
Odoo 19 Community Edition only.

Handles advanced billing scenarios:
* Prorated billing for plan changes
* Automated payment collection via tokens
* Stored payment methods
    """,
    'author': 'Subscription Suite Contributors',
    'website': 'https://github.com/subscription-suite',
    'license': 'LGPL-3',
    'depends': ['subscription_suite', 'payment'],
    'data': [
        'security/ir.model.access.csv',
        'security/plan_change_request_rules.xml',
        'data/sequence_data.xml',
        'data/cron_data.xml',
        'views/subscription_billing_views.xml',
        'views/subscription_usage_views.xml',
        'views/subscription_proration_views.xml',
        'views/subscription_plan_views.xml',
        'views/subscription_plan_change_request_views.xml',
        'views/subscription_manager_operation_views.xml',
        'views/sale_order_views.xml',
        'wizard/res_config_settings_views.xml',
        'wizard/subscription_change_plan_wizard_views.xml',
        'wizard/subscription_change_seats_wizard_views.xml',
        'wizard/subscription_change_addons_wizard_views.xml',
        'wizard/subscription_change_discounts_wizard_views.xml',
    ],
    'demo': [
        'demo/plan_change_approval_demo.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
