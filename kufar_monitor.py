import os
import json
import requests
import time
from datetime import datetime

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
            print("[ℹ️] Gist не найден — будет создан новый.")
            return set()
        resp.raise_for_status()
        gist = resp.json()
        content = gist["files"].get("seen_ads.json", {}).get("content", "[]")
        ids = json.loads(content)
        print(f"[📥 Gist] Загружено {len(ids)} ID")
        return set(ids)
    except Exception as e:
        print(f"[⚠️] Ошибка загрузки Gist: {e}")
        return set()


def create_or_update_gist(seen_ids):
    headers = {
        "Authorization": f"token {GIST_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    content = json.dumps(list(seen_ids), ensure_ascii=False, indent=2)
    gist_id = get_gist_id()

    payload = {
        "description": "Kufar.by seen ads IDs (auto-updated)",
        "public": False,
        "files": {
            "seen_ads.json": {"content": content}
        }
    }

    try:
        url = f"https://api.github.com/gists/{gist_id}" if gist_id else "https://api.github.com/gists"
        method = requests.patch if gist_id else requests.post
        resp = method(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        new_id = resp.json()["id"]
        if not gist_id:
            save_gist_id(new_id)
        print(f"[✅ Gist] {'Обновлён' if gist_id else 'Создан'} ({new_id})")
        return new_id
    except Exception as e:
        print(f"[❌] Ошибка Gist: {e}")
        return None


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
        if resp.status_code == 200:
            print(f"[✅ Telegram] Фото отправлено: {url}")
        else:
            print(f"[⚠️ Telegram] sendPhoto: {resp.status_code}")
            send_telegram_text(text, url)
    except Exception as e:
        print(f"[❌ Telegram] sendPhoto: {e}")
        send_telegram_text(text, url)


def send_telegram_text(text, url):
    try:
        resp = requests.post(
            f"{TELEGRAM_API_BASE}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": f"{text}\n🔗 {url}",
                "parse_mode": "HTML"
            },
            timeout=10
        )
        if resp.status_code == 200:
            print(f"[✅ Telegram] Текст отправлен: {url}")
        else:
            print(f"[⚠️ Telegram] sendMessage: {resp.status_code}")
    except Exception as e:
        print(f"[❌ Telegram] sendMessage: {e}")


def fetch_ads():
    # 🔥 ПРАВИЛЬНЫЙ ЭНДПОИНТ (ноябрь 2025)
    API_URL = "https://api.kufar.by/search-api/v2/search"  # ← ВОТ ОН!

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://kufar.by",
        "Referer": "https://kufar.by/"
    }

    payload = {
        "sort_type": "lst.d",
        "sort_order": "desc",
        "lang": "ru",
        "size": 10,
        "query": {
            "rgn": "1048",   # Гродно
            "t": "1010",     # продажа квартир
            "ar": "3"        # 2 комнаты
        }
    }

    print(f"[📡] Запрос к {API_URL}")
    try:
        resp = requests.post(API_URL, json=payload, headers=headers, timeout=15)
        print(f"[🔍] Статус: {resp.status_code}")
        resp.raise_for_status()
        data = resp.json()
        ads = data.get("ads", [])
        print(f"[✅] Получено {len(ads)} объявлений")
        return ads
    except Exception as e:
        print(f"[❌] Ошибка: {e}")
        return []


# ... (main() — без изменений)
def main():
    print(f"\n[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}] 🚀 Запуск (searchapi/v2 — ВЕРНО)")
    gist_id = get_gist_id()
    seen_ids = load_seen_ids_from_gist(gist_id)

    ads = fetch_ads()
    if not ads:
        print("[ℹ️] Объявлений нет")
        return

    new_count = 0
    for ad in ads:
        ad_id = str(ad.get("ad_id", ""))
        if not ad_id or ad_id in seen_ids:
            continue

        title = ad.get("subject", "Без названия")
        price_val = ad.get("price", {}).get("uah", {}).get("amount", "???")
        location = ad.get("location", {}).get("city", {}).get("name", "Гродно")
        district = ad.get("location", {}).get("district", {}).get("name", "")
        url = f"https://kufar.by/item/{ad_id}"

        price_str = f"{price_val:,} BYN".replace(",", " ")
        district_str = f", {district}" if district else ""
        base_text = f"<b>{title}</b>\n{price_str} | {location}{district_str}"
        caption = (base_text[:950] + "…") if len(base_text) > 1024 else base_text

        images = ad.get("images", [])
        photo_url = images[0].get("url", "") if images else ""

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