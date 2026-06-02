{
    'name': 'Test Addon',
    'version': '1.0',
    'category': 'Extra Tools',
    'summary': 'A simple test addon for development setup.',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/test_task_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
