# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Delivery via ORIS Hub',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Delivery',
    'summary': 'Multi-carrier delivery integration via ORIS Hub',
    'description': """
Multi-carrier Delivery Integration via ORIS Hub
===================================================
Features:
- 2-level administrative unit management (Province/City, Ward/Commune).
- Flexible mapping between internal administrative units and carrier codes (GHN, GHTK, etc.).
- Dynamic integration operation mapping to hub.request.
- Real-time rate quotes, estimated delivery dates, and pre-booking validation.
- Independent shipping order lifecycle management (supporting sale.order and expandable to pos.order).
- Webhook support for real-time status updates.
""",
    'depends': [
        'delivery',
        'stock_delivery',
        'oris_hub',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/delivery_ohub_security.xml',
        'data/delivery_ohub_data.xml',
        'views/res_admin_unit_views.xml',
        'views/res_partner_views.xml',
        'views/product_template_views.xml',
        'views/delivery_carrier_views.xml',
        'views/delivery_ohub_operation_views.xml',
        'views/delivery_address_mapping_views.xml',
        'views/delivery_shipping_order_views.xml',
        'views/sale_order_views.xml',
        'views/stock_picking_views.xml',
        'views/menus.xml',
        'wizard/choose_delivery_carrier_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
