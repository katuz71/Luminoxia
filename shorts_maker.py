# -*- coding: utf-8 -*-
import asyncio
import glob
import os
import PIL.Image
# Patch for older MoviePy versions working with new Pillow 10+
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS
import random
import re
from typing import Any, Dict, List, Optional, Tuple
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(override=True)
api_key = os.getenv("OPENAI_API_KEY", "").strip(" '\"\n\r")
client = OpenAI(api_key=api_key)

# --- АВТОМАТИЧЕСКИЙ ВЫБОР ПУТИ К IMAGEMAGICK ---
from moviepy.config import change_settings
if os.name == 'nt':
    # Путь для локального теста на Windows
    change_settings({"IMAGEMAGICK_BINARY": r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe"})
    print("🎨 ImageMagick connected (Windows Local Mode)")
else:
    # Путь для боевого Linux-сервера
    change_settings({"IMAGEMAGICK_BINARY": "/usr/bin/convert"})
    print("🎨 ImageMagick connected (Linux Server Mode)")
# -----------------------------------------------

from moviepy.editor import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    TextClip,
    VideoFileClip,
)
import moviepy.audio.fx.all as afx
import moviepy.video.fx.all as vfx

TARGET_W = 1080
TARGET_H = 1920
CLIP_DURATION = 4.0
MUSIC_VOLUME_FACTOR = 0.05
MAX_WORDS_PER_SUBTITLE_PHRASE = 2
CORRECT_BOT_NAME = "Luminoxia"
CORRECTIONS = {
    "джобхак": CORRECT_BOT_NAME,
    "job hack": CORRECT_BOT_NAME,
}



def _apply_corrections(s: str) -> str:
    for wrong, right in CORRECTIONS.items():
        s = re.sub(re.escape(wrong), right, s, flags=re.IGNORECASE)
    return s

def _split_text_into_chunks(text: str, chunk_size: int = 2) -> List[str]:
    """Split long text into short chunks"""
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size):
        chunks.append(" ".join(words[i:i+chunk_size]))
    return chunks

def _generate_tts_audio_and_words(
    text: str,
    title_text: str,
    audio_path: str,
    voice: str = "nova",
) -> List[Dict[str, Any]]:
    """
    Generate TTS audio and word timings
    """
    # Cleanup text for TTS
    text_to_speech = text.strip()

    os.makedirs(os.path.dirname(audio_path), exist_ok=True)
    response = client.audio.speech.create(
        model="tts-1-hd",
        voice=voice,
        input=text_to_speech,
        speed=1.05,
        response_format="mp3"
    )
    response.write_to_file(audio_path)

    word_items = []

    from moviepy.editor import AudioFileClip
    audio_clip = AudioFileClip(audio_path)
    total_duration = float(audio_clip.duration)
    audio_clip.close()

    chunks = _split_text_into_chunks(text, 2)
        
    if not chunks:
        return []

    available_duration = total_duration
    current_start = 0.0

    total_chars = sum(len(chunk) for chunk in chunks)
    if total_chars == 0:
        return []

    for i, chunk in enumerate(chunks):
        chunk_chars = len(chunk)
        chunk_duration = (chunk_chars / total_chars) * available_duration
        end_time = current_start + chunk_duration
        
        if i == len(chunks) - 1:
            end_time = total_duration
        
        word_items.append({
            "text": chunk,
            "start": current_start,
            "end": end_time
        })
        current_start = end_time

    return word_items

def _correct_bot_name_in_text(s: str) -> str:
    """
    Normalize bot name variations
    """
    if not s:
        return s

    s = re.sub(r"(?i)\bjob\s*-?\s*hack\b", "JobHack", s)
    s = re.sub(r"(?i)\bджоб\s*-?\s*хак\b", "JobHack", s)
    s = re.sub(r"(?i)\bJobHack\s+AI\b", CORRECT_BOT_NAME, s)
    return s

def _fit_to_frame(clip: VideoFileClip, target_w: int, target_h: int) -> VideoFileClip:
    """
    Fit video to 9:16 frame by cropping
    """
    scale = max(target_w / clip.w, target_h / clip.h)
    resized = clip.resize(scale)
    x_center = resized.w / 2
    y_center = resized.h / 2
    cropped = resized.crop(
        x_center=x_center,
        y_center=y_center,
        width=target_w,
        height=target_h,
    )
    return cropped

