import discord
import asyncio
import logging
import os
import random
import signal
import sys
from datetime import datetime, timezone, timedelta
from discord.ext import commands
from dotenv import load_dotenv

# ── Load .env ──────────────────────────────────────────────────────────────────
load_dotenv()
USER_TOKEN = os.getenv("DISCORD_TOKEN")

if not USER_TOKEN:
    raise ValueError("DISCORD_TOKEN not found! Check your .env or Render environment variables.")

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("lockdown")

# ── Stats — session জুড়ে accumulate হয়, bot restart-এ reset হয় না ────────────
stats = {
    "deleted":   0,
    "failed":    0,
    "skipped":   0,
    "unblocked": 0,
    "reopened":  0,
}

# ── Stealth Config ─────────────────────────────────────────────────────────────
DELETE_DELAY_MIN = 0.8   # সেকেন্ড — delete এর আগে minimum wait
DELETE_DELAY_MAX = 3.2   # সেকেন্ড — delete এর আগে maximum wait
BACKFILL_LIMIT   = 5     # বেশি history scan = বেশি suspicious

# ── Time Schedule (Bangladesh UTC+6) ──────────────────────────────────────────
BD_TZ        = timezone(timedelta(hours=6))
ACTIVE_START = 1   # রাত ১টা
ACTIVE_END   = 10  # সকাল ১০টা


# ── Schedule Helpers ───────────────────────────────────────────────────────────
def is_active_time() -> bool:
    h = datetime.now(BD_TZ).hour
    return ACTIVE_START <= h < ACTIVE_END


def secs_to_start() -> float:
    now = datetime.now(BD_TZ)
    nxt = now.replace(hour=ACTIVE_START, minute=0, second=0, microsecond=0)
    if now >= nxt:
        nxt += timedelta(days=1)
    return (nxt - now).total_seconds()


def secs_to_end() -> float:
    now = datetime.now(BD_TZ)
    end = now.replace(hour=ACTIVE_END, minute=0, second=0, microsecond=0)
    return max((end - now).total_seconds(), 0)


# ── Stealth Utilities ──────────────────────────────────────────────────────────
async def human_delay(min_s: float = DELETE_DELAY_MIN, max_s: float = DELETE_DELAY_MAX) -> None:
    """Random sleep — makes actions look human, not instant/robotic."""
    await asyncio.sleep(random.uniform(min_s, max_s))


def jitter(base: float) -> float:
    """±30% random jitter — avoids fixed-interval fingerprinting."""
    return base * random.uniform(0.7, 1.3)


# ── Message Helper ─────────────────────────────────────────────────────────────
def describe(message: discord.Message) -> str:
    parts = []
    if message.content:
        parts.append(f'text="{message.content[:50].replace(chr(10), " ")}"')
    if message.attachments:
        parts.append(f"files={[a.filename for a in message.attachments]}")
    if message.embeds:
        parts.append(f"{len(message.embeds)} embed(s)")
    if message.stickers:
        parts.append(f"{len(message.stickers)} sticker(s)")
    ch = getattr(message.channel, "name", None) or f"DM/{message.channel.id}"
    return f"ch={ch} | {', '.join(parts) or '(no text)'}"


# ── Core Actions ───────────────────────────────────────────────────────────────
async def safe_delete(message: discord.Message, source: str = "live") -> None:
    """Human-delayed delete with 429 retry + jitter."""
    delays = {
        "live":     (DELETE_DELAY_MIN, DELETE_DELAY_MAX),
        "edit":     (1.0, 4.0),
        "backfill": (2.0, 8.0),
    }
    lo, hi = delays.get(source, (DELETE_DELAY_MIN, DELETE_DELAY_MAX))
    await human_delay(lo, hi)

    for attempt in range(1, 5):
        try:
            await message.delete()
            stats["deleted"] += 1
            log.info(f"[WIPED #{stats['deleted']}] [{source.upper()}] {describe(message)}")
            return

        except discord.HTTPException as e:
            if e.status == 429:
                wait = jitter(getattr(e, "retry_after", None) or attempt * 3.0)
                log.warning(f"[RATE-LIMIT] Attempt {attempt}/4 → sleep {wait:.2f}s")
                await asyncio.sleep(wait)
            elif e.status == 403:
                stats["failed"] += 1
                log.error(f"[FORBIDDEN] {describe(message)}")
                return
            elif e.status == 404:
                stats["skipped"] += 1
                log.info(f"[GONE] {describe(message)}")
                return
            else:
                stats["failed"] += 1
                log.error(f"[HTTP {e.status}] {e.text}")
                return
        except discord.NotFound:
            stats["skipped"] += 1
            return
        except Exception as e:
            stats["failed"] += 1
            log.exception(f"[UNEXPECTED] {e}")
            return

    stats["failed"] += 1
    log.error(f"[FAILED] 4 attempts exhausted | {describe(message)}")


