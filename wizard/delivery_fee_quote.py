from odoo import api, fields, models


class DeliveryFeeQuote(models.TransientModel):
    _name = "delivery.fee.quote"
    _description = "Detailed Shipping Fee Quote"
    _order = "total_fee asc, id"

    wizard_id = fields.Many2one(
        comodel_name="choose.delivery.carrier",
        string="Delivery Wizard",
        required=False,
        ondelete="cascade",
        index=True,
    )
    carrier_id = fields.Many2one(
        comodel_name="delivery.carrier",
        string="Delivery Method",
        compute="_compute_carrier_id",
        store=True,
        readonly=False,
        required=False,
    )
    service_id = fields.Integer(string="Carrier Service ID", index=True)
    service_code = fields.Char(string="Service Code", index=True)
    service_name = fields.Char(string="Service Package", required=False, default="Standard Delivery")
    service_type = fields.Selection(
        selection=[
            ("standard", "Standard Delivery"),
            ("express", "Express Delivery"),
            ("economy", "Economy Delivery"),
        ],
        string="Service Type",
        default="standard",
    )
    service_fee = fields.Monetary(string="Base Fee")
    insurance_fee = fields.Monetary(string="Insurance Fee")
    cod_fee = fields.Monetary(string="COD Fee")
    total_fee = fields.Monetary(string="Estimated Total Fee", default=0.0)
    carrier_currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="Carrier Currency",
        compute="_compute_carrier_currency_id",
        store=True,
    )
    carrier_total_fee = fields.Monetary(
        string="Carrier Fee (Original)",
        currency_field="carrier_currency_id",
        default=0.0,
    )
    expected_delivery_time = fields.Datetime(string="Expected Delivery Date")
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="Currency",
        compute="_compute_currency_id",
        store=True,
        readonly=False,
    )
    payment_type_id = fields.Selection(
        selection=[
            ("1", "Sender / Shop Pays"),
            ("2", "Recipient Pays"),
        ],
        string="Shipping Payment Type",
        default="1",
    )
    cod_failed_amount = fields.Monetary(
        string="Failed Delivery Fee",
        default=0.0,
    )
    package_length = fields.Integer(
        string="Package Length (cm)",
        default=10,
    )
    package_width = fields.Integer(
        string="Package Width (cm)",
        default=10,
    )
    package_height = fields.Integer(
        string="Package Height (cm)",
        default=10,
    )
    is_selected = fields.Boolean(string="Selected", default=False)
    is_outdated = fields.Boolean(
        string="Outdated",
        default=False,
        help="Indicates whether the calculated rate is outdated due to cargo or address changes.",
    )
    error_message = fields.Char(
        string="Carrier Error",
        readonly=True,
        help="Error message returned by carrier API if rate calculation failed.",
    )

    @api.depends("wizard_id.carrier_id")
    def _compute_carrier_id(self):
        for quote in self:
            if not quote.carrier_id and quote.wizard_id.carrier_id:
                quote.carrier_id = quote.wizard_id.carrier_id

    @api.onchange("is_selected")
    def _onchange_is_selected(self):
        if self.is_selected and self.wizard_id:
            for sibling in self.wizard_id.fee_quote_ids:
                if sibling != self:
                    sibling.is_selected = False

    @api.depends("carrier_id.currency_id", "wizard_id.carrier_id.currency_id")
    def _compute_carrier_currency_id(self):
        for quote in self:
            carrier = quote.carrier_id or quote.wizard_id.carrier_id
            quote.carrier_currency_id = carrier.currency_id if carrier else False

    @api.depends("wizard_id.carrier_id.currency_id", "wizard_id.currency_id")
    def _compute_currency_id(self):
        for quote in self:
            quote.currency_id = (
                quote.wizard_id.currency_id
                or quote.carrier_id.currency_id
                or quote.env.company.currency_id
            )

    def action_calculate_fee(self):
        self.ensure_one()
        carrier = self.carrier_id or self.wizard_id.carrier_id
        if carrier:
            carrier.ohub_calculate_quote_fee(self)
        if self.wizard_id:
            for sibling in self.wizard_id.fee_quote_ids:
                sibling.is_selected = (sibling.id == self.id)
            self.wizard_id._set_quote_price(self)
            return {
                "type": "ir.actions.act_window",
                "res_model": "choose.delivery.carrier",
                "res_id": self.wizard_id.id,
                "view_mode": "form",
                "target": "new",
            }
        return True

    def action_select_quote(self):
        self.ensure_one()
        if self.total_fee <= 0.0 and not self.error_message:
            return self.action_calculate_fee()

        if self.wizard_id:
            for sibling in self.wizard_id.fee_quote_ids:
                sibling.is_selected = (sibling.id == self.id)
            self.wizard_id._set_quote_price(self)
            return {
                "type": "ir.actions.act_window",
                "res_model": "choose.delivery.carrier",
                "res_id": self.wizard_id.id,
                "view_mode": "form",
                "target": "new",
            }
        return False
