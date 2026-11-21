import argparse
import sys
import psycopg2


def get_mapping_86_code():
    return (
        "city_id = getattr(record, 'to_district_name', False)\n"
        "if not city_id:\n"
        "    raise UserError(_('Chua xac dinh duoc ma khu vuc van chuyen (city_id) tu dia chi giao hang. "
        "Vui long kiem tra Anh xa dia chi.'))\n\n"
        "quote = False\n"
        "if hasattr(record, 'fee_quote_ids') and record.fee_quote_ids:\n"
        "    quote = record.fee_quote_ids.filtered(lambda q: q.is_selected)[:1]\n\n"
        "service_code = ''\n"
        "if quote and getattr(quote, 'service_code', False):\n"
        "    service_code = quote.service_code\n"
        "elif getattr(record, 'service_code', False):\n"
        "    service_code = record.service_code\n"
        "elif shared.get('service_code'):\n"
        "    service_code = shared.get('service_code')\n"
        "elif shared.get('service_id'):\n"
        "    service_code = shared.get('service_id')\n\n"
        "if not service_code or service_code == 'standard':\n"
        "    stype = (quote.service_type if quote and getattr(quote, 'service_type', False) else False) or "
        "getattr(record, 'service_type', False) or getattr(record, 'delivery_service_type', False) or value or "
        "shared.get('service_type') or 'standard'\n"
        "    mapping = {\n"
        "        'express': f'{city_id}-BIKE',\n"
        "        'economy': f'{city_id}-ECO',\n"
        "        'standard': f'{city_id}-BIKE',\n"
        "    }\n"
        "    service_code = mapping.get(stype) or f'{city_id}-BIKE'\n\n"
        "result = [{'_id': service_code, 'requests': []}] if service_code else []\n"
    )


def get_mapping_87_code():
    return (
        "city_id = getattr(record, 'to_district_name', False)\n"
        "if not city_id:\n"
        "    raise UserError(_('Chua xac dinh duoc ma khu vuc van chuyen (city_id) tu dia chi giao hang. "
        "Vui long kiem tra Anh xa dia chi.'))\n\n"
        "quote = False\n"
        "if hasattr(record, 'fee_quote_ids') and record.fee_quote_ids:\n"
        "    quote = record.fee_quote_ids.filtered(lambda q: q.is_selected)[:1]\n\n"
        "service_code = ''\n"
        "if quote and getattr(quote, 'service_code', False):\n"
        "    service_code = quote.service_code\n"
        "elif getattr(record, 'service_code', False):\n"
        "    service_code = record.service_code\n"
        "elif shared.get('service_code'):\n"
        "    service_code = shared.get('service_code')\n"
        "elif shared.get('service_id'):\n"
        "    service_code = shared.get('service_id')\n\n"
        "if not service_code or service_code == 'standard':\n"
        "    stype = (quote.service_type if quote and getattr(quote, 'service_type', False) else False) or "
        "getattr(record, 'service_type', False) or getattr(record, 'delivery_service_type', False) or value or "
        "shared.get('service_type') or 'standard'\n"
        "    mapping = {\n"
        "        'express': f'{city_id}-BIKE',\n"
        "        'economy': f'{city_id}-ECO',\n"
        "        'standard': f'{city_id}-BIKE',\n"
        "    }\n"
        "    service_code = mapping.get(stype) or f'{city_id}-BIKE'\n\n"
        "result = service_code if service_code else None\n"
    )


