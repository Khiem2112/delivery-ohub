from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    length = fields.Integer(
        string='Length (cm)',
        default=0,
        help='Product length in centimeters.',
    )
    width = fields.Integer(
        string='Width (cm)',
        default=0,
        help='Product width in centimeters.',
    )
    height = fields.Integer(
        string='Height (cm)',
        default=0,
        help='Product height in centimeters.',
    )
