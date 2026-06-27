from datetime import datetime, timezone
import html
import json
import os
import re
import requests

TARGET_JS_URL = "https://goldpric.com/price.ultra.js"


def format_inr_taka(val):
  """Formats numbers into standard South Asian Lakh/Crore notation (e.g. 2,28,556/-)"""
  try:
    num = int(round(float(val)))
    s = str(num)
    if len(s) <= 3:
      return s + "/-"
    last3 = s[-3:]
    rest = s[:-3]
    chunks = []
    while len(rest) > 2:
      chunks.append(rest[-2:])
      rest = rest[:-2]
    chunks.append(rest)
    chunks.reverse()
    return ",".join(chunks) + "," + last3 + "/-"
  except Exception:
    return str(val)


def fetch_goldpric_stream():
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
          " (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
      ),
      "Referer": "https://goldpric.com/",  # Tells their CDN the request came from their homepage
  }

  res = requests.get(TARGET_JS_URL, headers=headers, timeout=15)
  res.raise_for_status()

  js_text = res.text

  # Slice out the pure JSON payload sitting between: const p = [ ... ];
  match = re.search(r"const\s+p\s*=\s*(\[.*?\]);", js_text, re.DOTALL)
  if not match:
    raise Exception(
        "Parser Error: Could not locate the 'const p' data array inside the JS"
        " file."
    )

  raw_json_array = match.group(1)
  data_list = json.loads(raw_json_array)

  # Map the JS "key" identifiers directly to your Tkinter & Google Sheet layout architecture
  key_map = {
      "22k": "22KDM Gold",
      "21k": "21KDM Gold",
      "18k": "18KDM Gold",
      "old": "Traditional Gold",
  }

  parsed_rates = {}

  for item in data_list:
    js_key = item.get("key")
    target_name = key_map.get(js_key)

    if not target_name:
      continue

    # Pull exact published market rates
    rates_node = item.get("unit_rate", {})
    gram_val = float(rates_node.get("gram", 0))
    vori_val = float(rates_node.get("bhori", 0))

    # Pull official customer store buyback / exchange rates
    sell_node = item.get("unit_sell", {})
    buyback_gram = float(sell_node.get("gram", 0))
    buyback_vori = float(sell_node.get("bhori", 0))

    parsed_rates[target_name] = {
        "bdt_per_gram": round(gram_val, 2),
        "bdt_per_vori": round(vori_val, 2),
        "formatted_gram": format_inr_taka(gram_val),
        "formatted_vori": format_inr_taka(vori_val),
        "customer_buyback_gram": round(buyback_gram, 2),
        "customer_buyback_vori": round(buyback_vori, 2),
    }

  # Lock output order strictly from 22K down to Traditional
  order = ["22KDM Gold", "21KDM Gold", "18KDM Gold", "Traditional Gold"]
  sorted_rates = {k: parsed_rates[k] for k in order if k in parsed_rates}

  return {
      "market_source": "GoldPric.CoM Live Data Stream",
      "fetched_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
      "rates": sorted_rates,
      "raw_dump": ["Stream captured successfully. Payload verified."],
  }


def broadcast_telegram(data):
  token = os.getenv("TELEGRAM_BOT_TOKEN")
  chat_id = os.getenv("TELEGRAM_CHAT_ID")

  if not token or not chat_id:
    print("⚠️ Telegram tokens missing. Skipping broadcast.")
    return

  url = f"https://api.telegram.org/bot{token}/sendMessage"
  rates = data.get("rates", {})

  msg = "🚨 <b>Live Gold Market Rates</b>\n\n"

  if not rates:
    msg += "⚠️ <i>Parser alert: Data stream interrupted. Check GitHub logs.</i>\n\n"
  else:
    for category, metrics in rates.items():
      msg += (
          f"🥇 <b>{html.escape(category)}</b>\n"
          f"• Gram: <code>{metrics['formatted_gram']} BDT</code>\n"
          f"• Vori (11.664g): <code>{metrics['formatted_vori']} BDT</code>\n\n"
      )

  msg += f"⏱️ <i>Checked: {data['fetched_at_utc']} UTC</i>"
  payload = {"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}

  try:
    requests.post(url, json=payload, timeout=10)
    print("🚀 Telegram alert dispatched successfully!")
  except Exception as e:
    print(f"Telegram Network Error: {e}")


if __name__ == "__main__":
  payload = fetch_goldpric_stream()

  os.makedirs("api", exist_ok=True)
  with open("api/latest.json", "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2, ensure_ascii=False)

  broadcast_telegram(payload)
