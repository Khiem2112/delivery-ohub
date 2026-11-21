from odoo import fields, models


class DeliveryShippingOrderLog(models.Model):
    _name = 'delivery.shipping.order.log'
    _description = 'Shipping Order Event Log'
    _order = 'event_time desc, id desc'

    shipping_order_id = fields.Many2one(
        comodel_name='delivery.shipping.order',
        string='Shipping Order',
        required=True,
        ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        related="shipping_order_id.company_id",
        store=True,
        index=True,
    )
    order_code = fields.Char(
        related='shipping_order_id.order_code',
        string='Carrier Order Code',
        store=True,
        index=True,
    )
    carrier_status = fields.Char(string='Carrier Status', required=True, index=True)
    event_type = fields.Char(string='Event Type')
    event_time = fields.Datetime(string='Event Time', required=True, index=True)
    event_uid = fields.Char(string='Event UID', index=True)
    warehouse = fields.Char(string='Processing Hub / Station')
    reason_code = fields.Char(string='Reason Code')
    reason = fields.Text(string='Detailed Reason')
    description = fields.Text(string='Event Description')
    total_fee = fields.Monetary(string='Total Fee')
    cod_amount = fields.Monetary(string='COD Amount')
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
    )
    raw_payload = fields.Text(string='Raw Payload (JSON)')
    source = fields.Selection(
        selection=[
            ('webhook', 'Webhook Push'),
            ('manual', 'Manual Sync'),
            ('cron', 'Scheduled Cron'),
            ('create', 'Order Creation'),
        ],
        string='Event Source',
        default='webhook',
        required=True,
    )

    _sql_constraints = [
        (
            'unique_shipping_event_uid',
            'unique(shipping_order_id, event_uid)',
            'Each shipping event UID must be unique per shipping order.',
        ),
    ]
