#!/usr/bin/env python3
"""Download Amazon order history and export to Tiller-compatible CSVs in a zip."""

import csv
import io
import os
import re
import zipfile
from datetime import date

from dotenv import load_dotenv

load_dotenv()

AMAZON_EMAIL = os.environ["AMAZON_EMAIL"]
AMAZON_PASSWORD = os.environ["AMAZON_PASSWORD"]
AMAZON_OTP_SECRET_KEY = os.environ.get("AMAZON_OTP_SECRET_KEY")
START_YEAR = int(os.environ.get("AMAZON_START_YEAR", 2010))
START_MONTH = int(os.environ.get("AMAZON_START_MONTH", 1))
END_YEAR = int(os.environ.get("AMAZON_END_YEAR", date.today().year))
END_MONTH = int(os.environ.get("AMAZON_END_MONTH", date.today().month))

START_DATE = date(START_YEAR, START_MONTH, 1)
END_DATE = date(END_YEAR, END_MONTH, 1)

PHYSICAL_HEADERS = [
    "Order Date",
    "Order ID",
    "Product Name",
    "Total Amount",
    "ASIN",
    "Payment Method Type",
    "Carrier Name & Tracking Number",
    "Original Quantity",
    "Purchase Order Number",
    "Ship Date",
    "Shipping Charge",
    "Total Discounts",
    "Unit Price",
    "Unit Price Tax",
    "Website",
]

DIGITAL_HEADERS = [
    "Order Date",
    "Order ID",
    "Product Name",
    "Transaction Amount",
    "ASIN",
    "Payment Information",
    "Digital Order Item ID",
    "Original Quantity",
    "Price",
    "Price Tax",
]

REFUND_HEADERS = [
    "Order ID",
    "Refund Amount",
    "Website",
    "Refund Date",
    "Creation Date",
    "Contract ID",
]

DIGITAL_RETURN_HEADERS = [
    "ASIN",
    "Order ID",
    "Return Date",
    "Transaction Amount",
]


def extract_asin(link: str) -> str:
    if not link:
        return ""
    m = re.search(r"/dp/([A-Z0-9]{10})(?:/|$|\?)", link)
    return m.group(1) if m else ""


def format_date(d) -> str:
    if d is None:
        return ""
    if hasattr(d, "strftime"):
        return d.strftime("%Y-%m-%d")
    return str(d)


def sum_discounts(order) -> str:
    total = 0.0
    for attr in ("coupon_savings", "subscription_discount"):
        val = getattr(order, attr, None)
        if val is not None:
            try:
                total += float(str(val).replace("$", "").replace(",", "").strip() or 0)
            except ValueError:
                pass
    return f"{total:.2f}" if total else ""


def tracking_string(order) -> str:
    shipments = getattr(order, "shipments", None) or []
    links = []
    for s in shipments:
        link = getattr(s, "tracking_link", None)
        if link:
            links.append(link)
    return "; ".join(links)


def format_amount(val) -> str:
    if val is None:
        return ""
    try:
        return f"{float(str(val).replace('$', '').replace(',', '').strip()):.2f}"
    except ValueError:
        return str(val)


