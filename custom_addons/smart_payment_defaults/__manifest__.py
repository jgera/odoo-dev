{
    'name': 'Smart Payment Defaults',
    'version': '1.1',
    'category': 'Accounting',
    'summary': 'Set default payment amount to 0.0 and add safety confirmation dialogs.',
    'description': """
Smart Payment Defaults
======================
This module enhances the standard Odoo "Register Payment" wizard by:
1. Optionally defaulting the payment amount to 0.0 to force manual entry.
2. Adding a confirmation dialog before creating payments to prevent accidental submissions.
    """,
    'depends': ['account'],
    'data': [
        'views/account_payment_register_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
