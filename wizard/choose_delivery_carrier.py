from odoo.exceptions import UserError

from odoo import _, api, fields, models


class ChooseDeliveryCarrier(models.TransientModel):
    _inherit = "choose.delivery.carrier"

    order_id = fields.Many2one(
        comodel_name="sale.order",
        required=False,
        ondelete="cascade",
    )
    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Delivery Order",
        ondelete="cascade",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
        compute="_compute_partner_id",
        inverse="_inverse_partner_id",
        required=False,
        readonly=False,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        compute="_compute_company_id",
        related=False,
        readonly=False,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="Currency",
        compute="_compute_currency_id",
        related=False,
        readonly=False,
    )
    total_weight = fields.Float(
        string="Total Order Weight",
        compute="_compute_total_weight",
        inverse="_inverse_total_weight",
        readonly=False,
    )
    is_ohub = fields.Boolean(
        string="Is oHUB Carrier",
        compute="_compute_is_ohub",
    )
    fee_quote_ids = fields.One2many(
        comodel_name="delivery.fee.quote",
        inverse_name="wizard_id",
        string="Available Service Package Quotes",
    )
    selected_quote_id = fields.Many2one(
        comodel_name="delivery.fee.quote",
        string="Selected Package Quote",
    )
    service_type = fields.Selection(
        selection=[
            ("standard", "Standard Delivery"),
            ("express", "Express Delivery"),
            ("economy", "Economy Delivery"),
        ],
        string="Service Type",
        default="standard",
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
        currency_field="currency_id",
        help="Amount to be collected from recipient if delivery fails.",
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

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        picking_id = res.get("picking_id") or self.env.context.get("default_picking_id")
        order_id = res.get("order_id") or self.env.context.get("default_order_id")
        if picking_id:
            picking = self.env["stock.picking"].browse(picking_id)
            if picking.exists():
                res["picking_id"] = picking.id
                if "partner_id" in fields_list and not res.get("partner_id"):
                    res["partner_id"] = picking.partner_id.id
                if "company_id" in fields_list and not res.get("company_id"):
                    res["company_id"] = picking.company_id.id
                if "currency_id" in fields_list and not res.get("currency_id"):
                    res["currency_id"] = (
                        picking.company_id.currency_id.id
                        or self.env.company.currency_id.id
                    )
                if "total_weight" in fields_list and not res.get("total_weight"):
                    res["total_weight"] = picking.weight
                if (
                    "carrier_id" in fields_list
                    and not res.get("carrier_id")
                    and picking.carrier_id
                ):
                    res["carrier_id"] = picking.carrier_id.id
                if "payment_type_id" in fields_list:
                    if picking.shipping_payment_type:
                        res["payment_type_id"] = picking.shipping_payment_type
                    elif picking.backorder_id:
                        res["payment_type_id"] = "1"
        elif order_id:
            order = self.env["sale.order"].browse(order_id)
            if order.exists():
                res["order_id"] = order.id
                if "partner_id" in fields_list and not res.get("partner_id"):
                    res["partner_id"] = (
                        order.partner_shipping_id or order.partner_id
                    ).id
                if "company_id" in fields_list and not res.get("company_id"):
                    res["company_id"] = order.company_id.id
                if "currency_id" in fields_list and not res.get("currency_id"):
                    res["currency_id"] = order.currency_id.id
                if "total_weight" in fields_list and not res.get("total_weight"):
                    res["total_weight"] = order.shipping_weight
                if (
                    "carrier_id" in fields_list
                    and not res.get("carrier_id")
                    and order.carrier_id
                ):
                    res["carrier_id"] = order.carrier_id.id
        return res

    @api.depends("order_id.partner_id", "picking_id.partner_id")
    def _compute_partner_id(self):
        for wizard in self:
            if wizard.order_id:
                wizard.partner_id = wizard.order_id.partner_id
            elif wizard.picking_id:
                wizard.partner_id = wizard.picking_id.partner_id
            else:
                wizard.partner_id = False

    def _inverse_partner_id(self):
        for wizard in self:
            if wizard.order_id and not wizard.order_id.partner_id:
                wizard.order_id.partner_id = wizard.partner_id

    @api.depends("order_id.company_id", "picking_id.company_id")
    def _compute_company_id(self):
        for wizard in self:
            if wizard.order_id and wizard.order_id.company_id:
                wizard.company_id = wizard.order_id.company_id
            elif wizard.picking_id and wizard.picking_id.company_id:
                wizard.company_id = wizard.picking_id.company_id
            else:
                wizard.company_id = self.env.company

    @api.depends(
        "order_id.currency_id",
        "picking_id.company_id.currency_id",
        "carrier_id.currency_id",
    )
    def _compute_currency_id(self):
        for wizard in self:
            if wizard.order_id and wizard.order_id.currency_id:
                wizard.currency_id = wizard.order_id.currency_id
            elif wizard.picking_id and wizard.picking_id.company_id.currency_id:
                wizard.currency_id = wizard.picking_id.company_id.currency_id
            elif wizard.carrier_id and wizard.carrier_id.currency_id:
                wizard.currency_id = wizard.carrier_id.currency_id
            else:
                wizard.currency_id = self.env.company.currency_id

    @api.depends("order_id.shipping_weight", "picking_id.weight")
    def _compute_total_weight(self):
        for wizard in self:
            if wizard.order_id:
                wizard.total_weight = wizard.order_id.shipping_weight
            elif wizard.picking_id:
                wizard.total_weight = wizard.picking_id.weight
            else:
                wizard.total_weight = 0.0

    def _inverse_total_weight(self):
        for wizard in self:
            if wizard.order_id:
                wizard.order_id.shipping_weight = wizard.total_weight

    @api.depends("carrier_id")
    def _compute_is_ohub(self):
        for wizard in self:
            wizard.is_ohub = bool(
                wizard.carrier_id and wizard.carrier_id.delivery_type == "ohub"
            )

    @api.depends("partner_id", "order_id", "picking_id")
    def _compute_available_carrier(self):
        for rec in self:
            company = rec.company_id or self.env.company
            carriers = self.env["delivery.carrier"].search(
                self.env["delivery.carrier"]._check_company_domain(company)
            )
            shipping_partner = False
            if rec.order_id:
                shipping_partner = (
                    rec.order_id.partner_shipping_id or rec.order_id.partner_id
                )
                rec.available_carrier_ids = (
                    carriers.available_carriers(shipping_partner, rec.order_id)
                    if shipping_partner
                    else carriers
                )
            elif rec.picking_id:
                shipping_partner = rec.picking_id.partner_id
                sale_order = rec.picking_id.sale_id
                if sale_order and shipping_partner:
                    rec.available_carrier_ids = carriers.available_carriers(
                        shipping_partner, sale_order
                    )
                elif shipping_partner:
                    rec.available_carrier_ids = carriers.filtered(
                        lambda c: c._match_address(shipping_partner)
                    )
                else:
                    rec.available_carrier_ids = carriers
            else:
                rec.available_carrier_ids = carriers

    def _set_quote_price(self, quote):
        if not quote:
            self.selected_quote_id = False
            self.display_price = 0.0
            self.delivery_price = 0.0
            self.delivery_message = False
            return
        self.selected_quote_id = quote.id
        self.service_type = quote.service_type
        self.display_price = quote.total_fee
        self.delivery_price = 0.0 if self.payment_type_id == "2" else quote.total_fee
        self.delivery_message = quote.error_message or False

    @api.onchange("fee_quote_ids")
    def _onchange_fee_quote_ids(self):
        selected = self.fee_quote_ids.filtered(lambda q: q.is_selected)[:1]
        self._set_quote_price(selected)

    @api.onchange("carrier_id")
    def _onchange_carrier_id_ohub(self):
        if not self.carrier_id or self.carrier_id.delivery_type != "ohub":
            return

        if self.fee_quote_ids:
            other_quotes = self.fee_quote_ids.filtered(
                lambda q: q.carrier_id != self.carrier_id
            )
            if other_quotes:
                other_quotes.unlink()

        if self.order_id:
            if self.order_id.shipping_payment_type:
                self.payment_type_id = self.order_id.shipping_payment_type
            if self.order_id.delivery_service_type:
                self.service_type = self.order_id.delivery_service_type
            lines = self.order_id.order_line.filtered(lambda l: not l.is_delivery)
            l, w, h = self.env["delivery.shipping.order"]._compute_package_dimensions(
                lines,
                default_length=0,
                default_width=0,
                default_height=0,
            )
            if l and w and h:
                self.package_length = l
                self.package_width = w
                self.package_height = h

        elif self.picking_id:
            picking = self.picking_id
            if picking.shipping_payment_type:
                self.payment_type_id = picking.shipping_payment_type
            elif picking.sale_id and picking.sale_id.shipping_payment_type:
                self.payment_type_id = picking.sale_id.shipping_payment_type

            if picking.delivery_service_type:
                self.service_type = picking.delivery_service_type

            if (
                picking.package_length
                and picking.package_width
                and picking.package_height
            ):
                self.package_length = picking.package_length
                self.package_width = picking.package_width
                self.package_height = picking.package_height
            else:
                lines = picking.move_line_ids.filtered(lambda l: l.quantity > 0)
                if not lines:
                    lines = picking.move_ids.filtered(
                        lambda m: (m.quantity or m.product_uom_qty) > 0
                    )
                calc_l, calc_w, calc_h = self.env["delivery.shipping.order"]._compute_package_dimensions(
                    lines,
                    default_length=0,
                    default_width=0,
                    default_height=0,
                )
                if calc_l and calc_w and calc_h:
                    self.package_length = calc_l
                    self.package_width = calc_w
                    self.package_height = calc_h
                elif picking.package_length and picking.package_width and picking.package_height:
                    self.package_length = picking.package_length
                    self.package_width = picking.package_width
                    self.package_height = picking.package_height

            if picking.cod_failed_amount:
                self.cod_failed_amount = picking.cod_failed_amount

    @api.onchange("selected_quote_id")
    def _onchange_selected_quote_id(self):
        self._set_quote_price(self.selected_quote_id)

    @api.onchange("payment_type_id")
    def _onchange_payment_type_id_ohub(self):
        if self.delivery_type == "ohub":
            base_fee = (
                self.selected_quote_id.total_fee
                if self.selected_quote_id
                else self.display_price
            )
            self.delivery_price = 0.0 if self.payment_type_id == "2" else base_fee

    def action_fetch_services_wizard(self):
        self.ensure_one()
        if not self.carrier_id or self.delivery_type != "ohub":
            return False

        if (
            not self.package_length
            or not self.package_width
            or not self.package_height
            or self.package_length <= 0
            or self.package_width <= 0
            or self.package_height <= 0
        ):
            raise UserError(
                _("Package dimensions (Length, Width, Height) must be greater than zero to fetch services.")
            )

        if not self.payment_type_id:
            raise UserError(
                _("Shipping payment type is required to fetch services.")
            )

        quotes = self.carrier_id.ohub_fetch_available_services(self)
        if quotes:
            target_service_code = ""
            if self.order_id and self.order_id.delivery_service_code:
                target_service_code = self.order_id.delivery_service_code
            elif self.picking_id and self.picking_id.delivery_service_code:
                target_service_code = self.picking_id.delivery_service_code

            selected = False
            if target_service_code:
                matched = quotes.filtered(
                    lambda q: q.service_code == target_service_code
                )
                if matched:
                    selected = matched[:1]

            if not selected:
                selected = quotes.filtered(
                    lambda q: q.service_type == self.service_type
                )[:1]
            if not selected:
                selected = quotes[:1]

            if selected:
                quotes.write({"is_selected": False})
                selected.write({"is_selected": True})
                if selected.total_fee <= 0.0:
                    self.carrier_id.ohub_calculate_quote_fee(selected)
                self._set_quote_price(selected)

        return {
            "type": "ir.actions.act_window",
            "res_model": "choose.delivery.carrier",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def _get_delivery_rate(self):
        if self.delivery_type == "ohub":
            selected = (
                self.fee_quote_ids.filtered(lambda q: q.is_selected)[:1]
                or self.selected_quote_id
                or self.fee_quote_ids[:1]
            )
            if selected:
                try:
                    with self.env.cr.savepoint():
                        self.carrier_id.ohub_calculate_quote_fee(selected)
                        self._set_quote_price(selected)
                        if selected.error_message:
                            return {"error_message": selected.error_message, "no_rate": True}
                        return {"no_rate": False}
                except Exception as e:
                    self.delivery_message = str(e)
                    return {"error_message": str(e), "no_rate": True}

            self._set_quote_price(False)
            return {"no_rate": True}

        if not self.order_id:
            return {
                "error_message": _(
                    "Rate calculation on delivery orders is supported through oHUB carriers."
                )
            }

        return super()._get_delivery_rate()

    def button_confirm(self):
        if self.delivery_type == "ohub":
            target_quote = (
                self.fee_quote_ids.filtered(lambda q: q.is_selected)[:1]
                or self.selected_quote_id
                or self.fee_quote_ids[:1]
            )
            if target_quote and target_quote.error_message:
                raise UserError(
                    _("Cannot confirm delivery method: %s") % target_quote.error_message
                )

            service_id = target_quote.service_id if target_quote else False
            service_code = (
                target_quote.service_code
                if target_quote
                else (str(service_id) if service_id else "")
            )
            service_name = (
                target_quote.service_name
                if target_quote
                else dict(self._fields["service_type"].selection).get(
                    self.service_type, _("Standard")
                )
            )
            total_fee = target_quote.total_fee if target_quote else self.display_price
            line_price = 0.0 if self.payment_type_id == "2" else total_fee

            service_type = (
                target_quote.service_type
                if target_quote and target_quote.service_type
                else self.service_type
            )

            if (
                not self.package_length
                or not self.package_width
                or not self.package_height
                or self.package_length <= 0
                or self.package_width <= 0
                or self.package_height <= 0
            ):
                raise UserError(
                    _("Package dimensions (Length, Width, Height) must be greater than zero.")
                )

            if not self.payment_type_id:
                raise UserError(
                    _("Shipping payment type is required.")
                )

            if self.order_id:
                self.order_id.write(
                    {
                        "carrier_id": self.carrier_id.id,
                        "delivery_service_id": service_id,
                        "delivery_service_name": service_name,
                        "delivery_service_code": service_code,
                        "delivery_service_type": service_type,
                        "shipping_payment_type": self.payment_type_id,
                        "fee_outdated": False,
                    }
                )
                self.delivery_price = line_price
                self.order_id.set_delivery_line(self.carrier_id, line_price)
                self.order_id.write(
                    {
                        "recompute_delivery_price": False,
                        "delivery_message": self.delivery_message,
                    }
                )

            if self.picking_id:
                sale_order = self.picking_id.sale_id
                is_backorder = bool(self.picking_id.backorder_id) or bool(
                    sale_order
                    and sale_order.shipping_order_ids.filtered(
                        lambda s: (
                            s.picking_id != self.picking_id
                            and s.internal_state not in ["cancelled"]
                            and s.carrier_status not in ["cancel"]
                        )
                    )
                )
                has_charged_delivery = bool(
                    sale_order
                    and sale_order.order_line.filtered(
                        lambda l: l.is_delivery and l.price_total > 0
                    )
                )
                if not is_backorder and has_charged_delivery and self.payment_type_id == "2":
                    raise UserError(
                        _(
                            "Sale order %(so)s already includes a delivery fee on the order. "
                            "Cannot set shipping payment type to 'Recipient Pays' (payment_type = 2) for the first shipment "
                            "as it would double charge the customer. "
                            "Please use 'Sender / Shop Pays' (payment_type = 1) or adjust the delivery line on the sale order first."
                        )
                        % {"so": sale_order.name}
                    )

                picking_vals = {
                    "carrier_id": self.carrier_id.id,
                    "delivery_service_id": service_id,
                    "delivery_service_name": service_name,
                    "delivery_service_code": service_code,
                    "delivery_service_type": service_type,
                    "shipping_payment_type": self.payment_type_id,
                    "package_length": self.package_length,
                    "package_width": self.package_width,
                    "package_height": self.package_height,
                    "cod_failed_amount": self.cod_failed_amount or 0.0,
                }
                self.picking_id.write(picking_vals)

                prep_data = self.env["delivery.shipping.order"]._prepare_shipping_data_from_picking(
                    self.picking_id, carrier=self.carrier_id
                )

                carrier_curr = self.carrier_id.currency_id or self.picking_id.company_id.currency_id
                picking_curr = self.picking_id.company_currency_id or self.picking_id.company_id.currency_id
                company = self.picking_id.company_id or self.company_id or self.env.company
                date_rate = fields.Date.today()

                picking_goods = prep_data.get("goods_amount", 0.0)
                picking_shipping = prep_data.get("shipping_fee_amount", 0.0)
                if carrier_curr and picking_curr and carrier_curr != picking_curr:
                    picking_goods = picking_curr.round(
                        carrier_curr._convert(picking_goods, picking_curr, company, date_rate)
                    )
                    picking_shipping = picking_curr.round(
                        carrier_curr._convert(picking_shipping, picking_curr, company, date_rate)
                    )

                self.picking_id.write({
                    "goods_amount": picking_goods,
                    "shipping_fee_amount": picking_shipping,
                })

                draft_ship = self.picking_id.shipping_order_ids.filtered(
                    lambda s: s.internal_state == "draft" and not s.order_code
                )[:1]
                if draft_ship:
                    quote_currency = self.currency_id

                    draft_fee = total_fee
                    if quote_currency and carrier_curr and quote_currency != carrier_curr:
                        draft_fee = quote_currency._convert(
                            draft_fee,
                            carrier_curr,
                            company,
                            date_rate,
                        )

                    cod_failed = self.cod_failed_amount or 0.0
                    if cod_failed and quote_currency and carrier_curr and quote_currency != carrier_curr:
                        cod_failed = quote_currency._convert(
                            cod_failed,
                            carrier_curr,
                            company,
                            date_rate,
                        )

                    draft_ship.write(
                        {
                            "carrier_id": self.carrier_id.id,
                            "service_id": service_id,
                            "service_name": service_name,
                            "service_code": service_code,
                            "service_type": service_type,
                            "payment_type_id": self.payment_type_id,
                            "length": self.package_length,
                            "width": self.package_width,
                            "height": self.package_height,
                            "cod_failed_amount": cod_failed,
                            "estimated_fee": draft_fee,
                            "cod_amount": prep_data.get("cod_amount", 0.0),
                            "goods_amount": prep_data.get("goods_amount", 0.0),
                            "shipping_fee_amount": prep_data.get("shipping_fee_amount", 0.0),
                            "insurance_value": prep_data.get("insurance_value", 0.0),
                        }
                    )

            return {"type": "ir.actions.act_window_close"}

        if self.order_id:
            return super().button_confirm()

        if self.picking_id:
            self.picking_id.carrier_id = self.carrier_id
            return {"type": "ir.actions.act_window_close"}

        return {"type": "ir.actions.act_window_close"}
