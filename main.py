from datetime import datetime, timezone
import html
import json
import os
import re
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests
import requests as std_requests

TARGET_URL = "https://gold-price.bd/"
PROXY_FALLBACKS = [
    f"https://api.allorigins.win/raw?url={TARGET_URL}",
    f"https://api.codetabs.com/v1/proxy?quest={TARGET_URL}",
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
  try:
    print(f"🌐 Attempting direct connection to {TARGET_URL}...")
    res = cffi_requests.get(TARGET_URL, impersonate="chrome120", timeout=15)
    if res.status_code == 200:
      return res.text
  except Exception as e:
    print(f"⚠️ Direct connection failed: {e}")

  print("🔄 Engaging failover proxy network...")
  for proxy in PROXY_FALLBACKS:
    try:
      res = std_requests.get(
          proxy, headers={"User-Agent": "Mozilla/5.0"}, timeout=20
      )
      if res.status_code == 200 and len(res.text) > 1000:
        return res.text
    except Exception:
      continue

  raise Exception(f"CRITICAL FAILURE: Could not retrieve HTML from {TARGET_URL}")


def fetch_gold_price_bd():
  raw_html = get_page_html()
  soup = BeautifulSoup(raw_html, "html.parser")

  parsed_rates = {}
  raw_dump = []

  # Search strategy 1: Scan WordPress table blocks
  for tr in soup.find_all("tr"):
    row_text = tr.get_text(separator=" ", strip=True)
    if any(k in row_text.upper() for k in ["22", "21", "18", "TRADITIONAL", "সনাতন"]):
      raw_dump.append(row_text)
      
      # Find all continuous digit strings that look like prices (> 10,000)
      numbers = re.findall(r"\b\d{1,3}(?:,\d{2,3})+\b|\b\d{5,7}\b", row_text)
      clean_nums = [float(n.replace(",", "")) for n in numbers if float(n.replace(",", "")) > 10000]

      if clean_nums:
        val = clean_nums[0] # Grab primary price
        
        # Determine karat category
        cat = "Unknown Gold"
        if "22" in row_text: cat = "22 Karat Gold"
        elif "21" in row_text: cat = "21 Karat Gold"
        elif "18" in row_text: cat = "18 Karat Gold"
        elif "TRADITIONAL" in row_text.upper() or "সনাতন" in row_text: cat = "Traditional Gold"

        # Determine if price is per Vori (~1,30,000+) or per Gram (~12,000+)
        if val > 50000:
          vori_rate = val
          gram_rate = val / 11.664
        else:
          gram_rate = val
          vori_rate = val * 11.664

        parsed_rates[cat] = {
            "bdt_per_gram": round(gram_rate, 2),
            "bdt_per_vori": round(vori_rate, 2),
            "formatted_gram": format_inr_taka(gram_rate),
            "formatted_vori": format_inr_taka(vori_rate),
        }

  return {
      "market_source": "gold-price.bd",
      "url": TARGET_URL,
      "page_title": "Latest Gold Price in Bangladesh",
      "fetched_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
      "rates": parsed_rates,
      "raw_dump": raw_dump
  }


def broadcast_telegram(data):
  token = os.getenv("TELEGRAM_BOT_TOKEN")
  chat_id = os.getenv("TELEGRAM_CHAT_ID")

  if not token or not chat_id:
    print("⚠️ Telegram tokens missing. Skipping broadcast.")
    return

  url = f"https://api.telegram.org/bot{token}/sendMessage"
  rates = data.get("rates", {})

  msg = f"🚨 <b>Gold Market Update ({data['market_source']})</b>\n\n"

  if not rates:
    msg += "⚠️ <i>Parser alert: The website layout changed or data loaded dynamically. Check raw API dump.</i>\n\n"
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
    std_requests.post(url, json=payload, timeout=10)
    print("🚀 Telegram alert dispatched!")
  except Exception as e:
    print(f"Telegram Network Error: {e}")


if __name__ == "__main__":
  payload = fetch_gold_price_bd()

  os.makedirs("api", exist_ok=True)
  with open("api/latest.json", "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2, ensure_ascii=False)

  broadcast_telegram(payload)