def get_script_15_code():
    return (
        "body = shared.get('BODY') or {}\n"
        "carrier = record.carrier_id if hasattr(record, 'carrier_id') else False\n"
        "sender_partner = carrier.sender_partner_id if carrier and carrier.sender_partner_id else False\n"
        "dest_partner = record.partner_id if hasattr(record, 'partner_id') and record.partner_id else False\n\n"
        "from_name = getattr(record, 'from_name', False) or (sender_partner.name if sender_partner else False) or 'Kho Hang'\n"
        "from_phone = getattr(record, 'from_phone', False) or (carrier.sender_phone if carrier and carrier.sender_phone else (sender_partner.phone or sender_partner.mobile if sender_partner else False))\n"
        "from_addr = getattr(record, 'from_address', False) or (carrier.sender_address if carrier and carrier.sender_address else False)\n"
        "if not from_addr and sender_partner:\n"
        "    addr_parts = [p for p in [sender_partner.street, sender_partner.street2, sender_partner.city, sender_partner.state_id.name if sender_partner.state_id else False] if p]\n"
        "    from_addr = ', '.join(addr_parts)\n"
        "if not from_addr or not from_phone:\n"
        "    raise UserError(_('Vui long cau hinh day du dia chi va so dien thoai kho gui hang.'))\n\n"
        "to_name = getattr(record, 'to_name', False) or (dest_partner.name if dest_partner else False) or 'Khach Hang'\n"
        "to_phone = getattr(record, 'to_phone', False) or (dest_partner.phone or dest_partner.mobile if dest_partner else False)\n"
        "to_addr = getattr(record, 'to_address', False) or False\n"
        "if not to_addr and dest_partner:\n"
        "    addr_parts = [p for p in [dest_partner.street, dest_partner.street2, dest_partner.city, dest_partner.state_id.name if dest_partner.state_id else False] if p]\n"
        "    to_addr = ', '.join(addr_parts)\n"
        "if not to_addr or not to_phone:\n"
        "    raise UserError(_('Vui long nhap day du dia chi va so dien thoai nguoi nhan hang.'))\n\n"
        "cod = int(round(float(getattr(record, 'cod_amount', 0.0) or 0.0)))\n"
        "item_val = int(round(float(getattr(record, 'insurance_value', 0.0) or getattr(record, 'goods_amount', 0.0) or getattr(record, 'amount_total', 0.0) or 0.0)))\n\n"
        "pickup_point = {\n"
        "    'address': from_addr,\n"
        "    'name': from_name,\n"
        "    'mobile': from_phone,\n"
        "}\n"
        "if sender_partner and sender_partner.partner_latitude and sender_partner.partner_longitude:\n"
        "    pickup_point['lat'] = float(sender_partner.partner_latitude)\n"
        "    pickup_point['lng'] = float(sender_partner.partner_longitude)\n\n"
        "dropoff_point = {\n"
        "    'address': to_addr,\n"
        "    'name': to_name,\n"
        "    'mobile': to_phone,\n"
        "}\n"
        "if dest_partner and dest_partner.partner_latitude and dest_partner.partner_longitude:\n"
        "    dropoff_point['lat'] = float(dest_partner.partner_latitude)\n"
        "    dropoff_point['lng'] = float(dest_partner.partner_longitude)\n\n"
        "if cod > 0:\n"
        "    dropoff_point['cod'] = cod\n"
        "if item_val > 0:\n"
        "    dropoff_point['item_value'] = item_val\n\n"
        "services = body.get('services')\n"
        "if not services:\n"
        "    service_code = getattr(record, 'service_code', False) or shared.get('service_code') or shared.get('service_id')\n"
        "    if service_code and service_code != 'standard':\n"
        "        services = [{'_id': service_code, 'requests': []}]\n\n"
        "body.update({\n"
        "    'order_time': 0,\n"
        "    'path': [pickup_point, dropoff_point],\n"
        "    'payment_method': shared.get('payment_method') or 'BALANCE',\n"
        "})\n"
        "if services:\n"
        "    body['services'] = services\n\n"
        "shared['BODY'] = body\n"
    )


