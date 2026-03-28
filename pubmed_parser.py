import os
import json
import time
import gspread
from datetime import datetime
from openai import OpenAI
from Bio import Entrez
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv

# 1. override=True принудительно читает из .env, игнорируя старые системные ключи
load_dotenv(override=True)

# 2. Жестко отрезаем случайные пробелы, кавычки и переносы строк
raw_key = os.getenv("OPENAI_API_KEY")
OPENAI_API_KEY = raw_key.strip(" '\"\n\r") if raw_key else None

# --- СИСТЕМА ДИАГНОСТИКИ (покажет, что реально видит Python) ---
if OPENAI_API_KEY:
    print(f"🔍 [DEBUG] Ключ OpenAI загружен: {OPENAI_API_KEY[:10]}...{OPENAI_API_KEY[-4:]} (Длина: {len(OPENAI_API_KEY)} симв.)")
else:
    print("❌ [DEBUG] КЛЮЧ НЕ НАЙДЕН В ФАЙЛЕ .env!")

# --- КОНФИГУРАЦИЯ ---
ENTREZ_EMAIL = os.getenv("ENTREZ_EMAIL", "your_email@example.com")
GOOGLE_CREDENTIALS_FILE = "credentials.json"
GOOGLE_SHEET_NAME = "Biohack_Shorts_DB" # Твоя таблица
WORKSHEET_NAME = "Biohack"              # Твоя новая вкладка

# Максимально широкие и вирусные темы (Top of Funnel)
SEARCH_TERMS = [
    "dopamine detox focus",       # Как вернуть концентрацию
    "circadian rhythm sleep hack", # Идеальный сон
    "testosterone natural boost",  # Гормоны и энергия
    "glucose spikes longevity",    # Сахар и старение
    "nootropics cognitive function", # Таблетки для ума
    "intermittent fasting brain",  # Голодание и мозг
    "cold exposure mitochondria"   # Ледяной душ и энергия
]
MAX_ARTICLES = 20  # Увеличим запас для пропуска уже обработанных

Entrez.email = ENTREZ_EMAIL
client = OpenAI(api_key=OPENAI_API_KEY)