def make_csv_buffer(headers: list, rows: list) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def main():
    from amazonorders.orders import AmazonOrders
    from amazonorders.session import AmazonSession
    from amazonorders.transactions import AmazonTransactions
    from amazonorders.exception import AmazonOrdersAuthRedirectError, AmazonOrdersError

    session_kwargs = dict(username=AMAZON_EMAIL, password=AMAZON_PASSWORD)
    if AMAZON_OTP_SECRET_KEY:
        session_kwargs["otp_secret_key"] = AMAZON_OTP_SECRET_KEY

    print("Logging in to Amazon...")
    session = AmazonSession(**session_kwargs)
    session.login()
    print("Login successful.")

    amazon_orders = AmazonOrders(session)
    amazon_transactions = AmazonTransactions(session)

    physical_rows = []
    digital_rows = []
    refund_rows = []
    digital_refund_rows = []
    digital_order_ids = set()

    for year in range(START_YEAR, END_YEAR + 1):
        print(f"Fetching orders for {year}...")
        try:
            orders = amazon_orders.get_order_history(year=year, full_details=True)
        except AmazonOrdersAuthRedirectError:
            print("Session expired mid-run. Please re-run the script to re-authenticate.")
            return
        except AmazonOrdersError as e:
            print(f"Error fetching orders for {year}: {e}")
            continue

        for order in orders:
            order_date = order.order_placed_date
            if hasattr(order_date, "year"):
                order_month_start = date(order_date.year, order_date.month, 1)
                if order_month_start < START_DATE or order_month_start > END_DATE:
                    continue

            is_digital = not getattr(order, "shipments", None)
            if is_digital:
                digital_order_ids.add(order.order_number)

            items = getattr(order, "items", []) or []
            if not items:
                items = []
                for shipment in (getattr(order, "shipments", None) or []):
                    items.extend(getattr(shipment, "items", []) or [])

            tracking = tracking_string(order)

            for i, item in enumerate(items):
                asin = extract_asin(getattr(item, "link", "") or "")
                qty = getattr(item, "quantity", "") or ""

                if is_digital:
                    digital_rows.append({
                        "Order Date": format_date(order.order_placed_date),
                        "Order ID": order.order_number,
                        "Product Name": getattr(item, "title", ""),
                        "Transaction Amount": format_amount(order.grand_total),
                        "ASIN": asin,
                        "Payment Information": getattr(order, "payment_method", ""),
                        "Digital Order Item ID": f"{order.order_number}-{i}",
                        "Original Quantity": qty,
                        "Price": format_amount(getattr(item, "price", None)),
                        "Price Tax": "",
                    })
                else:
                    physical_rows.append({
                        "Order Date": format_date(order.order_placed_date),
                        "Order ID": order.order_number,
                        "Product Name": getattr(item, "title", ""),
                        "Total Amount": format_amount(order.grand_total),
                        "ASIN": asin,
                        "Payment Method Type": getattr(order, "payment_method", ""),
                        "Carrier Name & Tracking Number": tracking,
                        "Original Quantity": qty,
                        "Purchase Order Number": "",
                        "Ship Date": "",
                        "Shipping Charge": format_amount(getattr(order, "shipping_total", None)),
                        "Total Discounts": sum_discounts(order),
                        "Unit Price": format_amount(getattr(item, "price", None)),
                        "Unit Price Tax": "",
                        "Website": "Amazon.com",
                    })

        print(f"  → {len(orders)} orders processed for {year}")

    days_to_fetch = (date.today() - START_DATE).days + 1
    print(f"Fetching transactions/refunds (last {days_to_fetch} days)...")
    try:
        transactions = amazon_transactions.get_transactions(days=days_to_fetch)
    except AmazonOrdersAuthRedirectError:
        print("Session expired. Please re-run.")
        return
    except AmazonOrdersError as e:
        print(f"Error fetching transactions: {e}")
        transactions = []

    for tx in transactions:
        grand_total = getattr(tx, "grand_total", None)
        if grand_total is None:
            continue

        try:
            amount = float(str(grand_total).replace("$", "").replace(",", "").strip())
        except ValueError:
            continue

        if amount >= 0:
            continue  # only process refunds (negative amounts)

        order_id = getattr(tx, "order_number", "") or ""
        refund_amount = f"{abs(amount):.2f}"
        tx_date = format_date(getattr(tx, "completed_date", None))

        if order_id in digital_order_ids:
            digital_refund_rows.append({
                "ASIN": "",
                "Order ID": order_id,
                "Return Date": tx_date,
                "Transaction Amount": refund_amount,
            })
        else:
            row = {
                "Order ID": order_id,
                "Refund Amount": refund_amount,
                "Website": "Amazon.com",
                "Refund Date": tx_date,
                "Creation Date": tx_date,
                "Contract ID": "",
            }
            refund_rows.append(row)

    print(f"  → {len(transactions)} transactions processed")

    today = date.today().strftime("%Y%m%d")
    zip_name = f"amazon_orders_{today}.zip"
    zip_path = os.path.join(os.path.dirname(__file__), "output/", zip_name)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Order History.csv", make_csv_buffer(PHYSICAL_HEADERS, physical_rows))
        zf.writestr("Digital Content Orders.csv", make_csv_buffer(DIGITAL_HEADERS, digital_rows))
        zf.writestr("Refund Details.csv", make_csv_buffer(REFUND_HEADERS, refund_rows))
        zf.writestr("Returns.csv", make_csv_buffer(REFUND_HEADERS, refund_rows))
        zf.writestr("Digital Returns.csv", make_csv_buffer(DIGITAL_RETURN_HEADERS, digital_refund_rows))

    print(f"\nDone! Output: {zip_path}")
    print(f"  Physical order rows : {len(physical_rows)}")
    print(f"  Digital order rows  : {len(digital_rows)}")
    print(f"  Refund rows         : {len(refund_rows)}")
    print(f"  Digital return rows : {len(digital_refund_rows)}")


if __name__ == "__main__":
    main()

