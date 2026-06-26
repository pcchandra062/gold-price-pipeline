from datetime import datetime, timezone
import json
import os
import requests

TICKER_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=1d"
)


def get_market_data():
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
    }
    res = requests.get(TICKER_URL, headers=headers, timeout=10)
    res.raise_for_status()
    meta = res.json()["chart"]["result"][0]["meta"]

    return {
        "asset": "Gold Spot (XAU/USD)",
        "price": meta["regularMarketPrice"],
        "currency": meta["currency"],
        "fetched_at_utc": datetime.now(timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
    }


def send_telegram(data):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    msg = (
        f"🚨 *Live Gold Market Update*\n\n"
        f"💰 *Spot Price:* `{data['price']:,} {data['currency']}`\n"
        f"⏱️ *Checked:* {data['fetched_at_utc']} UTC"
    )

    requests.post(
        url,
        json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
        timeout=10,
    )


if __name__ == "__main__":
    payload = get_market_data()
    os.makedirs("api", exist_ok=True)
    with open("api/latest.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4)
    send_telegram(payload)