async def safe_unblock(user: discord.User, reason: str = "") -> None:
    """Reverse block/ignore with small human delay."""
    await human_delay(0.5, 1.5)
    tag = f"{user} ({user.id})"

    for attempt in range(1, 4):
        try:
            await user.remove_relationship()
            stats["unblocked"] += 1
            log.warning(f"[UNBLOCKED #{stats['unblocked']}] '{reason}' reversed -> {tag}")
            return
        except discord.HTTPException as e:
            if e.status == 429:
                wait = jitter(getattr(e, "retry_after", None) or attempt * 3.0)
                await asyncio.sleep(wait)
            elif e.status == 404:
                return  # already removed
            else:
                log.error(f"[UNBLOCK HTTP {e.status}] {tag}")
                return
        except Exception as e:
            log.exception(f"[UNBLOCK ERR] {e}")
            return


async def safe_reopen_dm(user: discord.User) -> None:
    """Re-open a closed DM channel."""
    await human_delay(0.5, 2.0)
    tag = f"{user} ({user.id})"

    for attempt in range(1, 4):
        try:
            ch = await user.create_dm()
            stats["reopened"] += 1
            log.warning(f"[DM REOPENED #{stats['reopened']}] {tag} -> ch={ch.id}")
            return
        except discord.HTTPException as e:
            if e.status == 429:
                wait = jitter(getattr(e, "retry_after", None) or attempt * 3.0)
                await asyncio.sleep(wait)
            elif e.status == 403:
                log.warning(f"[DM REOPEN BLOCKED] User has DMs disabled | {tag}")
                return
            else:
                log.error(f"[DM REOPEN HTTP {e.status}] {tag}")
                return
        except Exception as e:
            log.exception(f"[DM REOPEN ERR] {e}")
            return


def print_stats() -> None:
    log.info(
        f"[STATS] Deleted={stats['deleted']} | Failed={stats['failed']} | "
        f"Skipped={stats['skipped']} | Unblocked={stats['unblocked']} | "
        f"Reopened={stats['reopened']}"
    )


# ── Graceful Shutdown ──────────────────────────────────────────────────────────
def handle_exit(sig, frame):
    log.info(f"[SHUTDOWN] Signal {sig}.")
    print_stats()
    sys.exit(0)

signal.signal(signal.SIGINT,  handle_exit)
signal.signal(signal.SIGTERM, handle_exit)


