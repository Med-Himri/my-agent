# Setting up the Medlout Auto reel agent

You need 5 things, then one server. Put every key in a file named `.env` (copy `.env.example`).

## 1. Claude (Anthropic API)
1. Go to https://console.anthropic.com, sign in, add a few dollars of credit (Billing).
2. API Keys → Create key → put it in `ANTHROPIC_API_KEY`.
Cost: roughly $0.10–0.30 per reel (topic research + script + image choice).

## 2. ElevenLabs (Brian's voice)
Profile → API Keys → create a key with Text-to-Speech permission → `ELEVENLABS_API_KEYS`.
Several keys can be listed, comma-separated; the agent moves to the next one when an account runs out of credits.
One reel uses about 800–1,000 credits.

## 3. Serper.dev (Google Images)
https://serper.dev → API key → `SERPER_API_KEY`. One reel uses about 5–6 searches.

## 4. Telegram bot
1. In Telegram, open **@BotFather**, send `/newbot`, choose a name and a username ending in `bot`.
2. Copy the token → `TELEGRAM_BOT_TOKEN`.
3. Start the agent once, open your bot, send `/start`. It replies with your user id → put it in `TELEGRAM_OWNER_ID` and restart.
Only that user id can use the bot.

## 5. Instagram
The account must be **Professional** (Business or Creator): Instagram app → Settings → Account type and tools.

1. Go to https://developers.facebook.com → My Apps → **Create app**.
2. Choose the use case **"Manage messaging & content on Instagram"** (Instagram API).
3. In the app: **Instagram → API setup with Instagram login** → *Generate access tokens* → **Add account** → log in with the Medlout Auto Instagram account and allow the permissions
   (`instagram_business_basic`, `instagram_business_content_publish`).
4. Copy the **token** → `IG_ACCESS_TOKEN`, and the account's **user id** shown next to it → `IG_USER_ID`.

The app can stay in *Development* mode: it only posts to your own account, so no Meta review is needed.
The token is valid 60 days; the agent renews it automatically every week.

## 6. Run it on a server
Any small Linux server works (e.g. Hetzner CX22, DigitalOcean 2 GB, about $5–7/month). Rendering needs ~2 GB RAM.

```bash
# on the server (Ubuntu), once:
curl -fsSL https://get.docker.com | sh
git clone https://github.com/Med-Himri/my-agent.git
cd my-agent/reel-agent
cp .env.example .env
nano .env                         # paste your keys, save
docker compose up -d --build      # start (and restart automatically after reboots)
docker compose logs -f            # watch what it does (Ctrl+C to stop watching)
```

Update later: `git pull && docker compose up -d --build`

## Using it
- Every day at `DAILY_TIME` you get `TOPICS_PER_DAY` ideas on Telegram → ✅ the ones you like.
- Each approved topic becomes a reel in ~3–5 minutes and arrives on Telegram.
- ✅ Post → it goes to Instagram with caption and hashtags. ✏️ Edit → write what to change. ❌ Drop.
- `/topics` gets ideas immediately; `/status` shows what's in progress.
