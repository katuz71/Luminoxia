import os
import json
import random
import datetime
import logging
import requests
import html
import gspread
from openai import OpenAI
from dotenv import load_dotenv

# Setup logging with UTF-8 to prevent Windows cp1251 Unicode errors
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("content_generator.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ContentGenerator")

load_dotenv(override=True)

# Configuration keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip(" '\"\n\r")
WP_URL = os.getenv("WP_URL", "https://luminoxia.com").rstrip("/")
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "Luminoxia")
GOOGLE_WORKSHEET_NAME = os.getenv("GOOGLE_WORKSHEET_NAME", "Luminoxia")
GOOGLE_CREDENTIALS_FILE = "credentials.json"

# Наш секретный ключ от созданного бэкдора
WP_SECRET_TOKEN = "luminoxia_god_mode" 

client = OpenAI(api_key=OPENAI_API_KEY)

# --- CONFIGURATION & PROMPTS ---
TOPICS = [
    "How I made money by scraping B2B leads",
    "Secret automation tools your competitors use",
    "Stop wasting time: Automate your PC tasks",
    "How to build a client list for free in 5 minutes",
    "The web scraping trick that saves 10 hours a week"
]

def fetch_live_links_from_wp():
    """
    Автоматически парсит страницы и записи, исключая технический мусор.
    """
    logger.info("🌍 Подтягиваю актуальные ссылки с Luminoxia.com...")
    live_links = []
    
    # 🔥 ЧЕРНЫЙ СПИСОК (Слова-маркеры технических страниц)
    STOP_WORDS = ["privacy", "policy", "terms", "contact", "about", 
        "cart", "checkout", "my-account", "logout", "login", 
        "register", "lost-password", "reset", "pricing"]

    def is_valid_link(title, link):
        text_to_check = (title + " " + link).lower()
        for word in STOP_WORDS:
            if word in text_to_check:
                return False
        return True

    try:
        # Тянем страницы
        pages_res = requests.get(f"{WP_URL}/wp-json/wp/v2/pages?status=publish&per_page=50&_fields=title,link", timeout=10)
        if pages_res.status_code == 200:
            for page in pages_res.json():
                title = html.unescape(page.get('title', {}).get('rendered', 'Page'))
                link = page.get('link', '')
                if is_valid_link(title, link):
                    live_links.append(f"{title}: {link}")

        # Тянем статьи блога
        posts_res = requests.get(f"{WP_URL}/wp-json/wp/v2/posts?status=publish&per_page=50&_fields=title,link", timeout=10)
        if posts_res.status_code == 200:
            for post in posts_res.json():
                title = html.unescape(post.get('title', {}).get('rendered', 'Post'))
                link = post.get('link', '')
                if is_valid_link(title, link):
                    live_links.append(f"{title}: {link}")
                
    except Exception as e:
        logger.error(f"❌ Ошибка при получении ссылок с сайта: {e}")

    # Если после фильтрации или ошибки список пуст — даем железный фоллбэк
    if not live_links:
        logger.warning("Использую резервную ссылку (Homepage).")
        live_links = [f"Homepage: {WP_URL}/"]

    logger.info(f"✅ Успешно загружено {len(live_links)} чистых целевых ссылок.")
    return live_links


