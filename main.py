from datetime import datetime, timezone
import html
import json
import os
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests
import requests as std_requests

BAJUS_URL = "https://www.bajus.org/gold-price/"

# If direct cloud access is blocked, Python will bounce through these public proxies
PROXY_FALLBACKS = [
    f"https://api.allorigins.win/raw?url={BAJUS_URL}",
    f"https://api.codetabs.com/v1/proxy?quest={BAJUS_URL}",
]


def format_inr_taka(val):
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


def get_page_html():
  # TIER 1: Low-level TLS Impersonation (Tricks Cloudflare browser checks)
  try:
    print("🌐 Tier 1: Attempting direct Chrome TLS handshake...")
    res = cffi_requests.get(BAJUS_URL, impersonate="chrome120", timeout=15)
    if res.status_code == 200:
      print("✅ Tier 1 Successful: Connected directly to BAJUS!")
      return res.text
    print(f"⚠️ Tier 1 Rejected (HTTP {res.status_code})")
  except Exception as e:
    print(f"⚠️ Tier 1 Failed: {e}")

  # TIER 2: Open Proxy Routing (Tricks Datacenter IP blocks)
  print("🔄 Tier 2: Engaging failover proxy network...")
  for proxy in PROXY_FALLBACKS:
    try:
      proxy_name = proxy.split("/")[2]
      print(f"📡 Bouncing through {proxy_name}...")
      res = std_requests.get(
          proxy, headers={"User-Agent": "Mozilla/5.0"}, timeout=20
      )
      if res.status_code == 200 and "bajus" in res.text.lower():
        print(f"✅ Tier 2 Successful: HTML retrieved via {proxy_name}!")
        return res.text
    except Exception as proxy_err:
      print(f"❌ {proxy_name} failed: {proxy_err}")

  raise Exception(
      "CRITICAL FAILURE: BAJUS blocked both direct TLS spoofing and all backup"
      " proxy tunnels."
  )


def fetch_bajus_tariff():
  raw_html = get_page_html()
  soup = BeautifulSoup(raw_html, "html.parser")

  parsed_rates = {}
  raw_table_dump = []

  for tr in soup.find_all("tr"):
    cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
    if len(cells) < 2:
      continue

    row_text = " ".join(cells).upper()

    if any(
        k in row_text
        for k in ["22 KARAT", "21 KARAT", "18 KARAT", "TRADITIONAL"]
    ):
      raw_table_dump.append(cells)
      category = cells[0]
      price_str = cells[-1]

      clean_digits = "".join(
          c for c in price_str if c.isdigit() or c == "."
      ).strip(".")

      if clean_digits:
        try:
          val = float(clean_digits)
          is_per_gram = "GRAM" in price_str.upper() or val < 50000

          if is_per_gram:
            gram_rate = round(val, 2)
            vori_rate = round(val * 11.664, 2)
          else:
            vori_rate = round(val, 2)
            gram_rate = round(val / 11.664, 2)

          parsed_rates[category] = {
              "raw_published_text": price_str,
              "bdt_per_gram": gram_rate,
              "bdt_per_vori": vori_rate,
              "formatted_gram": format_inr_taka(gram_rate),
              "formatted_vori": format_inr_taka(vori_rate),
          }
        except ValueError:
          continue

  header_text = "BAJUS Official Tariff"
  for h in soup.find_all(["h1", "h2", "h3", "h4"]):
    txt = h.get_text(strip=True)
    if "gold price" in txt.lower() or "স্বর্ণ" in txt:
      header_text = txt
      break

  return {
      "market_source": "Bangladesh Jewellers Association (BAJUS)",
      "url": BAJUS_URL,
      "page_title": header_text,
      "fetched_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
      "rates": parsed_rates,
      "raw_table_dump": raw_table_dump,
  }


def broadcast_telegram(data):
  token = os.getenv("TELEGRAM_BOT_TOKEN")
  chat_id = os.getenv("TELEGRAM_CHAT_ID")

  if not token or not chat_id:
    print("⚠️ Telegram tokens missing. Skipping broadcast.")
    return

  url = f"https://api.telegram.org/bot{token}/sendMessage"
  rates = data.get("rates", {})

  msg = f"🚨 <b>{html.escape(data['page_title'])}</b>\n\n"

  for category, metrics in rates.items():
    if "GOLD" in category.upper() or "TRADITIONAL" in category.upper():
      msg += (
          f"🥇 <b>{html.escape(category)}</b>\n"
          f"• Gram: <code>{metrics['formatted_gram']} BDT</code>\n"
          f"• Vori (11.664g): <code>{metrics['formatted_vori']} BDT</code>\n\n"
      )

  msg += f"⏱️ <i>Checked: {data['fetched_at_utc']} UTC</i>"
  payload = {"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}

  try:
    res = std_requests.post(url, json=payload, timeout=10)
    if res.status_code == 200:
      print("🚀 Telegram alert dispatched successfully!")
    else:
      print(f"❌ Telegram delivery failed: {res.text}")
  except Exception as e:
    print(f"Telegram Network Error: {e}")


if __name__ == "__main__":
  tariff_payload = fetch_bajus_tariff()

  os.makedirs("api", exist_ok=True)
  with open("api/latest.json", "w", encoding="utf-8") as f:
    json.dump(tariff_payload, f, indent=2, ensure_ascii=False)

  broadcast_telegram(tariff_payload)
