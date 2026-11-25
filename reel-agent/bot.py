"""Medlout Auto reel agent: Telegram bot + daily schedule.

Every day at DAILY_TIME it proposes topics on Telegram. Approve one and it builds the reel and
sends you the video. Then: ✅ post to Instagram, ✏️ ask for a change, or ❌ drop it.

Run:  python bot.py
"""
from __future__ import annotations

import asyncio
import html
import logging
from datetime import date, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton as Btn, InlineKeyboardMarkup as Kb, Update
from telegram.constants import ParseMode
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes,
                          MessageHandler, filters)

from reel import brain, config, instagram, store
from reel.produce import caption_text, produce, revise

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("agent")

OWNER = config.TELEGRAM_OWNER_ID
WORK = asyncio.Lock()          # one reel is rendered at a time
esc = html.escape


def is_owner(update: Update) -> bool:
    return bool(OWNER) and update.effective_user is not None and update.effective_user.id == OWNER


async def say(ctx: ContextTypes.DEFAULT_TYPE, text: str, kb: Kb | None = None):
    return await ctx.bot.send_message(OWNER, text, parse_mode=ParseMode.HTML, reply_markup=kb,
                                      disable_web_page_preview=True)


def short_error(e: Exception) -> str:
    return esc(f"{type(e).__name__}: {e}")[:600]


# ------------------------------------------------------------------ topics
async def propose_topics(ctx: ContextTypes.DEFAULT_TYPE, n: int | None = None) -> None:
    n = n or config.TOPICS_PER_DAY
    await say(ctx, f"🔎 Searching for {n} reel topics…")
    try:
        topics = await asyncio.to_thread(brain.find_topics, n, store.past_titles())
    except Exception as e:
        log.exception("topic search failed")
        await say(ctx, f"❌ Topic search failed:\n<code>{short_error(e)}</code>",
                  Kb([[Btn("🔁 Try again", callback_data="t:more")]]))
        return
    for i, t in enumerate(topics, 1):
        tid = store.add_topic(t)
        await say(ctx,
                  f"💡 <b>Topic {i}/{len(topics)}</b>\n\n<b>{esc(t['title_ar'])}</b>\n{esc(t['summary_ar'])}\n\n"
                  f"<i>Why: {esc(t['why'])}</i>",
                  Kb([[Btn("✅ Make this reel", callback_data=f"t:ok:{tid}"),
                       Btn("❌ Skip", callback_data=f"t:no:{tid}")]]))
    await say(ctx, "Pick the topics you like 👆", Kb([[Btn("🔄 More ideas", callback_data="t:more")]]))


