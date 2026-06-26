from datetime import datetime, timezone
import html
import json
import os
from bs4 import BeautifulSoup
import requests

BAJUS_URL = "https://www.bajus.org/gold-price/"


def format_inr_taka(val):
  """Formats numbers into standard South Asian Lakh/Crore notation (e.g. 1,38,288/-)"""
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


def fetch_bajus_tariff():
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
          " (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
      ),
      "Accept": (
          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
      ),
      "Accept-Language": "en-US,en;q=0.5",
  }

  res = requests.get(BAJUS_URL, headers=headers, timeout=15)
  res.raise_for_status()

  soup = BeautifulSoup(res.text, "html.parser")

  parsed_rates = {}
  raw_table_dump = []

  # Scan all table rows across the BAJUS tariff page
  for tr in soup.find_all("tr"):
    cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
    if len(cells) < 2:
      continue

    row_text = " ".join(cells).upper()

    # Catch standard jewelry karat tiers
    if any(
        k in row_text
        for k in ["22 KARAT", "21 KARAT", "18 KARAT", "TRADITIONAL"]
    ):
      raw_table_dump.append(cells)

      category = cells[0]
      price_str = cells[-1]

      # Strip non-numeric characters (keep decimals)
      clean_digits = "".join(
          c for c in price_str if c.isdigit() or c == "."
      ).strip(".")

      if clean_digits:
        try:
          val = float(clean_digits)

          # BAJUS publishes BDT/Gram. 1 Vori = 11.664 Grams
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

  # Extract page notice header
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
    # Filter to broadcast Gold tiers
    if "GOLD" in category.upper() or "TRADITIONAL" in category.upper():
      msg += (
          f"🥇 <b>{html.escape(category)}</b>\n"
          f"• Gram: <code>{metrics['formatted_gram']} BDT</code>\n"
          f"• Vori (11.664g): <code>{metrics['formatted_vori']} BDT</code>\n\n"
      )

  msg += f"⏱️ <i>Checked: {data['fetched_at_utc']} UTC</i>"

  # HTML parse mode is 100x safer against weird website text syntax than Markdown
  payload = {"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}

  try:
    res = requests.post(url, json=payload, timeout=10)
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
