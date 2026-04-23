import os
import time
import datetime
import traceback
import gspread
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Загружаем переменные из .env
load_dotenv(override=True)

# --- НАСТРОЙКИ ---
# Приоритет берем из .env, если нет — используем Jobhakai
SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "Jobhakai")
WORKSHEET_NAME = os.getenv("GOOGLE_WORKSHEET_NAME", "Luminoxia")
CREDENTIALS_FILE = "credentials.json"          # Ключ от таблиц
CLIENT_SECRETS_FILE = "client_secrets.json"    # Ключ от YouTube
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def get_youtube_service():
    """Авторизация в YouTube (при первом запуске откроет браузер)"""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', YOUTUBE_SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, YOUTUBE_SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('youtube', 'v3', credentials=creds)

def format_youtube_date(date_str):
    """Превращает дату из таблицы в формат ISO 8601 для YouTube"""
    date_str = str(date_str).strip()
    try:
        dt = datetime.datetime.strptime(date_str, "%d.%m.%Y %H:%M:%S")
    except ValueError:
        try:
            dt = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M")
        except ValueError:
            print(f"⚠️ Непонятный формат даты: {date_str}. Ставлю на завтра!")
            dt = datetime.datetime.now() + datetime.timedelta(days=1)
    
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")

def upload_video(youtube, filename, title, description, iso_date):
    """Выполняет загрузку видео в YouTube."""
    if not os.path.exists(filename):
        raise FileNotFoundError(f"Файл {filename} не найден!")
        
    print(f"\n🚀 НАЧИНАЕМ ЗАГРУЗКУ: {filename}")
    print(f"📅 Запланировано на: {iso_date}")
    
    body = {
        'snippet': {
            'title': title,
            'description': description,
            'tags': ['webscraping', 'b2b leads', 'automation', 'lead generation', 'shorts', 'luminoxia'],
            'categoryId': '28' # Science & Technology
        },
        'status': {
            'privacyStatus': 'private',
            'publishAt': iso_date,
            'selfDeclaredMadeForKids': False
        }
    }
    
    insert_request = youtube.videos().insert(
        part=','.join(body.keys()),
        body=body,
        media_body=MediaFileUpload(filename, chunksize=-1, resumable=True)
    )
    
    response = None
    while response is None:
        status_upload, response = insert_request.next_chunk()
        if status_upload:
            print(f"⏳ Загружено: {int(status_upload.progress() * 100)}%")
    
    print(f"✅ ВИДЕО УСПЕШНО ЗАГРУЖЕНО! ID: {response['id']}")
    return response['id']

def process_uploads():
    print(f"🤖 [YouTube Uploader] Проверка новых видео в таблице '{SHEET_NAME}'...")
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"❌ Ошибка: Файл {CREDENTIALS_FILE} не найден!")
        return

    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    
    try:
        sheet = client.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
        values = sheet.get_all_values()
        youtube = get_youtube_service()
        
        found_task = False
        
        for index, row in enumerate(values, start=1):
            if index == 1: continue 
                
            status = str(row[4]).strip().upper() if len(row) > 4 else ""
            
            if status != "VIDEO_DONE":
                continue
                
            found_task = True
            
            title = str(row[2]).strip() if len(row) > 2 else "Luminoxia Tech Update"
            desc = str(row[3]).strip() if len(row) > 3 else "#shorts #automation"
            date = str(row[5]).strip() if len(row) > 5 else ""
            
            iso_date = format_youtube_date(date)
            filename = f"assets/ready_videos/video_{index}.mp4"
            
            if not os.path.exists(filename):
                print(f"⚠️ Файл {filename} не найден. Пропускаю...")
                continue
                
            print(f"✅ Найдено готовое видео: {filename} (Строка {index})")
            
            try:
                # 1. Загружаем
                video_id = upload_video(youtube, filename, title, desc, iso_date)
                
                # 2. Обновляем статус в таблице с защитой от лагов
                if video_id:
                    time.sleep(2) # Пауза перед записью
                    try:
                        sheet.update_cell(index, 5, "SCHEDULED")
                        print(f"🚀 Статус обновлен на SCHEDULED (строка {index})")
                    except Exception as e_sheet:
                        print(f"⚠️ Ошибка записи статуса: {e_sheet}. Пробую еще раз...")
                        time.sleep(5)
                        sheet.update_cell(index, 5, "SCHEDULED")
                        print(f"🚀 Статус обновлен со второй попытки.")
                
                break # По одному за раз
                
            except Exception as e:
                print(f"❌ Ошибка при обработке строки {index}:")
                traceback.print_exc()
                break
                
        if not found_task:
            print("🔍 Нет видео со статусом VIDEO_DONE.")
                
    except Exception as e:
        print(f"❌ Критическая ошибка GSheets:")
        traceback.print_exc()

def main():
    process_uploads()
    print("🏁 Цикл загрузки завершен.")

if __name__ == '__main__':
    main()