def _list_background_videos(bg_folder: str) -> List[str]:
    if not os.path.exists(bg_folder):
        os.makedirs(bg_folder)
        return []

    return sorted(
        [
            os.path.join(bg_folder, f)
            for f in os.listdir(bg_folder)
            if f.lower().endswith(".mp4")
        ]
    )


def _build_dynamic_background(
    bg_folder: str,
    target_duration: float,
    target_w: int,
    target_h: int,
) -> Tuple[VideoFileClip, List[VideoFileClip], List[VideoFileClip], List[VideoFileClip]]:
    """
    Build b-roll segments
    """
    paths = _list_background_videos(bg_folder)
    if not paths:
        raise RuntimeError("Backgrounds directory is empty or missing mp4 files.")

    segments: List[VideoFileClip] = []
    base_clips: List[VideoFileClip] = []
    fitted_clips: List[VideoFileClip] = []

    total_duration = 0.0
    clip_duration = float(CLIP_DURATION)
    if clip_duration <= 0:
        raise ValueError("CLIP_DURATION must be > 0.")

    while total_duration < float(target_duration):
        bg_path = random.choice(paths)
        base_clip = VideoFileClip(bg_path)
        
        # Memory optimization: resize huge videos
        if base_clip.h > target_h or base_clip.w > target_w:
            base_clip = base_clip.resize(height=target_h)
            
        base_clips.append(base_clip)

        if float(base_clip.duration) >= clip_duration + 1e-6:
            max_start = max(0.0, float(base_clip.duration) - clip_duration)
            start_time = random.uniform(0.0, max_start)
            seg = base_clip.subclip(start_time, start_time + clip_duration)
        else:
            seg = base_clip.fx(vfx.loop, duration=clip_duration)

        seg = _fit_to_frame(seg, target_w, target_h)
        fitted_clips.append(seg)
        segments.append(seg)
        total_duration += clip_duration

    from moviepy.editor import concatenate_videoclips

    final_background = concatenate_videoclips(segments, method="compose")
    final_background = final_background.subclip(0, float(target_duration))
    final_background = final_background.set_duration(float(target_duration))
    return final_background, base_clips, fitted_clips, segments


def _list_music_files(music_folder: str) -> List[str]:
    if not os.path.exists(music_folder):
        print(f"Directory not found, creating: {music_folder}")
        os.makedirs(music_folder, exist_ok=True)
        return []

    return sorted(
        [
            os.path.join(music_folder, f)
            for f in os.listdir(music_folder)
            if f.lower().endswith((".mp3", ".wav"))
        ]
    )


def _prepare_bg_music(
    music_path: str,
    target_duration: float,
    volume_factor: float,
) -> AudioFileClip:
    """
    Match background music duration to voiceover and reduce volume.
    """
    bg_music = AudioFileClip(music_path)

    if bg_music.duration < target_duration:
        bg_music = afx.audio_loop(bg_music, duration=target_duration)
    else:
        bg_music = bg_music.subclip(0, target_duration)

    bg_music = afx.volumex(bg_music, volume_factor)
    return bg_music


