import os
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

def main():
    print("🔄 Подключение к YouTube API...")
    youtube = get_youtube_service()

    print("📊 Подключение к Google Таблице...")
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    gc = gspread.authorize(creds)
    sheet = gc.open(SHEET_NAME).sheet1
    READY_VIDEOS_DIR = "ready_videos"
    
    records = sheet.get_all_records()
    
    for i, row in enumerate(records, start=2):
        # Ищем колонки по их заголовкам
        status = row.get('Status', '')
        
        if status == 'DONE':
            yt_title = row.get('YT Title', 'JobHack AI Shorts')
            yt_desc = row.get('YT Description', '#shorts #jobhackai')
            post_date = row.get('Post Date', '')
            
            iso_date = format_youtube_date(post_date)
            
            # Генератор сохраняет видео как `ready_videos/video_{row_index}.mp4`
            filename = f"ready_videos/video_{i}.mp4"
            
            if not os.path.exists(filename):
                print(f"❌ ОШИБКА: Файл {filename} не найден в папке! Пропускаем строку {i}.")
                continue
                
            print(f"\n🚀 НАЧИНАЕМ ЗАГРУЗКУ: {filename}")
            print(f"📅 Дата публикации: {iso_date}")
            
            body = {
                'snippet': {
                    'title': yt_title,
                    'description': yt_desc,
                    'tags': ['работа', 'hr', 'айти', 'jobhack', 'shorts', 'собеседование'],
                    'categoryId': '27' # 27 - Образование, 22 - Люди и Блоги
                },
                'status': {
                    'privacyStatus': 'private', # Обязательно private для отложенной публикации
                    'publishAt': iso_date,
                    'selfDeclaredMadeForKids': False
                }
            }
            
            try:
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
                
                # Обновляем статус в таблице на SCHEDULED
                # Предполагаем, что Status - это колонка E (индекс 5). Если F, то измени 5 на 6!
                sheet.update_cell(i, 5, "SCHEDULED") 
                
            except Exception as e:
                print(f"❌ ПРОИЗОШЛА ОШИБКА ПРИ ЗАГРУЗКЕ: {e}")

if __name__ == '__main__':
    main()