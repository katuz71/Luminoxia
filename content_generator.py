# -*- coding: utf-8 -*-
"""
Universal Content Generator for Luminoxia & BotProof.
Generates SEO-optimized blog posts and video data for the pipeline.
Topics are read from the TopicMap tab in Google Sheets.
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

    logger.info(f"Loaded {len(links)} internal links for cross-linking.")
    return links


# ── Step 1: Get next topic from TopicMap ──────────────────
def get_next_topic_from_map():
    """Read the next TODO topic from TopicMap tab in Google Sheets."""
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        gc = gspread.authorize(creds)
        ws = gc.open(SHEET_NAME).worksheet("TopicMap")

        rows = ws.get_all_records()
        for i, row in enumerate(rows):
            row_category = row.get("Category", "").strip().lower().replace(" ", "-")
            niche_map = {
                "b2b-lead-generation": "b2b-lead-generation",
                "ai-for-business": "ai-for-business"
            }
            mapped_niche = niche_map.get(row_category, row_category)

            if mapped_niche == NICHE and row.get("Status", "").strip().upper() == "TODO":
                cell_row = i + 2
                ws.update_cell(cell_row, 5, "IN_PROGRESS")

                topic = row.get("Topic", "").strip()
                keyword = row.get("Keyword", "").strip()
                topic_type = row.get("Type", "CLUSTER").strip().upper()

                logger.info(f"TopicMap: [{topic_type}] {topic} | Keyword: {keyword}")
                return {
                    "topic": topic,
                    "target_keyword": keyword,
                    "type": topic_type,
                    "sheet_row": cell_row
                }

        logger.warning("No TODO topics found in TopicMap for this niche.")
        return None
    except Exception as e:
        logger.error(f"TopicMap read error: {e}")
        return None


def mark_topic_done(sheet_row):
    """Update TopicMap status to DONE after successful publish."""
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        gc = gspread.authorize(creds)
        ws = gc.open(SHEET_NAME).worksheet("TopicMap")
        ws.update_cell(sheet_row, 5, "DONE")
        logger.info(f"TopicMap row {sheet_row} marked DONE.")
    except Exception as e:
        logger.error(f"Could not update TopicMap: {e}")


# ── Step 2: Generate full SEO article + video data ────────
def generate_content(topic_data, internal_links):
    """Generate a full SEO blog post + YouTube Shorts data."""
    topic = topic_data["topic"]
    keyword = topic_data["target_keyword"]
    topic_type = topic_data.get("type", "CLUSTER")

    selected_links = random.sample(internal_links, min(5, len(internal_links)))
    links_list = []
    for l in selected_links:
        links_list.append("- " + l["title"] + ": " + l["url"])
    links_context = "\n".join(links_list)

    if topic_type == "PILLAR":
        word_count = "2500"
        structure_instructions = (
            "Structure the article as follows:\n"
            "- Opening hook paragraph (start with a surprising stat or bold claim, use the keyword in the first sentence)\n"
            "- Table of Contents (HTML anchor links to each H2)\n"
            "- 7-8 H2 sections, each containing:\n"
            "  * 3-4 paragraphs of substantive analysis (not filler)\n"
            "  * At least one specific example, case study, or data point per section\n"
            "  * Where relevant, a comparison table (<table> HTML) or step-by-step numbered list\n"
            "- 2 H3 sub-sections under the most complex H2s for deep-dives\n"
            '- H2 "Frequently Asked Questions" with 5 questions using <h3> for each question\n'
            '- H2 "Conclusion" with actionable summary and CTA to Luminoxia tools'
        )
    else:
        word_count = "1500"
        structure_instructions = (
            "Structure the article as follows:\n"
            "- Opening hook paragraph (start with a surprising stat or bold claim, use the keyword in the first sentence)\n"
            "- 5-6 H2 sections, each containing:\n"
            "  * 2-3 paragraphs of substantive analysis (not filler)\n"
            "  * At least one specific example, data point, or actionable step per section\n"
            "- 1 comparison table (<table> HTML) in the most relevant section\n"
            "- 1 H3 sub-section for a technical deep-dive or case study\n"
            '- H2 "Conclusion" with actionable takeaway and CTA to Luminoxia tools'
        )

    kw_count_target = "8-12" if topic_type == "PILLAR" else "5-8"

    system_prompt = (
        "You are a senior B2B content strategist writing for Luminoxia.com — "
        "a platform offering lead generation tools (Google Maps Scraper, Email Finder, "
        "Bulk Email Validator) and AI automation solutions.\n\n"
        "TARGET KEYWORD: \"" + keyword + "\"\n"
        "ARTICLE TOPIC: \"" + topic + "\"\n"
        "ARTICLE TYPE: " + topic_type + "\n\n"
        "=== KEYWORD PLACEMENT (CRITICAL FOR SEO) ===\n"
        "Place the EXACT keyword \"" + keyword + "\" in:\n"
        "1. The very FIRST sentence of the article\n"
        "2. At least one H2 heading (naturally worded)\n"
        "3. The first paragraph under the first H2\n"
        "4. " + kw_count_target + " more times throughout the body (naturally, not stuffed)\n"
        "5. The last paragraph / conclusion\n"
        "6. The seo_title and meta_desc\n\n"
        "=== CONTENT QUALITY REQUIREMENTS ===\n"
        "- Write like an experienced practitioner, NOT a generic AI article\n"
        "- Every claim must include a specific number, percentage, dollar amount, or timeframe\n"
        '  GOOD: "Companies using automated lead scraping report 3.2x more qualified leads per month"\n'
        '  BAD: "Lead scraping can significantly improve your results"\n'
        "- Include at least 3 real tool/platform names (e.g., Apollo.io, ZoomInfo, Hunter.io, HubSpot) as comparison points\n"
        "- Add \"Pro Tip:\" callouts wrapped in <blockquote> tags for expert insights\n"
        '- Use concrete scenarios: "If you are a SaaS company targeting mid-market CFOs..." not "If you are a business..."\n'
        "- Reference current year (2026) trends and data where relevant\n\n"
        "=== ARTICLE STRUCTURE ===\n"
        + structure_instructions + "\n\n"
        "=== INTERNAL LINKING (USE ALL OF THESE) ===\n"
        + links_context + "\n"
        "Embed each link naturally within relevant paragraphs using descriptive anchor text.\n"
        "Also link to the category pillar page where appropriate.\n\n"
        "=== HTML FORMATTING ===\n"
        "- Wrap everything in: <div style=\"font-family: 'Inter', sans-serif; color: #334155; line-height: 1.8; max-width: 800px;\">\n"
        '- H2 style: <h2 style="color: #0f172a; font-size: 28px; margin-top: 40px; margin-bottom: 16px;">\n'
        '- H3 style: <h3 style="color: #1e293b; font-size: 22px; margin-top: 32px; margin-bottom: 12px;">\n'
        '- Tables: <table style="width: 100%; border-collapse: collapse; margin: 24px 0;"> with <th style="background: #f1f5f9; padding: 12px; border: 1px solid #e2e8f0; text-align: left;"> and <td style="padding: 12px; border: 1px solid #e2e8f0;">\n'
        '- Blockquotes (Pro Tips): <blockquote style="border-left: 4px solid #2563eb; padding: 16px 20px; margin: 24px 0; background: #f8fafc; font-style: italic;">\n'
        '- Links: <a href="URL" style="color: #2563eb; text-decoration: underline;">anchor text</a>\n'
        '- Lists: use <ul> or <ol> with <li style="margin-bottom: 8px;">\n'
        "- NO emoji anywhere in the blog post\n"
        "- Write in English\n\n"
        "=== YOUTUBE SHORTS (separate from blog) ===\n"
        "- script: 30-40 second narrator script. Open with a hook question, deliver 2-3 value points, end with \"Link in the channel profile -- check it out!\"\n"
        "- screen_title: 2-5 words, ALL CAPS, punchy hook for on-screen text\n"
        "- yt_title: Clickable YouTube title (max 70 chars) + 1 relevant emoji at the end\n"
        "- yt_description: 2 sentences summarizing the value + 5 relevant hashtags\n"
        '- NEVER say "link in bio"\n\n'
        "=== RETURN FORMAT ===\n"
        "Return valid JSON with these exact keys:\n"
        '- focus_keyword: "' + keyword + '"\n'
        "- seo_title: SEO title 55-60 chars, keyword near the beginning\n"
        "- meta_desc: 150-155 chars, keyword included, compelling CTA\n"
        "- wp_post: full HTML blog post (minimum " + word_count + " words, count carefully)\n"
        "- screen_title: YouTube Shorts screen title\n"
        "- script: YouTube Shorts narrator script\n"
        "- yt_title: YouTube video title\n"
        "- yt_description: YouTube description with hashtags"
    )

    user_msg = (
        "Write a comprehensive, expert-level article about: " + topic + "\n\n"
        "Remember: minimum " + word_count + " words, specific data points in every section, "
        "and use ALL provided internal links."
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg}
            ],
            temperature=0.7
        )
        data = json.loads(resp.choices[0].message.content)
        logger.info("Content generated successfully.")

        logger.info("Generating featured image...")
        img_prompt = (
            "Modern professional blog header image for an article about '"
            + topic
            + "'. Clean tech aesthetic with abstract geometric shapes, "
            "gradient blues and whites, corporate B2B feel. "
            "No text, no words, no letters on the image."
        )
        img_resp = client.images.generate(
            model="dall-e-3",
            prompt=img_prompt,
            size="1792x1024",
            quality="standard",
            n=1
        )
        data["image_url"] = img_resp.data[0].url
        logger.info("Image generated.")

        return data

    except Exception as e:
        logger.error(f"Content generation error: {e}")
        return None


# ── Step 3: Publish to WordPress ──────────────────────────
def publish_to_wordpress(data):
    """Publish post via custom WordPress snippet endpoint."""
    logger.info("Publishing to WordPress...")
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
        resp = requests.post(WP_URL + "/wp-json/luminoxia/v1/publish", json=payload, timeout=60)
        if resp.status_code == 200:
            result = resp.json()
            logger.info("Published! URL: " + result.get("url", ""))
            return True
        else:
            logger.error("Publish failed: " + str(resp.status_code) + " -- " + resp.text)
            return False
    except Exception as e:
        logger.error("WordPress error: " + str(e))
        return False


# ── Step 4: Write video data to Google Sheets ─────────────
def write_to_sheets(data):
    """Append video row to Google Sheets for shorts_maker pipeline."""
    logger.info("Writing to Google Sheets...")
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
        logger.info("Sheet updated! Video scheduled for: " + publish_time)
        return True
    except Exception as e:
        logger.error("Google Sheets error: " + str(e))
        return False


# ── Main ──────────────────────────────────────────────────
def main():
    if not OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY not set in .env")
        return
    if not WP_URL:
        logger.error("WP_URL not set in .env")
        return

    # 1. Get next topic from TopicMap
    topic_data = get_next_topic_from_map()
    if not topic_data:
        return

    # 2. Get internal links for cross-linking
    internal_links = fetch_live_links()

    # 3. Generate content
    content = generate_content(topic_data, internal_links)
    if not content:
        return

    # 4. Publish to WordPress
    publish_to_wordpress(content)

    # 5. Mark topic as DONE in TopicMap
    mark_topic_done(topic_data["sheet_row"])

    # 6. Write video data to sheets
    if write_to_sheets(content):
        logger.info("CONTENT GENERATOR RUN COMPLETED SUCCESSFULLY!")
    else:
        logger.error("Pipeline completed with errors.")


if __name__ == "__main__":
    main()
