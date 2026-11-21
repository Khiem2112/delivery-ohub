import argparse
import sys
import uuid
import psycopg2


def migrate_request_15(db_host="localhost", db_port=5433, db_user="odoo", db_password="odoo", db_name="odoo"):
    conn = psycopg2.connect(
        host=db_host,
        port=db_port,
        user=db_user,
        password=db_password,
        dbname=db_name,
    )
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, name FROM hub_request WHERE id = 15")
        req = cur.fetchone()
        if not req:
            raise RuntimeError("Request ID 15 not found in database.")

        cur.execute("DELETE FROM hub_request_script WHERE request_id = 15 AND id IN (13, 14)")
        cur.execute(
            "DELETE FROM hub_request_script WHERE request_id = 15 AND event IN ('before_prepare', 'after_response')"
        )

        cur.execute("DELETE FROM hub_request_mapping WHERE request_id = 15")

        outbound_python = (
            "city_id = getattr(record, 'to_district_name', False)\n"
            "if not city_id:\n"
            "    raise UserError(_('Chua xac dinh duoc ma khu vuc van chuyen (city_id) tu dia chi giao hang. "
            "Vui long kiem tra Anh xa dia chi.'))\n"
            "return city_id\n"
        )
        cur.execute(
            """
            INSERT INTO hub_request_mapping (
                hub_uid, name, request_id, sequence, phase, source_type, source_key,
                python_code, transform_type, target_scope, target_key, active
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(uuid.uuid4()),
                "Outbound City ID Mapping",
                15,
                10,
                "outbound",
                "python",
                False,
                outbound_python,
                "none",
                "params",
                "city_id",
                True,
            ),
        )

        inbound_service_type_transform = (
            "code = str(value or '').upper()\n"
            "if 'ECO' in code:\n"
            "    return 'economy'\n"
            "elif any(k in code for k in ('INSTANT', 'BIKE')):\n"
            "    return 'express'\n"
            "return 'standard'\n"
        )

        inbound_mappings = [
            ("Inbound Service Code", 10, "response_data._id", "none", None, "service_code"),
            ("Inbound Service ID", 20, "response_data._id", "none", None, "service_id"),
            ("Inbound Service Name", 30, "response_data.name", "none", None, "service_name"),
            (
                "Inbound Service Type",
                40,
                "response_data._id",
                "python",
                inbound_service_type_transform,
                "service_type",
            ),
        ]

        for name, seq, src_key, trans_type, trans_code, tgt_key in inbound_mappings:
            cur.execute(
                """
                INSERT INTO hub_request_mapping (
                    hub_uid, name, request_id, sequence, phase, source_type, source_key,
                    transform_type, transform_code, target_scope, target_key, active
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(uuid.uuid4()),
                    name,
                    15,
                    seq,
                    "inbound",
                    "path",
                    src_key,
                    trans_type,
                    trans_code,
                    "inbound_data",
                    tgt_key,
                    True,
                ),
            )

        conn.commit()
        print("Migration for Request 15 completed successfully.")
    except Exception as exc:
        conn.rollback()
        print(f"Migration error: {exc}", file=sys.stderr)
        raise
    finally:
        cur.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Migrate Ahamove Request 15 to Declarative Mappings")
    parser.add_argument("--host", default="localhost", help="Database host")
    parser.add_argument("--port", type=int, default=5433, help="Database port")
    parser.add_argument("--user", default="odoo", help="Database user")
    parser.add_argument("--password", default="odoo", help="Database password")
    parser.add_argument("--dbname", default="odoo", help="Database name")
    args = parser.parse_args()

    migrate_request_15(
        db_host=args.host,
        db_port=args.port,
        db_user=args.user,
        db_password=args.password,
        db_name=args.dbname,
    )


if __name__ == "__main__":
    main()