async def make_short(
    text: str,
    title_text: str,
    yt_title: str = "",
    output_filename: str = "assets/ready_videos/promo_subs.mp4",
    bg_folder: str = "assets/backgrounds",
    music_folder: str = "assets/music",
    voice: str = "nova",
    max_words_per_subtitle_phrase: int = MAX_WORDS_PER_SUBTITLE_PHRASE,
) -> None:
    # Final cleanup of TTS text
    text = _apply_corrections(_correct_bot_name_in_text(text))
    title_text = _apply_corrections(_correct_bot_name_in_text(title_text))
    
    yt_title_clean = yt_title.strip()
    if not yt_title_clean:
        # Fallback to Screen Titles
        yt_title_clean = title_text.split('\n')[0].strip()

    # Clean markdown
    text = text.replace('*', '').replace('_', '')
    title_text = title_text.replace('*', '').replace('_', '').replace('\\n', '\n').upper()
    yt_title_clean = yt_title_clean.replace('*', '').replace('_', '').upper()
    if max_words_per_subtitle_phrase < 1:
        raise ValueError("max_words_per_subtitle_phrase must be >= 1.")

    print("Generating AI voice...")
    word_items = _generate_tts_audio_and_words(
        text=text,
        title_text=title_text,
        audio_path="temp/voice.mp3",
        voice=voice,
    )

    audio: Optional[AudioFileClip] = None
    final_video: Optional[CompositeVideoClip] = None
    background_clip: Optional[VideoFileClip] = None
    bg_music: Optional[AudioFileClip] = None
    mixed_audio: Optional[CompositeAudioClip] = None

    base_clips: List[VideoFileClip] = []
    fitted_clips: List[VideoFileClip] = []
    segments: List[VideoFileClip] = []

    title_clip: Optional[TextClip] = None
    subtitle_clips: List[TextClip] = []

    try:
        print("Starting montage...")
        audio = AudioFileClip("temp/voice.mp3")
        audio = audio.fx(afx.volumex, 1.5)
        audio_duration = float(audio.duration)

        music_files = _list_music_files(music_folder)
        paths_bg = _list_background_videos(bg_folder)

        print(f"\n--- DEBUG INFO ---")
        print(f"Backgrounds path: {os.path.abspath(bg_folder)}")
        print(f"Found videos: {len(paths_bg)}")
        print(f"Found music tracks: {len(music_files)}")
        print(f"------------------------\n")

        if not paths_bg:
            raise ValueError(f"Backgrounds folder is empty. Render impossible.")

        if music_files:
            music_path = random.choice(music_files)
            print(f"Selected music: {music_path}")
            bg_music = _prepare_bg_music(
                music_path=music_path,
                target_duration=audio_duration,
                volume_factor=MUSIC_VOLUME_FACTOR,
            )
            mixed_audio = CompositeAudioClip([audio, bg_music])
        else:
            print("Music folder is empty. Generating only with voice.")
            mixed_audio = audio

        background, base_clips, fitted_clips, segments = _build_dynamic_background(
            bg_folder=bg_folder,
            target_duration=audio_duration,
            target_w=TARGET_W,
            target_h=TARGET_H,
        )
        background_clip = background

        # Header clipping
        title_clip = TextClip(
            title_text,
            method="caption",
            fontsize=70,
            color="white",
            stroke_color="black",
            stroke_width=3,
            font='DejaVu-Sans-Bold',
            size=(800, None),
        )
        title_clip = (
            title_clip.set_position(("center", 0.25), relative=True)
            .set_start(0.0)
            .set_end(3.0)
        )

        # Dynamic subtitles
        filtered_items = []
        for w in word_items:
            start = w["start"]
            end = min(w["end"], audio_duration)
            if start >= audio_duration or end <= start:
                continue
            filtered_items.append({"text": w["text"], "start": start, "end": end})
        word_items = filtered_items

        print(f"Extracted subtitles: {len(word_items)}")
        if not word_items:
            print("WARNING: word_items is empty! Subtitles will not be generated.")

        for item in word_items:
            start_time = float(item["start"])
            duration = float(item["end"]) - start_time
            if duration <= 0:
                continue

            phrase_text = _apply_corrections(item["text"])
            if not phrase_text.strip():
                continue

            tc = TextClip(
                phrase_text,
                font='DejaVu-Sans-Bold',    
                fontsize=85,
                color='yellow',
                stroke_color='black', 
                stroke_width=3,
                method='caption',
                align='center',
                size=(800, None)
            )

            tc = tc.set_start(start_time).set_end(start_time + duration).set_position(('center', 0.75), relative=True)

            subtitle_clips.append(tc)

        print(f"Final subtitle text: {[w['text'] for w in word_items]}")
        
        final_video = CompositeVideoClip(
            [background, title_clip] + subtitle_clips,
            size=(TARGET_W, TARGET_H),
        ).set_audio(mixed_audio)

        print("Rendering final video file...")
        # Сохранение видео с полоской прогресса
        final_video.write_videofile(
            output_filename,
            fps=24,
            threads=2,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            bitrate="5000k",
            logger="bar"  
        )
   
        # Close clips
        try:
            if final_video: final_video.close()
            if audio: audio.close()
            if background_clip: background_clip.close()
            if mixed_audio: mixed_audio.close()
        except Exception:
            pass

        print(f"Done! Video saved as: {output_filename}")

    finally:
        for c in subtitle_clips:
            try:
                c.close()
            except Exception:
                pass
        subtitle_clips.clear()

        if title_clip is not None:
            try:
                title_clip.close()
            except Exception:
                pass

        if final_video is not None:
            try:
                final_video.close()
            except Exception:
                pass

        if mixed_audio is not None and mixed_audio is not audio:
            try:
                mixed_audio.close()
            except Exception:
                pass

        if bg_music is not None:
            try:
                bg_music.close()
            except Exception:
                pass

        if background_clip is not None:
            try:
                background_clip.close()
            except Exception:
                pass

        for s in segments:
            try:
                s.close()
            except Exception:
                pass

        for c in fitted_clips:
            try:
                c.close()
            except Exception:
                pass

        for c in base_clips:
            try:
                c.close()
            except Exception:
                pass

        if audio is not None:
            try:
                audio.close()
            except Exception:
                pass

        if os.path.exists("temp/voice.mp3"):
            try:
                os.remove("temp/voice.mp3")
            except Exception:
                pass

        if os.path.exists("temp_subs.srt"):
            try:
                os.remove("temp_subs.srt")
            except Exception:
                pass


