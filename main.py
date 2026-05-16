import discord
import asyncio
import logging
import os
import signal
import sys
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
    handlers=[
        logging.StreamHandler(sys.stdout),  # Render logs-এ দেখা যাবে
    ],
)
log = logging.getLogger("lockdown")

# ── Stats Counter ──────────────────────────────────────────────────────────────
stats = {
    "deleted": 0,
    "failed":  0,
    "skipped": 0,  # already-deleted / not-found
}

# ── Bot ────────────────────────────────────────────────────────────────────────
bot = commands.Bot(command_prefix="\x00", self_bot=True)


# ── Helpers ────────────────────────────────────────────────────────────────────
def describe(message: discord.Message) -> str:
    """Human-readable summary of a message for logging."""
    parts = []
    if message.content:
        preview = message.content[:50].replace("\n", " ")
        parts.append(f'text="{preview}"')
    if message.attachments:
        names = [a.filename for a in message.attachments]
        parts.append(f"attachments={names}")
    if message.embeds:
        parts.append(f"{len(message.embeds)} embed(s)")
    if message.stickers:
        parts.append(f"{len(message.stickers)} sticker(s)")

    ch = getattr(message.channel, "name", None) or f"DM/{message.channel.id}"
    content_str = ", ".join(parts) if parts else "(no text — attachment/embed only)"
    return f"ch={ch} | {content_str}"


async def safe_delete(message: discord.Message, source: str = "live") -> None:
    """
    Delete a message with retry on rate-limit.
    source: 'live' | 'backfill' | 'edit'
    """
    MAX_RETRIES = 4

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            await message.delete()
            stats["deleted"] += 1
            log.info(
                f"[WIPED #{stats['deleted']}] [{source.upper()}] {describe(message)}"
            )
            return

        except discord.HTTPException as e:

            if e.status == 429:  # Rate limited
                retry_after = getattr(e, "retry_after", None) or (attempt * 2.5)
                log.warning(
                    f"[RATE-LIMIT] Attempt {attempt}/{MAX_RETRIES}. "
                    f"Sleeping {retry_after:.2f}s... | {describe(message)}"
                )
                await asyncio.sleep(retry_after)

            elif e.status == 403:  # No permission
                stats["failed"] += 1
                log.error(f"[FORBIDDEN] No delete permission | {describe(message)}")
                return

            elif e.status == 404:  # Already gone
                stats["skipped"] += 1
                log.info(f"[ALREADY GONE] Message not found (deleted elsewhere) | {describe(message)}")
                return

            else:
                stats["failed"] += 1
                log.error(f"[HTTP {e.status}] {e.text} | {describe(message)}")
                return

        except discord.NotFound:
            stats["skipped"] += 1
            log.info(f"[ALREADY GONE] NotFound | {describe(message)}")
            return

        except Exception as e:
            stats["failed"] += 1
            log.exception(f"[UNEXPECTED] {e} | {describe(message)}")
            return

    stats["failed"] += 1
    log.error(f"[FAILED] Could not delete after {MAX_RETRIES} attempts | {describe(message)}")


def print_stats() -> None:
    log.info(
        f"[STATS] Deleted={stats['deleted']} | "
        f"Failed={stats['failed']} | "
        f"Skipped={stats['skipped']}"
    )


# ── Graceful Shutdown ──────────────────────────────────────────────────────────
def handle_exit(sig, frame):
    log.info(f"[SHUTDOWN] Signal {sig} received. Shutting down gracefully...")
    print_stats()
    log.info("[SHUTDOWN] Goodbye.")
    sys.exit(0)

signal.signal(signal.SIGINT,  handle_exit)
signal.signal(signal.SIGTERM, handle_exit)


# ── Events ─────────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    log.info("=" * 55)
    log.info("   ⚠️  EMERGENCY LOCKDOWN BOT — ACTIVE")
    log.info(f"   User     : {bot.user} (ID: {bot.user.id})")
    log.info(f"   Watching : ALL servers, DMs, Group DMs")
    log.info("=" * 55)

    # ── Backfill: recent DM messages sent before bot started ──
    log.info("[BACKFILL] Scanning cached DM/Group channels for recent messages...")
    backfill_count = 0

    for channel in bot.private_channels:
        try:
            async for message in channel.history(limit=20):
                if message.author.id == bot.user.id:
                    asyncio.ensure_future(safe_delete(message, source="backfill"))
                    backfill_count += 1
        except discord.Forbidden:
            log.warning(f"[BACKFILL] No access to channel {channel.id}")
        except Exception as e:
            log.warning(f"[BACKFILL] Error scanning channel {channel.id}: {e}")

    log.info(f"[BACKFILL] Queued {backfill_count} old message(s) for deletion.")


@bot.event
async def on_message(message: discord.Message):
    """Instantly wipe any new message sent by own account."""
    if message.author.id != bot.user.id:
        return

    # Fire-and-forget — event loop moves on immediately
    asyncio.ensure_future(safe_delete(message, source="live"))


@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    """Wipe edited messages too — compromised accounts sometimes edit instead of send."""
    if after.author.id != bot.user.id:
        return

    asyncio.ensure_future(safe_delete(after, source="edit"))


@bot.event
async def on_disconnect():
    log.warning("[DISCONNECT] Bot disconnected from Discord.")
    print_stats()


@bot.event
async def on_resumed():
    log.info("[RECONNECTED] Session resumed successfully.")


# ── Entry Point with Reconnect Loop ───────────────────────────────────────────
async def main():
    RECONNECT_DELAY = 5  # seconds between reconnect attempts

    while True:
        try:
            log.info("[START] Connecting to Discord...")
            await bot.start(USER_TOKEN)

        except discord.LoginFailure:
            log.critical("[FATAL] Invalid token — check DISCORD_TOKEN. Exiting.")
            sys.exit(1)  # No point retrying with a bad token

        except discord.ConnectionClosed as e:
            log.warning(f"[CONNECTION CLOSED] Code={e.code}. Reconnecting in {RECONNECT_DELAY}s...")
            await asyncio.sleep(RECONNECT_DELAY)

        except discord.GatewayNotFound:
            log.warning(f"[GATEWAY ERROR] Discord gateway unreachable. Retrying in {RECONNECT_DELAY}s...")
            await asyncio.sleep(RECONNECT_DELAY)

        except Exception as e:
            log.error(f"[ERROR] Unexpected: {e}. Retrying in {RECONNECT_DELAY}s...")
            await asyncio.sleep(RECONNECT_DELAY)

        finally:
            # Close the bot cleanly before retrying
            if not bot.is_closed():
                await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
