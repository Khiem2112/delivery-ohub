import json

from odoo import fields, models


class DeliveryOHubOperation(models.Model):
    _name = "delivery.ohub.operation"
    _description = "oHUB Delivery Integration Operation"
    _order = "sequence, id"

    carrier_id = fields.Many2one(
        comodel_name="delivery.carrier",
        string="Delivery Method",
        required=True,
        ondelete="cascade",
        index=True,
    )
    hub_flow_id = fields.Many2one(
        comodel_name="hub.flow",
        related="carrier_id.hub_flow_id",
        string="oHUB Integration Flow",
        store=True,
        readonly=True,
    )
    name = fields.Char(string="Operation Name", required=True)
    operation_type = fields.Selection(
        selection=[
            ("rate_shipment", "Calculate Fee"),
            ("available_services", "Available Services"),
            ("create_shipment", "Create Shipping Order"),
            ("cancel_shipment", "Cancel Shipping Order"),
            ("get_order_info", "Get Order Details"),
            ("preview_order", "Validate / Preview Order"),
            ("tracking", "Sync Tracking"),
            ("print_label", "Print Label"),
            ("update_cod", "Update COD Amount"),
            ("storing_again", "Redeliver Order"),
            ("return_order", "Return Order"),
            ("custom", "Custom Operation"),
        ],
        string="Operation Type",
        required=True,
        index=True,
    )
    request_id = fields.Many2one(
        comodel_name="hub.request",
        string="Hub Request (hub.request)",
        domain="[('flow_id', '=', hub_flow_id)]",
        required=True,
        ondelete="restrict",
    )
    execution_mode = fields.Selection(
        selection=[
            ("sync", "Synchronous"),
            ("queue", "Background Queue (queue_job)"),
        ],
        string="Execution Mode",
        default="sync",
        required=True,
    )
    sequence = fields.Integer(string="Sequence", default=10)
    active = fields.Boolean(string="Active", default=True)
    show_on_sale_order = fields.Boolean(
        string="Show Button on Sales Order", default=True
    )
    button_style = fields.Selection(
        selection=[
            ("primary", "Primary"),
            ("secondary", "Secondary"),
            ("warning", "Warning"),
            ("danger", "Danger"),
        ],
        string="Button Style",
        default="secondary",
    )

    def execute(self, record=None, extra_env=None):
        self.ensure_one()
        carrier = self.carrier_id
        environments = {
            "carrier_id": carrier.id,
            "flow_id": self.hub_flow_id.id if self.hub_flow_id else False,
            "__force_sync": self.execution_mode == "sync",
        }

        if record:
            if hasattr(record, "with_context"):
                record = record.with_context(default_carrier_id=carrier.id)
            environments["record_id"] = (
                record.id if isinstance(record.id, int) else False
            )
            environments["model_name"] = record._name
            environments["record"] = record

        if extra_env:
            environments.update(extra_env)

        run_result = self.request_id.run_request(environments)
        result_payload = None
        if isinstance(run_result, dict):
            if run_result.get("inbound_data") not in (None, False, {}, []):
                result_payload = run_result["inbound_data"]
            else:
                key = f"RESULT_{self.request_id.code}"
                result_payload = run_result.get(key)

        if isinstance(result_payload, str):
            try:
                result_payload = json.loads(result_payload)
            except Exception:
                pass

        return {
            "operation": self,
            "request": self.request_id,
            "raw_run_result": run_result,
            "payload": result_payload,
        }
