import asyncio
import glob
import os
import PIL.Image
# Патч для старых версий MoviePy, работающих с новым Pillow 10+
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS
import random
import re
from typing import Any, Dict, List, Optional, Tuple
from dotenv import load_dotenv
import os
from openai import OpenAI

load_dotenv(override=True)
api_key = os.getenv("OPENAI_API_KEY", "").strip(" '\"\n\r")
client = OpenAI(api_key=api_key)

# Указываем путь к установленному ImageMagick
from moviepy.config import change_settings
change_settings({"IMAGEMAGICK_BINARY": r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe"})
print("🎨 ImageMagick подключен: v7.1.2")

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
MUSIC_VOLUME_FACTOR = 0.1  # 10%
MAX_WORDS_PER_SUBTITLE_PHRASE = 2
CORRECT_BOT_NAME = "JobHack AI"
CORRECTIONS = {
    "джобхак": CORRECT_BOT_NAME,
    "job hack": CORRECT_BOT_NAME,
}
def _pick_title_font() -> str:
    """
    Пытаемся использовать Montserrat-ExtraBold, если он установлен в системе,
    иначе возвращаем Liberation-Sans-Bold.
    """
    fonts_dir = r"C:\Windows\Fonts"
    if os.path.exists(fonts_dir):
        patterns = [
            os.path.join(fonts_dir, "*Montserrat*ExtraBold*.ttf"),
            os.path.join(fonts_dir, "*Montserrat*ExtraBold*.otf"),
            os.path.join(fonts_dir, "*Montserrat*ExtraBold*.ttc"),
            os.path.join(fonts_dir, "*Montserrat*ExtraBold*.woff"),
        ]
        for p in patterns:
            if glob.glob(p):
                return "Montserrat-ExtraBold"
    return "Liberation-Sans-Bold"


def _pick_subtitle_font() -> str:
    """
    Подбираем максимально жирный шрифт для субтитров.
    Сначала пытаемся Impact (часто есть в Windows), затем Arial Black,
    иначе fallback на Liberation-Sans-Bold.
    """
    preferred_fonts = ["Impact", "Arial-Black", "Arial Black", "ArialBlack"]
    fonts_dir = r"C:\Windows\Fonts"
    if os.path.exists(fonts_dir):
        for fn in preferred_fonts:
            patterns = [
                os.path.join(fonts_dir, f"*{fn}*.ttf"),
                os.path.join(fonts_dir, f"*{fn}*.otf"),
                os.path.join(fonts_dir, f"*{fn}*.woff"),
                os.path.join(fonts_dir, f"*{fn}*.ttc"),
            ]
            for p in patterns:
                if glob.glob(p):
                    return fn.replace(" ", "-")
    return "Liberation-Sans-Bold"


def _apply_corrections(s: str) -> str:
    for wrong, right in CORRECTIONS.items():
        s = re.sub(re.escape(wrong), right, s, flags=re.IGNORECASE)
    return s


def _split_text_into_chunks(text: str, chunk_size: int = 2) -> List[str]:
    """Разбивает длинный текст на куски по 1-2 слова для субтитров."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size):
        chunks.append(" ".join(words[i:i+chunk_size]))
    return chunks


def _generate_tts_audio_and_words(
    text: str,
    title_text: str,
    audio_path: str,
    voice: str = "onyx", # <-- ТУТ МОЖНО ПОМЕНЯТЬ ГОЛОС
) -> List[Dict[str, Any]]:
    """
    Генерирует аудио через OpenAI TTS и равномерно распределяет тайминги титров с 0 до конца.
    """
    # 4) ЗАПЛАТКА: заменяем аббревиатуры перед озвучкой
    text_to_speech = text.replace(" ТГ ", " Телеграм-канал ").replace(" TG ", " Телеграм-канал ")

    os.makedirs(os.path.dirname(audio_path), exist_ok=True)
    response = client.audio.speech.create(
        model="tts-1-hd", # Улучшенное качество звука и битрейт
        voice=voice,
        input=text_to_speech,
        speed=1.05,       # Немного ускоряем Onyx, чтобы убрать медлительность и добавить энергии 
        response_format="mp3"
    )
    response.write_to_file(audio_path)

    word_items = []

    from moviepy.editor import AudioFileClip
    audio_clip = AudioFileClip(audio_path)
    total_duration = float(audio_clip.duration)
    audio_clip.close()

    # Текст для субтитров: строго тот же текст, что читает диктор (text), разбиваем по 1-2 слова
    chunks = _split_text_into_chunks(text, 2)
        
    if not chunks:
        return []

    # Распределение времени для титров от 0 до конца
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
    Нормализует вариации названия бота в единый вид: `CORRECT_BOT_NAME`.
    """
    if not s:
        return s

    # Замена латиницей: jobhack / job hack / job-hack
    s = re.sub(r"(?i)\bjob\s*-?\s*hack\b", "JobHack", s)
    # Замена кириллицей: Джобхак / Джоб хак
    s = re.sub(r"(?i)\bджоб\s*-?\s*хак\b", "JobHack", s)
    # Нормализуем пробел перед AI
    s = re.sub(r"(?i)\bJobHack\s+AI\b", CORRECT_BOT_NAME, s)
    return s


def _fit_to_frame(clip: VideoFileClip, target_w: int, target_h: int) -> VideoFileClip:
    """
    Приводит видео к нужному кадру (9:16): сначала масштабируем “вперёд” (cover),
    затем обрезаем по центру до target_w x target_h.
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
    Собирает B-roll принудительными отрезками ровно по `CLIP_DURATION` секунд.
    На каждой итерации:
      - случайно выбирается видео из `bg_folder`
      - если оно длиннее - делается `subclip()` на 4 секунды с случайным `start_time`
      - если короче - видео зацикливается до 4 секунд (`vfx.loop`)
    """
    paths = _list_background_videos(bg_folder)
    if not paths:
        raise RuntimeError("Папка 'backgrounds' пуста или не содержит mp4.")

    segments: List[VideoFileClip] = []
    base_clips: List[VideoFileClip] = []
    fitted_clips: List[VideoFileClip] = []

    total_duration = 0.0
    clip_duration = float(CLIP_DURATION)
    if clip_duration <= 0:
        raise ValueError("`CLIP_DURATION` должен быть > 0.")

    while total_duration < float(target_duration):
        bg_path = random.choice(paths)
        base_clip = VideoFileClip(bg_path)
        
        # ОПТИМИЗАЦИЯ ПАМЯТИ: Принудительный ресайз гигантских видео
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

    # Метод compose гарантирует корректную склейку, если где-то остались отличия размеров.
    from moviepy.editor import concatenate_videoclips

    final_background = concatenate_videoclips(segments, method="compose")
    # Аккуратно подрезаем фон ровно под длительность аудио.
    final_background = final_background.subclip(0, float(target_duration))
    final_background = final_background.set_duration(float(target_duration))
    return final_background, base_clips, fitted_clips, segments


def _list_music_files(music_folder: str) -> List[str]:
    if not os.path.exists(music_folder):
        print(f"⚠️ Папка для музыки не найдена, создаю: {music_folder}")
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
    Подгоняет фоновую музыку под длительность диктора и снижает громкость.
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
    voice: str = "onyx", # <-- ДЕФОЛТНЫЙ ГОЛОС ('onyx', 'alloy', 'echo', 'nova') 
    max_words_per_subtitle_phrase: int = MAX_WORDS_PER_SUBTITLE_PHRASE,
) -> None:
    # ОДНА финальная строка для TTS (и аудио, и субтитров):
    # - нормализуем варианты названия
    # - применяем коррекции
    text = _apply_corrections(_correct_bot_name_in_text(text))
    title_text = _apply_corrections(_correct_bot_name_in_text(title_text))
    
    yt_title_clean = yt_title.strip()
    if not yt_title_clean:
        # Fallback: если yt_title пустой, используем первую строчку из Screen Titles
        yt_title_clean = title_text.split('\n')[0].strip()

    # Очистка и форматирование разметки
    text = text.replace('*', '').replace('_', '')
    title_text = title_text.replace('*', '').replace('_', '').replace('\\n', '\n').upper()
    yt_title_clean = yt_title_clean.replace('*', '').replace('_', '').upper()
    if max_words_per_subtitle_phrase < 1:
        raise ValueError("`max_words_per_subtitle_phrase` должен быть >= 1.")

    # 1) Озвучка (OpenAI TTS -> temp_audio.mp3)
    print("🎙 Генерируем нейроголос...")
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
        # 3) Достаем длительность аудио
        print("🎬 Начинаем монтаж...")
        audio = AudioFileClip("temp/voice.mp3")
        audio = audio.fx(afx.volumex, 1.5) # БАЛАНС ЗВУКА: Увеличиваем громкость диктора (в 1.5 раза)
        audio_duration = float(audio.duration)

        # 3.1) Проверка медиа-файлов
        music_files = _list_music_files(music_folder)
        paths_bg = _list_background_videos(bg_folder)

        print(f"\n--- ПРОВЕРКА (Debug) ---")
        print(f"Путь к фонам: {os.path.abspath(bg_folder)}")
        print(f"Найдено видео: {len(paths_bg)}")
        print(f"Найдено треков: {len(music_files)}")
        print(f"------------------------\n")

        if not paths_bg:
            raise ValueError(f"Папка с фонами пуста! Рендер невозможен.")

        if music_files:
            music_path = random.choice(music_files)
            print(f"🎵 Выбрана музыка: {music_path}")
            bg_music = _prepare_bg_music(
                music_path=music_path,
                target_duration=audio_duration,
                volume_factor=MUSIC_VOLUME_FACTOR,
            )
            mixed_audio = CompositeAudioClip([audio, bg_music])
        else:
            print("⚠️ Папка с музыкой пуста. Генерируем только с голосом.")
            mixed_audio = audio

        # 4) Динамический фон (микс фонов до длительности аудио)
        background, base_clips, fitted_clips, segments = _build_dynamic_background(
            bg_folder=bg_folder,
            target_duration=audio_duration,
            target_w=TARGET_W,
            target_h=TARGET_H,
        )
        background_clip = background

        # 5) ЗАГОЛОВОК (Hook из row[0] / Screen Title)
        title_clip = TextClip(
            title_text,        # Текст хука (Screen Title)
            method="caption",
            fontsize=70,       # Размер 70
            color="white",     # СТРОГО БЕЛЫЙ
            stroke_color="black",
            stroke_width=3,    # Черная обводка для читаемости
            font='Arial-Bold', # Жирный шрифт
            size=(800, None),  # Ширина 800
        )
        # Устанавливаем появление от 0 до 3 секунд в верхней части (жесткие 200px)
        title_clip = (
            title_clip.set_position(lambda t: ('center', 200))
            .set_start(0.0)
            .set_end(3.0)
        )

        # 6) Динамические субтитры по таймингам (от 0-й секунды)
        filtered_items = []
        for w in word_items:
            start = w["start"]
            end = min(w["end"], audio_duration)
            if start >= audio_duration or end <= start:
                continue
            filtered_items.append({"text": w["text"], "start": start, "end": end})
        word_items = filtered_items

        print(f"Извлечено субтитров (word_items): {len(word_items)}")
        if not word_items:
            print("⚠️ ВНИМАНИЕ: Список word_items пуст! Субтитры не будут сгенерированы.")

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
                font='Arial-Bold',    
                fontsize=85,          # Крупный шрифт (около 80-90)
                color='yellow',       # СТРОГО ЖЕЛТЫЙ
                stroke_color='black', 
                stroke_width=3,       # Жирная черная обводка
                method='caption',     # Обязательно method='caption'
                align='center',
                size=(800, None)      # Ширина 800
            )

            # Позиция: ЖЕСТКАЯ абсолютная привязка вниз экрана через лямбду (1600px - нижняя треть)
            tc = tc.set_start(start_time).set_end(start_time + duration).set_position(lambda t: ('center', 1600))

            subtitle_clips.append(tc)

        print(f"Итоговый текст для субтитров: {[w['text'] for w in word_items]}")
        
        # 7) Компоузинг: фон + заголовок + субтитры + аудио
        final_video = CompositeVideoClip(
            [background, title_clip] + subtitle_clips,
            size=(TARGET_W, TARGET_H),
        ).set_audio(mixed_audio)

        print("⏳ Рендерим финальный файл (может занять пару минут)...")
        final_video.write_videofile(
            output_filename,
            fps=30,
            codec="libx264",
            audio_codec="aac",
            preset="ultrafast",  # 🚀 Главный спаситель памяти!
            threads=2,           # Повышаем до 2 для оптимальной производительности и низкого RAM
            logger=None          # Отключаем ползунок, чтобы не грузить терминал
        )
   
        # ПРИНУДИТЕЛЬНАЯ ОЧИСТКА РАМ: закрываем клипы после рендера сразу
        try:
            if final_video: final_video.close()
            if audio: audio.close()
            if background_clip: background_clip.close()
            if mixed_audio: mixed_audio.close()
        except Exception:
            pass

        print(f"✅ Готово! Твое видео сохранено как: {output_filename}")

    finally:
        # Важно: на Windows MoviePy/FFMPEG любит ругаться, если не закрыть клипы.
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

        # `segments` и `background` завязаны на источники, поэтому закрываем после рендера.
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

        # temp/voice.mp3 всегда чистим в конце.
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
    # ВНИМАНИЕ: замените значение на реальное имя таблицы.
    SPREADSHEET_NAME = "Jobhakai"
    WORKSHEET_NAME = "Biohack"
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
        
        # Индекс 5-й колонки для статуса (1-based index 5 = 5 column, in lists it's 4)
        status_col_idx = 5
        
        for row_number, row in enumerate(values, start=1):
            if row_number == 1:
                continue # Строго пропускаем заголовок (Строку 1)

            status = str(row[4]).strip().upper() if len(row) > 4 else ""
            debug_statuses.append(f"Строка {row_number}: '{status}'")

            # Берём только POSTED
            if status != "POSTED":
                continue

            screen_title = (row[0] if len(row) > 0 else "").strip()
            script = (row[1] if len(row) > 1 else "").strip()
            yt_title = (row[2] if len(row) > 2 else "").strip()
            yt_description = (row[3] if len(row) > 3 else "").strip()

            # Минимальные проверки
            if not screen_title or not script:
                continue

            tasks.append(
                {
                    "row_index": row_number,  # 1-based индекс для update_cell
                    "status_col_idx": status_col_idx,
                    "screen_title": screen_title,
                    "script": script,
                    "yt_title": yt_title,
                    "yt_description": yt_description,
                }
            )
            print(f"✅ Найдена первая строка в очереди! (Строка {row_number})")
            break # Берем строго ПЕРВУЮ ПОДХОДЯЩУЮ строку

        if not tasks:
            print(f"🔍 Отладка статусов для POSTED: {', '.join(debug_statuses)}")

        return ws, tasks

    async def _run_tasks():
        ws, tasks = _load_tasks_from_google_sheet()
        if not tasks:
            print("Нет задач: все строки уже имеют заполненный Status.")
            return

        os.makedirs(READY_VIDEOS_DIR, exist_ok=True)

        print(f"Найдено задач для генерации: {len(tasks)}")

        for task in tasks:
            row_index = task["row_index"]
            status_col_idx = task["status_col_idx"]
            screen_title = task["screen_title"]
            script = task["script"]

            output_filename = f"{READY_VIDEOS_DIR}/video_{row_index}.mp4"
            if os.path.exists(output_filename):
                print(f"⏭ Видео {output_filename} уже существует. Пропускаю...")
                continue

            print(f"--- Row {row_index}: рендерим {output_filename}")
            try:
                await make_short(script, screen_title, yt_title=task.get("yt_title", ""), output_filename=output_filename)
            except Exception as e:
                print(f"❌ Row {row_index}: ошибка рендера: {e}")
                continue

            # После успешного рендера помечаем DONE в динамически вычисленной колонке Status
            import time
            try:
                ws.update_cell(row_index, status_col_idx, "VIDEO_DONE")
                print(f"✅ Статус VIDEO_DONE записан в таблицу (строка {row_index}).")
            except Exception as e:
                print(f"⚠️ Google Таблицы не ответили (ошибка 500). Ждем 5 секунд и пробуем снова...")
                time.sleep(5)
                try:
                    ws.update_cell(row_index, status_col_idx, "VIDEO_DONE")
                    print(f"✅ Статус VIDEO_DONE записан в таблицу со второй попытки (строка {row_index}).")
                except Exception as e_retry:
                    print(f"❌ Не удалось обновить статус в таблице: {e_retry}. Идем дальше!")

    asyncio.run(_run_tasks())