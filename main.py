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


def get_raw_js_stream():
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
          " (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
      ),
      "Referer": "https://goldpric.com/",
  }

  # TIER 1: Direct Stream Capture
  try:
    print("🌐 Tier 1: Attempting direct stream capture...")
    res = requests.get(TARGET_JS_URL, headers=headers, timeout=10)
    if res.status_code == 200 and "const p" in res.text:
      print("✅ Tier 1 Successful: Direct data stream connected!")
      return res.text
  except Exception as e:
    print(f"⚠️ Tier 1 Blocked ({type(e).__name__}). Pivot initiated.")

  # TIER 2: Proxy Tunnel Routing (Bypasses Azure IP packet drops)
  print("🔄 Tier 2: Engaging backup proxy failover tunnels...")
  proxy_tunnels = [
      f"https://api.allorigins.win/raw?url={TARGET_JS_URL}",
      f"https://api.codetabs.com/v1/proxy?quest={TARGET_JS_URL}",
  ]

  for tunnel in proxy_tunnels:
    proxy_name = tunnel.split("/")[2]
    try:
      print(f"📡 Tunneling via {proxy_name}...")
      res = requests.get(
          tunnel, headers={"User-Agent": "Mozilla/5.0"}, timeout=15
      )
      if res.status_code == 200 and "const p" in res.text:
        print(f"✅ Tier 2 Successful: Stream captured via {proxy_name}!")
        return res.text
    except Exception as tunnel_err:
      print(f"❌ {proxy_name} tunnel failed: {tunnel_err}")

  raise Exception(
      "CRITICAL FAILURE: Cloud firewall dropped both direct TCP handshakes and"
      " proxy routing tunnels."
  )


def fetch_goldpric_stream():
  js_text = get_raw_js_stream()

  # Slice out the JSON array sitting inside: const p = [ ... ];
  match = re.search(r"const\s+p\s*=\s*(\[.*?\]);", js_text, re.DOTALL)
  if not match:
    raise Exception(
        "Parser Error: Could not locate the 'const p' array inside the stream"
        " dump."
    )

  data_list = json.loads(match.group(1))

  key_map = {
      "22k": "22KDM Gold",
      "21k": "21KDM Gold",
      "18k": "18KDM Gold",
      "old": "Traditional Gold",
  }

  parsed_rates = {}

  for item in data_list:
    target_name = key_map.get(item.get("key"))
    if not target_name:
      continue

    rates_node = item.get("unit_rate", {})
    gram_val = float(rates_node.get("gram", 0))
    vori_val = float(rates_node.get("bhori", 0))

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

  order = ["22KDM Gold", "21KDM Gold", "18KDM Gold", "Traditional Gold"]
  sorted_rates = {k: parsed_rates[k] for k in order if k in parsed_rates}

  return {
      "market_source": "GoldPric.CoM Live Data Stream",
      "fetched_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
      "rates": sorted_rates,
      "raw_dump": ["Stream captured successfully via automated failover."],
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
