from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    ward_id = fields.Many2one(
        comodel_name='res.admin.unit',
        string='Ward / Commune',
        domain="[('state_id', '=?', state_id)]",
        index=True,
    )

    @api.onchange('state_id')
    def _onchange_state_id_ohub(self):
        if self.ward_id and self.ward_id.state_id != self.state_id:
            self.ward_id = False

    @api.onchange('country_id')
    def _onchange_country_id_ohub(self):
        if self.country_id and self.country_id.code != 'VN':
            self.ward_id = False

    def check_delivery_address_ready(self):
        self.ensure_one()
        is_vietnam = self.country_id and self.country_id.code == 'VN'
        if not is_vietnam:
            return True

        missing_fields = []
        if not self.state_id:
            missing_fields.append(_('State / Province'))
        if not self.ward_id:
            missing_fields.append(_('Ward / Commune'))
        if not self.street:
            missing_fields.append(_('Street Address'))
        if not self.phone and not self.mobile:
            missing_fields.append(_('Contact Phone Number'))

        if missing_fields:
            raise UserError(
                _("Partner address for '%(partner_name)s' is missing required fields: %(fields)s.")
                % {
                    'partner_name': self.name,
                    'fields': ', '.join(missing_fields),
                }
            )
        return True
