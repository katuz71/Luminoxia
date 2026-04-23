# -*- coding: utf-8 -*-
"""
Universal Content Generator for Luminoxia & BotProof.
Generates SEO-optimized blog posts and video data for the pipeline.
Configuration is driven entirely by .env — one script, two projects.
"""

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
from oauth2client.service_account import ServiceAccountCredentials

# ── Logging ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("content_generator.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ContentGenerator")

# ── Config from .env ─────────────────────────────────────
load_dotenv(override=True)

OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY", "").strip(" '\"\n\r")
WP_URL           = os.getenv("WP_URL", "").rstrip("/")
WP_USER          = os.getenv("WP_USER", "")
WP_APP_PASS      = os.getenv("WP_APP_PASS", "")
SHEET_NAME       = os.getenv("GOOGLE_SHEET_NAME", "Jobhakai")
WORKSHEET_NAME   = os.getenv("GOOGLE_WORKSHEET_NAME", "Luminoxia")
WP_CATEGORY_ID   = int(os.getenv("WP_CATEGORY_ID", "1"))
NICHE            = os.getenv("NICHE", "b2b-lead-generation")
CREDENTIALS_FILE = "credentials.json"

client = OpenAI(api_key=OPENAI_API_KEY)

# ── Niche-specific topic seeds ───────────────────────────
# GPT will use these as inspiration to generate unique long-tail topics
TOPIC_SEEDS = {
    "b2b-lead-generation": [
        "web scraping for B2B lead generation",
        "cold email outreach automation",
        "Google Maps scraping for local leads",
        "email verification and list cleaning",
        "building prospect lists without paid tools",
        "LinkedIn scraping for sales teams",
        "data enrichment for outbound sales",
        "cold email deliverability and spam filters",
        "lead scoring with scraped data",
        "competitor analysis through web scraping",
        "extracting decision-maker contacts",
        "automating follow-up email sequences",
        "B2B sales pipeline automation",
        "scraping business directories for leads",
        "ROI of automated lead generation vs manual"
    ],
    "ai-for-business": [
        "AI chatbots replacing customer support teams",
        "automating business workflows with AI agents",
        "cost savings from AI automation in small business",
        "AI-powered lead qualification",
        "using GPT for automated content creation",
        "AI voice agents for appointment booking",
        "replacing manual data entry with AI",
        "AI tools for small business owners",
        "building no-code AI automations",
        "AI customer service vs human support costs",
        "predictive analytics for business decisions",
        "automating social media with AI",
        "AI-powered CRM and sales automation",
        "how AI agents handle repetitive business tasks",
        "ROI of implementing AI in operations"
    ]
}

# ── Helper: get published post titles to avoid duplicates ─
def get_published_titles():
    """Fetch all published post titles from WordPress to prevent topic duplication."""
    titles = set()
    try:
        page = 1
        while True:
            resp = requests.get(
                f"{WP_URL}/wp-json/wp/v2/posts",
                params={"per_page": 100, "page": page, "status": "publish,draft", "_fields": "title"},
                auth=(WP_USER, WP_APP_PASS),
                timeout=15
            )
            if resp.status_code != 200 or not resp.json():
                break
            for post in resp.json():
                titles.add(html.unescape(post["title"]["rendered"]).lower().strip())
            page += 1
    except Exception as e:
        logger.warning(f"Could not fetch existing titles: {e}")
    logger.info(f"📚 Found {len(titles)} existing posts on WordPress.")
    return titles