def get_script_17_code():
    return (
        "body = shared.get('BODY') or {}\n"
        "carrier = record.carrier_id if hasattr(record, 'carrier_id') else False\n"
        "sender_partner = carrier.sender_partner_id if carrier and carrier.sender_partner_id else False\n"
        "dest_partner = record.partner_id if hasattr(record, 'partner_id') and record.partner_id else False\n\n"
        "from_name = getattr(record, 'from_name', False) or (sender_partner.name if sender_partner else False) or 'Kho Hang'\n"
        "from_phone = getattr(record, 'from_phone', False) or (carrier.sender_phone if carrier and carrier.sender_phone else (sender_partner.phone or sender_partner.mobile if sender_partner else False))\n"
        "from_addr = getattr(record, 'from_address', False) or (carrier.sender_address if carrier and carrier.sender_address else False)\n"
        "if not from_addr and sender_partner:\n"
        "    addr_parts = [p for p in [sender_partner.street, sender_partner.street2, sender_partner.city, sender_partner.state_id.name if sender_partner.state_id else False] if p]\n"
        "    from_addr = ', '.join(addr_parts)\n"
        "if not from_addr or not from_phone:\n"
        "    raise UserError(_('Vui long cau hinh day du dia chi va so dien thoai kho gui hang.'))\n\n"
        "to_name = getattr(record, 'to_name', False) or (dest_partner.name if dest_partner else False) or 'Khach Hang'\n"
        "to_phone = getattr(record, 'to_phone', False) or (dest_partner.phone or dest_partner.mobile if dest_partner else False)\n"
        "to_addr = getattr(record, 'to_address', False) or False\n"
        "if not to_addr and dest_partner:\n"
        "    addr_parts = [p for p in [dest_partner.street, dest_partner.street2, dest_partner.city, dest_partner.state_id.name if dest_partner.state_id else False] if p]\n"
        "    to_addr = ', '.join(addr_parts)\n"
        "if not to_addr or not to_phone:\n"
        "    raise UserError(_('Vui long nhap day du dia chi va so dien thoai nguoi nhan hang.'))\n\n"
        "cod = int(round(float(getattr(record, 'cod_amount', 0.0) or 0.0)))\n"
        "item_val = int(round(float(getattr(record, 'insurance_value', 0.0) or getattr(record, 'goods_amount', 0.0) or getattr(record, 'amount_total', 0.0) or 0.0)))\n"
        "tracking_no = getattr(record, 'client_order_code', False) or getattr(record, 'name', False) or ''\n"
        "remarks = getattr(record, 'note', False) or getattr(record, 'comment', False) or ''\n\n"
        "pickup_point = {\n"
        "    'address': from_addr,\n"
        "    'name': from_name,\n"
        "    'mobile': from_phone,\n"
        "}\n"
        "if sender_partner and sender_partner.partner_latitude and sender_partner.partner_longitude:\n"
        "    pickup_point['lat'] = float(sender_partner.partner_latitude)\n"
        "    pickup_point['lng'] = float(sender_partner.partner_longitude)\n\n"
        "dropoff_point = {\n"
        "    'address': to_addr,\n"
        "    'name': to_name,\n"
        "    'mobile': to_phone,\n"
        "    'tracking_number': tracking_no,\n"
        "    'remarks': remarks,\n"
        "}\n"
        "if dest_partner and dest_partner.partner_latitude and dest_partner.partner_longitude:\n"
        "    dropoff_point['lat'] = float(dest_partner.partner_latitude)\n"
        "    dropoff_point['lng'] = float(dest_partner.partner_longitude)\n\n"
        "if cod > 0:\n"
        "    dropoff_point['cod'] = cod\n"
        "if item_val > 0:\n"
        "    dropoff_point['item_value'] = item_val\n\n"
        "items = []\n"
        "lines = record.line_ids if hasattr(record, 'line_ids') and record.line_ids else (record.order_line if hasattr(record, 'order_line') and record.order_line else [])\n"
        "for line in lines:\n"
        "    p_name = line.product_id.name if hasattr(line, 'product_id') and line.product_id else (line.name or 'San pham')\n"
        "    p_qty = int(line.product_uom_qty) if hasattr(line, 'product_uom_qty') else (int(line.quantity) if hasattr(line, 'quantity') else 1)\n"
        "    p_price = int(round(float(line.price_unit))) if hasattr(line, 'price_unit') else 0\n"
        "    p_id = str(line.product_id.id) if hasattr(line, 'product_id') and line.product_id else 'ITEM'\n"
        "    items.append({\n"
        "        '_id': p_id,\n"
        "        'name': p_name,\n"
        "        'num': max(1, p_qty),\n"
        "        'price': p_price,\n"
        "    })\n"
        "if not items:\n"
        "    items = [{\n"
        "        '_id': 'ITEM01',\n"
        "        'name': 'Kien hang',\n"
        "        'num': 1,\n"
        "        'price': max(0, item_val),\n"
        "    }]\n\n"
        "service_id = body.get('service_id') or getattr(record, 'service_code', False) or shared.get('service_code') or shared.get('service_id')\n\n"
        "body.update({\n"
        "    'order_time': 0,\n"
        "    'path': [pickup_point, dropoff_point],\n"
        "    'requests': [],\n"
        "    'payment_method': shared.get('payment_method') or 'BALANCE',\n"
        "    'remarks': remarks,\n"
        "    'items': items,\n"
        "})\n"
        "if service_id and service_id != 'standard':\n"
        "    body['service_id'] = service_id\n\n"
        "shared['BODY'] = body\n"
    )


def migrate_requests_16_17(db_host="localhost", db_port=5433, db_user="odoo", db_password="odoo", db_name="odoo"):
    conn = psycopg2.connect(
        host=db_host,
        port=db_port,
        user=db_user,
        password=db_password,
        dbname=db_name,
    )
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE hub_request_mapping
            SET transform_type = 'python',
                transform_code = %s
            WHERE id = 86 OR (request_id = 16 AND phase = 'outbound' AND target_key = 'services')
            """,
            (get_mapping_86_code(),),
        )

        cur.execute(
            """
            UPDATE hub_request_mapping
            SET transform_type = 'python',
                transform_code = %s
            WHERE id = 87 OR (request_id = 17 AND phase = 'outbound' AND target_key = 'service_id')
            """,
            (get_mapping_87_code(),),
        )

        cur.execute(
            """
            UPDATE hub_request_script
            SET code = %s
            WHERE id = 15 OR (request_id = 16 AND event = 'before_prepare')
            """,
            (get_script_15_code(),),
        )

        cur.execute(
            """
            UPDATE hub_request_script
            SET code = %s
            WHERE id = 17 OR (request_id = 17 AND event = 'before_prepare')
            """,
            (get_script_17_code(),),
        )

        conn.commit()
        print("Migration for Requests 16 and 17 completed successfully.")
    except Exception as exc:
        conn.rollback()
        print(f"Migration error: {exc}", file=sys.stderr)
        raise
    finally:
        cur.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Migrate Ahamove Requests 16 and 17 to eliminate fake data")
    parser.add_argument("--host", default="localhost", help="Database host")
    parser.add_argument("--port", type=int, default=5433, help="Database port")
    parser.add_argument("--user", default="odoo", help="Database user")
    parser.add_argument("--password", default="odoo", help="Database password")
    parser.add_argument("--dbname", default="odoo", help="Database name")
    args = parser.parse_args()

    migrate_requests_16_17(
        db_host=args.host,
        db_port=args.port,
        db_user=args.user,
        db_password=args.password,
        db_name=args.dbname,
    )


if __name__ == "__main__":
    main()