async def daily_job(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await propose_topics(ctx)


# ------------------------------------------------------------------ reels
async def send_for_review(ctx, rid: int, spec: dict, video, note: str = "") -> None:
    cap = caption_text(spec)
    store.update_reel(rid, status="review", caption=cap)
    preview = f"🎬 <b>Reel #{rid}</b> {note}\n\n{esc(cap)}"
    if len(preview) > 1000:
        preview = preview[:990] + "…"
    with open(video, "rb") as f:
        await ctx.bot.send_video(OWNER, f, caption=preview, parse_mode=ParseMode.HTML, supports_streaming=True,
                                 width=1080, height=1920, read_timeout=300, write_timeout=300,
                                 reply_markup=Kb([[Btn("✅ Post", callback_data=f"r:post:{rid}"),
                                                   Btn("✏️ Edit", callback_data=f"r:edit:{rid}"),
                                                   Btn("❌ Drop", callback_data=f"r:drop:{rid}")]]))


async def make_reel(ctx, tid: int, rid: int | None = None) -> None:
    t = store.topic(tid)
    if rid is None:
        rid = store.add_reel(tid, "")
    folder = config.REELS_DIR / f"{date.today():%Y%m%d}-{rid}"
    store.update_reel(rid, folder=str(folder), status="producing", error=None)
    topic = {"title_ar": t["title"], "summary_ar": t["summary"], "angle": t["angle"]}
    if WORK.locked():
        await say(ctx, f"⏳ Reel #{rid} is queued behind another reel…")
    async with WORK:
        await say(ctx, f"🎬 Making reel #{rid}: <b>{esc(t['title'])}</b>\nScript → images → voice → video (about 3–5 min)…")
        try:
            video, spec = await asyncio.to_thread(produce, topic, folder)
        except Exception as e:
            log.exception("production failed")
            store.update_reel(rid, status="failed", error=str(e)[:1000])
            await say(ctx, f"❌ Reel #{rid} failed:\n<code>{short_error(e)}</code>",
                      Kb([[Btn("🔁 Try again", callback_data=f"r:retry:{rid}")]]))
            return
    await send_for_review(ctx, rid, spec, video)


async def edit_reel(ctx, rid: int, feedback: str) -> None:
    r = store.reel(rid)
    folder = Path(r["folder"])
    store.update_reel(rid, status="editing")
    async with WORK:
        await say(ctx, f"✏️ Updating reel #{rid}…")
        try:
            video, spec = await asyncio.to_thread(revise, folder, feedback)
        except Exception as e:
            log.exception("revision failed")
            store.update_reel(rid, status="review", error=str(e)[:1000])
            await say(ctx, f"❌ Edit failed:\n<code>{short_error(e)}</code>\nThe previous version is unchanged.",
                      Kb([[Btn("✏️ Try another edit", callback_data=f"r:edit:{rid}")]]))
            return
    await send_for_review(ctx, rid, spec, video, "(updated)")


def ig_token() -> str | None:
    return store.get("ig_token") or config.IG_ACCESS_TOKEN


async def post_reel(ctx, rid: int) -> None:
    r = store.reel(rid)
    video = Path(r["folder"]) / "reel.mp4"
    store.update_reel(rid, status="posting")
    await say(ctx, f"📤 Posting reel #{rid} to Instagram…")
    try:
        res = await asyncio.to_thread(instagram.publish_reel, video, r["caption"], ig_token())
    except Exception as e:
        log.exception("instagram publish failed")
        store.update_reel(rid, status="review", error=str(e)[:1000])
        await say(ctx, f"❌ Posting failed:\n<code>{short_error(e)}</code>",
                  Kb([[Btn("🔁 Try posting again", callback_data=f"r:post:{rid}")]]))
        return
    store.update_reel(rid, status="posted", ig_id=res["id"], permalink=res.get("permalink"))
    await say(ctx, f"✅ Reel #{rid} is live on Instagram!\n{res.get('permalink') or ''}")


async def refresh_ig_token(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    tok = ig_token()
    if not tok:
        return
    try:
        store.put("ig_token", await asyncio.to_thread(instagram.refresh_token, tok))
        log.info("Instagram token refreshed")
    except Exception as e:
        await say(ctx, f"⚠️ Could not refresh the Instagram token:\n<code>{short_error(e)}</code>")


# ------------------------------------------------------------------ handlers
async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not is_owner(update):
        await q.answer("Not allowed"); return
    await q.answer()
    kind, action, *rest = q.data.split(":")
    ident = int(rest[0]) if rest else None
    run = ctx.application.create_task

    async def mark(note: str):            # replace the buttons with a status line
        try:
            if q.message.caption is not None:
                await q.edit_message_caption((q.message.caption_html or "") + f"\n\n{note}", parse_mode=ParseMode.HTML)
            else:
                await q.edit_message_text(q.message.text_html + f"\n\n{note}", parse_mode=ParseMode.HTML)
        except Exception:
            await q.edit_message_reply_markup(None)

    if kind == "t":
        if action == "more":
            await q.edit_message_reply_markup(None)
            run(propose_topics(ctx))
        elif action == "ok":
            store.set_topic_status(ident, "approved"); await mark("✅ <b>Approved</b>")
            run(make_reel(ctx, ident))
        elif action == "no":
            store.set_topic_status(ident, "rejected"); await mark("❌ Skipped")
    elif kind == "r":
        r = store.reel(ident)
        if not r:
            return
        if action == "post":
            if r["status"] in ("posting", "posted"):
                return
            await mark("📤 Posting…"); run(post_reel(ctx, ident))
        elif action == "edit":
            ctx.bot_data["edit_for"] = ident
            await q.edit_message_reply_markup(None)
            await say(ctx, f"✏️ What should I change in reel #{ident}?\nWrite it in one message, Arabic or English "
                           "(e.g. <i>make the hook shorter</i>, <i>change the picture in scene 3</i>, "
                           "<i>add a tip about winter</i>).")
        elif action == "drop":
            store.update_reel(ident, status="dropped"); await mark("🗑 Dropped")
        elif action == "retry":
            await q.edit_message_reply_markup(None)
            run(make_reel(ctx, r["topic_id"], ident))


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_owner(update):
        return
    rid = ctx.bot_data.pop("edit_for", None)
    if rid is None:
        await update.message.reply_text("Use the buttons, or /topics to get new ideas now. /help shows everything.")
        return
    await update.message.reply_text(f"👍 Got it, updating reel #{rid}.")
    ctx.application.create_task(edit_reel(ctx, rid, update.message.text))


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not OWNER:
        await update.message.reply_text(f"Your Telegram user id is {uid}.\nPut TELEGRAM_OWNER_ID={uid} in the .env file and restart the agent.")
    elif uid == OWNER:
        await cmd_help(update, ctx)
    else:
        await update.message.reply_text("This is a private bot.")


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_owner(update):
        return
    await update.message.reply_html(
        f"🤖 <b>{esc(config.BRAND)} reel agent</b>\n\n"
        f"Every day at <b>{config.DAILY_TIME}</b> ({config.TIMEZONE}) I send {config.TOPICS_PER_DAY} topic ideas.\n"
        "✅ a topic → I make the reel and send it to you.\n"
        "Then ✅ Post (to Instagram), ✏️ Edit (tell me what to change) or ❌ Drop.\n\n"
        "/topics: get topic ideas now\n/status: what I'm working on\n/help: this message")


async def cmd_topics(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if is_owner(update):
        ctx.application.create_task(propose_topics(ctx))


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_owner(update):
        return
    lines = []
    for st, label in [("producing", "🎬 making"), ("editing", "✏️ editing"), ("review", "👀 waiting for you"),
                      ("posting", "📤 posting"), ("failed", "❌ failed")]:
        rs = store.reels_by_status(st)
        if rs:
            lines.append(f"{label}: " + ", ".join(f"#{r['id']}" for r in rs))
    posted = store.reels_by_status("posted")
    lines.append(f"✅ posted so far: {len(posted)}")
    await update.message.reply_html("\n".join(lines))


async def on_startup(app: Application) -> None:
    # reels interrupted by a restart go back to "failed" so they can be retried
    for r in store.reels_by_status("producing", "editing", "posting"):
        store.update_reel(r["id"], status="failed" if r["status"] == "producing" else "review")
    if OWNER:
        await app.bot.send_message(OWNER, f"🤖 Agent started. Topics every day at {config.DAILY_TIME} ({config.TIMEZONE}). /help")


def main() -> None:
    if not config.TELEGRAM_TOKEN:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN in .env")
    app = (Application.builder().token(config.TELEGRAM_TOKEN).concurrent_updates(True)
           .post_init(on_startup).build())
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("topics", cmd_topics))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    if OWNER:
        hh, mm = map(int, config.DAILY_TIME.split(":"))
        tz = ZoneInfo(config.TIMEZONE)
        app.job_queue.run_daily(daily_job, time=dtime(hh, mm, tzinfo=tz), name="daily-topics")
        app.job_queue.run_repeating(refresh_ig_token, interval=7 * 24 * 3600, first=60, name="ig-token")
    log.info("Agent running")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
