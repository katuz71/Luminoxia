import subprocess
import sys
import os

def main():
    # Список твоих боевых скриптов в строгом порядке
    scripts = [
        "content_generator.py",
        "shorts_maker.py",
        "youtube_uploader.py"
    ]

    print("\n" + "="*60)
    print("🚀 STARTING LUMINOXIA PIPELINE (Cron Mode)")
    print("="*60 + "\n")

    overall_success = True

    for i, script in enumerate(scripts, 1):
        print(f"[{i}/{len(scripts)}] STAGE: {script}")
        print("-" * 40)
        
        if not os.path.exists(script):
            print(f"❌ ERROR: Script {script} not found! Skipping stage.")
            overall_success = False
            continue

        try:
            # Запускаем скрипт и дожидаемся его завершения (линейный запуск)
            result = subprocess.run([sys.executable, script], check=False)
            
            if result.returncode == 0:
                print(f"✅ SUCCESS: {script} completed successfully.\n")
            else:
                print(f"⚠️ WARNING: {script} exited with code {result.returncode}.\n")
                # overall_success = False # Don't fail the whole pipeline if one stage has issues (e.g. no articles found)
        except Exception as e:
            print(f"❌ CRITICAL ERROR running {script}: {e}\n")
            overall_success = False

    print("="*60)
    if overall_success:
        print("🎉 PIPELINE EXECUTION FINISHED SUCCESSFULLY!")
    else:
        print("⚠️ PIPELINE FINISHED WITH ERRORS. CHECK LOGS.")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()