# ── Helper: get live internal links for cross-linking ─────
def fetch_live_links():
    """Fetch published pages and posts for internal linking."""
    links = []
    STOP_WORDS = ["privacy", "policy", "terms", "contact", "about",
                  "cart", "checkout", "my-account", "logout", "login",
                  "register", "lost-password", "reset", "pricing",
                  "dashboard", "account", "user", "members", "password-reset"]

    def is_valid(title, link):
        text = (title + " " + link).lower()
        return not any(w in text for w in STOP_WORDS)

    try:
        for endpoint in ["pages", "posts"]:
            resp = requests.get(
                f"{WP_URL}/wp-json/wp/v2/{endpoint}",
                params={"status": "publish", "per_page": 100, "_fields": "title,link"},
                timeout=10
            )
            if resp.status_code == 200:
                for item in resp.json():
                    title = html.unescape(item.get("title", {}).get("rendered", ""))
                    link = item.get("link", "")
                    if is_valid(title, link):
                        links.append({"title": title, "url": link})
    except Exception as e:
        logger.error(f"Error fetching links: {e}")

    if not links:
        links = [{"title": "Homepage", "url": f"{WP_URL}/"}]

    logger.info(f"🔗 Loaded {len(links)} internal links for cross-linking.")
    return links


# ── Step 1: Generate unique topic via GPT ─────────────────
def generate_unique_topic(existing_titles):
    """Ask GPT to create a unique long-tail SEO topic that hasn't been covered."""
    seeds = TOPIC_SEEDS.get(NICHE, TOPIC_SEEDS["b2b-lead-generation"])
    seed_sample = random.sample(seeds, min(5, len(seeds)))

    prompt = f"""You are an SEO strategist. Generate ONE unique blog post topic for the niche: "{NICHE}".

INSPIRATION SEEDS (use as starting points, NOT exact topics):
{json.dumps(seed_sample)}

ALREADY PUBLISHED (do NOT repeat these or anything too similar):
{json.dumps(list(existing_titles)[:30])}

RULES:
1. The topic must target a specific LONG-TAIL KEYWORD (4-8 words) that someone would Google.
2. The topic must be EVERGREEN (useful for years, not news-dependent).
3. Focus on actionable, how-to, or comparison angles.
4. Return ONLY a JSON object: {{"topic": "...", "target_keyword": "..."}}
"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are an SEO expert. Reply only in valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.9
        )
        data = json.loads(resp.choices[0].message.content)
        logger.info(f"🎯 Generated topic: {data.get('topic')} | Keyword: {data.get('target_keyword')}")
        return data
    except Exception as e:
        logger.error(f"Topic generation failed: {e}")
        return None


# ── Step 2: Generate full SEO article + video data ────────
def generate_content(topic_data, internal_links):
    """Generate a full SEO blog post + YouTube Shorts data."""
    topic = topic_data["topic"]
    keyword = topic_data["target_keyword"]

    # Pick 2 random internal links for cross-linking
    selected_links = random.sample(internal_links, min(2, len(internal_links)))
    links_context = "\n".join([f"- {l['title']}: {l['url']}" for l in selected_links])

    system_prompt = f"""You are an elite SEO copywriter for Luminoxia.com — a B2B toolkit and AI automation platform.

TARGET KEYWORD: "{keyword}"
You MUST use this EXACT keyword in:
- The VERY FIRST sentence of the blog post
- The seo_title
- The meta_desc
- At least 4 more times naturally throughout the body

INTERNAL LINKS (use EXACTLY these 2 links, once each, naturally in the text):
{links_context}

BLOG POST RULES:
1. Minimum 1000 words. Write detailed, expert-level content.
2. Structure: Introduction (3 paragraphs) → 5 H2 sections (each with 2+ paragraphs and examples) → Technical deep-dive H3 → Conclusion with CTA
3. Wrap all HTML in: <div style="font-family: 'Poppins', sans-serif; color: #333; line-height: 1.8;">
4. Style links as: <a href="URL" style="color: #0056b3; text-decoration: underline; font-weight: bold;">anchor text</a>
5. Use <ul> lists inside H2 sections where appropriate
6. NO emoji in the blog post body
7. Write in English

YOUTUBE SHORTS RULES:
1. script: 30-40 second narrator script, conversational, end with "Link in the channel profile — check it out!"
2. screen_title: 2-5 words, ALL CAPS, punchy hook
3. NEVER use "link in bio"

