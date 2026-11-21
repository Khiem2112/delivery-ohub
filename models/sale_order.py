from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    delivery_service_id = fields.Integer(
        string="Selected Carrier Service ID",
        copy=False,
        help="Carrier service package identifier agreed upon with the customer.",
    )
    delivery_service_name = fields.Char(
        string="Selected Service Package Name",
        copy=False,
        help="Display name of the agreed carrier service package.",
    )
    delivery_service_code = fields.Char(
        string="Selected Service Code",
        copy=False,
        help="Technical service code provided by the delivery carrier.",
    )
    delivery_service_type = fields.Selection(
        selection=[
            ("standard", "Standard Delivery"),
            ("express", "Express Delivery"),
            ("economy", "Economy Delivery"),
        ],
        string="Selected Service Type",
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
        help="Agreed shipping payment method: Shop collects fee and pays carrier, or customer pays driver directly upon delivery.",
    )
    fee_outdated = fields.Boolean(
        string="Outdated Rate Quote",
        default=False,
        help="Indicates whether the calculated shipping fee quote is outdated due to order or address changes.",
    )
    shipping_order_ids = fields.One2many(
        comodel_name="delivery.shipping.order",
        inverse_name="sale_order_id",
        string="Shipping Orders",
        readonly=True,
    )
    shipping_order_count = fields.Integer(
        string="Shipping Order Count",
        compute="_compute_shipping_order_count",
    )

    @api.depends("shipping_order_ids")
    def _compute_shipping_order_count(self):
        for order in self:
            order.shipping_order_count = len(order.shipping_order_ids)

    def _is_order_line_delivery_only(self, order_lines):
        if not order_lines:
            return True
        carrier_product_ids = self.mapped("carrier_id.product_id").ids
        for cmd in order_lines:
            if not isinstance(cmd, (list, tuple)) or not cmd:
                return False
            cmd_type = cmd[0]
            if cmd_type == 0:
                vals = cmd[2] if len(cmd) > 2 and isinstance(cmd[2], dict) else {}
                if vals.get("is_delivery"):
                    continue
                if vals.get("product_id") and vals.get("product_id") in carrier_product_ids:
                    continue
                return False
            elif cmd_type in (1, 2, 3):
                line_id = cmd[1]
                line = self.env["sale.order.line"].browse(line_id)
                if not line.exists():
                    continue
                if line.is_delivery:
                    continue
                return False
            elif cmd_type == 4:
                line_id = cmd[1]
                line = self.env["sale.order.line"].browse(line_id)
                if line.exists() and line.is_delivery:
                    continue
                return False
            elif cmd_type == 6:
                new_ids = set(cmd[2]) if len(cmd) > 2 and isinstance(cmd[2], (list, tuple, set)) else set()
                existing_lines = self.mapped("order_line")
                existing_ids = set(existing_lines.ids)
                changed_ids = (existing_ids - new_ids) | (new_ids - existing_ids)
                changed_lines = self.env["sale.order.line"].browse(changed_ids)
                if any(not line.is_delivery for line in changed_lines):
                    return False
            else:
                return False
        return True

    def write(self, vals):
        if "fee_outdated" not in vals:
            should_mark_outdated = False
            if "partner_shipping_id" in vals or "warehouse_id" in vals:
                should_mark_outdated = True

            if not should_mark_outdated and "carrier_id" in vals:
                is_wizard_service_update = any(
                    k in vals for k in ("delivery_service_id", "delivery_service_code", "delivery_service_name")
                )
                carrier_unchanged = all(order.carrier_id.id == vals["carrier_id"] for order in self)
                if not is_wizard_service_update and not carrier_unchanged:
                    should_mark_outdated = True

            if not should_mark_outdated and "order_line" in vals:
                if not self._is_order_line_delivery_only(vals["order_line"]):
                    should_mark_outdated = True

            if should_mark_outdated:
                vals["fee_outdated"] = True

        return super().write(vals)

    def action_confirm(self):
        for order in self:
            if order.carrier_id and order.carrier_id.delivery_type == "ohub":
                if not order.delivery_service_id and not order.delivery_service_code:
                    raise UserError(
                        _(
                            "Please select a carrier shipping service before confirming sales order %s."
                        )
                        % order.name
                    )
                if order.shipping_payment_type == "1":
                    delivery_line = order.order_line.filtered(
                        lambda l: l.is_delivery and l.price_total > 0
                    )
                    if not delivery_line:
                        if not self.env.context.get("confirm_freeship"):
                            raise UserError(
                                _(
                                    "Sales order %s is configured with 'Sender / Shop Pays' shipping payment policy "
                                    "but has no delivery fee charged. If you intend to offer Free Shipping for this order, "
                                    "please confirm with Free Shipping approval."
                                )
                                % order.name
                            )
        return super().action_confirm()

    def _prepare_delivery_line_vals(self, carrier, price_unit):
        values = super()._prepare_delivery_line_vals(carrier, price_unit)
        if carrier.delivery_type == "ohub" and self.currency_id.is_zero(price_unit):
            free_label = _("Free Shipping")
            if free_label not in values.get("name", ""):
                values["name"] = f"{values['name']}\n{free_label}"
        return values

    def action_open_delivery_wizard(self):
        res = super().action_open_delivery_wizard()
        if self.carrier_id and "context" in res:
            res["context"]["default_carrier_id"] = self.carrier_id.id
        return res

    def action_view_shipping_orders(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "delivery_ohub.action_delivery_shipping_order"
        )
        action["domain"] = [("sale_order_id", "=", self.id)]
        action["context"] = {"default_sale_order_id": self.id}
        if len(self.shipping_order_ids) == 1:
            action["views"] = [(False, "form")]
            action["res_id"] = self.shipping_order_ids.id
        return action
