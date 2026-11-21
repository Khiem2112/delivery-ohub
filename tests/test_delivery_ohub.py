from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase


class TestDeliveryOHub(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.currency_usd = cls.env.ref("base.USD")
        cls.currency_vnd = cls.env.ref("base.VND")

        cls.product_1 = cls.env["product.product"].create({
            "name": "Test Package Product A",
            "type": "consu",
            "lst_price": 10.0,
            "weight": 0.5,
            "length": 20,
            "width": 15,
            "height": 5,
            "taxes_id": [(5, 0, 0)],
        })
        cls.product_2 = cls.env["product.product"].create({
            "name": "Test Package Product B",
            "type": "consu",
            "lst_price": 25.0,
            "weight": 1.0,
            "length": 10,
            "width": 30,
            "height": 8,
            "taxes_id": [(5, 0, 0)],
        })

    def test_compute_package_dimensions(self):
        shipping_model = self.env["delivery.shipping.order"]
        order = self.env["sale.order"].create({
            "partner_id": self.env.user.partner_id.id,
            "order_line": [
                (0, 0, {
                    "product_id": self.product_1.id,
                    "product_uom_qty": 2,
                    "price_unit": 10.0,
                }),
                (0, 0, {
                    "product_id": self.product_2.id,
                    "product_uom_qty": 1,
                    "price_unit": 25.0,
                }),
            ],
        })
        lines = order.order_line
        length, width, height = shipping_model._compute_package_dimensions(lines)

        self.assertEqual(length, 20)
        self.assertEqual(width, 30)
        self.assertEqual(height, 5 * 2 + 8 * 1)

    def test_set_quote_price_payment_types(self):
        carrier = self.env["delivery.carrier"].create({
            "name": "Test OHub Method",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
        })
        wizard = self.env["choose.delivery.carrier"].create({
            "carrier_id": carrier.id,
            "payment_type_id": "1",
        })
        quote = self.env["delivery.fee.quote"].create({
            "wizard_id": wizard.id,
            "carrier_id": carrier.id,
            "service_type": "standard",
            "total_fee": 15.0,
        })

        wizard._set_quote_price(quote)
        self.assertEqual(wizard.display_price, 15.0)
        self.assertEqual(wizard.delivery_price, 15.0)

        wizard.payment_type_id = "2"
        wizard._set_quote_price(quote)
        self.assertEqual(wizard.display_price, 15.0)
        self.assertEqual(wizard.delivery_price, 0.0)

        wizard._set_quote_price(False)
        self.assertEqual(wizard.display_price, 0.0)
        self.assertEqual(wizard.delivery_price, 0.0)
        self.assertFalse(wizard.selected_quote_id)

    def test_carrier_convert_currency_helper(self):
        carrier = self.env["delivery.carrier"].create({
            "name": "Test Helper Method",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
        })
        amount = 100.0
        same_result = carrier._convert_currency(amount, self.currency_usd, self.currency_usd)
        self.assertEqual(same_result, 100.0)

        zero_result = carrier._convert_currency(0.0, self.currency_usd, self.currency_vnd)
        self.assertEqual(zero_result, 0.0)

    def test_active_shipping_order_rule_and_reship(self):
        carrier = self.env["delivery.carrier"].create({
            "name": "Test Active Rule Carrier",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
        })
        picking_type = self.env["stock.picking.type"].search([("code", "=", "outgoing")], limit=1)
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": picking_type.default_location_src_id.id,
            "location_dest_id": self.env.ref("stock.stock_location_customers").id,
            "carrier_id": carrier.id,
        })

        self.assertFalse(picking.has_active_shipping_order)
        self.assertFalse(picking._get_active_shipping_order())

        shipping_order = self.env["delivery.shipping.order"].create({
            "name": "SHIP/TEST/001",
            "client_order_code": "CLI-TEST-001",
            "order_code": "TRACK001",
            "picking_id": picking.id,
            "carrier_id": carrier.id,
            "internal_state": "ready",
            "carrier_status": "ready_to_pick",
        })

        self.assertTrue(picking.has_active_shipping_order)
        self.assertEqual(picking._get_active_shipping_order(), shipping_order)

        shipping_order.write({
            "internal_state": "cancelled",
            "carrier_status": "cancel",
        })
        self.assertFalse(picking.has_active_shipping_order)
        self.assertFalse(picking._get_active_shipping_order())

        new_shipping_order = self.env["delivery.shipping.order"].create({
            "name": "SHIP/TEST/002",
            "client_order_code": "CLI-TEST-002",
            "order_code": "TRACK002",
            "picking_id": picking.id,
            "carrier_id": carrier.id,
            "internal_state": "ready",
            "carrier_status": "ready_to_pick",
        })
        self.assertTrue(picking.has_active_shipping_order)
        self.assertEqual(picking._get_active_shipping_order(), new_shipping_order)

        new_shipping_order.write({
            "internal_state": "delivered",
            "carrier_status": "delivered",
        })
        self.assertFalse(picking.has_active_shipping_order)

    def test_auto_create_shipping_on_validate_and_idempotency(self):
        carrier = self.env["delivery.carrier"].create({
            "name": "Test Auto Validate Carrier",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
            "auto_create_shipping_on_validate": True,
        })
        self.assertTrue(carrier.auto_create_shipping_on_validate)

        picking_type = self.env["stock.picking.type"].search([("code", "=", "outgoing")], limit=1)
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": picking_type.default_location_src_id.id,
            "location_dest_id": self.env.ref("stock.stock_location_customers").id,
            "carrier_id": carrier.id,
        })

        called_auto_create = []

        def mock_auto_create(self_picking):
            called_auto_create.append(self_picking.id)

        picking.state = "done"
        self.patch(type(picking), "_auto_create_shipping_order", mock_auto_create)

        picking.button_validate()
        self.assertEqual(called_auto_create, [picking.id])

        self.env["delivery.shipping.order"].create({
            "name": "SHIP/TEST/AUTO1",
            "client_order_code": "CLI-AUTO-01",
            "order_code": "TRACK-AUTO-1",
            "picking_id": picking.id,
            "carrier_id": carrier.id,
            "internal_state": "ready",
            "carrier_status": "ready_to_pick",
        })
        self.assertTrue(picking.has_active_shipping_order)

        called_auto_create.clear()
        picking.button_validate()
        self.assertEqual(called_auto_create, [])

    def test_backorder_shipping_flow(self):
        carrier = self.env["delivery.carrier"].create({
            "name": "Test Backorder Carrier",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
        })
        partner = self.env["res.partner"].create({
            "name": "Test Backorder Customer",
            "street": "123 Test Street",
            "phone": "0901234567",
        })
        order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "carrier_id": carrier.id,
            "shipping_payment_type": "2",
            "order_line": [
                (0, 0, {
                    "product_id": self.product_1.id,
                    "product_uom_qty": 2,
                    "price_unit": 50.0,
                }),
            ],
        })

        picking_type = self.env["stock.picking.type"].search([("code", "=", "outgoing")], limit=1)
        parent_picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": picking_type.default_location_src_id.id,
            "location_dest_id": self.env.ref("stock.stock_location_customers").id,
            "partner_id": partner.id,
            "sale_id": order.id,
            "carrier_id": carrier.id,
            "shipping_payment_type": "2",
        })

        backorder_picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": picking_type.default_location_src_id.id,
            "location_dest_id": self.env.ref("stock.stock_location_customers").id,
            "partner_id": partner.id,
            "sale_id": order.id,
            "carrier_id": carrier.id,
            "backorder_id": parent_picking.id,
            "shipping_payment_type": "2",
        })

        backorder_data = self.env["delivery.shipping.order"]._prepare_shipping_data_from_picking(
            backorder_picking, carrier=carrier
        )
        self.assertEqual(backorder_data.get("payment_type_id"), "1")

        backorder_default = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": picking_type.default_location_src_id.id,
            "location_dest_id": self.env.ref("stock.stock_location_customers").id,
            "partner_id": partner.id,
            "sale_id": order.id,
            "carrier_id": carrier.id,
            "backorder_id": parent_picking.id,
        })
        backorder_default_data = self.env["delivery.shipping.order"]._prepare_shipping_data_from_picking(
            backorder_default, carrier=carrier
        )
        self.assertEqual(backorder_default_data.get("payment_type_id"), "1")

    def test_prevent_double_shipping_charge(self):
        carrier = self.env["delivery.carrier"].create({
            "name": "Test Double Charge Carrier",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
        })
        partner = self.env["res.partner"].create({
            "name": "Test Customer",
            "street": "123 Street",
            "phone": "0901234567",
        })
        order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "carrier_id": carrier.id,
            "shipping_payment_type": "1",
            "order_line": [
                (0, 0, {
                    "product_id": self.product_1.id,
                    "product_uom_qty": 1,
                    "price_unit": 100.0,
                }),
                (0, 0, {
                    "product_id": self.product_1.id,
                    "is_delivery": True,
                    "product_uom_qty": 1,
                    "price_unit": 30.0,
                }),
            ],
        })
        picking_type = self.env["stock.picking.type"].search([("code", "=", "outgoing")], limit=1)
        with self.assertRaises(UserError):
            self.env["stock.picking"].create({
                "picking_type_id": picking_type.id,
                "location_id": picking_type.default_location_src_id.id,
                "location_dest_id": self.env.ref("stock.stock_location_customers").id,
                "partner_id": partner.id,
                "sale_id": order.id,
                "carrier_id": carrier.id,
                "shipping_payment_type": "2",
            })

    def test_generic_carrier_response_handling(self):
        carrier = self.env["delivery.carrier"].create({
            "name": "Test Generic Extraction Carrier",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
        })
        picking_type = self.env["stock.picking.type"].search([("code", "=", "outgoing")], limit=1)
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": picking_type.default_location_src_id.id,
            "location_dest_id": self.env.ref("stock.stock_location_customers").id,
            "carrier_id": carrier.id,
        })
        shipping_order = self.env["delivery.shipping.order"].create({
            "name": "SHIP/TEST/GEN1",
            "client_order_code": "CLI-GEN-01",
            "picking_id": picking.id,
            "carrier_id": carrier.id,
            "weight": 500,
            "length": 10,
            "width": 10,
            "height": 10,
        })

        fake_carrier_response = {
            "payload": {
                "order_code": "GENERIC_TRACK_999",
                "tracking_number": "GENERIC_TRACK_999",
                "carrier_status": "ready_to_pick",
                "total_fee": 45000.0,
                "sort_code": "HUB_SGN_01",
            }
        }

        def mock_execute_operation(carrier_self, operation_type, record=None, extra_env=None, raise_if_not_found=True):
            if operation_type == "create_shipment":
                return fake_carrier_response
            return {}

        self.patch(type(carrier), "execute_ohub_operation", mock_execute_operation)

        shipping_order.action_send_to_carrier()
        self.assertEqual(shipping_order.order_code, "GENERIC_TRACK_999")
        self.assertEqual(shipping_order.estimated_fee, 45000.0)
        self.assertEqual(shipping_order.sort_code, "HUB_SGN_01")
        self.assertEqual(picking.carrier_tracking_ref, "GENERIC_TRACK_999")

    def test_transported_moves_and_picking_action(self):
        carrier = self.env["delivery.carrier"].create({
            "name": "Test Move View Carrier",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
        })
        picking_type = self.env["stock.picking.type"].search([("code", "=", "outgoing")], limit=1)
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": picking_type.default_location_src_id.id,
            "location_dest_id": self.env.ref("stock.stock_location_customers").id,
            "carrier_id": carrier.id,
            "move_ids": [
                (0, 0, {
                    "name": self.product_1.name,
                    "product_id": self.product_1.id,
                    "product_uom_qty": 3,
                    "product_uom": self.product_1.uom_id.id,
                    "location_id": picking_type.default_location_src_id.id,
                    "location_dest_id": self.env.ref("stock.stock_location_customers").id,
                }),
                (0, 0, {
                    "name": self.product_2.name,
                    "product_id": self.product_2.id,
                    "product_uom_qty": 5,
                    "product_uom": self.product_2.uom_id.id,
                    "location_id": picking_type.default_location_src_id.id,
                    "location_dest_id": self.env.ref("stock.stock_location_customers").id,
                }),
            ],
        })

        shipping_order = self.env["delivery.shipping.order"].create({
            "name": "SHIP/TEST/MV1",
            "client_order_code": "CLI-MV-01",
            "picking_id": picking.id,
            "carrier_id": carrier.id,
        })

        self.assertEqual(shipping_order.move_count, 2)
        self.assertEqual(set(shipping_order.move_ids.mapped("product_id")), {self.product_1, self.product_2})

        action = shipping_order.action_view_picking()
        self.assertEqual(action.get("res_id"), picking.id)
        self.assertEqual(action.get("res_model"), "stock.picking")

    def test_freeship_order_without_delivery_line(self):
        carrier = self.env["delivery.carrier"].create({
            "name": "Test Freeship Carrier",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
        })
        partner = self.env["res.partner"].create({
            "name": "Test Freeship Customer",
            "street": "123 Freeship Street",
            "phone": "0901234567",
        })
        order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "carrier_id": carrier.id,
            "shipping_payment_type": "1",
            "order_line": [
                (0, 0, {
                    "product_id": self.product_1.id,
                    "product_uom_qty": 2,
                    "price_unit": 100.0,
                    "tax_id": [(5, 0, 0)],
                }),
            ],
        })
        picking_type = self.env["stock.picking.type"].search([("code", "=", "outgoing")], limit=1)
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": picking_type.default_location_src_id.id,
            "location_dest_id": self.env.ref("stock.stock_location_customers").id,
            "partner_id": partner.id,
            "sale_id": order.id,
            "carrier_id": carrier.id,
            "shipping_payment_type": "1",
            "move_ids": [
                (0, 0, {
                    "name": self.product_1.name,
                    "product_id": self.product_1.id,
                    "product_uom_qty": 2,
                    "product_uom": self.product_1.uom_id.id,
                    "location_id": picking_type.default_location_src_id.id,
                    "location_dest_id": self.env.ref("stock.stock_location_customers").id,
                    "sale_line_id": order.order_line[0].id,
                }),
            ],
        })
        vals = self.env["delivery.shipping.order"]._prepare_shipping_data_from_picking(
            picking, carrier=carrier
        )
        shipping_order = self.env["delivery.shipping.order"].create(vals)
        self.assertEqual(shipping_order.cod_amount, 200.0)

        fake_carrier_response = {
            "payload": {
                "order_code": "FREESHIP_TRACK_01",
                "tracking_number": "FREESHIP_TRACK_01",
                "carrier_status": "ready_to_pick",
                "total_fee": 30000.0,
                "sort_code": "HUB_01",
            }
        }
        self.patch(type(carrier), "execute_ohub_operation", lambda *args, **kwargs: fake_carrier_response)
        shipping_order.action_send_to_carrier()

        self.assertEqual(shipping_order.cod_amount, 200.0)
        self.assertFalse(order.order_line.filtered(lambda l: l.is_delivery))

    def test_picking_inherits_service_fields_from_so(self):
        carrier = self.env["delivery.carrier"].create({
            "name": "Test Inheritance Carrier",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
        })
        partner = self.env["res.partner"].create({
            "name": "Test Inheritance Customer",
            "street": "123 Inherit Street",
            "phone": "0901234567",
        })
        order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "carrier_id": carrier.id,
            "delivery_service_id": 53320,
            "delivery_service_name": "GHN Fast Express",
            "delivery_service_code": "FAST_01",
            "delivery_service_type": "express",
            "shipping_payment_type": "1",
            "order_line": [
                (0, 0, {
                    "product_id": self.product_1.id,
                    "product_uom_qty": 1,
                    "price_unit": 50.0,
                }),
            ],
        })
        proc_group = self.env["procurement.group"].create({
            "name": order.name,
            "sale_id": order.id,
        })
        picking_type = self.env["stock.picking.type"].search([("code", "=", "outgoing")], limit=1)
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": picking_type.default_location_src_id.id,
            "location_dest_id": self.env.ref("stock.stock_location_customers").id,
            "partner_id": partner.id,
            "group_id": proc_group.id,
        })
        self.assertEqual(picking.delivery_service_id, 53320)
        self.assertEqual(picking.delivery_service_name, "GHN Fast Express")
        self.assertEqual(picking.delivery_service_code, "FAST_01")
        self.assertEqual(picking.delivery_service_type, "express")
        self.assertEqual(picking.carrier_id, carrier)

        shipping_data = self.env["delivery.shipping.order"]._prepare_shipping_data_from_picking(
            picking, carrier=carrier
        )
        self.assertEqual(shipping_data.get("service_id"), 53320)
        self.assertEqual(shipping_data.get("service_name"), "GHN Fast Express")
        self.assertEqual(shipping_data.get("service_code"), "FAST_01")
        self.assertEqual(shipping_data.get("service_type"), "express")

    def test_picking_payment_type_constraint_and_onchange(self):
        carrier = self.env["delivery.carrier"].create({
            "name": "Test Constraint Carrier",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
        })
        partner = self.env["res.partner"].create({
            "name": "Test Constraint Customer",
            "street": "123 Constraint Street",
            "phone": "0901234567",
        })
        order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "carrier_id": carrier.id,
            "shipping_payment_type": "1",
            "order_line": [
                (0, 0, {
                    "product_id": self.product_1.id,
                    "product_uom_qty": 1,
                    "price_unit": 100.0,
                }),
                (0, 0, {
                    "product_id": self.product_1.id,
                    "is_delivery": True,
                    "product_uom_qty": 1,
                    "price_unit": 30.0,
                }),
            ],
        })
        picking_type = self.env["stock.picking.type"].search([("code", "=", "outgoing")], limit=1)
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": picking_type.default_location_src_id.id,
            "location_dest_id": self.env.ref("stock.stock_location_customers").id,
            "partner_id": partner.id,
            "sale_id": order.id,
            "carrier_id": carrier.id,
            "shipping_payment_type": "1",
        })

        picking_form = self.env["stock.picking"].new({
            "partner_id": partner.id,
            "sale_id": order.id,
            "carrier_id": carrier.id,
            "shipping_payment_type": "2",
        })
        res_onchange = picking_form._onchange_shipping_payment_type_ohub()
        self.assertIn("warning", res_onchange or {})
        self.assertEqual(picking_form.shipping_payment_type, "1")

        with self.assertRaises(UserError):
            picking.write({"shipping_payment_type": "2"})

    def test_picking_package_dimensions_auto_compute(self):
        carrier = self.env["delivery.carrier"].create({
            "name": "Dimension Test Carrier",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
        })
        partner = self.env["res.partner"].create({
            "name": "Dimension Customer",
            "street": "123 Dimension St",
            "phone": "0901234567",
        })
        order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "carrier_id": carrier.id,
            "shipping_payment_type": "1",
            "order_line": [
                (0, 0, {
                    "product_id": self.product_1.id,
                    "product_uom_qty": 2,
                    "price_unit": 50.0,
                    "tax_id": [(5, 0, 0)],
                }),
            ],
        })
        picking_type = self.env["stock.picking.type"].search([("code", "=", "outgoing")], limit=1)
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": picking_type.default_location_src_id.id,
            "location_dest_id": self.env.ref("stock.stock_location_customers").id,
            "partner_id": partner.id,
            "sale_id": order.id,
            "carrier_id": carrier.id,
            "shipping_payment_type": "1",
            "move_ids": [
                (0, 0, {
                    "name": self.product_1.name,
                    "product_id": self.product_1.id,
                    "product_uom_qty": 2,
                    "product_uom": self.product_1.uom_id.id,
                    "location_id": picking_type.default_location_src_id.id,
                    "location_dest_id": self.env.ref("stock.stock_location_customers").id,
                    "sale_line_id": order.order_line[0].id,
                }),
            ],
        })
        self.assertEqual(picking.package_length, 0)
        self.assertEqual(picking.package_width, 0)
        self.assertEqual(picking.package_height, 0)

        vals = self.env["delivery.shipping.order"]._prepare_shipping_data_from_picking(
            picking, carrier=carrier
        )
        self.assertEqual(vals["length"], 20)
        self.assertEqual(vals["width"], 15)
        self.assertEqual(vals["height"], 10)

    def test_decimal_quantity_items_and_declared_value(self):
        decimal_product = self.env["product.product"].create({
            "name": "Fresh Meat Decimal Product",
            "type": "consu",
            "lst_price": 80.0,
            "weight": 1.0,
            "length": 12,
            "width": 10,
            "height": 4,
            "taxes_id": [(5, 0, 0)],
        })
        shipping_model = self.env["delivery.shipping.order"]
        order = self.env["sale.order"].create({
            "partner_id": self.env.user.partner_id.id,
            "order_line": [
                (0, 0, {
                    "product_id": decimal_product.id,
                    "product_uom_qty": 0.5,
                    "price_unit": 80.0,
                    "tax_id": [(5, 0, 0)],
                }),
            ],
        })
        lines = order.order_line
        length, width, height = shipping_model._compute_package_dimensions(lines)
        self.assertEqual(length, 12)
        self.assertEqual(width, 10)
        self.assertEqual(height, 2)

        items, total_weight, total_items_price = shipping_model._prepare_package_items(
            lines, order.currency_id, order.currency_id, self.company, order.date_order
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["quantity"], 0.5)
        self.assertEqual(total_items_price, 40.0)
        self.assertEqual(total_weight, 500)

    def test_cod_zero_when_order_fully_paid(self):
        carrier = self.env["delivery.carrier"].create({
            "name": "Full Paid Test Carrier",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
        })
        partner = self.env["res.partner"].create({
            "name": "Paid Customer",
            "street": "123 Paid Road",
            "phone": "0912345678",
        })
        order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "carrier_id": carrier.id,
            "shipping_payment_type": "1",
            "order_line": [
                (0, 0, {
                    "product_id": self.product_1.id,
                    "product_uom_qty": 2,
                    "price_unit": 50.0,
                    "tax_id": [(5, 0, 0)],
                }),
                (0, 0, {
                    "product_id": self.product_1.id,
                    "is_delivery": True,
                    "product_uom_qty": 1,
                    "price_unit": 20.0,
                    "tax_id": [(5, 0, 0)],
                }),
            ],
        })
        picking_type = self.env["stock.picking.type"].search([("code", "=", "outgoing")], limit=1)
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": picking_type.default_location_src_id.id,
            "location_dest_id": self.env.ref("stock.stock_location_customers").id,
            "partner_id": partner.id,
            "sale_id": order.id,
            "carrier_id": carrier.id,
            "shipping_payment_type": "1",
            "move_ids": [
                (0, 0, {
                    "name": self.product_1.name,
                    "product_id": self.product_1.id,
                    "product_uom_qty": 2,
                    "product_uom": self.product_1.uom_id.id,
                    "location_id": picking_type.default_location_src_id.id,
                    "location_dest_id": self.env.ref("stock.stock_location_customers").id,
                    "sale_line_id": order.order_line[0].id,
                }),
            ],
        })

        class MockInvoice:
            state = "posted"
            move_type = "out_invoice"
            currency_id = order.currency_id
            amount_total = 120.0
            amount_residual = 0.0

        class MockInvoiceList(list):
            def filtered(self, func):
                return MockInvoiceList([x for x in self if func(x)])

        self.patch(type(order), "invoice_ids", MockInvoiceList([MockInvoice()]))

        picking_vals = self.env["delivery.shipping.order"]._prepare_shipping_data_from_picking(
            picking, carrier=carrier
        )
        self.assertEqual(picking_vals.get("cod_amount"), 0.0)
        self.assertEqual(picking_vals.get("goods_amount"), 100.0)
        self.assertEqual(picking_vals.get("shipping_fee_amount"), 20.0)

        so_vals = self.env["delivery.shipping.order"]._prepare_shipping_data_from_sale_order(
            order, carrier=carrier
        )
        self.assertEqual(so_vals.get("cod_amount"), 0.0)
        self.assertEqual(so_vals.get("goods_amount"), 100.0)
        self.assertEqual(so_vals.get("shipping_fee_amount"), 20.0)

    def test_cod_capped_when_order_partially_paid(self):
        carrier = self.env["delivery.carrier"].create({
            "name": "Partial Paid Test Carrier",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
        })
        partner = self.env["res.partner"].create({
            "name": "Deposit Customer",
            "street": "456 Deposit Ave",
            "phone": "0912345679",
        })
        order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "carrier_id": carrier.id,
            "shipping_payment_type": "1",
            "order_line": [
                (0, 0, {
                    "product_id": self.product_1.id,
                    "product_uom_qty": 2,
                    "price_unit": 50.0,
                    "tax_id": [(5, 0, 0)],
                }),
                (0, 0, {
                    "product_id": self.product_1.id,
                    "is_delivery": True,
                    "product_uom_qty": 1,
                    "price_unit": 20.0,
                    "tax_id": [(5, 0, 0)],
                }),
            ],
        })
        picking_type = self.env["stock.picking.type"].search([("code", "=", "outgoing")], limit=1)
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": picking_type.default_location_src_id.id,
            "location_dest_id": self.env.ref("stock.stock_location_customers").id,
            "partner_id": partner.id,
            "sale_id": order.id,
            "carrier_id": carrier.id,
            "shipping_payment_type": "1",
            "move_ids": [
                (0, 0, {
                    "name": self.product_1.name,
                    "product_id": self.product_1.id,
                    "product_uom_qty": 2,
                    "product_uom": self.product_1.uom_id.id,
                    "location_id": picking_type.default_location_src_id.id,
                    "location_dest_id": self.env.ref("stock.stock_location_customers").id,
                    "sale_line_id": order.order_line[0].id,
                }),
            ],
        })

        class MockInvoice:
            state = "posted"
            move_type = "out_invoice"
            currency_id = order.currency_id
            amount_total = 120.0
            amount_residual = 50.0

        class MockInvoiceList(list):
            def filtered(self, func):
                return MockInvoiceList([x for x in self if func(x)])

        self.patch(type(order), "invoice_ids", MockInvoiceList([MockInvoice()]))

        picking_vals = self.env["delivery.shipping.order"]._prepare_shipping_data_from_picking(
            picking, carrier=carrier
        )
        self.assertEqual(picking_vals.get("cod_amount"), 50.0)
        self.assertEqual(picking_vals.get("goods_amount"), 100.0)
        self.assertEqual(picking_vals.get("shipping_fee_amount"), 20.0)

        class MockTx:
            state = "done"
            currency_id = order.currency_id
            amount = 80.0

        class MockTxList(list):
            def filtered(self, func):
                return MockTxList([x for x in self if func(x)])

        self.patch(type(order), "invoice_ids", MockInvoiceList([]))
        self.patch(type(order), "transaction_ids", MockTxList([MockTx()]))

        picking_vals_tx = self.env["delivery.shipping.order"]._prepare_shipping_data_from_picking(
            picking, carrier=carrier
        )
        self.assertEqual(picking_vals_tx.get("cod_amount"), 40.0)

    def test_sale_order_cod_ceiling_with_prior_active_ships(self):
        carrier = self.env["delivery.carrier"].create({
            "name": "Prior Ship Carrier",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
        })
        partner = self.env["res.partner"].create({
            "name": "Multi Ship Customer",
            "street": "789 Split Road",
            "phone": "0912345680",
        })
        order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "carrier_id": carrier.id,
            "shipping_payment_type": "1",
            "order_line": [
                (0, 0, {
                    "product_id": self.product_1.id,
                    "product_uom_qty": 3,
                    "price_unit": 50.0,
                    "tax_id": [(5, 0, 0)],
                }),
                (0, 0, {
                    "product_id": self.product_1.id,
                    "is_delivery": True,
                    "product_uom_qty": 1,
                    "price_unit": 30.0,
                    "tax_id": [(5, 0, 0)],
                }),
            ],
        })
        self.assertEqual(order.amount_total, 180.0)

        first_ship = self.env["delivery.shipping.order"].create({
            "name": "SHIP/FIRST/01",
            "client_order_code": "CLI-PRIOR-01",
            "sale_order_id": order.id,
            "carrier_id": carrier.id,
            "cod_amount": 100.0,
            "goods_amount": 70.0,
            "shipping_fee_amount": 30.0,
            "internal_state": "in_transit",
            "carrier_status": "delivering",
            "weight": 500,
            "length": 10,
            "width": 10,
            "height": 10,
        })

        so_vals = self.env["delivery.shipping.order"]._prepare_shipping_data_from_sale_order(
            order, carrier=carrier
        )
        self.assertEqual(so_vals.get("cod_amount"), 80.0)
        self.assertEqual(so_vals.get("goods_amount"), 150.0)
        self.assertEqual(so_vals.get("shipping_fee_amount"), 0.0)

    def test_wizard_change_service_updates_cod_and_picking_amounts(self):
        carrier = self.env["delivery.carrier"].create({
            "name": "Wizard Service Carrier",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
        })
        partner = self.env["res.partner"].create({
            "name": "Wizard Customer",
            "street": "321 Wizard Lane",
            "phone": "0912345681",
        })
        order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "carrier_id": carrier.id,
            "shipping_payment_type": "1",
            "order_line": [
                (0, 0, {
                    "product_id": self.product_1.id,
                    "product_uom_qty": 2,
                    "price_unit": 40.0,
                    "tax_id": [(5, 0, 0)],
                }),
            ],
        })
        picking_type = self.env["stock.picking.type"].search([("code", "=", "outgoing")], limit=1)
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": picking_type.default_location_src_id.id,
            "location_dest_id": self.env.ref("stock.stock_location_customers").id,
            "partner_id": partner.id,
            "sale_id": order.id,
            "carrier_id": carrier.id,
            "shipping_payment_type": "1",
            "move_ids": [
                (0, 0, {
                    "name": self.product_1.name,
                    "product_id": self.product_1.id,
                    "product_uom_qty": 2,
                    "product_uom": self.product_1.uom_id.id,
                    "location_id": picking_type.default_location_src_id.id,
                    "location_dest_id": self.env.ref("stock.stock_location_customers").id,
                    "sale_line_id": order.order_line[0].id,
                }),
            ],
        })

        draft_ship = self.env["delivery.shipping.order"].create({
            "name": "SHIP/DRAFT/01",
            "client_order_code": "CLI-DRAFT-01",
            "picking_id": picking.id,
            "sale_order_id": order.id,
            "carrier_id": carrier.id,
            "cod_amount": 80.0,
            "goods_amount": 80.0,
            "shipping_fee_amount": 0.0,
            "internal_state": "draft",
            "weight": 400,
            "length": 10,
            "width": 10,
            "height": 10,
        })

        wizard = self.env["choose.delivery.carrier"].create({
            "picking_id": picking.id,
            "carrier_id": carrier.id,
            "payment_type_id": "1",
        })
        quote_express = self.env["delivery.fee.quote"].create({
            "wizard_id": wizard.id,
            "carrier_id": carrier.id,
            "service_id": 999,
            "service_code": "EXP_01",
            "service_name": "Express Super Speed",
            "service_type": "express",
            "total_fee": 35000.0,
            "is_selected": True,
        })
        wizard.selected_quote_id = quote_express.id
        wizard.button_confirm()

        self.assertEqual(picking.delivery_service_id, 999)
        self.assertEqual(picking.delivery_service_name, "Express Super Speed")
        self.assertEqual(picking.delivery_service_type, "express")
        self.assertEqual(picking.goods_amount, 80.0)
        self.assertEqual(picking.shipping_fee_amount, 0.0)

        self.assertEqual(draft_ship.service_id, 999)
        self.assertEqual(draft_ship.service_name, "Express Super Speed")
        self.assertEqual(draft_ship.service_type, "express")
        self.assertEqual(draft_ship.estimated_fee, 35000.0)
        self.assertEqual(draft_ship.cod_amount, 80.0)
        self.assertEqual(draft_ship.goods_amount, 80.0)
        self.assertEqual(draft_ship.shipping_fee_amount, 0.0)

    def test_fee_outdated_behavior_on_order_line_changes(self):
        carrier = self.env["delivery.carrier"].create({
            "name": "Fee Outdated Carrier",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
        })
        partner = self.env["res.partner"].create({
            "name": "Fee Outdated Partner",
            "street": "123 Fee Outdated St",
            "phone": "0911223344",
        })
        order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "carrier_id": carrier.id,
            "fee_outdated": False,
            "order_line": [
                (0, 0, {
                    "product_id": self.product_1.id,
                    "product_uom_qty": 1,
                    "price_unit": 50.0,
                }),
            ],
        })
        order.fee_outdated = False

        # Them dong cuoc van chuyen thong qua set_delivery_line khong duoc lam fee_outdated tro thanh True
        order.set_delivery_line(carrier, 20.0)
        self.assertFalse(order.fee_outdated)

        # Cap nhat thong tin dich vu cung dong cuoc
        order.write({
            "delivery_service_id": 101,
            "delivery_service_name": "Standard Delivery",
            "delivery_service_code": "STD",
            "fee_outdated": False,
        })
        self.assertFalse(order.fee_outdated)

        # Chinh sua dong hang san pham thong thuong phai danh dau fee_outdated = True
        normal_line = order.order_line.filtered(lambda l: not l.is_delivery)[:1]
        order.write({
            "order_line": [
                (1, normal_line.id, {"product_uom_qty": 3}),
            ],
        })
        self.assertTrue(order.fee_outdated)

    def test_resolve_address_payload_unmapped_raises_user_error(self):
        carrier = self.env["delivery.carrier"].create({
            "name": "Carrier Mapping Test",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
        })
        country_vn = self.env.ref("base.vn")
        state_dn = self.env["res.country.state"].create({
            "name": "Da Nang Test State",
            "code": "DNG_TEST",
            "country_id": country_vn.id,
        })
        ward_hc = self.env["res.admin.unit"].create({
            "name": "Hai Chau Test Ward",
            "code": "HC_TEST",
            "state_id": state_dn.id,
        })
        partner = self.env["res.partner"].create({
            "name": "Unmapped Partner",
            "street": "99 Hai Chau St",
            "phone": "0988776655",
            "country_id": country_vn.id,
            "state_id": state_dn.id,
            "ward_id": ward_hc.id,
        })

        shipping_model = self.env["delivery.shipping.order"]
        with self.assertRaises(UserError) as cm:
            shipping_model._resolve_address_payload(carrier, partner, is_sender=False)

        error_message = str(cm.exception)
        self.assertIn("Unmapped Partner", error_message)
        self.assertIn("Da Nang Test State", error_message)
        self.assertIn("Hai Chau Test Ward", error_message)
        self.assertIn("Carrier Mapping Test", error_message)

    def test_sale_order_action_confirm_constraints_ohub(self):
        carrier = self.env["delivery.carrier"].create({
            "name": "Confirm Constraint Carrier",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
        })
        partner = self.env["res.partner"].create({
            "name": "Confirm Partner",
            "street": "100 Confirm Road",
            "phone": "0977112233",
        })
        order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "carrier_id": carrier.id,
            "shipping_payment_type": "1",
            "order_line": [
                (0, 0, {
                    "product_id": self.product_1.id,
                    "product_uom_qty": 2,
                    "price_unit": 60.0,
                }),
            ],
        })

        # Don hang chua chon goi cuoc dich vu phai bi chan
        with self.assertRaises(UserError) as cm_service:
            order.action_confirm()
        self.assertIn("Please select a carrier shipping service before confirming sales order", str(cm_service.exception))

        # Chon goi cuoc dich vu cho don hang
        order.write({
            "delivery_service_id": 501,
            "delivery_service_name": "Standard Delivery",
            "delivery_service_code": "STD_501",
        })

        # Shop tra cuoc nhung chua co dong cuoc van chuyen va chua xac nhan freeship
        with self.assertRaises(UserError) as cm_fee:
            order.action_confirm()
        self.assertIn("is configured with 'Sender / Shop Pays' shipping payment policy but has no delivery fee charged", str(cm_fee.exception))

        # Xac nhan voi co confirm_freeship thanh cong
        order.with_context(confirm_freeship=True).action_confirm()
        self.assertIn(order.state, ("sale", "done"))

    def test_cancel_shipment_invalid_status_blocked(self):
        carrier = self.env["delivery.carrier"].create({
            "name": "Cancel Test Carrier",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
        })
        picking_type = self.env["stock.picking.type"].search([("code", "=", "outgoing")], limit=1)
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": picking_type.default_location_src_id.id,
            "location_dest_id": self.env.ref("stock.stock_location_customers").id,
            "carrier_id": carrier.id,
        })
        shipping_order = self.env["delivery.shipping.order"].create({
            "name": "SHIP/CANCEL/001",
            "client_order_code": "CLI-CANCEL-001",
            "order_code": "TRACK-CANCEL-001",
            "picking_id": picking.id,
            "carrier_id": carrier.id,
            "internal_state": "in_transit",
            "carrier_status": "delivering",
            "weight": 500,
            "length": 10,
            "width": 10,
            "height": 10,
        })

        with self.assertRaises(UserError) as cm_carrier:
            carrier.ohub_cancel_shipment(picking)
        self.assertIn("A shipping order can only be cancelled while in 'Ready to Pick' or 'Draft' status.", str(cm_carrier.exception))

        with self.assertRaises(UserError) as cm_so:
            shipping_order.action_cancel_order()
        self.assertIn("A shipping order can only be cancelled while in 'Ready to Pick' or 'Draft' status.", str(cm_so.exception))

    def test_cancel_shipment_carrier_rejection_and_acceptance(self):
        carrier = self.env["delivery.carrier"].create({
            "name": "Cancel Carrier Mock",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
        })
        picking_type = self.env["stock.picking.type"].search([("code", "=", "outgoing")], limit=1)
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": picking_type.default_location_src_id.id,
            "location_dest_id": self.env.ref("stock.stock_location_customers").id,
            "carrier_id": carrier.id,
        })
        shipping_order = self.env["delivery.shipping.order"].create({
            "name": "SHIP/CANCEL/002",
            "client_order_code": "CLI-CANCEL-002",
            "order_code": "TRACK-CANCEL-002",
            "picking_id": picking.id,
            "carrier_id": carrier.id,
            "internal_state": "ready",
            "carrier_status": "ready_to_pick",
            "weight": 500,
            "length": 10,
            "width": 10,
            "height": 10,
        })

        rejection_response = {
            "payload": {
                "success": False,
                "carrier_status": "ready_to_pick",
                "message": "Shipper is currently at the warehouse, cancellation rejected.",
            }
        }
        self.patch(type(carrier), "execute_ohub_operation", lambda *args, **kwargs: rejection_response)

        with self.assertRaises(UserError) as cm_reject:
            carrier.ohub_cancel_shipment(picking)
        self.assertIn("Shipper is currently at the warehouse, cancellation rejected.", str(cm_reject.exception))
        self.assertEqual(shipping_order.carrier_status, "ready_to_pick")
        self.assertEqual(shipping_order.internal_state, "ready")

        with self.assertRaises(UserError) as cm_reject_so:
            shipping_order.action_cancel_order()
        self.assertIn("Shipper is currently at the warehouse, cancellation rejected.", str(cm_reject_so.exception))
        self.assertEqual(shipping_order.carrier_status, "ready_to_pick")
        self.assertEqual(shipping_order.internal_state, "ready")

        acceptance_response = {
            "payload": {
                "success": True,
                "carrier_status": "cancel",
                "message": "Shipment cancellation accepted successfully.",
            }
        }
        self.patch(type(carrier), "execute_ohub_operation", lambda *args, **kwargs: acceptance_response)

        res_cancel = carrier.ohub_cancel_shipment(picking)
        self.assertTrue(res_cancel)
        self.assertEqual(shipping_order.carrier_status, "cancel")
        self.assertEqual(shipping_order.internal_state, "cancelled")

    def test_redelivery_and_return_invalid_status_blocked(self):
        carrier = self.env["delivery.carrier"].create({
            "name": "Redeliver Return Carrier",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
        })
        shipping_order = self.env["delivery.shipping.order"].create({
            "name": "SHIP/REDELIVER/001",
            "client_order_code": "CLI-REDELIVER-001",
            "order_code": "TRACK-REDELIVER-001",
            "carrier_id": carrier.id,
            "internal_state": "ready",
            "carrier_status": "ready_to_pick",
            "weight": 500,
            "length": 10,
            "width": 10,
            "height": 10,
        })

        with self.assertRaises(UserError) as cm_redeliver_ready:
            shipping_order.action_delivery_again()
        self.assertIn("Redelivery can only be requested when the shipping order is in delivery failure or issue status.", str(cm_redeliver_ready.exception))

        with self.assertRaises(UserError) as cm_return_ready:
            shipping_order.action_request_return()
        self.assertIn("Return can only be requested when delivery has failed or the shipment has an issue.", str(cm_return_ready.exception))

        shipping_order.write({
            "carrier_status": "delivered",
            "internal_state": "delivered",
        })

        with self.assertRaises(UserError) as cm_redeliver_delivered:
            shipping_order.action_delivery_again()
        self.assertIn("Redelivery can only be requested when the shipping order is in delivery failure or issue status.", str(cm_redeliver_delivered.exception))

        with self.assertRaises(UserError) as cm_return_delivered:
            shipping_order.action_request_return()
        self.assertIn("Return can only be requested when delivery has failed or the shipment has an issue.", str(cm_return_delivered.exception))

    def test_redelivery_and_return_carrier_response(self):
        carrier = self.env["delivery.carrier"].create({
            "name": "Redelivery Operations Carrier",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
        })
        shipping_order = self.env["delivery.shipping.order"].create({
            "name": "SHIP/RETURN/001",
            "client_order_code": "CLI-RETURN-001",
            "order_code": "TRACK-RETURN-001",
            "carrier_id": carrier.id,
            "internal_state": "issue",
            "carrier_status": "delivery_fail",
            "weight": 500,
            "length": 10,
            "width": 10,
            "height": 10,
        })

        rejection_response = {
            "payload": {
                "success": False,
                "message": "Carrier cannot schedule redelivery after 3 attempts.",
            }
        }
        self.patch(type(carrier), "execute_ohub_operation", lambda *args, **kwargs: rejection_response)

        with self.assertRaises(UserError) as cm_redeliver_reject:
            shipping_order.action_delivery_again()
        self.assertIn("Carrier cannot schedule redelivery after 3 attempts.", str(cm_redeliver_reject.exception))

        return_reject_response = {
            "payload": {
                "success": False,
                "message": "Return request rejected due to carrier depot policy.",
            }
        }
        self.patch(type(carrier), "execute_ohub_operation", lambda *args, **kwargs: return_reject_response)

        with self.assertRaises(UserError) as cm_return_reject:
            shipping_order.action_request_return()
        self.assertIn("Return request rejected due to carrier depot policy.", str(cm_return_reject.exception))
        self.assertEqual(shipping_order.carrier_status, "delivery_fail")
        self.assertEqual(shipping_order.internal_state, "issue")

        return_success_response = {
            "payload": {
                "success": True,
                "message": "Return order registered.",
            }
        }
        self.patch(type(carrier), "execute_ohub_operation", lambda *args, **kwargs: return_success_response)

        shipping_order.action_request_return()
        self.assertEqual(shipping_order.carrier_status, "return")
        self.assertEqual(shipping_order.internal_state, "returning")

    def test_auto_create_shipping_order_network_failure_resilience(self):
        carrier = self.env["delivery.carrier"].create({
            "name": "Resilient Auto Validate Carrier",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
            "auto_create_shipping_on_validate": True,
        })
        partner = self.env["res.partner"].create({
            "name": "Resilient Customer",
            "street": "123 Resilient Rd",
            "phone": "0987654321",
        })
        order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "carrier_id": carrier.id,
            "delivery_service_id": 100,
            "delivery_service_name": "Standard Delivery",
            "delivery_service_code": "STD",
            "shipping_payment_type": "1",
            "order_line": [
                (0, 0, {
                    "product_id": self.product_1.id,
                    "product_uom_qty": 2,
                    "price_unit": 60.0,
                    "tax_id": [(5, 0, 0)],
                }),
                (0, 0, {
                    "product_id": self.product_1.id,
                    "is_delivery": True,
                    "product_uom_qty": 1,
                    "price_unit": 15.0,
                    "tax_id": [(5, 0, 0)],
                }),
            ],
        })
        order.action_confirm()

        picking = order.picking_ids[:1]
        self.assertTrue(picking)
        self.assertEqual(picking.carrier_id, carrier)

        # Dat so luong thuc xuat cho cac dong dich chuyen kho
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True

        def mock_send_network_failure(shipping_self):
            raise UserError("Carrier API gateway connection timeout: 504 Gateway Timeout")

        self.patch(type(self.env["delivery.shipping.order"]), "action_send_to_carrier", mock_send_network_failure)

        # Xac nhan xuat kho khong bi crash boi loi mang tu phia hang
        validation_res = picking.button_validate()
        self.assertEqual(picking.state, "done")

        # Don van chuyen phai duoc tao trong database voi ma client_order_code on dinh de tranh don ma
        shipping_orders = picking.shipping_order_ids
        self.assertEqual(len(shipping_orders), 1)
        created_shipping = shipping_orders[0]
        self.assertTrue(created_shipping.client_order_code)
        self.assertFalse(created_shipping.order_code)

        # Kiem tra nhat ky chatter tren picking va shipping order
        picking_messages = picking.message_ids.mapped("body")
        self.assertTrue(any("504 Gateway Timeout" in msg for msg in picking_messages))

        shipping_messages = created_shipping.message_ids.mapped("body")
        self.assertTrue(any("504 Gateway Timeout" in msg for msg in shipping_messages))

    def test_multi_company_shipping_order_isolation(self):
        company_a = self.env["res.company"].create({"name": "Company A Isolation"})
        company_b = self.env["res.company"].create({"name": "Company B Isolation"})

        user_company_a = self.env["res.users"].create({
            "name": "User Company A",
            "login": "user_company_a_test",
            "email": "user_company_a@example.com",
            "company_id": company_a.id,
            "company_ids": [(6, 0, [company_a.id])],
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
        })

        carrier_a = self.env["delivery.carrier"].create({
            "name": "Carrier Comp A",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
            "company_id": company_a.id,
        })
        carrier_b = self.env["delivery.carrier"].create({
            "name": "Carrier Comp B",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
            "company_id": company_b.id,
        })

        order_model = self.env["delivery.shipping.order"]
        order_a = order_model.create({
            "name": "SHIP/COMP_A/001",
            "client_order_code": "CLI-COMP-A-001",
            "carrier_id": carrier_a.id,
            "company_id": company_a.id,
        })
        order_b = order_model.create({
            "name": "SHIP/COMP_B/001",
            "client_order_code": "CLI-COMP-B-001",
            "carrier_id": carrier_b.id,
            "company_id": company_b.id,
        })

        log_model = self.env["delivery.shipping.order.log"]
        log_a = log_model.create({
            "shipping_order_id": order_a.id,
            "carrier_status": "ready_to_pick",
            "event_time": "2026-11-19 10:00:00",
            "event_uid": "LOG_COMP_A_001",
        })
        log_b = log_model.create({
            "shipping_order_id": order_b.id,
            "carrier_status": "ready_to_pick",
            "event_time": "2026-11-19 10:00:00",
            "event_uid": "LOG_COMP_B_001",
        })

        self.assertEqual(log_a.company_id, company_a)
        self.assertEqual(log_b.company_id, company_b)

        orders_seen_by_a = order_model.with_user(user_company_a).search([
            ("id", "in", (order_a.id, order_b.id))
        ])
        self.assertIn(order_a, orders_seen_by_a)
        self.assertNotIn(order_b, orders_seen_by_a)

        with self.assertRaises(AccessError):
            order_b.with_user(user_company_a).check_access_rule("read")

        logs_seen_by_a = log_model.with_user(user_company_a).search([
            ("id", "in", (log_a.id, log_b.id))
        ])
        self.assertIn(log_a, logs_seen_by_a)
        self.assertNotIn(log_b, logs_seen_by_a)

        with self.assertRaises(AccessError):
            log_b.with_user(user_company_a).check_access_rule("read")

        carrier_shared = self.env["delivery.carrier"].create({
            "name": "Carrier Shared Test",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
            "company_id": False,
        })
        picking_type = self.env["stock.picking.type"].search([("code", "=", "outgoing")], limit=1)
        test_picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": picking_type.default_location_src_id.id,
            "location_dest_id": self.env.ref("stock.stock_location_customers").id,
            "carrier_id": carrier_shared.id,
        })
        prep_picking_vals = order_model._prepare_shipping_data_from_picking(test_picking, carrier=carrier_shared)
        self.assertEqual(prep_picking_vals.get("company_id"), test_picking.company_id.id)

        test_partner = self.env["res.partner"].create({
            "name": "Company Partner",
        })
        test_so = self.env["sale.order"].create({
            "partner_id": test_partner.id,
            "carrier_id": carrier_shared.id,
        })
        prep_so_vals = order_model._prepare_shipping_data_from_sale_order(test_so, carrier=carrier_shared)
        self.assertEqual(prep_so_vals.get("company_id"), test_so.company_id.id)

    def test_address_mapping_carrier_and_admin_unit_views(self):
        carrier = self.env["delivery.carrier"].create({
            "name": "Mapping Carrier Test",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
        })
        state = self.env["res.country.state"].search([("country_id.code", "=", "VN")], limit=1)
        ward = self.env["res.admin.unit"].create({
            "name": "Phuong Test Mapping",
            "code": "TEST_WARD_MAP_001",
            "level": "3",
            "state_id": state.id,
        })

        self.assertEqual(carrier.address_mapping_count, 0)
        self.assertEqual(ward.mapping_count, 0)

        mapping = self.env["delivery.address.mapping"].create({
            "carrier_id": carrier.id,
            "state_id": state.id,
            "oris_ward_id": ward.id,
            "external_ward_code": "EXT_CODE_123",
            "external_ward_name": "Phuong Ngoai",
            "state": "matched",
        })

        carrier._compute_address_mapping_count()
        ward._compute_mapping_count()
        self.assertEqual(carrier.address_mapping_count, 1)
        self.assertIn(mapping, carrier.address_mapping_ids)
        self.assertEqual(ward.mapping_count, 1)
        self.assertIn(mapping, ward.mapping_ids)

        carrier_action = carrier.action_view_address_mappings()
        self.assertEqual(carrier_action["res_model"], "delivery.address.mapping")
        self.assertEqual(carrier_action["domain"], [("carrier_id", "=", carrier.id)])
        self.assertEqual(carrier_action["context"]["default_carrier_id"], carrier.id)

        ward_action = ward.action_view_address_mappings()
        self.assertEqual(ward_action["res_model"], "delivery.address.mapping")
        self.assertEqual(ward_action["domain"], [("oris_ward_id", "=", ward.id)])
        self.assertEqual(ward_action["context"]["default_oris_ward_id"], ward.id)
        self.assertEqual(ward_action["context"]["default_state_id"], state.id)

    def test_resolve_carrier_address_prevents_cross_carrier_fallback(self):
        state = self.env["res.country.state"].search([("country_id.code", "=", "VN")], limit=1)
        ward = self.env["res.admin.unit"].create({
            "name": "Phuong Cross Carrier Test",
            "code": "TEST_CROSS_CARRIER_WARD",
            "level": "3",
            "state_id": state.id,
        })
        flow_ghn = self.env["hub.flow"].create({"name": "GHN Flow"})
        flow_ahamove = self.env["hub.flow"].create({"name": "Ahamove Flow"})

        carrier_ghn = self.env["delivery.carrier"].create({
            "name": "GHN Carrier",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
            "hub_flow_id": flow_ghn.id,
        })
        carrier_ahamove = self.env["delivery.carrier"].create({
            "name": "Ahamove Carrier",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
            "hub_flow_id": flow_ahamove.id,
        })

        ghn_mapping = self.env["delivery.address.mapping"].create({
            "carrier_id": carrier_ghn.id,
            "hub_flow_id": flow_ghn.id,
            "state_id": state.id,
            "oris_ward_id": ward.id,
            "external_province_id": 201,
            "external_district_id": 1442,
            "external_district_name": "Quan 1",
            "external_ward_code": "20101",
            "external_ward_name": "Phuong Ben Nghe",
            "state": "matched",
        })

        resolved_ghn = self.env["delivery.address.mapping"].resolve_carrier_address(
            carrier_ghn, state=state, ward=ward
        )
        self.assertEqual(resolved_ghn.id, ghn_mapping.id)
        self.assertEqual(resolved_ghn.external_district_name, "Quan 1")

        with self.assertRaises(UserError) as cm:
            self.env["delivery.address.mapping"].resolve_carrier_address(
                carrier_ahamove, state=state, ward=ward
            )
        self.assertIn("has not been mapped", str(cm.exception))

        ahamove_mapping = self.env["delivery.address.mapping"].create({
            "carrier_id": carrier_ahamove.id,
            "hub_flow_id": flow_ahamove.id,
            "state_id": state.id,
            "oris_ward_id": ward.id,
            "external_district_name": "SGN",
            "external_ward_code": "SGN_WARD_01",
            "external_ward_name": "Ben Nghe Ahamove",
            "state": "matched",
        })
        resolved_ahamove = self.env["delivery.address.mapping"].resolve_carrier_address(
            carrier_ahamove, state=state, ward=ward
        )
        self.assertEqual(resolved_ahamove.id, ahamove_mapping.id)
        self.assertEqual(resolved_ahamove.external_district_name, "SGN")

    def test_ohub_fetch_available_services_excludes_invalid_and_normalizes_types(self):
        carrier = self.env["delivery.carrier"].create({
            "name": "Service Normalization Carrier",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
        })
        request = self.env["hub.request"].search([], limit=1)
        if not request:
            flow = self.env["hub.flow"].create({"name": "Test Flow", "code": "TEST_FLOW"})
            request = self.env["hub.request"].create({
                "flow_id": flow.id,
                "name": "Test Request",
                "code": "TEST_REQ",
                "url": "https://api.example.com",
            })
        op = self.env["delivery.ohub.operation"].create({
            "name": "Op Available Services",
            "carrier_id": carrier.id,
            "request_id": request.id,
            "operation_type": "available_services",
            "execution_mode": "sync",
        })
        wizard = self.env["choose.delivery.carrier"].create({
            "carrier_id": carrier.id,
            "payment_type_id": "1",
        })

        mock_payload_services = {
            "services": [
                {
                    "service_id": 1,
                    "service_code": "SGN-BIKE",
                    "service_name": "Giao Hoa Toc",
                    "service_type": "express",
                    "total_fee": 30000.0,
                    "service_fee": 30000.0,
                },
                {
                    "service_id": 99,
                    "service_code": "99",
                    "service_name": "Tiet Kiem Eco",
                    "service_type": "economy",
                    "total_fee": 18000.0,
                    "service_fee": 18000.0,
                },
            ]
        }

        self.patch(type(carrier), "execute_ohub_operation", lambda *args, **kwargs: {"payload": mock_payload_services})
        quotes = carrier.ohub_fetch_available_services(wizard)

        self.assertEqual(len(quotes), 2)
        quote_express = quotes.filtered(lambda q: q.service_code == "SGN-BIKE")
        self.assertTrue(quote_express)
        self.assertEqual(quote_express.service_name, "Giao Hoa Toc")
        self.assertEqual(quote_express.service_type, "express")

        quote_eco = quotes.filtered(lambda q: q.service_code == "99")
        self.assertTrue(quote_eco)
        self.assertEqual(quote_eco.service_name, "Tiet Kiem Eco")
        self.assertEqual(quote_eco.service_type, "economy")

        mock_payload_missing_services = {
            "invalid_key": []
        }

        self.patch(type(carrier), "execute_ohub_operation", lambda *args, **kwargs: {"payload": mock_payload_missing_services})
        with self.assertRaises(UserError) as cm:
            carrier.ohub_fetch_available_services(wizard)
        self.assertIn("must contain a 'services' list", str(cm.exception))

    def test_standard_contract_validation_error(self):
        shipping_model = self.env["delivery.shipping.order"]
        with self.assertRaises(UserError) as cm_not_dict:
            shipping_model._validate_contract_payload(["invalid_list"], ["order_code"], "test_op")
        self.assertIn("must be a JSON object", str(cm_not_dict.exception))

        with self.assertRaises(UserError) as cm_missing:
            shipping_model._validate_contract_payload({"fee": 1000}, ["order_code", "total_fee"], "test_op")
        self.assertIn("missing required contract field(s)", str(cm_missing.exception))
        self.assertIn("order_code", str(cm_missing.exception))

    def test_rate_shipment_standard_contract(self):
        carrier = self.env["delivery.carrier"].create({
            "name": "Standard Rate Carrier",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
        })
        country_vn = self.env.ref("base.vn")
        state_dn = self.env["res.country.state"].search([("country_id", "=", country_vn.id)], limit=1)
        ward_hc = self.env["res.admin.unit"].create({
            "name": "Hai Chau Standard Ward",
            "code": "HC_STD_001",
            "state_id": state_dn.id,
        })
        self.env["delivery.address.mapping"].create({
            "carrier_id": carrier.id,
            "state_id": state_dn.id,
            "oris_ward_id": ward_hc.id,
            "state": "matched",
            "external_province_id": 201,
            "external_district_name": "Hai Chau",
            "external_ward_code": "001",
        })
        partner = self.env["res.partner"].create({
            "name": "Standard Rate Customer",
            "street": "100 Nguyen Van Linh",
            "phone": "0911223344",
            "country_id": country_vn.id,
            "state_id": state_dn.id,
            "ward_id": ward_hc.id,
        })
        order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "partner_shipping_id": partner.id,
            "carrier_id": carrier.id,
            "order_line": [
                (0, 0, {
                    "product_id": self.product_1.id,
                    "product_uom_qty": 1,
                    "price_unit": 50.0,
                }),
            ],
        })

        mock_rate_payload = {
            "total_fee": 25000.0,
            "service_fee": 25000.0,
            "insurance_fee": 0.0,
            "cod_fee": 0.0,
        }
        self.patch(type(carrier), "execute_ohub_operation", lambda *args, **kwargs: {"payload": mock_rate_payload})
        res = carrier.ohub_rate_shipment(order)
        self.assertTrue(res["success"])
        self.assertEqual(res["price"], 25000.0)

    def test_sync_order_info_standard_contract(self):
        carrier = self.env["delivery.carrier"].create({
            "name": "Standard Sync Carrier",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
        })
        shipping_order = self.env["delivery.shipping.order"].create({
            "name": "SHIP/SYNC/001",
            "client_order_code": "CLI-SYNC-001",
            "order_code": "TRACK-SYNC-001",
            "carrier_id": carrier.id,
            "internal_state": "ready",
            "carrier_status": "ready_to_pick",
        })

        mock_info_payload = {
            "order_code": "TRACK-SYNC-001",
            "carrier_status": "delivering",
            "internal_state": "in_transit",
            "converted_weight": 550,
            "current_warehouse": "Buu cuc Cau Giay",
            "timeline": [
                {
                    "time": "2026-11-21 08:30:00",
                    "status": "delivering",
                    "description": "Dang giao hang",
                    "station": "Buu cuc Cau Giay",
                }
            ],
        }
        self.patch(type(carrier), "execute_ohub_operation", lambda *args, **kwargs: {"payload": mock_info_payload})
        shipping_order.action_sync_order_info()

        self.assertEqual(shipping_order.carrier_status, "delivering")
        self.assertEqual(shipping_order.internal_state, "in_transit")
        self.assertEqual(shipping_order.converted_weight, 550)
        logs = self.env["delivery.shipping.order.log"].search([("shipping_order_id", "=", shipping_order.id)])
        self.assertTrue(logs)
        self.assertEqual(logs[0].warehouse, "Buu cuc Cau Giay")

    def test_print_label_standard_contract(self):
        carrier = self.env["delivery.carrier"].create({
            "name": "Standard Print Carrier",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
        })
        shipping_order = self.env["delivery.shipping.order"].create({
            "name": "SHIP/PRINT/001",
            "client_order_code": "CLI-PRINT-001",
            "order_code": "TRACK-PRINT-001",
            "carrier_id": carrier.id,
            "internal_state": "ready",
            "carrier_status": "ready_to_pick",
        })

        mock_print_payload = {
            "url": "https://example.com/shipping_labels/track001.pdf",
        }
        self.patch(type(carrier), "execute_ohub_operation", lambda *args, **kwargs: {"payload": mock_print_payload})
        action = shipping_order.action_print_label()
        self.assertEqual(action.get("type"), "ir.actions.act_url")
        self.assertEqual(action.get("url"), "https://example.com/shipping_labels/track001.pdf")

    def test_process_carrier_webhook_standard_contract(self):
        carrier = self.env["delivery.carrier"].create({
            "name": "Standard Webhook Carrier",
            "delivery_type": "ohub",
            "product_id": self.product_1.id,
        })
        shipping_order = self.env["delivery.shipping.order"].create({
            "name": "SHIP/WH/001",
            "client_order_code": "CLI-WH-001",
            "order_code": "TRACK-WH-001",
            "carrier_id": carrier.id,
            "internal_state": "ready",
            "carrier_status": "ready_to_pick",
        })

        webhook_payload = {
            "order_code": "TRACK-WH-001",
            "status": "delivered",
            "action_time": "2026-11-21T10:00:00",
            "warehouse": "Kho Cau Giay 02",
            "reason": "Giao thanh cong",
            "converted_weight": 600,
            "total_fee": 32000.0,
        }
        res = self.env["delivery.shipping.order"].process_carrier_webhook(webhook_payload)
        self.assertEqual(res.get("code"), 200)
        self.assertEqual(shipping_order.carrier_status, "delivered")
        self.assertEqual(shipping_order.internal_state, "delivered")
        self.assertEqual(shipping_order.converted_weight, 600)
        self.assertEqual(shipping_order.actual_total_fee, 32000.0)