if __name__ == "__main__":
    SPREADSHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "Luminoxia")
    WORKSHEET_NAME = os.getenv("GOOGLE_WORKSHEET_NAME", "Luminoxia")
    CREDENTIALS_JSON_PATH = "credentials.json"
    READY_VIDEOS_DIR = "assets/ready_videos"

    def _load_tasks_from_google_sheet():
        import gspread
        from oauth2client.service_account import ServiceAccountCredentials

        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            CREDENTIALS_JSON_PATH, scope
        )
        gc = gspread.authorize(creds)

        sh = gc.open(SPREADSHEET_NAME)
        ws = sh.worksheet(WORKSHEET_NAME)

        values = ws.get_all_values()
        if not values:
            return ws, []

        tasks = []
        debug_statuses = []
        
        status_col_idx = 5
        
        for row_number, row in enumerate(values, start=1):
            if row_number == 1:
                continue

            status = str(row[4]).strip().upper() if len(row) > 4 else ""
            debug_statuses.append(f"Row {row_number}: '{status}'")

            if status != "NEW":
                continue

            screen_title = (row[0] if len(row) > 0 else "").strip()
            script = (row[1] if len(row) > 1 else "").strip()
            yt_title = (row[2] if len(row) > 2 else "").strip()
            yt_description = (row[3] if len(row) > 3 else "").strip()

            if not screen_title or not script:
                continue

            tasks.append(
                {
                    "row_index": row_number,
                    "status_col_idx": status_col_idx,
                    "screen_title": screen_title,
                    "script": script,
                    "yt_title": yt_title,
                    "yt_description": yt_description,
                }
            )
            print(f"Found an active row in the queue! (Row {row_number})")
            break

        if not tasks:
            print(f"Debug statuses for POSTED: {', '.join(debug_statuses)}")

        return ws, tasks

    async def _run_tasks():
        ws, tasks = _load_tasks_from_google_sheet()
        if not tasks:
            print("No new tasks found: all rows have a Status.")
            return

        os.makedirs(READY_VIDEOS_DIR, exist_ok=True)

        print(f"Found tasks for generation: {len(tasks)}")

        import random
        AVAILABLE_VOICES = ["nova", "shimmer", "onyx", "alloy"]

        for task in tasks:
            row_index = task["row_index"]
            status_col_idx = task["status_col_idx"]
            screen_title = task["screen_title"]
            script = task["script"]

            output_filename = f"{READY_VIDEOS_DIR}/video_{row_index}.mp4"
            if os.path.exists(output_filename):
                print(f"Video {output_filename} already exists. Skipping...")
                continue

            selected_voice = random.choice(AVAILABLE_VOICES)

            print(f"--- Row {row_index}: rendering {output_filename} with voice '{selected_voice}'")
            try:
                await make_short(
                    text=script, 
                    title_text=screen_title, 
                    yt_title=task.get("yt_title", ""), 
                    output_filename=output_filename,
                    voice=selected_voice
                )
            except Exception as e:
                print(f"Row {row_index} final render error: {e}")
                continue

            import time
            try:
                ws.update_cell(row_index, status_col_idx, "VIDEO_DONE")
                print(f"Status VIDEO_DONE recorded (row {row_index}).")
            except Exception as e:
                print(f"Google Sheets timeout (500). Waiting 5 seconds and retrying...")
                time.sleep(5)
                try:
                    ws.update_cell(row_index, status_col_idx, "VIDEO_DONE")
                    print(f"Status VIDEO_DONE recorded on second attempt (row {row_index}).")
                except Exception as e_retry:
                    print(f"Failed to update status: {e_retry}. Continuing!")

    asyncio.run(_run_tasks())