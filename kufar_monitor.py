import os
import json
import requests
import time
from datetime import datetime

# === Настройки из переменных окружения ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GIST_TOKEN = os.getenv("GIST_TOKEN")
GITHUB_USER = os.getenv("GITHUB_USER", "kufar-monitor")  # fallback

if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GIST_TOKEN]):
    raise ValueError("❌ Не заданы обязательные переменные: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GIST_TOKEN")

# Gist ID будем хранить в переменной, можно также в файле, но проще в env
GIST_ID_FILE = "gist_id.txt"

# API endpoints
GIST_API = "https://api.github.com/gists"
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

# Параметры поиска: 2-комн. квартиры в Гродно
PARAMS = {
    "lang": "ru",
    "currency": "BYN",
    "rgn": "1048",  # Гродно
    "t": "1010",    # продажа квартир
    "ot": "1",
    "ar": "3",      # 2 комнаты
    "prc": "r",     # новые
    "size": "10"
}
API_URL = "https://cre-api-v2.kufar.by/items_search/v2/search"


def get_gist_id():
    """Читает Gist ID из gist_id.txt (если есть), иначе None"""
    if os.path.exists(GIST_ID_FILE):
        with open(GIST_ID_FILE, "r") as f:
            return f.read().strip()
    return None


def save_gist_id(gist_id):
    """Сохраняет ID Gist в файл (для следующего запуска)"""
    with open(GIST_ID_FILE, "w") as f:
        f.write(gist_id)


def load_seen_ids_from_gist(gist_id):
    """Загружает seen_ads.json из Gist"""
    headers = {"Authorization": f"token {GIST_TOKEN}"}
    try:
        resp = requests.get(f"{GIST_API}/{gist_id}", headers=headers, timeout=10)
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
    """Создаёт или обновляет Gist с seen_ads.json"""
    headers = {
        "Authorization": f"token {GIST_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    content = json.dumps(list(seen_ids), ensure_ascii=False, indent=2)
    gist_id = get_gist_id()

    payload = {
        "description": "Kufar.by seen ads IDs (auto-updated)",
        "public": False,  # приватный Gist
        "files": {
            "seen_ads.json": {
                "content": content
            }
        }
    }

    try:
        if gist_id:
            # Обновляем существующий
            resp = requests.patch(f"{GIST_API}/{gist_id}", json=payload, headers=headers, timeout=10)
            if resp.status_code == 200:
                print(f"[✅ Gist] Обновлён ({gist_id})")
                return gist_id
            else:
                print(f"[⚠️] Ошибка обновления Gist: {resp.status_code} — создаём новый")
        # Создаём новый
        resp = requests.post(GIST_API, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        new_id = resp.json()["id"]
        save_gist_id(new_id)
        print(f"[🆕 Gist] Создан новый: https://gist.github.com/{new_id}")
        return new_id
    except Exception as e:
        print(f"[❌] Ошибка работы с Gist: {e}")
        return None


def send_telegram(text, url):
    msg = f"🏠 Новое объявление!\n{text}\n🔗 {url}"
    try:
        resp = requests.post(
            TELEGRAM_API,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": msg,
                "disable_web_page_preview": False,
                "parse_mode": "HTML"
            },
            timeout=10
        )
        if resp.status_code == 200:
            print(f"[✅ Telegram] Отправлено: {url}")
        else:
            print(f"[⚠️ Telegram] {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[❌ Telegram] {e}")


def main():
    print(f"\n[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}] 🚀 Запуск Kufar Monitor")
    gist_id = get_gist_id() or "неизвестен"
    print(f"Текущий Gist ID: {gist_id}")

    seen_ids = load_seen_ids_from_gist(gist_id)
    print(f"Загружено {len(seen_ids)} просмотренных объявлений")

    try:
        response = requests.get(API_URL, params=PARAMS, timeout=15)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"[❌ API] Ошибка: {e}")
        return

    ads = data.get("ads", [])
    print(f"Получено {len(ads)} объявлений")

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
        text = f"<b>{title}</b>\n{price_str} | {location}{district_str}"

        send_telegram(text, url)
        seen_ids.add(ad_id)
        new_count += 1
        time.sleep(0.3)

    if new_count > 0:
        print(f"[💾] Сохраняем {len(seen_ids)} ID в Gist...")
        create_or_update_gist(seen_ids)
        print(f"[🎉] Отправлено {new_count} новых объявлений")
    else:
        print("[ℹ️] Новых объявлений нет")

    print("✅ Завершено")


if __name__ == "__main__":
    main()