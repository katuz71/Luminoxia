import os
import time
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# --- НАСТРОЙКИ ---
SHEET_NAME = "Jobhakai"
WORKSHEET_NAME = "Biohack"
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
    """Превращает дату из таблицы в формат ISO 8601 (нужен для YouTube)"""
    date_str = str(date_str).strip()
    try:
        # Пытаемся распарсить формат 26.03.2026 18:00:00
        dt = datetime.datetime.strptime(date_str, "%d.%m.%Y %H:%M:%S")
    except ValueError:
        try:
            # Пытаемся распарсить формат 2026-03-26 18:00
            dt = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M")
        except ValueError:
            print(f"⚠️ Непонятный формат даты: {date_str}. Ставлю на завтра!")
            dt = datetime.datetime.now() + datetime.timedelta(days=1)
    
    # YouTube требует формат: 2026-03-26T18:00:00.000Z
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")

def upload_video(youtube, filename, title, description, iso_date):
    """Выполняет загрузку видео в YouTube."""
    if not os.path.exists(filename):
        raise FileNotFoundError(f"Файл {filename} не найден!")
        
    print(f"\n🚀 НАЧИНАЕМ ЗАГРУЗКУ: {filename}")
    print(f"📅 Дата публикации: {iso_date}")
    
    body = {
        'snippet': {
            'title': title,
            'description': description,
            'tags': ['biohacking', 'science', 'health', 'shorts'],
            'categoryId': '28' # Science & Technology
        },
        'status': {
            'privacyStatus': 'private', # Обязательно private для отложенной публикации
            'publishAt': iso_date,
            'selfDeclaredMadeForKids': False
        }
    }
    
    from googleapiclient.http import MediaFileUpload
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
    print("🤖 [YouTube Uploader] Проверка новых видео для загрузки...")
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    
    try:
        sheet = client.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
        values = sheet.get_all_values()
        youtube = get_youtube_service()
        
        debug_statuses = []
        found_task = False
        
        for index, row in enumerate(values, start=1):
            if index == 1:
                continue # пропускаем заголовки
                
            status = str(row[4]).strip().upper() if len(row) > 4 else ""
            debug_statuses.append(f"Строка {index}: '{status}'")
            
            # Берет только строки, где Status == "VIDEO_DONE" (5-я колонка)
            if status != "VIDEO_DONE":
                continue
                
            found_task = True
            
            # 3-я колонка = title (индекс 2), 4-я колонка = desc (индекс 3), 6-я колонка = дата (индекс 5)
            title = str(row[2]).strip() if len(row) > 2 else "Biohack Shorts"
            desc = str(row[3]).strip() if len(row) > 3 else "#shorts"
            date = str(row[5]).strip() if len(row) > 5 else datetime.datetime.now().strftime("%d.%m.%Y")
            
            iso_date = format_youtube_date(date)
            filename = f"assets/ready_videos/video_{index}.mp4"
            
            if not os.path.exists(filename):
                print(f"⚠️ Файл {filename} не найден, хотя статус VIDEO_DONE. Пропускаю...")
                continue
                
            print(f"✅ Найдено видео для загрузки: {filename} (Строка {index})")
            
            try:
                upload_video(youtube, filename, title, desc, iso_date)
                
                # При успехе меняет Status в 5-й колонке на "SCHEDULED"
                sheet.update_cell(index, 5, "SCHEDULED")
                print(f"🚀 Видео загружено! Статус обновлен на SCHEDULED.")
                break # Обязательно прерываем цикл, берем 1 видео за запуск
            except Exception as e:
                print(f"❌ Ошибка загрузки видео {filename}: {e}")
                break # Если ошибка, статус не менять, выходим
                
        if not found_task:
            print(f"🔍 Отладка статусов для VIDEO_DONE: {', '.join(debug_statuses)}")
                
    except Exception as e:
        print(f"❌ [GSheets] Ошибка доступа к таблице: {e}")

def main():
    while True:
        process_uploads()
        print("💤 Ожидание 10 минут...")
        time.sleep(600)

if __name__ == '__main__':
    main()