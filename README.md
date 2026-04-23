# Luminoxia — Automated Content Pipeline

## Architecture

    ┌─────────────────────────────────────────────────────┐
    │                    CRON (daily 16:00)                │
    │                    start_all.py                      │
    └──────────────┬──────────────┬──────────────┬────────┘
                   │              │              │
                   v              v              v
            ┌──────────┐  ┌──────────────┐  ┌──────────────┐
            │ Step 1   │  │   Step 2     │  │   Step 3     │
            │ content_ │  │  shorts_     │  │  youtube_    │
            │generator │  │  maker.py    │  │  uploader.py │
            └────┬─────┘  └──────┬───────┘  └──────┬───────┘
                 │               │                 │
                 v               v                 v
         ┌───────────────┐ ┌──────────┐    ┌──────────────┐
         │ OpenAI GPT-4o │ │ TTS +    │    │ YouTube API  │
         │ + DALL-E 3    │ │ FFmpeg   │    │ (OAuth2)     │
         └───────┬───────┘ └────┬─────┘    └──────────────┘
                 │              │
                 v              v
         ┌───────────────┐ ┌──────────┐
         │  WordPress    │ │  Google  │
         │  REST API     │ │  Sheets  │
         │  + Rank Math  │ │ TopicMap │
         └───────────────┘ └──────────┘

## Pipeline Flow

### Step 1: content_generator.py
1. Reads next TODO topic from Google Sheets TopicMap tab
2. Fetches internal links from WordPress REST API for cross-linking
3. Generates SEO article (1500-2500 words) via OpenAI GPT-4o
4. Generates featured image via DALL-E 3
5. Publishes to WordPress via custom REST endpoint
6. Sets Rank Math SEO meta (focus keyword, meta description, SEO title)
7. Marks topic as DONE in TopicMap
8. Writes YouTube Shorts data to Google Sheets

### Step 2: shorts_maker.py
1. Reads NEW rows from Google Sheets
2. Generates voiceover via TTS
3. Creates video with subtitles using FFmpeg
4. Marks row as READY

### Step 3: youtube_uploader.py
1. Reads READY rows from Google Sheets
2. Uploads video to YouTube via API (OAuth2)
3. Marks row as UPLOADED

## Topic Strategy
- Category: B2B Lead Generation (WP Category ID: 15)
- Structure: Pillar + Cluster model
- Publishing: 1 article/day at 16:00 UTC

## Tech Stack
- Python 3.12, OpenAI API (GPT-4o + DALL-E 3)
- WordPress REST API + Custom Endpoint + Rank Math SEO
- Google Sheets API (gspread + oauth2client)
- YouTube Data API v3, FFmpeg, Cron

## Server
- VPS: 2 CPU / 4 GB RAM, Ubuntu, Hostinger
