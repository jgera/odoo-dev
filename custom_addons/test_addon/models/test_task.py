from odoo import models, fields

class TestTask(models.Model):
    _name = 'test.task'
    _description = 'Test Task'

    name = fields.Char(string='Task Name', required=True)
    description = fields.Text(string='Description')
    is_done = fields.Boolean(string='Done?', default=False)
    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High')
    ], string='Priority', default='1')