Return JSON:
- focus_keyword: the exact target keyword
- seo_title: SEO title ~60 chars including keyword
- meta_desc: ~155 chars including keyword  
- wp_post: full HTML blog post (1000+ words)
- screen_title: short screen title for video
- script: YouTube Shorts narrator script
- yt_title: clickable YouTube title + 1 emoji
- yt_description: 2 sentences + hashtags"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Write about: {topic}"}
            ],
            temperature=0.7
        )
        data = json.loads(resp.choices[0].message.content)
        logger.info("✅ Content generated successfully.")

        # Generate featured image
        logger.info("🎨 Generating featured image...")
        img_resp = client.images.generate(
            model="dall-e-3",
            prompt=f"Modern minimalist blog header image about {topic}. Tech aesthetic, clean design, no text on image.",
            size="1792x1024",
            quality="standard",
            n=1
        )
        data["image_url"] = img_resp.data[0].url
        logger.info(f"🖼️ Image generated.")

        return data
    except Exception as e:
        logger.error(f"Content generation failed: {e}")
        return None


# ── Step 3: Publish to WordPress via REST API ─────────────
def publish_to_wordpress(data):
    """Publish post via custom WordPress snippet endpoint."""
    logger.info("📝 Publishing to WordPress...")
    WP_SECRET = os.getenv("WP_SECRET_TOKEN", "Xk9mW2vLpQ7nR4jTfB8sYd3hA6wZcE1gUoN5iMxKvJ0qDrFy2b")
    payload = {
        "token": WP_SECRET,
        "title": data.get("seo_title", "New Article"),
        "content": data.get("wp_post", ""),
        "image_url": data.get("image_url", ""),
        "focus_keyword": data.get("focus_keyword", ""),
        "meta_desc": data.get("meta_desc", ""),
        "seo_title": data.get("seo_title", ""),
        "category_id": WP_CATEGORY_ID
    }
    try:
        resp = requests.post(f"{WP_URL}/wp-json/luminoxia/v1/publish", json=payload, timeout=60)
        if resp.status_code == 200:
            result = resp.json()
            logger.info(f"✅ Published! URL: {result.get('url')}")
            return True
        else:
            logger.error(f"❌ Publish failed: {resp.status_code} — {resp.text}")
            return False
    except Exception as e:
        logger.error(f"❌ WordPress error: {e}")
        return False


# ── Step 4: Write video data to Google Sheets ─────────────
def write_to_sheets(data):
    """Append video row to Google Sheets for shorts_maker pipeline."""
    logger.info("📊 Writing to Google Sheets...")
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        gc = gspread.authorize(creds)
        ws = gc.open(SHEET_NAME).worksheet(WORKSHEET_NAME)

        publish_time = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%d.%m.%Y %H:%M:%S")

        row = [
            data.get("screen_title", ""),
            data.get("script", ""),
            data.get("yt_title", ""),
            data.get("yt_description", ""),
            "NEW",
            publish_time
        ]
        ws.append_row(row)
        logger.info(f"✅ Sheet updated! Video scheduled for: {publish_time}")
        return True
    except Exception as e:
        logger.error(f"❌ Google Sheets error: {e}")
        return False


# ── Main ──────────────────────────────────────────────────
def main():
    if not OPENAI_API_KEY:
        logger.error("❌ OPENAI_API_KEY not set in .env")
        return
    if not WP_URL:
        logger.error("❌ WP_URL not set in .env")
        return

    # 1. Get existing posts to avoid duplicates
    existing_titles = get_published_titles()

    # 2. Generate unique topic
    topic_data = generate_unique_topic(existing_titles)
    if not topic_data:
        return

    # 3. Get internal links for cross-linking
    internal_links = fetch_live_links()

    # 4. Generate content
    content = generate_content(topic_data, internal_links)
    if not content:
        return

    # 5. Publish to WordPress
    publish_to_wordpress(content)

    # 6. Write video data to sheets
    if write_to_sheets(content):
        logger.info("🚀 CONTENT GENERATOR RUN COMPLETED SUCCESSFULLY!")
    else:
        logger.error("Pipeline completed with errors.")


if __name__ == "__main__":
    main()