# ────────────────────────────────────────────────────────────────────────────────
# KEY FIX: Bot factory — প্রতিটি session-এ নতুন Bot instance তৈরি হয়।
#
# কেন দরকার:
#   discord.py-self-এ একবার bot.close() হলে সেই object permanently closed হয়ে যায়।
#   পুরনো instance-এ আবার bot.start() call করলে "This client is already running."
#   বা silent failure হয় — কোনো event fire হয় না, কোনো কাজ হয় না।
#   Solution: প্রতিটি session শুরুতে fresh Bot + fresh event registrations।
# ────────────────────────────────────────────────────────────────────────────────
def make_bot() -> commands.Bot:
    """
    প্রতিটি connection cycle-এ একটি brand-new Bot object তৈরি করে।
    সব event handler এখানেই register হয় — global `bot` variable নেই।
    """
    instance = commands.Bot(
        command_prefix="\x00",
        self_bot=True,
        status=discord.Status.invisible,
        activity=None,
    )

    # ── on_ready ────────────────────────────────────────────────────────────────
    @instance.event
    async def on_ready():
        log.info("=" * 60)
        log.info("   LOCKDOWN BOT v3 — STEALTH MODE ACTIVE")
        log.info(f"   User   : {instance.user} (ID: {instance.user.id})")
        log.info(f"   Status : invisible | Delay: {DELETE_DELAY_MIN}-{DELETE_DELAY_MAX}s")
        log.info(f"   Window : 01:00-10:00 BD time")
        log.info("=" * 60)

        # Invisible নিশ্চিত করো connect হওয়ার পর
        try:
            await instance.change_presence(status=discord.Status.invisible, activity=None)
        except Exception:
            pass

        # Backfill — ছোট limit, কম suspicious
        count = 0
        for ch in instance.private_channels:
            try:
                async for msg in ch.history(limit=BACKFILL_LIMIT):
                    if msg.author.id == instance.user.id:
                        asyncio.ensure_future(safe_delete(msg, source="backfill"))
                        count += 1
            except Exception:
                pass
        log.info(f"[BACKFILL] Queued {count} old message(s).")

        # Block sweep — startup-এ আগে থেকে block করা থাকলে clear
        swept = 0
        try:
            for rel in instance.user.relationships:
                if rel.type in (
                    discord.RelationshipType.blocked,
                    discord.RelationshipType.ignored,
                ):
                    asyncio.ensure_future(safe_unblock(rel.user, str(rel.type)))
                    swept += 1
        except AttributeError:
            pass
        if swept:
            log.warning(f"[STARTUP] {swept} pre-existing block(s) queued for reversal.")

    # ── on_message ──────────────────────────────────────────────────────────────
    @instance.event
    async def on_message(message: discord.Message):
        if message.author.id != instance.user.id:
            return
        asyncio.ensure_future(safe_delete(message, source="live"))

    # ── on_message_edit ─────────────────────────────────────────────────────────
    @instance.event
    async def on_message_edit(before: discord.Message, after: discord.Message):
        if after.author.id != instance.user.id:
            return
        asyncio.ensure_future(safe_delete(after, source="edit"))

    # ── on_relationship_add ─────────────────────────────────────────────────────
    @instance.event
    async def on_relationship_add(relationship: discord.Relationship):
        if relationship.type not in (
            discord.RelationshipType.blocked,
            discord.RelationshipType.ignored,
        ):
            return
        log.warning(
            f"[ALERT] {relationship.type} detected -> {relationship.user}. Reversing..."
        )
        asyncio.ensure_future(safe_unblock(relationship.user, str(relationship.type)))

    # ── on_relationship_update ──────────────────────────────────────────────────
    @instance.event
    async def on_relationship_update(before: discord.Relationship, after: discord.Relationship):
        if after.type not in (
            discord.RelationshipType.blocked,
            discord.RelationshipType.ignored,
        ):
            return
        log.warning(
            f"[ALERT] Escalated to {after.type} -> {after.user}. Reversing..."
        )
        asyncio.ensure_future(safe_unblock(after.user, str(after.type)))

    # ── on_private_channel_delete ───────────────────────────────────────────────
    @instance.event
    async def on_private_channel_delete(channel: discord.abc.PrivateChannel):
        if not isinstance(channel, discord.DMChannel) or channel.recipient is None:
            return
        log.warning(
            f"[ALERT] DM closed -> {channel.recipient}. Re-opening..."
        )
        asyncio.ensure_future(safe_reopen_dm(channel.recipient))

    # ── on_disconnect / on_resumed ──────────────────────────────────────────────
    @instance.event
    async def on_disconnect():
        log.warning("[DISCONNECT]")
        print_stats()

    @instance.event
    async def on_resumed():
        log.info("[RECONNECTED]")
        try:
            await instance.change_presence(status=discord.Status.invisible, activity=None)
        except Exception:
            pass

    return instance


# ── Main Loop ──────────────────────────────────────────────────────────────────
async def main():
    while True:

        # ── Active window এর বাইরে হলে ঘুমাও ────────────────────────────────────
        if not is_active_time():
            sleep = secs_to_start()
            wake  = datetime.now(BD_TZ) + timedelta(seconds=sleep)
            log.info(
                f"[SCHEDULE] Outside active window. "
                f"Sleeping {sleep / 3600:.2f}h -> wake at {wake.strftime('%H:%M BD')}"
            )
            await asyncio.sleep(sleep)
            continue

        # ── Active window: ১টা-১০টা ──────────────────────────────────────────────
        remaining = secs_to_end()
        log.info(
            f"[SCHEDULE] Active window ON — {remaining / 3600:.2f}h remaining (until 10:00 BD)"
        )

        # প্রতিটি session-এ fresh bot instance — এটাই মূল fix
        bot = make_bot()

        try:
            await asyncio.wait_for(bot.start(USER_TOKEN), timeout=remaining)

        except asyncio.TimeoutError:
            # ১০টা বাজলে gracefully shutdown
            log.info("[SCHEDULE] 10:00 AM — active window ended. Shutting down for the day.")
            print_stats()
            if not bot.is_closed():
                await bot.close()

            sleep = secs_to_start()
            wake  = datetime.now(BD_TZ) + timedelta(seconds=sleep)
            log.info(f"[SCHEDULE] Next wake: {wake.strftime('%H:%M BD')}")
            await asyncio.sleep(sleep)

        except discord.LoginFailure:
            log.critical("[FATAL] Bad token. Exiting.")
            sys.exit(1)

        except (discord.ConnectionClosed, discord.GatewayNotFound) as e:
            # Network hiccup — জিততর নয়, reconnect করো
            wait = jitter(5)
            log.warning(f"[RECONNECT] {e.__class__.__name__} -> retry in {wait:.1f}s")
            await asyncio.sleep(wait)

        except Exception as e:
            wait = jitter(5)
            log.error(f"[ERROR] {e} -> retry in {wait:.1f}s")
            await asyncio.sleep(wait)

        finally:
            # close() safe to call multiple times — idempotent
            if not bot.is_closed():
                await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
