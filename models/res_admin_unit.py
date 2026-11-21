from odoo import api, fields, models, _


class ResAdminUnit(models.Model):
    _name = 'res.admin.unit'
    _description = 'Administrative Unit (ORIS)'
    _order = 'level, code, name'

    name = fields.Char(string='Unit Name', required=True, index=True)
    code = fields.Char(string='Unit Code', required=True, index=True)
    level = fields.Selection(
        selection=[
            ('1', 'Province / City'),
            ('2', 'District'),
            ('3', 'Ward / Commune'),
        ],
        string='Administrative Level',
        required=True,
        default='1',
        index=True,
    )
    state_id = fields.Many2one(
        comodel_name='res.country.state',
        string='State / Province',
        domain="[('country_id.code', '=', 'VN')]",
        index=True,
        ondelete='cascade',
    )
    parent_id = fields.Many2one(
        comodel_name='res.admin.unit',
        string='Parent Unit',
        index=True,
        ondelete='cascade',
    )
    child_ids = fields.One2many(
        comodel_name='res.admin.unit',
        inverse_name='parent_id',
        string='Subordinate Units',
    )
    mapping_ids = fields.One2many(
        comodel_name='delivery.address.mapping',
        inverse_name='oris_ward_id',
        string='Carrier Address Mappings',
    )
    mapping_count = fields.Integer(
        string='Carrier Mapping Count',
        compute='_compute_mapping_count',
    )
    country_id = fields.Many2one(
        comodel_name='res.country',
        string='Country',
        default=lambda self: self.env.ref('base.vn', raise_if_not_found=False),
        index=True,
    )
    active = fields.Boolean(string='Active', default=True)

    _sql_constraints = [
        (
            'unique_code_level_country',
            'unique(code, level, country_id)',
            'The administrative unit code must be unique per level and country.',
        ),
    ]

    @api.depends('name', 'level', 'state_id.name', 'parent_id.name')
    def _compute_display_name(self):
        for unit in self:
            parent_name = unit.state_id.name or (unit.parent_id.name if unit.parent_id else '')
            if parent_name:
                unit.display_name = f"{unit.name}, {parent_name}"
            else:
                unit.display_name = unit.name or ''

    @api.depends()
    def _compute_mapping_count(self):
        mapping_data = self.env['delivery.address.mapping']._read_group(
            [('oris_ward_id', 'in', self.ids)],
            ['oris_ward_id'],
            ['__count'],
        )
        counts = {ward.id: count for ward, count in mapping_data}
        for unit in self:
            unit.mapping_count = counts.get(unit.id, 0)

    def action_view_address_mappings(self):
        self.ensure_one()
        return {
            'name': _('Carrier Address Mappings - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'delivery.address.mapping',
            'view_mode': 'list,form',
            'domain': [('oris_ward_id', '=', self.id)],
            'context': {
                'default_oris_ward_id': self.id,
                'default_state_id': self.state_id.id if self.state_id else False,
            },
        }
