from odoo import api, fields, models, _
from odoo.exceptions import UserError


class DeliveryAddressMapping(models.Model):
    _name = 'delivery.address.mapping'
    _description = 'ORIS - Carrier Address Mapping'
    _order = 'state_id, oris_ward_id, id desc'

    name = fields.Char(string='Mapping Description', compute='_compute_name', store=True)
    carrier_id = fields.Many2one(
        comodel_name='delivery.carrier',
        string='Delivery Method',
        index=True,
        ondelete='cascade',
    )
    hub_flow_id = fields.Many2one(
        comodel_name='hub.flow',
        string='oHUB Integration Flow',
        index=True,
        ondelete='cascade',
    )
    state_id = fields.Many2one(
        comodel_name='res.country.state',
        string='State / Province',
        domain="[('country_id.code', '=', 'VN')]",
        index=True,
        required=True,
        ondelete='cascade',
    )
    oris_ward_id = fields.Many2one(
        comodel_name='res.admin.unit',
        string='Ward / Commune',
        domain="[('state_id', '=?', state_id)]",
        index=True,
        required=True,
        ondelete='cascade',
    )
    external_province_id = fields.Integer(string='Carrier Province ID')
    external_province_name = fields.Char(string='Carrier Province Name')
    external_district_id = fields.Integer(string='Carrier District ID')
    external_district_name = fields.Char(string='Carrier District Name')
    external_ward_code = fields.Char(string='Carrier Ward Code', required=True)
    external_ward_name = fields.Char(string='Carrier Ward Name')
    state = fields.Selection(
        selection=[
            ('matched', 'Matched'),
            ('unmatched', 'Unmatched'),
        ],
        string='Status',
        default='matched',
        required=True,
        index=True,
    )
    match_method = fields.Selection(
        selection=[
            ('auto', 'Automatic'),
            ('manual', 'Manual'),
        ],
        string='Matching Method',
        default='manual',
        required=True,
    )
    is_default = fields.Boolean(
        string='Default on Duplicate Route',
        default=True,
        help='Prioritize using this mapping if a ward corresponds to multiple carrier codes.',
    )
    active = fields.Boolean(string='Active', default=True)

    @api.depends('oris_ward_id.name', 'state_id.name', 'external_ward_name', 'external_ward_code')
    def _compute_name(self):
        for rec in self:
            oris_label = f"{rec.oris_ward_id.name or ''}, {rec.state_id.name or ''}".strip(', ')
            external_label = f"{rec.external_ward_name or ''} [{rec.external_ward_code or ''}]".strip()
            rec.name = f"{oris_label} -> {external_label}" if (oris_label or external_label) else _('New Mapping')

    @api.model
    def resolve_carrier_address(self, carrier, state=None, ward=None):
        if not state or not ward:
            raise UserError(_("Missing State/Province or Ward/Commune to resolve shipping address."))

        domain = [
            ('state_id', '=', state.id),
            ('oris_ward_id', '=', ward.id),
            ('active', '=', True),
            ('state', '=', 'matched'),
        ]
        carrier_domain = list(domain)
        if carrier.hub_flow_id and carrier.id:
            carrier_domain += [
                '|',
                ('carrier_id', '=', carrier.id),
                '&',
                ('carrier_id', '=', False),
                ('hub_flow_id', '=', carrier.hub_flow_id.id),
            ]
        elif carrier.hub_flow_id:
            carrier_domain += [('hub_flow_id', '=', carrier.hub_flow_id.id)]
        elif carrier.id:
            carrier_domain += [('carrier_id', '=', carrier.id)]

        mapping = self.search(carrier_domain, order='is_default desc, id desc', limit=1)
        if not mapping:
            raise UserError(
                _("The address '%(ward)s, %(state)s' has not been mapped for delivery method '%(carrier)s'.")
                % {
                    'ward': ward.name,
                    'state': state.name,
                    'carrier': carrier.name,
                }
            )
        return mapping
