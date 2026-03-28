import subprocess
import time
import sys

# Список твоих боевых скриптов
scripts = [
    "pubmed_parser.py",
    "tg_autoposter.py",
    "shorts_maker.py",
    "youtube_uploader.py"
]

processes = []

print("🚀 Запуск конвейера Biohack AI...")

try:
    for script in scripts:
        print(f" Wait... Запускаю {script}")
        # Запускаем каждый скрипт как отдельный процесс
        proc = subprocess.Popen([sys.executable, script])
        processes.append(proc)
        time.sleep(2) # Небольшая пауза, чтобы API не офигели от резких запросов

    print("\n✅ Все системы запущены. Конвейер работает!")
    print("Нажми Ctrl+C, чтобы остановить все сразу.\n")

    # Держим мастер-скрипт запущенным, пока работают дочерние
    while True:
        time.sleep(1)

except KeyboardInterrupt:
    print("\n🛑 Останавливаю конвейер...")
    for proc in processes:
        proc.terminate()
    print("👋 Все процессы завершены. До связи!")