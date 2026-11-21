from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    delivery_service_id = fields.Integer(
        string="Carrier Service ID",
        copy=False,
    )
    delivery_service_name = fields.Char(
        string="Carrier Service Name",
        copy=False,
    )
    delivery_service_code = fields.Char(
        string="Carrier Service Code",
        copy=False,
    )
    delivery_service_type = fields.Selection(
        selection=[
            ("standard", "Standard Delivery"),
            ("express", "Express Delivery"),
            ("economy", "Economy Delivery"),
        ],
        string="Carrier Service Type",
        default="standard",
        copy=False,
    )
    shipping_payment_type = fields.Selection(
        selection=[
            ("1", "Sender / Shop Pays"),
            ("2", "Recipient Pays"),
        ],
        string="Shipping Payment Type",
        default="1",
        help="Shipping fee payment policy: Shop pays carrier and collects via COD/prepayment, or customer pays driver directly.",
    )
    package_length = fields.Integer(string="Package Length (cm)")
    package_width = fields.Integer(string="Package Width (cm)")
    package_height = fields.Integer(string="Package Height (cm)")
    cod_failed_amount = fields.Monetary(
        string="Failed Delivery Fee",
        default=0.0,
        currency_field="company_currency_id",
    )
    goods_amount = fields.Monetary(
        string="Goods Amount",
        currency_field="company_currency_id",
    )
    shipping_fee_amount = fields.Monetary(
        string="Shipping Fee Amount",
        currency_field="company_currency_id",
    )
    company_currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="Company Currency",
        related="company_id.currency_id",
        readonly=True,
    )
    shipping_order_ids = fields.One2many(
        comodel_name="delivery.shipping.order",
        inverse_name="picking_id",
        string="Shipping Orders",
    )
    shipping_order_count = fields.Integer(
        string="Shipping Order Count",
        compute="_compute_shipping_order_count",
    )
    has_active_shipping_order = fields.Boolean(
        string="Has Active Shipping Order",
        compute="_compute_has_active_shipping_order",
    )

    def _get_active_shipping_order(self):
        self.ensure_one()
        inactive_internal = {"cancelled", "returned", "delivered"}
        inactive_carrier = {"cancel", "returned", "delivered"}
        return self.shipping_order_ids.filtered(
            lambda s: s.internal_state not in inactive_internal
            and s.carrier_status not in inactive_carrier
        )[:1]

    @api.depends("shipping_order_ids")
    def _compute_shipping_order_count(self):
        for picking in self:
            picking.shipping_order_count = len(picking.shipping_order_ids)

    @api.depends("shipping_order_ids.internal_state", "shipping_order_ids.carrier_status")
    def _compute_has_active_shipping_order(self):
        for picking in self:
            picking.has_active_shipping_order = bool(picking._get_active_shipping_order())

    @api.constrains("shipping_payment_type", "carrier_id")
    def _check_shipping_payment_type(self):
        for picking in self:
            if picking.carrier_id and picking.carrier_id.delivery_type == "ohub":
                sale = picking.sale_id
                if not sale or picking.picking_type_code == "incoming":
                    continue
                is_backorder = bool(picking.backorder_id) or bool(
                    sale.shipping_order_ids.filtered(
                        lambda s: (
                            s.picking_id != picking
                            and s.internal_state not in ["cancelled"]
                            and s.carrier_status not in ["cancel"]
                        )
                    )
                )
                has_charged_delivery = bool(
                    sale.order_line.filtered(
                        lambda l: l.is_delivery and l.price_total > 0
                    )
                )
                if not is_backorder and has_charged_delivery and picking.shipping_payment_type == "2":
                    raise UserError(
                        _(
                            "Sale order %(so)s already includes a delivery fee on the order. "
                            "Cannot set shipping payment type to 'Recipient Pays' (payment_type = 2) for the first shipment "
                            "as it would double charge the customer. "
                            "Please use 'Sender / Shop Pays' (payment_type = 1) or adjust the delivery line on the sale order first."
                        )
                        % {"so": sale.name}
                    )

    @api.onchange("shipping_payment_type")
    def _onchange_shipping_payment_type_ohub(self):
        if self.carrier_id and self.carrier_id.delivery_type == "ohub" and self.sale_id:
            if self.picking_type_code == "incoming":
                return
            target_picking = self._origin if hasattr(self, "_origin") and self._origin else self
            is_backorder = bool(self.backorder_id) or bool(
                self.sale_id.shipping_order_ids.filtered(
                    lambda s: (
                        s.picking_id != target_picking
                        and s.internal_state not in ["cancelled"]
                        and s.carrier_status not in ["cancel"]
                    )
                )
            )
            has_charged_delivery = bool(
                self.sale_id.order_line.filtered(
                    lambda l: l.is_delivery and l.price_total > 0
                )
            )
            if not is_backorder and has_charged_delivery and self.shipping_payment_type == "2":
                self.shipping_payment_type = "1"
                return {
                    "warning": {
                        "title": _("Invalid Payment Type"),
                        "message": _(
                            "Sale order %(so)s already includes a delivery fee on the order. "
                            "Cannot set shipping payment type to 'Recipient Pays' (payment_type = 2) for the first shipment "
                            "as it would double charge the customer. "
                            "Please use 'Sender / Shop Pays' (payment_type = 1) or adjust the delivery line on the sale order first."
                        )
                        % {"so": self.sale_id.name},
                    }
                }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            sale = False
            if vals.get("sale_id"):
                sale = self.env["sale.order"].browse(vals["sale_id"])
            elif vals.get("group_id"):
                sale = self.env["procurement.group"].browse(vals["group_id"]).sale_id
            if sale and sale.exists():
                if not vals.get("carrier_id") and sale.carrier_id:
                    vals["carrier_id"] = sale.carrier_id.id
                if not vals.get("delivery_service_id") and sale.delivery_service_id:
                    vals["delivery_service_id"] = sale.delivery_service_id
                if not vals.get("delivery_service_name") and sale.delivery_service_name:
                    vals["delivery_service_name"] = sale.delivery_service_name
                if not vals.get("delivery_service_code") and sale.delivery_service_code:
                    vals["delivery_service_code"] = sale.delivery_service_code
                if not vals.get("delivery_service_type") and sale.delivery_service_type:
                    vals["delivery_service_type"] = sale.delivery_service_type
                if not vals.get("shipping_payment_type"):
                    if vals.get("backorder_id"):
                        vals["shipping_payment_type"] = "1"
                    elif sale.shipping_payment_type:
                        vals["shipping_payment_type"] = sale.shipping_payment_type
        pickings = super().create(vals_list)

        for picking in pickings:
            sale = picking.sale_id
            if sale:
                write_vals = {}
                if not picking.carrier_id and sale.carrier_id:
                    write_vals["carrier_id"] = sale.carrier_id.id
                if not picking.delivery_service_id and sale.delivery_service_id:
                    write_vals["delivery_service_id"] = sale.delivery_service_id
                if not picking.delivery_service_name and sale.delivery_service_name:
                    write_vals["delivery_service_name"] = sale.delivery_service_name
                if not picking.delivery_service_code and sale.delivery_service_code:
                    write_vals["delivery_service_code"] = sale.delivery_service_code
                if not picking.delivery_service_type and sale.delivery_service_type:
                    write_vals["delivery_service_type"] = sale.delivery_service_type
                if not picking.shipping_payment_type:
                    if picking.backorder_id:
                        write_vals["shipping_payment_type"] = "1"
                    elif sale.shipping_payment_type:
                        write_vals["shipping_payment_type"] = sale.shipping_payment_type
                if write_vals:
                    picking.write(write_vals)
        return pickings

    @api.onchange("sale_id")
    def _onchange_sale_id_ohub(self):
        if self.sale_id:
            if self.sale_id.carrier_id and not self.carrier_id:
                self.carrier_id = self.sale_id.carrier_id
            if self.sale_id.delivery_service_id:
                self.delivery_service_id = self.sale_id.delivery_service_id
            if self.sale_id.delivery_service_name:
                self.delivery_service_name = self.sale_id.delivery_service_name
            if self.sale_id.delivery_service_code:
                self.delivery_service_code = self.sale_id.delivery_service_code
            if self.sale_id.delivery_service_type:
                self.delivery_service_type = self.sale_id.delivery_service_type
            if self.sale_id.shipping_payment_type:
                self.shipping_payment_type = self.sale_id.shipping_payment_type

    @api.onchange("carrier_id")
    def _onchange_carrier_id_ohub(self):
        if self.carrier_id and self.carrier_id.delivery_type == "ohub":
            if self.sale_id and self.carrier_id != self.sale_id.carrier_id:
                self.delivery_service_id = False
                self.delivery_service_name = False
                self.delivery_service_code = False
                self.delivery_service_type = False

    def _create_backorder(self):
        backorders = super()._create_backorder()
        for bo in backorders:
            if bo.carrier_id and bo.carrier_id.delivery_type == "ohub":
                bo.shipping_payment_type = "1"
        return backorders

    def button_validate(self):
        res = super().button_validate()
        if res is True:
            for picking in self:
                if (
                    picking.state == "done"
                    and picking.carrier_id
                    and picking.carrier_id.delivery_type == "ohub"
                    and picking.carrier_id.auto_create_shipping_on_validate
                    and not picking.has_active_shipping_order
                ):
                    picking._auto_create_shipping_order()
        return res

    def _auto_create_shipping_order(self):
        self.ensure_one()
        if self.picking_type_id.code == "dropship" or (
            self.location_id.usage == "supplier" and self.location_dest_id.usage == "customer"
        ):
            return False

        vals = self.env["delivery.shipping.order"]._prepare_shipping_data_from_picking(
            self, carrier=self.carrier_id
        )
        carrier_curr = self.carrier_id.currency_id or self.company_currency_id
        picking_curr = self.company_currency_id
        company = self.company_id
        date_rate = self.scheduled_date or fields.Date.today()
        picking_goods = vals.get("goods_amount", 0.0)
        picking_shipping = vals.get("shipping_fee_amount", 0.0)
        if carrier_curr and picking_curr and carrier_curr != picking_curr:
            picking_goods = round(carrier_curr._convert(picking_goods, picking_curr, company, date_rate))
            picking_shipping = round(carrier_curr._convert(picking_shipping, picking_curr, company, date_rate))
        self.write({
            "goods_amount": picking_goods,
            "shipping_fee_amount": picking_shipping,
        })
        # Tao don van chuyen truoc de co ma client_order_code on dinh va tranh sinh don ma
        shipping_order = self.env["delivery.shipping.order"].create(vals)
        try:
            with self.env.cr.savepoint():
                shipping_order.action_send_to_carrier()
        except Exception as exc:
            error_message = str(exc)
            fail_msg = _(
                "Automatic transmission of shipping order %(name)s to carrier failed: %(error)s"
            ) % {
                "name": shipping_order.client_order_code or shipping_order.name,
                "error": error_message,
            }
            self.message_post(body=fail_msg)
            shipping_order.message_post(body=fail_msg)
        return shipping_order

    def action_open_delivery_wizard(self):
        self.ensure_one()
        view_id = self.env.ref("delivery.choose_delivery_carrier_view_form").id
        return {
            "name": _("Choose Delivery Method"),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "choose.delivery.carrier",
            "view_id": view_id,
            "views": [(view_id, "form")],
            "target": "new",
            "context": {
                "default_picking_id": self.id,
                "default_carrier_id": self.carrier_id.id if self.carrier_id else False,
            },
        }

    def action_view_shipping_orders(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "delivery_ohub.action_delivery_shipping_order"
        )
        action["domain"] = [("picking_id", "=", self.id)]
        action["context"] = {"default_picking_id": self.id}
        if len(self.shipping_order_ids) == 1:
            action["views"] = [(False, "form")]
            action["res_id"] = self.shipping_order_ids.id
        return action

    def action_create_shipping_order(self):
        self.ensure_one()
        if self.picking_type_id.code == "dropship" or (
            self.location_id.usage == "supplier" and self.location_dest_id.usage == "customer"
        ):
            raise UserError(
                _("Drop-shipping orders are fulfilled directly by the vendor. Shipping order creation is not supported.")
            )

        carrier = self.carrier_id
        if not carrier or carrier.delivery_type != "ohub":
            raise UserError(_("Please select an 'oHUB Integration' delivery method."))

        delivered_order = self.shipping_order_ids.filtered(
            lambda s: s.internal_state == "delivered" or s.carrier_status == "delivered"
        )[:1]
        if delivered_order:
            raise UserError(
                _("Picking has already been delivered successfully (Carrier code: %s). Creating another shipping order is not allowed.")
                % delivered_order.order_code
            )

        active_order = self._get_active_shipping_order()
        if active_order:
            raise UserError(
                _("Picking already has an active shipping order: %s. Cancel the current order before creating a new one.")
                % (active_order.order_code or active_order.name)
            )

        vals = self.env["delivery.shipping.order"]._prepare_shipping_data_from_picking(
            self, carrier=carrier
        )
        carrier_curr = carrier.currency_id or self.company_currency_id
        picking_curr = self.company_currency_id
        company = self.company_id
        date_rate = self.scheduled_date or fields.Date.today()
        picking_goods = vals.get("goods_amount", 0.0)
        picking_shipping = vals.get("shipping_fee_amount", 0.0)
        if carrier_curr and picking_curr and carrier_curr != picking_curr:
            picking_goods = round(carrier_curr._convert(picking_goods, picking_curr, company, date_rate))
            picking_shipping = round(carrier_curr._convert(picking_shipping, picking_curr, company, date_rate))
        self.write({
            "goods_amount": picking_goods,
            "shipping_fee_amount": picking_shipping,
        })
        shipping_order = self.env["delivery.shipping.order"].create(vals)
        shipping_order.action_send_to_carrier()
        return self.action_view_shipping_orders()
