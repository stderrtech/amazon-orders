# amazon-orders downloader

Downloads your Amazon order history and exports it as a zip of CSVs compatible with the [Tiller Money](https://www.tillerhq.com/) import format.

## What it exports

| File | Contents |
|---|---|
| `Order History.csv` | Physical orders, one row per item |
| `Digital Content Orders.csv` | Digital orders, one row per item |
| `Refund Details.csv` | Physical order refunds |
| `Returns.csv` | Physical order returns (same data as Refund Details) |
| `Digital Returns.csv` | Digital order refunds |

## Setup

**Prerequisites:** Python 3.10+, [uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/stderrtech/amazon-orders.git
cd amazon-orders
uv sync
```

Copy the credentials template and fill it in:

```bash
cp .env.example .env
```

`.env` fields:

| Variable | Required | Description |
|---|---|---|
| `AMAZON_EMAIL` | Yes | Amazon account email |
| `AMAZON_PASSWORD` | Yes | Amazon account password |
| `AMAZON_OTP_SECRET_KEY` | Yes | TOTP secret from your authenticator app (the string behind the QR code when you set up 2FA) |
| `AMAZON_START_YEAR` | No | First year to fetch (default: `2010`) |
| `AMAZON_START_MONTH` | No | First month to fetch, 1–12 (default: `1`) |
| `AMAZON_END_YEAR` | No | Last year to fetch (default: current year) |
| `AMAZON_END_MONTH` | No | Last month to fetch, 1–12 (default: current month) |

## Usage

```bash
uv run python download_amazon_orders.py
```

The script logs in, fetches orders year by year with full details, then fetches transactions for the same date range. Progress is printed to stdout. When complete it writes `amazon_orders_YYYYMMDD.zip` in the project directory.

**Runtime:** fetching full order details requires one extra HTTP request per order. Expect roughly 1–2 seconds per order — a large history can take 10–30 minutes.

## Importing into Tiller

1. Open your Tiller spreadsheet.
2. Use the Tiller Money Feeds add-on → **Import transactions from file**.
3. Upload `amazon_orders_YYYYMMDD.zip`.

## Known limitations

- **Ship Date**, **Unit Price Tax**, and **Contract ID** columns are always blank — the underlying `amazon-orders` library doesn't expose these fields.
- **Carrier Name & Tracking Number** contains the tracking URL rather than a formatted carrier + number string.
- This script scrapes Amazon's website via the [`amazon-orders`](https://github.com/alexdlaird/amazon-orders) library. It may break if Amazon changes their HTML.