def generate_ai_content(topic, available_links):
    logger.info(f"--- STEP 1 & 2: Generating content for topic: '{topic}' ---")
    
    # ПИТОН САМ ВЫБИРАЕТ 1 ССЫЛКУ ИЗ ЖИВЫХ ССЫЛОК САЙТА
    selected_link = random.choice(available_links)
    logger.info(f"Selected link for this post: {selected_link}")

    # Извлекаем только URL для HTML-тега
    clean_url = selected_link.split(': ')[-1] if ': ' in selected_link else selected_link

    SYSTEM_PROMPT = f"""You are an Elite SEO Copywriter and Tech Indie Hacker. Generate highly engaging SEO content for Luminoxia.com.

CRITICAL SEO & LINK RULES:
1. FOCUS KEYWORD: Invent a 2-4 word focus SEO keyword. 
   - You MUST use this EXACT keyword in the VERY FIRST SENTENCE of the 'wp_post' HTML.
   - You MUST also use it in 'seo_title', 'meta_desc', and at least 4 other times in the body.
2. INTERNAL LINKING (STRICT LIMIT): 
   - You are allowed to use EXACTLY ONE URL in this entire generation: {clean_url}
   - Insert this EXACT link TWICE in the 'wp_post' HTML (once in the intro, once in the conclusion).
   - NEVER use the <a> HTML tag more than twice in the entire document. ZERO external links. ZERO other internal links. Do not hallucinate URLs.
3. LENGTH & STRUCTURE (ABSOLUTE MINIMUM 800 WORDS): AI models tend to write short text. You MUST overcome this by writing extremely detailed, long-form content. Use this exact structure:
   - Introduction: 3 long paragraphs explaining the core problem and the pain point (150+ words).
   - Main Body: 5 distinct H2 sections. EACH H2 section MUST contain at least 2 long paragraphs, detailed real-world examples, and a <ul> list (500+ words total).
   - Technical Deep Dive: A detailed H3 section explaining exactly how the automation works step-by-step (150+ words).
   - Conclusion: 2 long paragraphs summarizing the value and ending with the CTA link (100 words).

CRITICAL DESIGN RULES FOR 'wp_post':
1. Wrap the ENTIRE HTML content inside this exact div: 
<div style="font-family: 'Poppins', sans-serif; color: #333333; line-height: 1.6;">
2. Style your TWO link insertions strictly like this: 
<a href="{clean_url}" style="color: #0056b3; text-decoration: underline; font-weight: bold;">Check out the tool here</a>

CRITICAL YOUTUBE SHORTS RULES:
1. NEVER use the phrase "link in bio". It is forbidden.
2. ALWAYS use the exact phrase: "link in the channel profile".

JSON format to return:
- 'focus_keyword': Your chosen 2-4 word SEO keyword.
- 'screen_title': 2-5 words, ALL CAPS.
- 'script': 30-sec YouTube Shorts script. End with CTA: 'Get the tools at Luminoxia dot com, link in the channel profile!'. DO NOT USE THE WORD 'BIO'.
- 'yt_title': Clickable title + 1 emoji.
- 'yt_description': 2 sentences + tags (#webscraping #coldemail #tech #shorts).
- 'seo_title': Clickable SEO Title (around 60 chars) including the EXACT 'focus_keyword'.
- 'meta_desc': 150-character SEO description including the EXACT 'focus_keyword'.
- 'wp_post': 800+ word SEO blog post HTML. MUST be extremely detailed and long."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            response_format={ "type": "json_object" },
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Topic: {topic}"}
            ],
            temperature=0.7
        )
        content = json.loads(response.choices[0].message.content)
        logger.info("AI text generated successfully.")

        logger.info("Requesting image from DALL-E 3...")
        img_prompt = f"A modern, minimalist blog cover image about {topic}. IT, cybersecurity, automation, web scraping theme. Tech aesthetic, neon accents, no text."
        img_response = client.images.generate(
            model="dall-e-3",
            prompt=img_prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        content["image_url"] = img_response.data[0].url
        logger.info(f"Image URL generated: {content['image_url'][:50]}...")

        return content
    except Exception as e:
        logger.error(f"Error during OpenAI generation: {e}")
        return None


def publish_to_wordpress(data):
    logger.info("--- STEP 3: Publishing to WordPress via Custom API ---")
    custom_api_url = f"{WP_URL}/wp-json/luminoxia/v1/publish"
    
    payload = {
        "token": WP_SECRET_TOKEN,
        "title": data.get("yt_title", "New Tech Article"),
        "content": data.get("wp_post", ""),
        "image_url": data.get("image_url", ""),
        "focus_keyword": data.get("focus_keyword", ""),
        "meta_desc": data.get("meta_desc", ""),
        "seo_title": data.get("seo_title", data.get("yt_title", ""))
    }

    try:
        logger.info("Sending payload to our secret backdoor...")
        response = requests.post(custom_api_url, json=payload)
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"✅ Post successfully published! URL: {result.get('url')}")
            return True
        else:
            logger.error(f"❌ Failed to publish post. Status: {response.status_code}, Response: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ WordPress Custom API error: {e}")
        return False

def write_to_sheets(data):
    logger.info("--- STEP 4: Saving video data to Google Sheets ---")
    try:
        gc = gspread.service_account(filename=GOOGLE_CREDENTIALS_FILE)
        sh = gc.open(GOOGLE_SHEET_NAME)
        ws = sh.worksheet(GOOGLE_WORKSHEET_NAME)
        
        # Считаем дату: текущее время + 24 часа
        # Это обеспечит график "1 видео в день" автоматически
        publish_time = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%d.%m.%Y %H:%M:%S")

        row = [
            data.get("screen_title", ""),
            data.get("script", ""),
            data.get("yt_title", ""),
            data.get("yt_description", ""),
            "NEW",           # Статус
            publish_time     # Автоматическая дата публикации
        ]
        
        ws.append_row(row)
        logger.info(f"✅ Google Sheet updated! Scheduled for: {publish_time}")
        return True
    except Exception as e:
        logger.error(f"❌ Google Sheets error: {e}")
        return False

def main():
    if not OPENAI_API_KEY:
        logger.error("Missing OPENAI_API_KEY. Check .env")
        return

    # Шаг 0: Динамически собираем актуальные ссылки с сайта (с фильтрацией мусора)
    live_links = fetch_live_links_from_wp()

    selected_topic = random.choice(TOPICS)
    
    # Передаем живые ссылки в генератор
    content = generate_ai_content(selected_topic, live_links)
    
    if content:
        publish_to_wordpress(content)
        if write_to_sheets(content):
            logger.info("🚀 SUPER-GENERATOR RUN COMPLETED SUCCESSFULLY! 🚀")
        else:
            logger.error("Failed to sync with Google Sheets.")
    else:
        logger.error("Content generation failed.")

if __name__ == "__main__":
    main()