import os
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(override=True)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY").strip(" '\""))

test_text = "Твой мозг — это биокомпьютер. Хватит кормить его мусором. Подписывайся на мой Телеграм-канал, ссылка в описании профиля!"
voices = ["alloy", "echo", "onyx"] # Самые топовые для нашей ниши

print("🎙 Начинаю тест голосов...")

for voice in voices:
    response = client.audio.speech.create(
        model="tts-1-hd", # Используем HD версию для качества
        voice=voice,
        input=test_text
    )
    filename = f"test_voice_{voice}.mp3"
    response.stream_to_file(filename)
    print(f"✅ Готово: {filename}")

print("\n🎧 Послушай файлы в папке проекта и скажи, какой голос оставляем.")