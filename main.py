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


def bn_to_en(text):
  """Translates Bengali numerals (০-৯) to standard English digits (0-9)"""
  bengali_digits = "০১২৩৪৫৬৭৮৯"
  english_digits = "0123456789"
  trans_table = str.maketrans(bengali_digits, english_digits)
  return text.translate(trans_table)


def get_page_html():
  try:
    print("🌐 Attempting direct connection...")
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

  raise Exception("CRITICAL FAILURE: Could not retrieve target HTML")


def fetch_gold_price_bd():
  raw_html = get_page_html()
  soup = BeautifulSoup(raw_html, "html.parser")

  parsed_rates = {}
  raw_dump = []

  # Scan standard table rows, list items, paragraphs, and div boxes
  for element in soup.find_all(["tr", "li", "p", "div"]):
    row_text = element.get_text(separator=" ", strip=True)
    norm_text = bn_to_en(row_text)

    # Skip massive multi-line container wrappers (> 150 chars) or empty blocks
    if len(norm_text) > 150 or len(norm_text) < 5:
      continue

    cat = None
    if re.search(r"\b22\b|২২", norm_text):
      cat = "22KDM Gold"
    elif re.search(r"\b21\b|২১", norm_text):
      cat = "21KDM Gold"
    elif re.search(r"\b18\b|১৮", norm_text):
      cat = "18KDM Gold"
    elif any(w in norm_text for w in ["সনাতন", "TRADITIONAL", "OLD GOLD"]):
      cat = "Traditional Gold"

    if not cat or cat in parsed_rates:
      continue

    # Extract price floats (> 10,000 BDT)
    raw_nums = re.findall(r"[\d,\.]+", norm_text)
    clean_vals = []
    for rn in raw_nums:
      clean_str = rn.strip(",.").replace(",", "")
      try:
        v = float(clean_str)
        if v > 10000:  # Valid gold rates per vori/gram are always > 10,000 BDT
          clean_vals.append(v)
      except ValueError:
        continue

    if clean_vals:
      val = clean_vals[0]
      raw_dump.append(norm_text)

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

  # Lock output order strictly from highest purity down to traditional
  order = ["22KDM Gold", "21KDM Gold", "18KDM Gold", "Traditional Gold"]
  sorted_rates = {k: parsed_rates[k] for k in order if k in parsed_rates}

  return {
      "market_source": "Local Bullion Tariff",
      "fetched_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
      "rates": sorted_rates,
      "raw_dump": raw_dump,
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
    msg += "⚠️ <i>Parser alert: Data layout unreadable. Check GitHub logs.</i>\n\n"
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
    print("🚀 Telegram alert dispatched successfully!")
  except Exception as e:
    print(f"Telegram Network Error: {e}")


if __name__ == "__main__":
  payload = fetch_gold_price_bd()

  os.makedirs("api", exist_ok=True)
  with open("api/latest.json", "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2, ensure_ascii=False)

  broadcast_telegram(payload)
