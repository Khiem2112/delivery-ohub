import math
from datetime import UTC

from odoo.exceptions import UserError

from odoo import _, api, fields, models


class DeliveryShippingOrder(models.Model):
    _name = "delivery.shipping.order"
    _description = "Shipping Order via oHUB"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(
        string="Reference", required=True, copy=False, default=lambda self: _("New")
    )
    client_order_code = fields.Char(
        string="Client Order Code", required=True, copy=False, index=True
    )
    order_code = fields.Char(
        string="Carrier Order Code", index=True, copy=False, tracking=True
    )
    sort_code = fields.Char(string="Sort Code", copy=False)
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    carrier_id = fields.Many2one(
        comodel_name="delivery.carrier",
        string="Delivery Method",
        required=True,
    )
    service_id = fields.Integer(string="Carrier Service ID", index=True)
    service_code = fields.Char(string="Service Code", index=True)
    service_name = fields.Char(string="Service Package Name")
    sale_order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Sales Order",
        index=True,
    )
    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Delivery Order",
        index=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Recipient / Customer",
    )
    to_name = fields.Char(string="Recipient Name")
    to_phone = fields.Char(string="Recipient Phone")
    to_address = fields.Char(string="Recipient Address")
    to_ward_code = fields.Char(string="Ward / Commune Code")
    to_ward_name = fields.Char(string="Ward / Commune Name")
    to_district_id = fields.Integer(string="District ID")
    to_district_name = fields.Char(string="District Name")
    to_province_id = fields.Integer(string="Recipient Province ID")
    to_province_name = fields.Char(string="Recipient Province Name")

    from_name = fields.Char(string="Sender Name")
    from_phone = fields.Char(string="Sender Phone")
    from_address = fields.Char(string="Sender Address")
    from_ward_code = fields.Char(string="Sender Ward / Commune Code")
    from_ward_name = fields.Char(string="Sender Ward / Commune Name")
    from_district_id = fields.Integer(string="Sender District ID")
    from_district_name = fields.Char(string="Sender District Name")
    from_province_id = fields.Integer(string="Sender Province ID")
    from_province_name = fields.Char(string="Sender Province Name")

    weight = fields.Integer(string="Weight (g)", default=0)
    length = fields.Integer(string="Length (cm)", default=0)
    width = fields.Integer(string="Width (cm)", default=0)
    height = fields.Integer(string="Height (cm)", default=0)

    payment_type_id = fields.Selection(
        selection=[
            ("1", "Sender / Shop Pays"),
            ("2", "Recipient Pays"),
        ],
        string="Payment Type",
        default="1",
    )
    required_note = fields.Selection(
        selection=[
            ("open_no_trial", "Allow Inspection (No Trial)"),
            ("open_trial", "Allow Trial"),
            ("no_inspection", "Do Not Allow Inspection"),
        ],
        string="Inspection Policy",
        default="open_no_trial",
    )
    cod_amount = fields.Monetary(string="Cash on Delivery (COD)")
    goods_amount = fields.Monetary(
        string="Goods Amount",
        currency_field="currency_id",
    )
    shipping_fee_amount = fields.Monetary(
        string="Shipping Fee Amount",
        currency_field="currency_id",
    )
    insurance_value = fields.Monetary(string="Declared Value")
    content = fields.Char(string="Cargo Content")
    note = fields.Char(string="Delivery Note")
    service_type = fields.Selection(
        selection=[
            ("standard", "Standard Delivery"),
            ("express", "Express Delivery"),
            ("economy", "Economy Delivery"),
        ],
        string="Service Type",
        default="standard",
    )
    cod_failed_amount = fields.Monetary(
        string="Failed Delivery COD Amount",
        default=0.0,
        help="Amount collected by carrier from recipient if delivery fails.",
    )
    items = fields.Json(string="Package Items")

    currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="Carrier Currency",
        compute="_compute_currency_id",
        store=True,
        readonly=False,
        precompute=True,
    )
    estimated_fee = fields.Monetary(string="Estimated Initial Fee")
    actual_total_fee = fields.Monetary(string="Actual Fee", tracking=True)
    converted_weight = fields.Integer(string="Converted Weight (g)")
    expected_delivery_time = fields.Datetime(string="Expected Delivery Date")

    carrier_status = fields.Selection(
        selection=[
            ("ready_to_pick", "Ready to Pick"),
            ("picking", "Picking"),
            ("money_collect_picking", "Collecting Money on Pick"),
            ("picked", "Picked"),
            ("storing", "Storing in Hub"),
            ("transporting", "Transporting"),
            ("sorting", "Sorting"),
            ("delivering", "Delivering"),
            ("money_collect_delivering", "Collecting Money on Delivery"),
            ("delivered", "Delivered"),
            ("delivery_fail", "Delivery Failed"),
            ("waiting_to_return", "Waiting to Return"),
            ("return", "Return"),
            ("return_transporting", "Return Transporting"),
            ("return_sorting", "Return Sorting"),
            ("returning", "Returning"),
            ("return_fail", "Return Failed"),
            ("returned", "Returned"),
            ("exception", "Exception"),
            ("damage", "Damaged"),
            ("lost", "Lost"),
            ("cancel", "Cancelled"),
            ("scrap", "Scrapped"),
        ],
        string="Carrier Status",
        index=True,
        tracking=True,
    )
    internal_state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("ready", "Ready to Ship"),
            ("in_transit", "In Transit"),
            ("delivered", "Delivered"),
            ("issue", "Delivery Exception"),
            ("returning", "Returning"),
            ("returned", "Returned"),
            ("cancelled", "Cancelled"),
        ],
        string="Internal State",
        default="draft",
        index=True,
        tracking=True,
    )
    last_event_time = fields.Datetime(string="Last Event Time", readonly=True)
    last_sync_at = fields.Datetime(string="Last Synchronized Date", readonly=True)
    log_ids = fields.One2many(
        comodel_name="delivery.shipping.order.log",
        inverse_name="shipping_order_id",
        string="Tracking Logs",
    )
    log_count = fields.Integer(string="Log Count", compute="_compute_log_count")
    move_ids = fields.Many2many(
        comodel_name="stock.move",
        string="Transported Items",
        compute="_compute_move_ids",
        help="Stock moves associated with this shipping order through the delivery picking.",
    )
    move_count = fields.Integer(
        string="Item Lines Count",
        compute="_compute_move_ids",
    )

    @api.depends("picking_id.move_ids")
    def _compute_move_ids(self):
        for rec in self:
            moves = (
                rec.picking_id.move_ids if rec.picking_id else self.env["stock.move"]
            )
            rec.move_ids = moves
            rec.move_count = len(moves)

    def action_view_picking(self):
        self.ensure_one()
        if not self.picking_id:
            raise UserError(
                _("There is no delivery picking associated with this shipping order.")
            )
        return {
            "name": _("Delivery Order"),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "stock.picking",
            "res_id": self.picking_id.id,
        }

    @api.depends("carrier_id.currency_id")
    def _compute_currency_id(self):
        for rec in self:
            rec.currency_id = (
                rec.carrier_id.currency_id
                or rec.carrier_id.company_id.currency_id
                or self.env.company.currency_id
            )

    @api.depends("log_ids")
    def _compute_log_count(self):
        for rec in self:
            rec.log_count = len(rec.log_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "delivery.shipping.order"
                ) or _("New")
        return super().create(vals_list)

    def _map_internal_state(self, status):
        status_map = {
            "ready_to_pick": "ready",
            "picking": "in_transit",
            "money_collect_picking": "in_transit",
            "picked": "in_transit",
            "storing": "in_transit",
            "transporting": "in_transit",
            "sorting": "in_transit",
            "delivering": "in_transit",
            "money_collect_delivering": "in_transit",
            "delivered": "delivered",
            "delivery_fail": "issue",
            "waiting_to_return": "issue",
            "return": "returning",
            "return_transporting": "returning",
            "return_sorting": "returning",
            "returning": "returning",
            "return_fail": "issue",
            "returned": "returned",
            "exception": "issue",
            "damage": "issue",
            "lost": "issue",
            "cancel": "cancelled",
            "scrap": "cancelled",
        }
        return status_map.get(status, "in_transit")

    def action_sync_order_info(self):
        self.ensure_one()
        if not self.order_code:
            raise UserError(
                _("The shipping order does not have a carrier tracking code to query.")
            )

        res = self.carrier_id.execute_ohub_operation(
            "get_order_info",
            record=self,
        )
        payload = res.get("payload") if isinstance(res, dict) else {}
        if not isinstance(payload, dict):
            raise UserError(
                _(
                    "Integration configuration error: Response from oHUB for 'get_order_info' must be a JSON object."
                )
            )

        self._validate_contract_payload(
            payload, ["carrier_status", "internal_state"], "get_order_info"
        )

        carrier_status = str(payload["carrier_status"])
        internal_state = str(payload["internal_state"])
        converted_weight = int(payload.get("converted_weight") or 0)
        current_warehouse = str(payload.get("current_warehouse") or "")
        timeline = payload.get("timeline") or []
        if not isinstance(timeline, list):
            raise UserError(
                _("Contract violation in 'get_order_info': 'timeline' must be a list.")
            )

        vals = {
            "carrier_status": carrier_status,
            "internal_state": internal_state,
            "last_sync_at": fields.Datetime.now(),
        }
        if converted_weight > 0:
            vals["converted_weight"] = converted_weight
        self.write(vals)

        log_model = self.env["delivery.shipping.order.log"].sudo()
        for entry in timeline:
            if not isinstance(entry, dict):
                raise UserError(
                    _("Contract violation in 'get_order_info': timeline entry must be a dictionary.")
                )
            self._validate_contract_payload(
                entry,
                ["time", "status", "description", "station"],
                "get_order_info.timeline",
            )
            entry_time = str(entry["time"])
            entry_status = str(entry["status"])
            entry_desc = str(entry["description"])
            entry_station = str(entry["station"])
            event_uid = f"{self.id}_{entry_status}_{entry_time}_sync"
            if not log_model.search(
                [
                    ("shipping_order_id", "=", self.id),
                    ("event_uid", "=", event_uid),
                ],
                limit=1,
            ):
                log_model.create(
                    {
                        "shipping_order_id": self.id,
                        "carrier_status": entry_status,
                        "event_type": "status_update",
                        "event_time": entry_time,
                        "event_uid": event_uid,
                        "warehouse": entry_station,
                        "description": entry_desc,
                        "source": "manual",
                    }
                )

        self.message_post(
            body=_("Updated latest information from carrier. Status: %s")
            % carrier_status
        )
        return True

    @api.model
    def _validate_contract_payload(self, payload, required_fields, operation_name):
        if not isinstance(payload, dict):
            raise UserError(
                _(
                    "Integration configuration error: Response from oHUB for '%(op)s' must be a JSON object."
                )
                % {"op": operation_name}
            )
        missing = [f for f in required_fields if f not in payload or payload[f] is None]
        if missing:
            raise UserError(
                _(
                    "Integration configuration error: Response from oHUB for '%(op)s' is missing required contract field(s): %(fields)s."
                )
                % {"op": operation_name, "fields": ", ".join(missing)}
            )
        return True

    @api.model
    def _parse_carrier_response(self, res):
        payload = res.get("payload") if isinstance(res, dict) else res
        if not isinstance(payload, dict):
            return False, _("Integration configuration error: Response from oHUB must be a JSON object.")

        self._validate_contract_payload(payload, ["success"], "carrier_operation")
        is_success = bool(payload["success"])
        err_msg = False
        if not is_success:
            err_msg = payload.get("message") or _("Carrier operation rejected.")
        return is_success, err_msg

    def action_cancel_order(self):
        self.ensure_one()
        if not self.order_code:
            self.write(
                {
                    "internal_state": "cancelled",
                }
            )
            self.message_post(body=_("Draft shipping order cancelled."))
            return True

        carrier_status = self.carrier_status or "draft"
        if carrier_status not in ["ready_to_pick", "draft"]:
            raise UserError(
                _(
                    "A shipping order can only be cancelled while in 'Ready to Pick' or 'Draft' status."
                )
            )

        res = self.carrier_id.execute_ohub_operation(
            "cancel_shipment",
            record=self,
        )
        payload = res.get("payload") if isinstance(res, dict) else res
        if not isinstance(payload, dict):
            raise UserError(
                _("Carrier integration did not return a valid cancellation response.")
            )

        self._validate_contract_payload(
            payload, ["success", "carrier_status"], "cancel_shipment"
        )
        is_success = bool(payload["success"])
        carrier_status = str(payload["carrier_status"])
        if not is_success:
            err_msg = payload.get("message") or _(
                "Carrier rejected the cancellation request."
            )
            raise UserError(err_msg)

        self.write(
            {
                "carrier_status": carrier_status,
                "internal_state": "cancelled",
            }
        )
        self.message_post(body=_("Successfully sent cancellation request to carrier."))
        return True

    def action_delivery_again(self):
        self.ensure_one()
        if self.carrier_status not in [
            "delivery_fail",
            "issue",
            "return_fail",
            "exception",
        ] and self.internal_state not in ["issue", "delivery_fail"]:
            raise UserError(
                _(
                    "Redelivery can only be requested when the shipping order is in delivery failure or issue status."
                )
            )

        res = self.carrier_id.execute_ohub_operation(
            "storing_again",
            record=self,
        )
        is_success, err_msg = self._parse_carrier_response(res)
        if not is_success:
            raise UserError(err_msg or _("Carrier rejected the redelivery request."))

        self.message_post(body=_("Successfully sent redelivery request to carrier."))
        return True

    def action_request_return(self):
        self.ensure_one()
        if self.carrier_status not in [
            "delivery_fail",
            "waiting_to_return",
            "issue",
            "exception",
        ] and self.internal_state not in ["issue", "delivery_fail"]:
            raise UserError(
                _(
                    "Return can only be requested when delivery has failed or the shipment has an issue."
                )
            )

        res = self.carrier_id.execute_ohub_operation(
            "return_order",
            record=self,
        )
        is_success, err_msg = self._parse_carrier_response(res)
        if not is_success:
            raise UserError(err_msg or _("Carrier rejected the return request."))

        self.write(
            {
                "carrier_status": "return",
                "internal_state": "returning",
            }
        )
        self.message_post(body=_("Successfully sent return request to carrier."))
        return True

    def action_print_label(self):
        self.ensure_one()
        if not self.order_code:
            raise UserError(
                _(
                    "The shipping order does not have a carrier tracking code to print label."
                )
            )

        res = self.carrier_id.execute_ohub_operation(
            "print_label",
            record=self,
        )
        payload = res.get("payload") if isinstance(res, dict) else {}
        if not isinstance(payload, dict):
            raise UserError(
                _("Carrier integration did not return a valid print_label response.")
            )

        if payload.get("error_message"):
            raise UserError(str(payload["error_message"]))

        self._validate_contract_payload(payload, ["url"], "print_label")
        print_url = str(payload["url"])
        if not (print_url.startswith("http://") or print_url.startswith("https://")):
            raise UserError(
                _("Carrier integration returned an invalid printable label URL: %s")
                % print_url
            )

        return {
            "type": "ir.actions.act_url",
            "url": print_url,
            "target": "new",
        }

    def apply_carrier_status_update(
        self,
        status,
        event_time=None,
        total_fee=0.0,
        warehouse="",
        reason_code="",
        reason="",
        description="",
        converted_weight=0,
        event_type="status_update",
        source="webhook",
        raw_payload="",
    ):
        self.ensure_one()
        parsed_time = event_time
        if isinstance(event_time, str):
            try:
                from datetime import datetime

                clean_time = event_time.replace("Z", "+00:00")
                parsed_dt = datetime.fromisoformat(clean_time)
                if parsed_dt.tzinfo:
                    parsed_time = parsed_dt.astimezone(UTC).replace(tzinfo=None)
                else:
                    parsed_time = parsed_dt
            except Exception:
                parsed_time = fields.Datetime.now()
        elif not parsed_time:
            parsed_time = fields.Datetime.now()

        event_uid = (
            f"{self.id}_{status}_{fields.Datetime.to_string(parsed_time)}_{event_type}"
        )
        log_model = self.env["delivery.shipping.order.log"].sudo()
        existing_log = log_model.search(
            [
                ("shipping_order_id", "=", self.id),
                ("event_uid", "=", event_uid),
            ],
            limit=1,
        )
        if existing_log:
            return {"code": 200, "message": "Event already processed"}

        import json

        payload_str = (
            raw_payload
            if isinstance(raw_payload, str)
            else json.dumps(raw_payload, ensure_ascii=False)
        )
        log_vals = {
            "shipping_order_id": self.id,
            "carrier_status": status or self.carrier_status,
            "event_type": event_type,
            "event_time": parsed_time,
            "event_uid": event_uid,
            "warehouse": warehouse,
            "reason_code": str(reason_code) if reason_code else False,
            "reason": reason,
            "description": description,
            "total_fee": float(total_fee),
            "raw_payload": payload_str,
            "source": source,
        }
        log_model.create(log_vals)

        can_update_status = True
        if self.last_event_time and parsed_time < self.last_event_time:
            can_update_status = False

        if can_update_status and status:
            vals_to_update = {
                "carrier_status": status,
                "internal_state": self._map_internal_state(status),
                "last_event_time": parsed_time,
            }
            if float(total_fee) > 0:
                vals_to_update["actual_total_fee"] = float(total_fee)
            if int(converted_weight) > 0:
                vals_to_update["converted_weight"] = int(converted_weight)
            self.write(vals_to_update)

            extra_desc = (
                _("Reason: %s") % reason
                if reason
                else (_("Description: %s") % description if description else "")
            )
            chatter_body = _(
                "Carrier updated status: <b>%(status)s</b>. "
                "Hub/Station: %(warehouse)s. "
                "Time: %(time)s. "
                "%(extra)s"
            ) % {
                "status": status,
                "warehouse": warehouse or _("Unknown"),
                "time": fields.Datetime.to_string(parsed_time),
                "extra": extra_desc,
            }
            self.message_post(body=chatter_body)

            if self.sale_order_id:
                sale_extra = _("Reason: %s") % reason if reason else ""
                self.sale_order_id.message_post(
                    body=_(
                        "Shipping order <b>%(order_code)s</b> status updated: <b>%(status)s</b>.<br/>"
                        "Hub/Station: %(warehouse)s.<br/>%(extra)s"
                    )
                    % {
                        "order_code": self.order_code,
                        "status": status,
                        "warehouse": warehouse or _("Unknown"),
                        "extra": sale_extra,
                    }
                )

                if status in [
                    "delivery_fail",
                    "waiting_to_return",
                    "exception",
                    "damage",
                    "lost",
                ]:
                    self.sale_order_id.activity_schedule(
                        "mail.mail_activity_data_todo",
                        summary=_("Shipping order issue: %s") % status,
                        note=_(
                            "Shipping order %(order_code)s encountered an exception: %(status)s. Reason: %(reason)s"
                        )
                        % {
                            "order_code": self.order_code,
                            "status": status,
                            "reason": reason or description or _("Unknown"),
                        },
                        user_id=self.sale_order_id.user_id.id or self.env.user.id,
                    )

        return {"code": 200, "message": "Success"}

    @api.model
    def process_carrier_webhook(self, payload):
        self._validate_contract_payload(
            payload, ["order_code", "status"], "process_carrier_webhook"
        )
        order_code = str(payload["order_code"])
        status = str(payload["status"])
        action_time = payload.get("action_time")
        warehouse = str(payload.get("warehouse") or "")
        reason = str(payload.get("reason") or "")
        converted_weight = int(payload.get("converted_weight") or 0)
        total_fee = float(payload.get("total_fee") or 0.0)

        shipping_order = self.search([("order_code", "=", order_code)], limit=1)
        if not shipping_order:
            raise UserError(
                _("Shipping order with code '%(code)s' was not found.")
                % {"code": order_code}
            )

        return shipping_order.apply_carrier_status_update(
            status=status,
            event_time=action_time,
            total_fee=total_fee,
            warehouse=warehouse,
            reason=reason,
            converted_weight=converted_weight,
            source="webhook",
            raw_payload=str(payload),
        )

    @api.model
    def _resolve_address_payload(
        self,
        carrier,
        partner,
        is_sender=False,
        default_name=None,
        default_phone=None,
        default_street=None,
        default_state=None,
        default_ward=None,
    ):
        name = default_name or (partner.name if partner else "")
        phone = default_phone or (
            (partner.phone or partner.mobile or "") if partner else ""
        )
        address = default_street or (partner.street if partner else "")
        state = default_state or (partner.state_id if partner else False)
        ward = default_ward or (partner.ward_id if partner else False)

        dist_id = 0
        ward_code = ""
        prov_id = 0
        prov_name = state.name if state else ""
        dist_name = ""
        ward_name = ward.name if ward else ""

        role_label = _("Sender") if is_sender else _("Recipient")
        partner_name = partner.name if partner else (default_name or _("Unknown"))

        if partner:
            partner.check_delivery_address_ready()

        if state and ward:
            try:
                mapping = carrier.resolve_carrier_address(state=state, ward=ward)
                if not mapping:
                    raise UserError(_("No mapping found."))
                dist_id = mapping.external_district_id
                ward_code = mapping.external_ward_code
                prov_id = mapping.external_province_id
                if mapping.external_province_name:
                    prov_name = mapping.external_province_name
                if mapping.external_district_name:
                    dist_name = mapping.external_district_name
                if mapping.external_ward_name:
                    ward_name = mapping.external_ward_name
            except Exception as exc:
                state_name = state.name if state else ""
                ward_name_val = ward.name if ward else ""
                carrier_name = carrier.name if carrier else ""
                raise UserError(
                    _(
                        "The %(role)s address for '%(partner)s' (State: %(state)s, Ward: %(ward)s) "
                        "has not been mapped for delivery method '%(carrier)s'."
                    )
                    % {
                        "role": role_label,
                        "partner": partner_name,
                        "state": state_name,
                        "ward": ward_name_val,
                        "carrier": carrier_name,
                    }
                ) from exc

        prefix = "from_" if is_sender else "to_"
        return {
            f"{prefix}name": name,
            f"{prefix}phone": phone,
            f"{prefix}address": address,
            f"{prefix}province_id": prov_id,
            f"{prefix}province_name": prov_name,
            f"{prefix}district_id": dist_id,
            f"{prefix}district_name": dist_name,
            f"{prefix}ward_code": ward_code,
            f"{prefix}ward_name": ward_name,
        }

    @api.model
    def _compute_package_dimensions(
        self,
        lines,
        default_length=0,
        default_width=0,
        default_height=0,
    ):
        valid_lines = [
            l
            for l in lines
            if getattr(l, "product_id", False)
            and l.product_id.type != "service"
            and (getattr(l, "quantity", 0) or getattr(l, "product_uom_qty", 0)) > 0
        ]
        p_lengths = [
            l.product_id.length for l in valid_lines if l.product_id.length > 0
        ]
        p_widths = [l.product_id.width for l in valid_lines if l.product_id.width > 0]
        p_heights = [
            l.product_id.height
            * float(getattr(l, "quantity", 0) or getattr(l, "product_uom_qty", 0))
            for l in valid_lines
            if l.product_id.height > 0
        ]
        length = math.ceil(max(p_lengths)) if p_lengths else default_length
        width = math.ceil(max(p_widths)) if p_widths else default_width
        height = math.ceil(sum(p_heights)) if p_heights else default_height
        return int(length), int(width), int(height)

    @api.model
    def _prepare_package_items(
        self,
        lines,
        source_currency,
        target_currency,
        company,
        date_rate,
    ):
        items = []
        total_weight = 0.0
        total_items_price = 0.0

        for line in lines:
            product = line.product_id
            if product.type == "service":
                continue
            qty = float(
                getattr(line, "quantity", 0) or getattr(line, "product_uom_qty", 0)
            )
            if qty <= 0:
                continue

            item_weight = float((product.weight or 0.0) * 1000)
            unit_price = 0.0
            move = getattr(line, "move_id", line)
            sale_line = getattr(move, "sale_line_id", False) or getattr(
                line, "sale_line_id", False
            )
            if sale_line:
                if sale_line.product_uom_qty > 0:
                    unit_price = sale_line.price_total / sale_line.product_uom_qty
                else:
                    unit_price = sale_line.price_unit * (
                        1 - (sale_line.discount or 0.0) / 100.0
                    )
            elif line._name == "sale.order.line":
                if line.product_uom_qty > 0:
                    unit_price = line.price_total / line.product_uom_qty
                else:
                    unit_price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
            elif hasattr(line, "price_unit") and line.price_unit > 0:
                unit_price = line.price_unit
            elif product.lst_price:
                unit_price = product.lst_price
            elif product.standard_price:
                unit_price = product.standard_price

            total_items_price += unit_price * qty
            total_weight += item_weight * qty

            converted_unit_price = unit_price
            if (
                source_currency
                and target_currency
                and source_currency != target_currency
            ):
                converted_unit_price = source_currency._convert(
                    unit_price, target_currency, company, date_rate
                )
            nominal_price = (
                round(converted_unit_price) if converted_unit_price > 0 else 0
            )

            item_qty = int(qty) if qty.is_integer() else round(qty, 4)
            items.append(
                {
                    "name": product.name or _("Product"),
                    "code": product.default_code or product.name or _("ITEM"),
                    "quantity": item_qty,
                    "price": nominal_price,
                    "weight": int(round(item_weight)),
                }
            )

        return items, int(round(total_weight)), total_items_price

    @api.model
    def _prepare_shipping_data_from_picking(self, picking, carrier=None):
        carrier = carrier or picking.carrier_id
        if not carrier:
            raise UserError(_("Delivery method is required to prepare shipping order."))

        is_return = picking.picking_type_code == "incoming"
        warehouse = picking.picking_type_id.warehouse_id or carrier.sender_warehouse_id
        warehouse_partner = (
            warehouse.partner_id if warehouse else picking.company_id.partner_id
        )

        if is_return:
            sender_partner = picking.partner_id
            recipient_partner = warehouse_partner
        else:
            sender_partner = carrier.sender_partner_id or warehouse_partner
            recipient_partner = picking.partner_id

        from_data = self._resolve_address_payload(
            carrier,
            sender_partner,
            is_sender=True,
            default_name=warehouse_partner.name
            if warehouse_partner
            else (carrier.company_id.name or self.env.company.name),
            default_phone=carrier.sender_phone if not is_return else None,
            default_street=carrier.sender_address if not is_return else None,
            default_state=carrier.sender_state_id if not is_return else None,
            default_ward=carrier.sender_ward_id if not is_return else None,
        )
        to_data = self._resolve_address_payload(
            carrier,
            recipient_partner,
            is_sender=False,
        )

        sale_order = picking.sale_id
        carrier_curr = carrier.currency_id or picking.company_id.currency_id
        order_curr = (
            sale_order.currency_id
            if sale_order
            else (picking.company_id.currency_id or self.env.company.currency_id)
        )
        company = picking.company_id or self.env.company
        date_rate = picking.scheduled_date or fields.Date.today()

        lines = picking.move_line_ids.filtered(lambda l: l.quantity > 0)
        if not lines:
            lines = picking.move_ids.filtered(
                lambda m: (m.quantity or m.product_uom_qty) > 0
            )

        items, total_items_weight, total_items_price = self._prepare_package_items(
            lines, order_curr, carrier_curr, company, date_rate
        )

        picking_weight_g = int((getattr(picking, "shipping_weight", 0) or 0.0) * 1000)
        pkg_weight = picking_weight_g or total_items_weight or 0

        package = (
            getattr(picking, "package_ids", False) and picking.package_ids[:1]
        ) or False
        if not package and hasattr(picking, "move_line_ids"):
            packages = picking.move_line_ids.mapped("result_package_id").filtered(
                lambda p: p
            )
            package = packages[:1] if packages else False

        pkg_type = (
            package.package_type_id
            if package and hasattr(package, "package_type_id")
            else False
        )
        pkg_len = (
            getattr(pkg_type, "packaging_length", 0)
            if pkg_type
            else (picking.package_length or 0)
        )
        pkg_wid = (
            getattr(pkg_type, "packaging_width", 0)
            if pkg_type
            else (picking.package_width or 0)
        )
        pkg_hgt = (
            getattr(pkg_type, "packaging_height", 0)
            if pkg_type
            else (picking.package_height or 0)
        )

        if pkg_len and pkg_wid and pkg_hgt:
            length, width, height = int(pkg_len), int(pkg_wid), int(pkg_hgt)
        else:
            calc_l, calc_w, calc_h = self._compute_package_dimensions(
                lines,
                default_length=0,
                default_width=0,
                default_height=0,
            )
            length = int(pkg_len or calc_l or 0)
            width = int(pkg_wid or calc_w or 0)
            height = int(pkg_hgt or calc_h or 0)

        is_backorder = bool(picking.backorder_id) or bool(
            sale_order
            and sale_order.shipping_order_ids.filtered(
                lambda s: (
                    s.picking_id != picking
                    and s.internal_state not in ["cancelled"]
                    and s.carrier_status not in ["cancel"]
                )
            )
        )
        payment_type = (
            ("1" if is_backorder else picking.shipping_payment_type)
            or (
                "1"
                if is_backorder
                else (sale_order and sale_order.shipping_payment_type)
            )
            or False
        )
        if not is_return and sale_order and not is_backorder:
            has_charged_delivery = bool(
                sale_order.order_line.filtered(
                    lambda l: l.is_delivery and l.price_total > 0
                )
            )
            if has_charged_delivery and payment_type == "2":
                raise UserError(
                    _(
                        "Sale order %(so)s already includes a delivery fee on the order. "
                        "Cannot set shipping payment type to 'Recipient Pays' (payment_type = 2) for the first shipment "
                        "as it would double charge the customer. "
                        "Please use 'Sender / Shop Pays' (payment_type = 1) or adjust the delivery line on the sale order first."
                    )
                    % {"so": sale_order.name}
                )
        picking_cod_failed = picking.cod_failed_amount or 0.0
        if (
            picking_cod_failed
            and picking.company_currency_id
            and carrier_curr
            and picking.company_currency_id != carrier_curr
        ):
            cod_failed_amount = round(
                picking.company_currency_id._convert(
                    picking_cod_failed, carrier_curr, company, date_rate
                )
            )
        else:
            cod_failed_amount = picking_cod_failed

        service_id = (
            picking.delivery_service_id
            or (sale_order and sale_order.delivery_service_id)
            or False
        )
        service_name = (
            picking.delivery_service_name
            or (sale_order and sale_order.delivery_service_name)
            or False
        )
        service_code = (
            picking.delivery_service_code
            or (sale_order and sale_order.delivery_service_code)
            or (str(service_id) if service_id else "")
        )
        service_type = (
            picking.delivery_service_type
            or (sale_order and sale_order.delivery_service_type)
            or False
        )

        cod_amount = 0.0
        insurance_value = 0.0
        goods_amount_res = 0.0
        shipping_fee_res = 0.0
        if not is_return and sale_order:
            goods_amount = total_items_price
            shipping_fee_amount = 0.0

            prior_active_ships = sale_order.shipping_order_ids.filtered(
                lambda s: (
                    s.picking_id != picking
                    and s.internal_state not in ["cancelled"]
                    and s.carrier_status not in ["cancel"]
                )
            )

            if payment_type == "1" and not is_backorder and not prior_active_ships:
                delivery_line = sale_order.order_line.filtered(lambda l: l.is_delivery)[
                    :1
                ]
                shipping_fee_amount = (
                    delivery_line.price_total if delivery_line else 0.0
                )

            cod_val = goods_amount + shipping_fee_amount

            existing_cod_sum_in_order_curr = 0.0
            for s in prior_active_ships:
                s_curr = s.currency_id or carrier_curr
                if s_curr and order_curr and s_curr != order_curr:
                    existing_cod_sum_in_order_curr += s_curr._convert(
                        s.cod_amount, order_curr, company, date_rate
                    )
                else:
                    existing_cod_sum_in_order_curr += s.cod_amount

            amount_paid = 0.0
            posted_invoices = sale_order.invoice_ids.filtered(
                lambda inv: inv.state == "posted" and inv.move_type == "out_invoice"
            )
            if posted_invoices:
                for inv in posted_invoices:
                    inv_paid = inv.amount_total - inv.amount_residual
                    if inv.currency_id and order_curr and inv.currency_id != order_curr:
                        amount_paid += inv.currency_id._convert(
                            inv_paid, order_curr, company, date_rate
                        )
                    else:
                        amount_paid += inv_paid
            else:
                done_txs = getattr(
                    sale_order, "transaction_ids", self.env["payment.transaction"]
                ).filtered(lambda tx: tx.state == "done")
                for tx in done_txs:
                    tx_amount = tx.amount
                    if tx.currency_id and order_curr and tx.currency_id != order_curr:
                        amount_paid += tx.currency_id._convert(
                            tx_amount, order_curr, company, date_rate
                        )
                    else:
                        amount_paid += tx_amount

            effective_total_debt = max(0.0, sale_order.amount_total - amount_paid)
            remaining_debt = max(
                0.0, effective_total_debt - existing_cod_sum_in_order_curr
            )
            cod_val = min(cod_val, remaining_debt)

            if carrier_curr and order_curr and carrier_curr != order_curr:
                cod_amount = round(
                    order_curr._convert(
                        cod_val,
                        carrier_curr,
                        company,
                        date_rate,
                    )
                )
                insurance_value = round(
                    order_curr._convert(
                        goods_amount,
                        carrier_curr,
                        company,
                        date_rate,
                    )
                )
                goods_amount_res = round(
                    order_curr._convert(
                        goods_amount,
                        carrier_curr,
                        company,
                        date_rate,
                    )
                )
                shipping_fee_res = round(
                    order_curr._convert(
                        shipping_fee_amount,
                        carrier_curr,
                        company,
                        date_rate,
                    )
                )
            else:
                cod_amount = round(cod_val)
                insurance_value = round(goods_amount)
                goods_amount_res = round(goods_amount)
                shipping_fee_res = round(shipping_fee_amount)
        elif not is_return:
            goods_amount = total_items_price
            shipping_fee_amount = 0.0
            if carrier_curr and order_curr and carrier_curr != order_curr:
                goods_amount_res = round(
                    order_curr._convert(
                        goods_amount,
                        carrier_curr,
                        company,
                        date_rate,
                    )
                )
                shipping_fee_res = 0.0
                insurance_value = goods_amount_res
            else:
                goods_amount_res = round(goods_amount)
                shipping_fee_res = 0.0
                insurance_value = goods_amount_res

        required_note = (
            getattr(picking, "required_note", False)
            or (sale_order and getattr(sale_order, "required_note", False))
            or (
                self._fields["required_note"].default(self)
                if callable(self._fields["required_note"].default)
                else self._fields["required_note"].default
            )
        )
        delivery_note = picking.note or (sale_order.note if sale_order else "")

        existing_count = len(picking.shipping_order_ids)
        seq_suffix = f"-{existing_count + 1:02d}" if existing_count > 0 else ""
        if sale_order:
            client_code = f"{sale_order.name}-{picking.id}{seq_suffix}"
        else:
            client_code = f"{picking.name.replace('/', '-')}{seq_suffix}"

        content_desc = picking.origin or picking.name or (_("Order %s") % picking.name)

        res_vals = {
            "name": _("New"),
            "client_order_code": client_code,
            "content": content_desc,
            "company_id": picking.company_id.id or self.env.company.id,
            "carrier_id": carrier.id,
            "currency_id": carrier_curr.id,
            "service_id": service_id,
            "service_code": service_code,
            "service_name": service_name,
            "service_type": service_type,
            "cod_failed_amount": cod_failed_amount,
            "sale_order_id": sale_order.id if sale_order else False,
            "picking_id": picking.id,
            "partner_id": recipient_partner.id if recipient_partner else False,
            "weight": int(pkg_weight),
            "length": int(length),
            "width": int(width),
            "height": int(height),
            "cod_amount": cod_amount,
            "goods_amount": goods_amount_res,
            "shipping_fee_amount": shipping_fee_res,
            "insurance_value": insurance_value,
            "payment_type_id": payment_type,
            "required_note": required_note,
            "note": delivery_note,
            "items": items,
            "carrier_status": False,
            "internal_state": "draft",
        }
        res_vals.update(from_data)
        res_vals.update(to_data)
        return res_vals

    @api.model
    def _prepare_shipping_data_from_sale_order(self, order, carrier=None):
        carrier = carrier or order.carrier_id
        if not carrier:
            raise UserError(_("Delivery method is required to prepare shipping order."))

        warehouse = order.warehouse_id or carrier.sender_warehouse_id
        warehouse_partner = (
            warehouse.partner_id if warehouse else order.company_id.partner_id
        )
        sender_partner = carrier.sender_partner_id or warehouse_partner
        recipient_partner = order.partner_shipping_id or order.partner_id

        from_data = self._resolve_address_payload(
            carrier,
            sender_partner,
            is_sender=True,
            default_name=warehouse_partner.name
            if warehouse_partner
            else order.company_id.name,
            default_phone=carrier.sender_phone,
            default_street=carrier.sender_address,
            default_state=carrier.sender_state_id,
            default_ward=carrier.sender_ward_id,
        )
        to_data = self._resolve_address_payload(
            carrier,
            recipient_partner,
            is_sender=False,
        )

        carrier_curr = carrier.currency_id or order.company_id.currency_id
        order_curr = order.currency_id
        company = order.company_id or self.env.company
        date_rate = order.date_order or fields.Date.today()

        valid_lines = [
            l
            for l in order.order_line
            if not l.is_delivery
            and l.product_id.type != "service"
            and l.product_uom_qty > 0
        ]
        items, total_weight, total_items_price = self._prepare_package_items(
            valid_lines, order_curr, carrier_curr, company, date_rate
        )
        total_weight = int(round(total_weight)) if total_weight > 0 else 0

        length, width, height = self._compute_package_dimensions(
            valid_lines,
            default_length=0,
            default_width=0,
            default_height=0,
        )

        payment_type = order.shipping_payment_type or False
        has_charged_delivery = bool(
            order.order_line.filtered(lambda l: l.is_delivery and l.price_total > 0)
        )
        if has_charged_delivery and payment_type == "2":
            raise UserError(
                _(
                    "Sale order %(so)s already includes a delivery fee on the order. "
                    "Cannot set shipping payment type to 'Recipient Pays' (payment_type = 2) "
                    "as it would double charge the customer. "
                    "Please use 'Sender / Shop Pays' (payment_type = 1) or adjust the delivery line on the sale order first."
                )
                % {"so": order.name}
            )
        service_id = order.delivery_service_id or False
        service_code = order.delivery_service_code or (
            str(service_id) if service_id else ""
        )
        service_name = order.delivery_service_name or False
        service_type = order.delivery_service_type or False

        goods_amount = total_items_price
        prior_active_ships = order.shipping_order_ids.filtered(
            lambda s: (
                s.internal_state not in ["cancelled"]
                and s.carrier_status not in ["cancel"]
            )
        )

        shipping_fee_amount = 0.0
        if payment_type == "1" and not prior_active_ships:
            delivery_line = order.order_line.filtered(lambda l: l.is_delivery)[:1]
            shipping_fee_amount = delivery_line.price_total if delivery_line else 0.0

        cod_val = goods_amount + shipping_fee_amount

        existing_cod_sum_in_order_curr = 0.0
        for s in prior_active_ships:
            s_curr = s.currency_id or carrier_curr
            if s_curr and order_curr and s_curr != order_curr:
                existing_cod_sum_in_order_curr += s_curr._convert(
                    s.cod_amount, order_curr, company, date_rate
                )
            else:
                existing_cod_sum_in_order_curr += s.cod_amount

        amount_paid = 0.0
        posted_invoices = order.invoice_ids.filtered(
            lambda inv: inv.state == "posted" and inv.move_type == "out_invoice"
        )
        if posted_invoices:
            for inv in posted_invoices:
                inv_paid = inv.amount_total - inv.amount_residual
                if inv.currency_id and order_curr and inv.currency_id != order_curr:
                    amount_paid += inv.currency_id._convert(
                        inv_paid, order_curr, company, date_rate
                    )
                else:
                    amount_paid += inv_paid
        else:
            done_txs = getattr(
                order, "transaction_ids", self.env["payment.transaction"]
            ).filtered(lambda tx: tx.state == "done")
            for tx in done_txs:
                tx_amount = tx.amount
                if tx.currency_id and order_curr and tx.currency_id != order_curr:
                    amount_paid += tx.currency_id._convert(
                        tx_amount, order_curr, company, date_rate
                    )
                else:
                    amount_paid += tx_amount

        effective_total_debt = max(0.0, order.amount_total - amount_paid)
        remaining_debt = max(0.0, effective_total_debt - existing_cod_sum_in_order_curr)
        cod_val = min(cod_val, remaining_debt)

        if carrier_curr and order_curr and carrier_curr != order_curr:
            cod_amount = round(
                order_curr._convert(
                    cod_val,
                    carrier_curr,
                    company,
                    date_rate,
                )
            )
            insurance_value = round(
                order_curr._convert(
                    goods_amount,
                    carrier_curr,
                    company,
                    date_rate,
                )
            )
            goods_amount_res = round(
                order_curr._convert(
                    goods_amount,
                    carrier_curr,
                    company,
                    date_rate,
                )
            )
            shipping_fee_res = round(
                order_curr._convert(
                    shipping_fee_amount,
                    carrier_curr,
                    company,
                    date_rate,
                )
            )
        else:
            cod_amount = round(cod_val)
            insurance_value = round(goods_amount)
            goods_amount_res = round(goods_amount)
            shipping_fee_res = round(shipping_fee_amount)

        existing_count = len(order.shipping_order_ids)
        client_code = f"{order.name}-{existing_count + 1:02d}"

        res_vals = {
            "name": _("New"),
            "client_order_code": client_code,
            "content": _("Order %s") % order.name,
            "company_id": order.company_id.id or self.env.company.id,
            "carrier_id": carrier.id,
            "currency_id": carrier_curr.id,
            "service_id": service_id,
            "service_code": service_code,
            "service_name": service_name,
            "service_type": service_type,
            "cod_failed_amount": 0.0,
            "sale_order_id": order.id,
            "partner_id": recipient_partner.id if recipient_partner else False,
            "weight": int(total_weight),
            "length": int(length),
            "width": int(width),
            "height": int(height),
            "cod_amount": cod_amount,
            "goods_amount": goods_amount_res,
            "shipping_fee_amount": shipping_fee_res,
            "insurance_value": insurance_value,
            "payment_type_id": payment_type,
            "required_note": (
                getattr(order, "required_note", False)
                or (
                    self._fields["required_note"].default(self)
                    if callable(self._fields["required_note"].default)
                    else self._fields["required_note"].default
                )
            ),
            "note": order.note or "",
            "items": items,
            "carrier_status": False,
            "internal_state": "draft",
        }
        res_vals.update(from_data)
        res_vals.update(to_data)
        return res_vals

    def _check_dimensions(self):
        for ship in self:
            missing = []
            if not ship.weight or ship.weight <= 0:
                missing.append(_("Weight (weight)"))
            if not ship.length or ship.length <= 0:
                missing.append(_("Length (length)"))
            if not ship.width or ship.width <= 0:
                missing.append(_("Width (width)"))
            if not ship.height or ship.height <= 0:
                missing.append(_("Height (height)"))
            if missing:
                raise UserError(
                    _(
                        "Package dimensions and weight are required for %(shipment)s: %(fields)s. Values must be greater than zero."
                    )
                    % {
                        "shipment": ship.name
                        or ship.client_order_code
                        or _("Shipping Order"),
                        "fields": ", ".join(missing),
                    }
                )

    def _send_customer_shipping_notification(self):
        self.ensure_one()
        # Customer notification hook for Zalo ZNS / SMS / Email integrations
        return True

    def action_send_to_carrier(self):
        self.ensure_one()
        self._check_dimensions()
        carrier = self.carrier_id
        if not carrier or carrier.delivery_type != "ohub":
            raise UserError(_("Please select an 'oHUB Integration' delivery method."))

        res = carrier.execute_ohub_operation("create_shipment", record=self)
        payload = res.get("payload") if isinstance(res, dict) else {}
        if not isinstance(payload, dict):
            raise UserError(
                _("Carrier integration did not return a valid create_shipment response.")
            )

        if payload.get("error_message"):
            raise UserError(str(payload["error_message"]))

        self._validate_contract_payload(
            payload,
            ["order_code", "tracking_number", "carrier_status", "total_fee"],
            "create_shipment",
        )

        order_code = str(payload["order_code"])
        tracking_number = str(payload["tracking_number"])
        carrier_status = str(payload["carrier_status"])
        total_fee = float(payload["total_fee"])
        sort_code = str(payload.get("sort_code") or "")

        self.write(
            {
                "order_code": order_code,
                "sort_code": sort_code,
                "estimated_fee": total_fee,
                "carrier_status": carrier_status,
                "internal_state": self._map_internal_state(carrier_status),
            }
        )

        if self.picking_id:
            self.picking_id.carrier_tracking_ref = tracking_number

        msg_parts = [
            _("Successfully created shipping order on carrier %(carrier)s.")
            % {"carrier": carrier.name},
            _("Tracking Code: <b>%(code)s</b>") % {"code": order_code},
        ]
        if self.cod_amount:
            msg_parts.append(
                _("COD Amount: <b>%(cod)s %(curr)s</b>")
                % {
                    "cod": f"{self.cod_amount:,.0f}",
                    "curr": self.currency_id.name or "",
                }
            )
        if self.expected_delivery_time:
            msg_parts.append(
                _("Expected Delivery: %(date)s")
                % {"date": fields.Datetime.to_string(self.expected_delivery_time)}
            )
        full_msg = "<br/>".join(msg_parts)
        self.message_post(body=full_msg)
        if self.picking_id:
            self.picking_id.message_post(body=full_msg)
        if self.sale_order_id:
            self.sale_order_id.message_post(body=full_msg)

        self._send_customer_shipping_notification()
        return True

    def action_preview_with_carrier(self):
        self.ensure_one()
        self._check_dimensions()
        carrier = self.carrier_id
        if not carrier or carrier.delivery_type != "ohub":
            raise UserError(_("Please select an 'oHUB Integration' delivery method."))

        res = carrier.execute_ohub_operation("preview_order", record=self)
        is_success, err_msg = self._parse_carrier_response(res)

        if is_success:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Validation Successful"),
                    "message": _(
                        "Package and delivery address information is valid with carrier."
                    ),
                    "sticky": False,
                    "type": "success",
                },
            }
        else:
            raise UserError(
                err_msg
                or _("Order information is not valid according to carrier regulations.")
            )