def load_history():
    if not os.path.exists("parsed_history.txt"):
        return set()
    with open("parsed_history.txt", "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def save_to_history(title):
    with open("parsed_history.txt", "a", encoding="utf-8") as f:
        f.write(title + "\n")

def fetch_pubmed_articles(queries, max_results=3):
    print("🧠 [PubMed] Ищу свежие исследования...")
    query = " OR ".join([f"({q}[Title/Abstract])" for q in queries])
    search_query = f"({query}) AND (\"last 1 years\"[PDat])"
    
    try:
        handle = Entrez.esearch(db="pubmed", term=search_query, retmax=max_results, sort="date")
        record = Entrez.read(handle)
        handle.close()
        
        id_list = record["IdList"]
        if not id_list:
            return []
            
        handle = Entrez.efetch(db="pubmed", id=id_list, retmode="xml")
        articles = Entrez.read(handle)
        handle.close()
        
        results = []
        for article in articles['PubmedArticle']:
            medline = article['MedlineCitation']['Article']
            title = medline.get('ArticleTitle', '')
            abstract_list = medline.get('Abstract', {}).get('AbstractText', [])
            abstract = " ".join([str(a) for a in abstract_list]) if abstract_list else ""
            
            if title and abstract:
                results.append({"title": title, "abstract": abstract})
        return results
    except Exception as e:
        print(f"❌ [PubMed] Ошибка парсинга: {e}")
        return []

def generate_content(article):
    """Генерирует сценарий Shorts И текст поста для Telegram."""
    print(f"🤖 [OpenAI] Генерирую контент для: {article['title'][:30]}...")
    
    prompt = f"""
    Ты АГРЕССИВНЫЙ БИОХАКИНГ-ПРОДЮСЕР. Твоя цель — сделать из скучной научной статьи вирусный контент.
    Стиль: дерзкий, экспертный, но простой. Убери "исследование показало", замени на "ученые нашли способ взломать...".
    
    ВАЖНЫЕ ПРАВИЛА ДЛЯ ТЕКСТА:
    1. ЕСТЕСТВЕННОСТЬ И ПУНКТУАЦИЯ: Пиши текст живым разговорным языком. Избегай сложных деепричастных оборотов, которые робот читает "на одном дыхании". ОБЯЗАТЕЛЬНО используй тире (—) для логических пауз и многоточия (...) там, где нужно заинтриговать. Это поможет нейроголосу звучать по-человечески.
    2. ТЕРМИНЫ: Никогда не используй аббревиатуры "ТГ" или "TG". Всегда пиши полностью: "Телеграм-канал". Вместо сложных латинских названий (когда это возможно) используй понятные простому человеку аналоги.
    3. ЗАЩИТА ОТ ДУБЛЕЙ: КРИТИЧЕСКИ ВАЖНО: Текст в screen_title и script НЕ ДОЛЖЕН совпадать! screen_title — это только короткая затравка из 3-5 слов, а script — это полный сценарий.
    4. ПРАВИЛО TELEGRAM CTA: Пост для Telegram должен заканчиваться СТРОГО вопросом к аудитории для обсуждения в комментариях. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО добавлять в Telegram-пост призывы подписаться на канал, переходить по ссылкам в профиле или писать фразу 'Хочешь взломать свой потенциал...'. Этот призыв нужен ТОЛЬКО для поля script.
    
    Данные статьи (PubMed):
    Title: {article['title']}
    Abstract: {article['abstract']}
    
    Сгенерируй ответ СТРОГО В ФОРМАТЕ JSON по жесткой логике:
    КРЮЧОК (Hook): Начни с проблемы, которая бесит (плохой сон, лень, туман в голове).
    НАУКА: Вытащи из статьи ОДИН конкретный факт или цифру, которые удивляют. Не пересказывай всю статью!
    ПРАКТИКА: Практический совет, что юзер должен сделать СЕГОДНЯ (например: "не пей кофе первые 90 минут").
    ПРИЗЫВ К ДЕЙСТВИЮ (CTA): Сценарий ОБЯЗАТЕЛЬНО должен заканчиваться фразой: "Хочешь взломать свой потенциал? Ссылка на исследования и мой Телеграм-канал — в описании профиля. Заходи!"
    
    "screen_title": "СУПЕР-КОРОТКИЙ кликбейтный хук (максимум 3-6 слов). Писать КАПСОМ. Это просто заголовок для экрана, а не весь текст! (Пример: КАК ВЗЛОМАТЬ СОН?)",
    "script": "Длинный, подробный текст для диктора. Написан разговорным языком. Использовать тире (—) и многоточия (...) для естественных пауз нейроголоса. Поле script ОБЯЗАТЕЛЬНО должно всегда заканчиваться фразой: Хочешь взломать свой потенциал? Ссылка на исследования и мой Телеграм-канал — в описании профиля. Заходи!",
    "col3": "Название для YouTube (Кликабельное + 1 эмодзи)",
    "col4": "Описание для YouTube (1 предложение + хештеги #наука #биохакинг #shorts)",
    "tg_post": "Текст поста для Telegram (100-150 слов). СТРУКТУРА: 1. ПЕРВАЯ СТРОКА: Короткий кликбейтный заголовок ЗАГЛАВНЫМИ БУКВАМИ (без эмодзи). 2. ПУСТАЯ СТРОКА. 3. ОСНОВНОЙ ТЕКСТ: 3-4 коротких абзаца (Крючок -> Научный факт -> Практический совет). 4. ПРАВИЛО ЭМОДЗИ: Строго 1 тематический эмодзи В НАЧАЛЕ каждого абзаца (внутри предложений запрещены). 5. ПРАВИЛО АКЦЕНТОВ: КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНЫ любые звездочки (**). Только ЗАГЛАВНЫЕ БУКВЫ для выделения 1-2 главных слов на абзац. 6. ПУСТАЯ СТРОКА между каждым абзацем. 7. ФИНАЛ: Провокационный вопрос, выделенный пустой строкой сверху."
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            response_format={ "type": "json_object" },
            messages=[
                {"role": "system", "content": "Ты агрессивный биохакинг-продюсер. Дерзкий и экспертный. Отвечаешь только валидным JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"❌ [OpenAI] Ошибка генерации: {e}")
        return None

def write_to_google_sheets(data):
    print("📊 [GSheets] Записываю в базу данных...")
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
    sheet_client = gspread.authorize(creds)
    
    try:
        sheet = sheet_client.open("Jobhakai").worksheet("Biohack")
        # Формируем строку из 8 колонок (под английские заголовки)
        row = [
            data.get("screen_title", data.get("col1", "")),
            data.get("script", data.get("col2", "")),
            data.get("col3", ""),
            data.get("col4", ""),
            "NEW",              # 5: Status (для YouTube)
            datetime.now().strftime("%d.%m.%Y"), # 6: Date
            data.get("tg_post", ""), # 7: TG Post Text
            ""                  # 8: TG Status (пока пусто)
        ]
        sheet.append_row(row)
        print("✅ Успешно добавлено!")
    except Exception as e:
        print(f"❌ [GSheets] Ошибка записи: {e}")

def main():
    print("🚀 Запуск конвейера PubMed -> OpenAI -> GSheets")
    history = load_history()
    articles = fetch_pubmed_articles(SEARCH_TERMS, max_results=MAX_ARTICLES)
    
    if not articles:
        print("🤷‍♂️ Новых статей не найдено.")
        return

    for article in articles:
        if article['title'] in history:
            print(f"⏭ Статья '{article['title'][:30]}...' уже была в истории. Пропускаю.")
            continue
            
        content_data = generate_content(article)
        if content_data:
            write_to_google_sheets(content_data)
            save_to_history(article['title'])
            print(f"✅ Статья добавлена в очередь! Остановка до следующего запуска.")
            break
    else:
        print("🤷‍♂️ Все найденные статьи уже есть в истории. Нужно больше результатов или другие ключи.")

if __name__ == "__main__":
    main()