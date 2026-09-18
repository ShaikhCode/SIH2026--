from pathlib import Path
root=Path(__file__).resolve().parents[1]/'apps/api/models'
checks=[('IndicTrans2 Indic-Indic',root/'translation'/'indic-indic'),('IndicTrans2 En-Indic',root/'translation'/'en-indic'),('IndicTrans2 Indic-En',root/'translation'/'indic-en'),('Whisper Small',root/'stt'/'whisper-small'),('Indic Parler-TTS',root/'tts'/'indic-parler-tts')]
ok=True
for name,p in checks:
    good=p.exists() and any(p.iterdir())
    print(('OK   ' if good else 'MISS ')+f'{name} -> {p}')
    ok &= good
print('\nAll required folders look populated.' if ok else '\nOne or more required model folders are missing/incomplete.')
raise SystemExit(0 if ok else 1)
