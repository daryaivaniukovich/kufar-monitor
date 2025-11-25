import os
import json
import requests
import time
from datetime import datetime
from urllib.parse import quote

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GIST_TOKEN = os.getenv("GIST_TOKEN")

if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GIST_TOKEN]):
    raise ValueError("❌ Не заданы обязательные переменные")

GIST_ID_FILE = "gist_id.txt"
TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def get_gist_id():
    if os.path.exists(GIST_ID_FILE):
        with open(GIST_ID_FILE, "r") as f:
            return f.read().strip()
    return None

def save_gist_id(gist_id):
    with open(GIST_ID_FILE, "w") as f:
        f.write(gist_id)

def load_seen_ids_from_gist(gist_id):
    headers = {"Authorization": f"token {GIST_TOKEN}"}
    try:
        resp = requests.get(f"https://api.github.com/gists/{gist_id}", headers=headers, timeout=10)
        if resp.status_code == 404:
            print("[ℹ️] Gist не найден")
            return set()
        resp.raise_for_status()
        gist = resp.json()
        content = gist["files"].get("seen_ads.json", {}).get("content", "[]")
        return set(json.loads(content))
    except Exception as e:
        print(f"[⚠️] Ошибка Gist: {e}")
        return set()

def create_or_update_gist(seen_ids):
    headers = {"Authorization": f"token {GIST_TOKEN}"}
    content = json.dumps(list(seen_ids), ensure_ascii=False)
    gist_id = get_gist_id()

    payload = {
        "description": "Kufar.by seen ads IDs",
        "public": False,
        "files": {"seen_ads.json": {"content": content}}
    }

    try:
        url = f"https://api.github.com/gists/{gist_id}" if gist_id else "https://api.github.com/gists"
        method = requests.patch if gist_id else requests.post
        resp = method(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        new_id = resp.json()["id"]
        if not gist_id:
            save_gist_id(new_id)
        return new_id
    except Exception as e:
        print(f"[❌] Gist error: {e}")
        return None


# --- Telegram helpers (без изменений) ---
def send_telegram_with_photo(photo_url, text, url):
    try:
        resp = requests.post(
            f"{TELEGRAM_API_BASE}/sendPhoto",
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "photo": photo_url,
                "caption": text,
                "parse_mode": "HTML",
                "reply_markup": json.dumps({
                    "inline_keyboard": [[{"text": "📸 Открыть", "url": url}]]
                })
            },
            timeout=20
        )
        if resp.status_code != 200:
            send_telegram_text(text, url)
    except:
        send_telegram_text(text, url)

def send_telegram_text(text, url):
    try:
        requests.post(
            f"{TELEGRAM_API_BASE}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": f"{text}\n🔗 {url}",
                "parse_mode": "HTML"
            },
            timeout=10
        )
    except:
        pass


def fetch_ads():
    # Твой точный URL (GET-запрос!)
    base_url = "https://api.kufar.by/search-api/v2/search/rendered-paginated"
    params = {
        "cat": "1010",  # продажа квартир
        "cur": "USD",   # валюта
        "gtsy": "country-belarus~province-grodnenskaja_oblast~locality-grodno",
        "lang": "ru",
        "rms": "v.or:2",  # 2-х комнатные
        "size": "20",     # 20 объявлений за раз
        "typ": "sell"
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Accept": "application/json"
    }

    print("[📡] Запрос к search-api/v2/rendered-paginated (GET)")
    try:
        resp = requests.get(base_url, params=params, headers=headers, timeout=15)
        print(f"[🔍] Статус: {resp.status_code}")
        resp.raise_for_status()
        data = resp.json()
        ads = data.get("ads", [])
        print(f"[✅] Получено {len(ads)} объявлений")
        return ads
    except Exception as e:
        print(f"[❌] Ошибка: {e}")
        return []


def main():
    print(f"\n[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}] 🚀 Запуск (rendered-paginated — ТВОЙ URL)")
    seen_ids = load_seen_ids_from_gist(get_gist_id())
    print(f"✅ Загружено {len(seen_ids)} ID из Gist")
    print(f"🔍 Примеры ID: {list(seen_ids)[:3]}")

    ads = fetch_ads()
    if not ads:
        print("[ℹ️] Объявлений нет")
        return

    print(f"📡 Получено {len(ads)} объявлений")
    print(f"🔍 Первые ad_id: {[ad.get('ad_id') for ad in ads[:3]]}")

    new_count = 0
    for ad in ads:
        ad_id = str(ad.get("ad_id", ""))
        print(f"ID={ad_id}")
        if not ad_id or ad_id in seen_ids:
            continue

        # Данные
        title = ad.get("subject", "Без названия")
        price_byn_val = float(ad.get("price_byn", "0")) // 100
        price_usd_val = float(ad.get("price_usd", "0")) // 100

        ad_params = ad.get("ad_parameters", [])
        for ad_param in ad_params:
            param_name = ad_param.get("p")
            if param_name == "area"
                district = ad_param.get("v1", "")
            if param_name == "size"
                size = ad_param.get("v", "")
            if param_name == "floor"
                floor = ad_param.get("v1", [])[0]
            if param_name == "re_number_floors"
                all_number_floors = ad_param.get("v1", "")
            if param_name == "year_built"
                year_built = ad_param.get("v1", "")
        url = f"https://kufar.by/item/{ad_id}"

        # Форматирование
        price_str = f"{price_usd_val} USD ({price_val} BYN)"
        base_text = f"<b>{title}</b>\n{price_str}\n{district} | {size} кв.м. | {floor}/{all_number_floors} этаж | {year_built} год"
        caption = (base_text[:950] + "…") if len(base_text) > 1024 else base_text

        # Фото
        images = ad.get("images", [])
        photo_url = images[0].get("url", "") if images else ""

        # Отправка
        if photo_url:
            send_telegram_with_photo(photo_url, caption, url)
        else:
            send_telegram_text(base_text, url)

        seen_ids.add(ad_id)
        new_count += 1
        time.sleep(0.5)

    if new_count:
        create_or_update_gist(seen_ids)
        print(f"[🎉] Отправлено {new_count} новых объявлений")
    else:
        print("[ℹ️] Новых объявлений нет")

    print("✅ Завершено")


if __name__ == "__main__":
    main()