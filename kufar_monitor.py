import os
import json
import requests
import time
from datetime import datetime
from urllib.parse import quote

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GIST_TOKEN = os.getenv("GIST_TOKEN")
GIST_ID = os.getenv("GIST_ID")
AUTHORIZED_CHAT_IDS = set()
auth_raw = os.getenv("AUTHORIZED_CHAT_IDS", "")

if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GIST_TOKEN, GIST_ID]):
    raise ValueError("❌ Не заданы обязательные переменные")

if auth_raw:
    try:
        AUTHORIZED_CHAT_IDS = {str(x).strip() for x in auth_raw.split(",") if x.strip()}
        print(f"[🔐] Авторизовано {len(AUTHORIZED_CHAT_IDS)} чатов: {AUTHORIZED_CHAT_IDS}")
    except Exception as e:
        print(f"[⚠️] Ошибка парсинга AUTHORIZED_CHAT_IDS: {e}")


TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

def load_seen_ids():
    try:
        resp = requests.get(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"token {GIST_TOKEN}"},
            timeout=10
        )
        resp.raise_for_status()
        content = resp.json()["files"]["seen_ads.json"]["content"]
        return set(json.loads(content))
    except Exception as e:
        print(f"[⚠️] Ошибка загрузки Gist {GIST_ID}: {e}. Возвращаем пустой набор.")
        return set()


def save_seen_ids(seen_ids):
    try:
        clean_ids = sorted({str(x).strip() for x in seen_ids if x})
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={
                "Authorization": f"token {GIST_TOKEN}",
                "Accept": "application/vnd.github+json"
            },
            json={
                "files": {
                    "seen_ads.json": {
                        "content": json.dumps(clean_ids, ensure_ascii=False)
                    }
                }
            },
            timeout=10
        )
        resp.raise_for_status()
        print(f"[✅] Сохранено {len(clean_ids)} ID в Gist {GIST_ID}")
    except Exception as e:
        print(f"[❌] Ошибка сохранения Gist: {e}")

def send_notification(text, url, photo_url=None):
    if not AUTHORIZED_CHAT_IDS:
        print("[⚠️] Нет авторизованных чатов — пропускаем отправку")
        return

    for chat_id in AUTHORIZED_CHAT_IDS:
        try:
            if photo_url:
                resp = requests.post(
                    f"{TELEGRAM_API_BASE}/sendPhoto",
                    data={
                        "chat_id": chat_id,
                        "photo": photo_url,
                        "caption": text,
                        "parse_mode": "HTML",
                        "reply_markup": json.dumps({
                            "inline_keyboard": [[{"text": "📸 Открыть", "url": url}]]
                        })
                    },
                    timeout=20
                )
            else:
                resp = requests.post(
                    f"{TELEGRAM_API_BASE}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": f"{text}\n🔗 {url}",
                        "parse_mode": "HTML"
                    },
                    timeout=10
                )
            if resp.status_code == 200:
                print(f"[✅] Отправлено в чат {chat_id}")
            else:
                print(f"[❌] Ошибка в чат {chat_id}: {resp.status_code}")
        except Exception as e:
            print(f"[⚠️] Исключение при отправке в {chat_id}: {e}")
        time.sleep(0.3)


def fetch_ads():
    # Твой точный URL (GET-запрос!)
    base_url = "https://api.kufar.by/search-api/v2/search/rendered-paginated"
    params = {
        "cat": "1020",  # продажа квартир
        "cur": "USD",   # валюта
        "gtsy": "country-belarus~province-grodnenskaja_oblast",
        "gbx": "b%3A23.617241071925587%2C53.558095463687145%2C24.064247297511532%2C53.718464167366534",
        "gcm": "1",
        "prc": "r%3A0%2C35000",
        "saa": "r%3A15%2C1000",
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
    print(f"[{datetime.utcnow().isoformat()}] 🚀 Старт")
    seen_ids = load_seen_ids()

    ads = fetch_ads()
    if not ads:
        return

    new_count = 0
    for ad in ads:
        ad_id = str(ad.get("ad_id", "")).strip()
        if not ad_id or ad_id in seen_ids:
            continue

        # Данные
        title = ad.get("subject", "Без названия")
        price_byn_val = float(ad.get("price_byn", "0")) // 100
        price_usd_val = float(ad.get("price_usd", "0")) // 100

        ad_params = ad.get("ad_parameters", [])
        size = 0
        floor = 0
        all_number_floors = 0
        year_built = 0
        square_meter = 0
        for ad_param in ad_params:
            param_name = ad_param.get("p")
            if param_name == "size":
                size = ad_param.get("v", "")
            elif param_name == "floor":
                floor = ad_param.get("v", [])
            elif param_name == "re_number_floors":
                all_number_floors = ad_param.get("v", "")
            elif param_name == "year_built":
                year_built = ad_param.get("v", "")
            elif param_name == "square_meter":
                square_meter = ad_param.get("v", "")
        url = f"https://kufar.by/item/{ad_id}"

        # Форматирование
        price_str = f"{price_usd_val} USD ({price_byn_val} BYN) [{square_meter} USD за кв.м.]"
        base_text = f"<b>{title}</b>\n{price_str} | {size} кв.м. | {floor}/{all_number_floors} этаж | {year_built} год"
        caption = (base_text[:950] + "…") if len(base_text) > 1024 else base_text

        # Фото
        images = ad.get("images", [])
        photo_url = images[0].get("url", "") if images else ""

        # Отправка
        send_notification(caption, url, photo_url)

        seen_ids.add(ad_id)
        new_count += 1
        time.sleep(0.5)

    if new_count:
        save_seen_ids(seen_ids)
        print(f"[🎉] Отправлено {new_count} новых объявлений")
    else:
        print("[ℹ️] Новых объявлений нет")

    print("✅ Завершено")


if __name__ == "__main__":
    main()