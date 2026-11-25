# Medlout Auto reel agent (work in progress)

Builds daily Arabic Instagram reels in the Medlout Auto style.

Done so far:
- `reel/images.py`: Google Images search via Serper.dev (`SERPER_API_KEY`), with Wikimedia Commons as fallback
- `reel/video.py`: reel spec (`reel.json`) + images + per-scene voice clips → timeline → final MP4
- `renderer/`: HTML/CSS template rendered frame by frame with headless Chromium (Playwright), encoded with ffmpeg

Next: Claude topic research + script writing, ElevenLabs voice (Brian, `nPczCjzI2devNBz1zQrb`), Telegram approvals, Instagram posting.

```bash
python3 -m reel.video work/<reel>/reel.json out.mp4 [music.mp3]
```
Needs Python 3.11+, Pillow, requests, Node 18+ with `playwright`, ffmpeg.
