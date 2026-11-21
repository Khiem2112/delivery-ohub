from odoo import api, fields, models, _
from odoo.exceptions import UserError


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(
        selection_add=[('ohub', 'oHUB Integration')],
        ondelete={'ohub': 'set default'},
    )
    auto_create_shipping_on_validate = fields.Boolean(
        string='Auto Create Shipping on Validate',
        default=True,
        help='Automatically create and send shipping order to carrier when delivery picking is validated.',
    )
    hub_flow_id = fields.Many2one(
        comodel_name='hub.flow',
        string='oHUB Integration Flow',
        index=True,
    )
    sender_warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string='Default Shipping Warehouse',
    )
    sender_partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Sender Contact Address',
    )
    sender_phone = fields.Char(string='Sender Phone')
    sender_address = fields.Char(string='Sender Detailed Address')
    sender_state_id = fields.Many2one(
        comodel_name='res.country.state',
        string='Sender State / Province',
        domain="[('country_id.code', '=', 'VN')]",
    )
    sender_ward_id = fields.Many2one(
        comodel_name='res.admin.unit',
        string='Sender Ward / Commune',
        domain="[('state_id', '=?', sender_state_id)]",
    )
    operation_ids = fields.One2many(
        comodel_name='delivery.ohub.operation',
        inverse_name='carrier_id',
        string='Integration Operations',
    )
    address_mapping_ids = fields.One2many(
        comodel_name='delivery.address.mapping',
        inverse_name='carrier_id',
        string='Address Mappings',
    )
    address_mapping_count = fields.Integer(
        string='Address Mapping Count',
        compute='_compute_address_mapping_count',
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Carrier Currency',
        compute='_compute_carrier_currency_id',
        store=True,
        readonly=False,
        precompute=True,
        required=True,
        help='Currency used by this delivery method and its integration API (e.g. VND).',
    )

    @api.depends('product_id', 'company_id')
    def _compute_carrier_currency_id(self):
        for carrier in self:
            if not carrier.currency_id:
                carrier.currency_id = (
                    carrier.product_id.currency_id
                    or carrier.company_id.currency_id
                    or self.env.company.currency_id
                )

    def _get_conversion_currencies(self, order, conversion):
        carrier_currency = self.currency_id or (self.company_id or self.env['res.company']._get_main_company()).currency_id
        pricelist_currency = order.currency_id

        if conversion == 'company_to_pricelist':
            return carrier_currency, pricelist_currency
        elif conversion == 'pricelist_to_company':
            return pricelist_currency, carrier_currency
        return super()._get_conversion_currencies(order, conversion)

    def _get_operation(self, operation_type, raise_if_not_found=True):
        self.ensure_one()
        operation = self.operation_ids.filtered(
            lambda op: op.operation_type == operation_type and op.active
        )[:1]
        if not operation and raise_if_not_found:
            raise UserError(
                _("Delivery method '%(carrier)s' has no configured operation: %(op_type)s.")
                % {
                    'carrier': self.name,
                    'op_type': operation_type,
                }
            )
        return operation

    def execute_ohub_operation(self, operation_type, record=None, extra_env=None, raise_if_not_found=True):
        self.ensure_one()
        operation = self._get_operation(operation_type, raise_if_not_found=raise_if_not_found)
        if not operation:
            return False
        return operation.execute(record=record, extra_env=extra_env)

    def _convert_currency(self, amount, from_currency, to_currency, company=None, date=None):
        if not amount or not from_currency or not to_currency or from_currency == to_currency:
            return amount
        return from_currency._convert(
            amount,
            to_currency,
            company or self.company_id or self.env.company,
            date or fields.Date.today(),
        )

    def ohub_rate_shipment(self, order):
        self.ensure_one()
        if isinstance(order, int):
            order = self.env['sale.order'].browse(order)

        if hasattr(order, '_name') and order._name == 'stock.picking':
            vals = self.env['delivery.shipping.order']._prepare_shipping_data_from_picking(
                order, carrier=self
            )
        else:
            vals = self.env['delivery.shipping.order']._prepare_shipping_data_from_sale_order(
                order, carrier=self
            )
        shipping_order = self.env['delivery.shipping.order'].new(vals)
        try:
            shipping_order._check_dimensions()
        except UserError as e:
            return {
                'success': False,
                'price': 0.0,
                'error_message': str(e),
                'warning_message': False,
            }

        res = self.execute_ohub_operation('rate_shipment', record=shipping_order)
        fee_data = res.get('payload') if isinstance(res, dict) else {}
        if not isinstance(fee_data, dict):
            return {
                'success': False,
                'price': 0.0,
                'error_message': _("Carrier integration did not return a valid rate_shipment response."),
                'warning_message': False,
            }

        if fee_data.get('error_message'):
            return {
                'success': False,
                'price': 0.0,
                'error_message': str(fee_data['error_message']),
                'warning_message': False,
            }

        self.env["delivery.shipping.order"]._validate_contract_payload(
            fee_data, ["total_fee", "service_fee"], "rate_shipment"
        )
        total_fee = float(fee_data["total_fee"])
        service_fee = float(fee_data["service_fee"])
        insurance_fee = float(fee_data.get("insurance_fee") or 0.0)
        cod_fee = float(fee_data.get("cod_fee") or 0.0)

        carrier_currency = self.currency_id or self.company_id.currency_id or self.env.company.currency_id
        if hasattr(order, '_name') and order._name == 'stock.picking':
            order_currency = (
                order.sale_id.currency_id
                if getattr(order, 'sale_id', False) and order.sale_id
                else (order.company_id.currency_id or self.env.company.currency_id)
            )
            date_rate = order.scheduled_date or fields.Date.today()
            company = order.company_id or self.env.company
        else:
            order_currency = getattr(order, 'currency_id', False) or carrier_currency
            date_rate = getattr(order, 'date_order', False) or fields.Date.today()
            company = getattr(order, 'company_id', False) or self.env.company

        price = self._convert_currency(
            total_fee,
            carrier_currency,
            order_currency,
            company,
            date_rate,
        )

        return {
            'success': True,
            'price': price,
            'error_message': False,
            'warning_message': False,
        }

    def ohub_send_shipping(self, pickings):
        carrier_currency = self.currency_id or self.company_id.currency_id or self.env.company.currency_id
        results = []
        shipping_order_model = self.env['delivery.shipping.order']
        for picking in pickings:
            if isinstance(picking, int):
                picking = self.env['stock.picking'].browse(picking)

            sale_order = picking.sale_id
            order_currency = sale_order.currency_id if sale_order else picking.company_id.currency_id

            shipping_order = picking._get_active_shipping_order()

            if not shipping_order:
                vals = shipping_order_model._prepare_shipping_data_from_picking(picking, carrier=self)
                shipping_order = shipping_order_model.create(vals)

            if not shipping_order.order_code:
                try:
                    with self.env.cr.savepoint():
                        shipping_order.action_send_to_carrier()
                except Exception as exc:
                    fail_msg = _(
                        "Automatic transmission of shipping order %(name)s to carrier failed: %(error)s"
                    ) % {
                        "name": shipping_order.client_order_code or shipping_order.name,
                        "error": str(exc),
                    }
                    picking.message_post(body=fail_msg)
                    shipping_order.message_post(body=fail_msg)

            exact_price = self._convert_currency(
                shipping_order.estimated_fee or 0.0,
                carrier_currency,
                order_currency,
                picking.company_id or self.env.company,
                fields.Date.today(),
            )

            results.append({
                'exact_price': exact_price,
                'tracking_number': shipping_order.order_code,
            })
        return results

    def ohub_cancel_shipment(self, picking):
        shipping_order = picking._get_active_shipping_order()
        if not shipping_order:
            return True

        carrier_status = shipping_order.carrier_status or "draft"
        if carrier_status not in ["ready_to_pick", "draft"]:
            raise UserError(
                _("A shipping order can only be cancelled while in 'Ready to Pick' or 'Draft' status.")
            )

        if not shipping_order.order_code:
            shipping_order.write({
                "internal_state": "cancelled",
            })
            shipping_order.message_post(body=_("Draft shipping order cancelled."))
            return True

        res = self.execute_ohub_operation("cancel_shipment", record=shipping_order)
        payload = res.get("payload") if isinstance(res, dict) else res
        if not isinstance(payload, dict):
            raise UserError(_("Carrier integration did not return a valid cancellation response."))

        self.env["delivery.shipping.order"]._validate_contract_payload(
            payload, ["success", "carrier_status"], "cancel_shipment"
        )
        is_success = bool(payload["success"])
        carrier_status = str(payload["carrier_status"])
        if not is_success:
            err_msg = payload.get("message") or _("Carrier rejected the cancellation request.")
            raise UserError(err_msg)

        shipping_order.write({
            "carrier_status": carrier_status,
            "internal_state": "cancelled",
        })
        shipping_order.message_post(body=_("Successfully sent cancellation request to carrier."))
        picking.message_post(
            body=_("Shipping order %(order)s was cancelled successfully.")
            % {"order": shipping_order.order_code or shipping_order.name}
        )
        return True

    def ohub_get_tracking_link(self, picking):
        shipping_order = self.env['delivery.shipping.order'].search([
            ('picking_id', '=', picking.id)
        ], limit=1)
        if shipping_order and shipping_order.order_code and self.tracking_url:
            return self.tracking_url.replace('<shipmenttrackingnumber>', shipping_order.order_code)
        return False

    def ohub_fetch_available_services(self, record):
        self.ensure_one()
        if not record:
            return False

        if record._name == "choose.delivery.carrier":
            if record.order_id:
                vals = self.env["delivery.shipping.order"]._prepare_shipping_data_from_sale_order(
                    record.order_id, carrier=self
                )
            elif hasattr(record, "picking_id") and record.picking_id:
                vals = self.env["delivery.shipping.order"]._prepare_shipping_data_from_picking(
                    record.picking_id, carrier=self
                )
            else:
                vals = {}
            pkg_l = record.package_length or (vals.get("length") if isinstance(vals, dict) else 0) or 0
            pkg_w = record.package_width or (vals.get("width") if isinstance(vals, dict) else 0) or 0
            pkg_h = record.package_height or (vals.get("height") if isinstance(vals, dict) else 0) or 0
            pkg_payment = record.payment_type_id or (vals.get("payment_type_id") if isinstance(vals, dict) else False)
            if not pkg_l or not pkg_w or not pkg_h or pkg_l <= 0 or pkg_w <= 0 or pkg_h <= 0:
                raise UserError(
                    _("Package dimensions (Length, Width, Height) are required to fetch available carrier services.")
                )
            if not pkg_payment:
                raise UserError(
                    _("Shipping payment type is required to fetch available carrier services.")
                )
            vals.update({
                "length": pkg_l,
                "width": pkg_w,
                "height": pkg_h,
                "payment_type_id": pkg_payment,
                "cod_failed_amount": record.cod_failed_amount or (vals.get("cod_failed_amount") if isinstance(vals, dict) else 0.0) or 0.0,
            })
            shipping_order = self.env["delivery.shipping.order"].new(vals)
        elif record._name == "sale.order":
            vals = self.env["delivery.shipping.order"]._prepare_shipping_data_from_sale_order(
                record, carrier=self
            )
            shipping_order = self.env["delivery.shipping.order"].new(vals)
        elif record._name == "stock.picking":
            vals = self.env["delivery.shipping.order"]._prepare_shipping_data_from_picking(
                record, carrier=self
            )
            shipping_order = self.env["delivery.shipping.order"].new(vals)
        else:
            shipping_order = record

        op_available = self.operation_ids.filtered(
            lambda op: op.operation_type == "available_services" and op.active
        )
        services_data = []
        if op_available:
            res_services = self.execute_ohub_operation(
                "available_services", record=shipping_order
            )
            payload = res_services.get("payload") if isinstance(res_services, dict) else {}
            if not isinstance(payload, dict) or "services" not in payload or not isinstance(payload["services"], list):
                raise UserError(
                    _("Contract violation in 'available_services': response payload must contain a 'services' list.")
                )
            services_data = payload["services"]

        if not op_available:
            raise UserError(
                _("Delivery method '%(carrier)s' has no configured available_services operation.")
                % {"carrier": self.name}
            )
        if not services_data:
            raise UserError(
                _("Carrier '%(carrier)s' did not return any available shipping services for this shipment.")
                % {"carrier": self.name}
            )

        if record._name == "choose.delivery.carrier":
            is_real_record = isinstance(record.id, int)
            target_quotes = record.fee_quote_ids.filtered(lambda q: q.carrier_id == self)
            if is_real_record and target_quotes:
                target_quotes.unlink()

            carrier_currency = self.currency_id or self.company_id.currency_id or self.env.company.currency_id
            target_currency = record.currency_id or carrier_currency
            company = getattr(record, "company_id", False) or self.company_id or self.env.company
            date_rate = fields.Date.today()
            if getattr(record, "order_id", False) and record.order_id.date_order:
                date_rate = record.order_id.date_order
            elif getattr(record, "picking_id", False) and record.picking_id.scheduled_date:
                date_rate = record.picking_id.scheduled_date

            quotes_vals = []
            for svc in services_data:
                if not isinstance(svc, dict):
                    continue
                self.env["delivery.shipping.order"]._validate_contract_payload(
                    svc,
                    [
                        "service_id",
                        "service_code",
                        "service_name",
                        "service_type",
                        "total_fee",
                        "service_fee",
                    ],
                    "available_services.service",
                )
                service_id = svc["service_id"]
                service_code = str(svc["service_code"])
                service_name = str(svc["service_name"])
                service_type = str(svc["service_type"]).lower()
                if service_type not in ("standard", "express", "economy"):
                    raise UserError(
                        _(
                            "Contract violation in 'available_services': invalid service_type '%(type)s'. Must be standard, express, or economy."
                        )
                        % {"type": service_type}
                    )

                raw_total = float(svc["total_fee"])
                raw_service = float(svc["service_fee"])
                raw_insurance = float(svc.get("insurance_fee") or 0.0)
                raw_cod = float(svc.get("cod_fee") or 0.0)

                total_fee = raw_total
                service_fee = raw_service
                insurance_fee = raw_insurance
                cod_fee = raw_cod

                if carrier_currency and target_currency and carrier_currency != target_currency:
                    total_fee = self._convert_currency(raw_total, carrier_currency, target_currency, company, date_rate)
                    service_fee = self._convert_currency(raw_service, carrier_currency, target_currency, company, date_rate)
                    insurance_fee = self._convert_currency(raw_insurance, carrier_currency, target_currency, company, date_rate)
                    cod_fee = self._convert_currency(raw_cod, carrier_currency, target_currency, company, date_rate)

                error_msg = svc.get("error_message") or False

                quote_dict = {
                    "wizard_id": record.id if is_real_record else False,
                    "carrier_id": self.id,
                    "service_id": int(service_id) if isinstance(service_id, int) or (isinstance(service_id, str) and service_id.isdigit()) else False,
                    "service_code": service_code,
                    "service_name": service_name,
                    "service_type": service_type,
                    "service_fee": service_fee,
                    "insurance_fee": insurance_fee,
                    "cod_fee": cod_fee,
                    "total_fee": total_fee,
                    "carrier_total_fee": raw_total,
                    "error_message": error_msg,
                    "is_outdated": False,
                    "payment_type_id": pkg_payment,
                    "package_length": pkg_l,
                    "package_width": pkg_w,
                    "package_height": pkg_h,
                    "cod_failed_amount": record.cod_failed_amount or 0.0,
                }
                quotes_vals.append(quote_dict)

            if not quotes_vals:
                raise UserError(
                    _("Carrier '%(carrier)s' did not return any valid shipping services for this route.")
                    % {"carrier": self.name}
                )

            if is_real_record:
                created_quotes = self.env["delivery.fee.quote"].create(quotes_vals)
                if created_quotes:
                    created_quotes[0].write({"is_selected": True})
                    if not op_available:
                        self.ohub_calculate_quote_fee(created_quotes[0])
                return created_quotes
            else:
                commands = [(5, 0, 0)] + [(0, 0, q) for q in quotes_vals]
                record.fee_quote_ids = commands
                created_quotes = record.fee_quote_ids.filtered(lambda q: q.carrier_id == self)
                if created_quotes:
                    created_quotes[0].is_selected = True
                    if not op_available:
                        self.ohub_calculate_quote_fee(created_quotes[0])
                return created_quotes

        return services_data

    def ohub_calculate_quote_fee(self, quote):
        self.ensure_one()
        if not quote:
            return False

        quote.ensure_one()
        wizard = quote.wizard_id
        if wizard.order_id:
            data = self.env["delivery.shipping.order"]._prepare_shipping_data_from_sale_order(
                wizard.order_id, carrier=self
            )
        elif hasattr(wizard, "picking_id") and wizard.picking_id:
            data = self.env["delivery.shipping.order"]._prepare_shipping_data_from_picking(
                wizard.picking_id, carrier=self
            )
        else:
            data = {}

        pkg_l = quote.package_length or (wizard.package_length if wizard else 0) or (data.get("length") if isinstance(data, dict) else 0) or 0
        pkg_w = quote.package_width or (wizard.package_width if wizard else 0) or (data.get("width") if isinstance(data, dict) else 0) or 0
        pkg_h = quote.package_height or (wizard.package_height if wizard else 0) or (data.get("height") if isinstance(data, dict) else 0) or 0
        pkg_payment = quote.payment_type_id or (wizard.payment_type_id if wizard else False) or (data.get("payment_type_id") if isinstance(data, dict) else False)
        if not pkg_l or not pkg_w or not pkg_h or pkg_l <= 0 or pkg_w <= 0 or pkg_h <= 0:
            raise UserError(
                _("Package dimensions (Length, Width, Height) are required to calculate quote fee.")
            )
        if not pkg_payment:
            raise UserError(
                _("Shipping payment type is required to calculate quote fee.")
            )

        data.update({
            "service_id": int(quote.service_id) if quote.service_id else False,
            "service_code": quote.service_code or "",
            "service_type": quote.service_type or (wizard.service_type if wizard else False),
            "length": pkg_l,
            "width": pkg_w,
            "height": pkg_h,
            "payment_type_id": pkg_payment,
            "cod_failed_amount": quote.cod_failed_amount or (wizard.cod_failed_amount if wizard else 0.0) or (data.get("cod_failed_amount") if isinstance(data, dict) else 0.0) or 0.0,
        })
        shipping_order = self.env["delivery.shipping.order"].new(data)

        res_fee = self.execute_ohub_operation(
            "rate_shipment",
            record=shipping_order,
            extra_env={
                "service_id": int(quote.service_id) if quote.service_id else False,
                "service_code": quote.service_code or "",
                "service_type": quote.service_type or (wizard.service_type if wizard else False),
            },
        )
        fee_data = res_fee.get("payload") if isinstance(res_fee, dict) else {}
        if not isinstance(fee_data, dict):
            raise UserError(_("Carrier integration did not return a valid rate_shipment response."))

        error_msg = str(fee_data["error_message"]) if fee_data.get("error_message") else False
        if not error_msg:
            self.env["delivery.shipping.order"]._validate_contract_payload(
                fee_data, ["total_fee", "service_fee"], "rate_shipment"
            )
            total_fee = float(fee_data["total_fee"])
            service_fee = float(fee_data["service_fee"])
            insurance_fee = float(fee_data.get("insurance_fee") or 0.0)
            cod_fee = float(fee_data.get("cod_fee") or 0.0)
        else:
            total_fee = 0.0
            service_fee = 0.0
            insurance_fee = 0.0
            cod_fee = 0.0

        raw_total_fee = total_fee
        raw_service_fee = service_fee
        raw_insurance_fee = insurance_fee
        raw_cod_fee = cod_fee

        carrier_currency = self.currency_id or self.company_id.currency_id or self.env.company.currency_id
        target_currency = quote.currency_id or (wizard.currency_id if wizard else carrier_currency)
        company = (wizard.company_id if wizard else False) or self.company_id or self.env.company
        date_rate = fields.Date.today()
        if wizard:
            if wizard.order_id and wizard.order_id.date_order:
                date_rate = wizard.order_id.date_order
            elif getattr(wizard, "picking_id", False) and wizard.picking_id.scheduled_date:
                date_rate = wizard.picking_id.scheduled_date

        if not error_msg and carrier_currency and target_currency and carrier_currency != target_currency:
            total_fee = self._convert_currency(raw_total_fee, carrier_currency, target_currency, company, date_rate)
            service_fee = self._convert_currency(raw_service_fee, carrier_currency, target_currency, company, date_rate)
            insurance_fee = self._convert_currency(raw_insurance_fee, carrier_currency, target_currency, company, date_rate)
            cod_fee = self._convert_currency(raw_cod_fee, carrier_currency, target_currency, company, date_rate)

        if wizard:
            for sibling in wizard.fee_quote_ids:
                if sibling != quote:
                    sibling.is_selected = False

        quote_vals = {
            "service_fee": service_fee,
            "insurance_fee": insurance_fee,
            "cod_fee": cod_fee,
            "total_fee": total_fee,
            "carrier_total_fee": raw_total_fee,
            "error_message": error_msg,
            "is_selected": True,
            "is_outdated": False,
        }
        quote.write(quote_vals)

        if wizard:
            if error_msg:
                wizard.delivery_message = error_msg
                wizard.display_price = 0.0
                wizard.delivery_price = 0.0
            else:
                wizard.delivery_message = False

        return quote

    def resolve_carrier_address(self, state=None, ward=None):
        self.ensure_one()
        return self.env["delivery.address.mapping"].resolve_carrier_address(
            self, state=state, ward=ward
        )

    @api.depends()
    def _compute_address_mapping_count(self):
        mapping_data = self.env['delivery.address.mapping']._read_group(
            [('carrier_id', 'in', self.ids)],
            ['carrier_id'],
            ['__count'],
        )
        counts = {carrier.id: count for carrier, count in mapping_data}
        for carrier in self:
            carrier.address_mapping_count = counts.get(carrier.id, 0)

    def action_view_address_mappings(self):
        self.ensure_one()
        domain = [('carrier_id', '=', self.id)]
        return {
            'name': _('Carrier Address Mappings - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'delivery.address.mapping',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {
                'default_carrier_id': self.id,
                'default_hub_flow_id': self.hub_flow_id.id if self.hub_flow_id else False,
                'search_default_group_by_state': 1,
            },
        }
