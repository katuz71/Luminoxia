import os
import time
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv

load_dotenv()

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN") 
TG_CHANNEL_ID = os.getenv("TG_CHANNEL_ID") # например, @biohack_science
GOOGLE_CREDENTIALS_FILE = "credentials.json"
GOOGLE_SHEET_NAME = "Biohack_Shorts_DB"

def send_telegram_message(text):
    text = text.replace("Хочешь взломать свой потенциал? Ссылка на исследования и мой Телеграм-канал — в описании профиля. Заходи!", "").strip()
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHANNEL_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ [Telegram] Ошибка публикации: {e}")
        return False

def process_tg_autoposting():
    print("🤖 [TG Autoposter] Проверка новых постов...")
    
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    
    try:
        sheet = client.open("Jobhakai").worksheet("Biohack")
        values = sheet.get_all_values()
        
        debug_statuses = []
        found_task = False
        
        for index, row in enumerate(values, start=1):
            if index == 1:
                continue # Пропускаем заголовки
                
            status = str(row[4]).strip().upper() if len(row) > 4 else ""
            tg_text = str(row[6]).strip() if len(row) > 6 else ""
            debug_statuses.append(f"Строка {index}: '{status}'")
            
            if status == "NEW" and tg_text:
                found_task = True
                print(f"✅ Найден готовый пост (Строка {index}). Публикую...")
                
                try:
                    if send_telegram_message(tg_text):
                        sheet.update_cell(index, 5, "POSTED") # 5 - основной Status
                        sheet.update_cell(index, 8, "SUCCESS") # 8 - лог TG
                        print(f"🚀 Пост опубликован! Статус обновлен. Остановка до следующего цикла.")
                        break # СТРОГО ВЫХОДИМ, ЧТОБЫ ОБРАБАТЫВАТЬ ТОЛЬКО 1 СТРОКУ ЗА РАЗ!
                    else:
                        print("⚠️ Ошибка API Telegram. Статус не изменен.")
                        break
                except Exception as e:
                    print(f"❌ Ошибка публикации: {e}. Статус не изменен.")
                    break
                    
        if not found_task:
            print(f"🔍 Отладка статусов для NEW: {', '.join(debug_statuses)}")

    except Exception as e:
        print(f"❌ [GSheets] Ошибка доступа к таблице: {e}")

if __name__ == "__main__":
    while True:
        process_tg_autoposting()
        print("💤 Ожидание 1 час...")
        time.sleep(3600)