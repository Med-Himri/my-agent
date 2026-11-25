# Medlout Auto reel agent

Makes daily Arabic Instagram reels for **Medlout Auto** and runs everything through Telegram:

1. **Topics**: Claude searches the web each morning and proposes car topics on Telegram → you ✅ / ❌.
2. **Script**: Claude writes the reel (hook → what → how → benefit → mistake → tip → outro), caption and hashtags.
3. **Images**: Google Images via Serper.dev; Claude looks at the candidates and picks the best per scene.
4. **Voice**: ElevenLabs, voice *Brian* in Arabic (several API keys supported).
5. **Video**: HTML/CSS template rendered frame by frame with Chromium + ffmpeg, background music ducked under the voice.
6. **Review**: the video arrives on Telegram → ✅ Post / ✏️ Edit (free-text change request) / ❌ Drop.
7. **Instagram**: posted with the Graph API (direct upload, no hosting needed).

Setup and deployment: see **[SETUP.md](SETUP.md)**.

| Path | What |
|---|---|
| `bot.py` | Telegram bot, daily schedule, approval flow |
| `reel/brain.py` | Claude: topics, scripts, edits, image choice |
| `reel/produce.py` | script → images → voice → video |
| `reel/images.py` / `voice.py` / `video.py` | Google Images, ElevenLabs, timeline + audio mix |
| `reel/instagram.py` | publishing + token refresh |
| `renderer/` | the Medlout Auto visual template and frame renderer |
| `assets/` | fonts, background music, the approved example reel |

Make one reel by hand: `python3 -m reel.video <folder>/reel.json out.mp4`
