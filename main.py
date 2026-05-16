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
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("lockdown")

# ── Stats Counter ──────────────────────────────────────────────────────────────
stats = {
    "deleted":   0,
    "failed":    0,
    "skipped":   0,   # already-deleted / not-found
    "unblocked": 0,   # relationships reversed by lockdown
    "reopened":  0,   # DM channels re-opened after closure
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


async def safe_unblock(user: discord.User, reason: str) -> None:
    """
    Reverse a block/ignore action performed by a compromised account.
    Handles both RelationshipType.blocked and RelationshipType.incoming_request
    that a hacker might trigger to hide communication trails.
    """
    MAX_RETRIES = 3

    user_tag = f"{user} (ID: {user.id})"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # discord.py-self exposes remove_relationship() to undo block/ignore
            await user.remove_relationship()
            stats["unblocked"] += 1
            log.warning(
                f"[UNBLOCKED #{stats['unblocked']}] Reversed '{reason}' on {user_tag}"
            )
            return

        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, "retry_after", None) or (attempt * 2.5)
                log.warning(
                    f"[RATE-LIMIT/UNBLOCK] Attempt {attempt}/{MAX_RETRIES}. "
                    f"Sleeping {retry_after:.2f}s... | {user_tag}"
                )
                await asyncio.sleep(retry_after)

            elif e.status == 404:
                # Relationship already gone — that's fine
                log.info(f"[UNBLOCK SKIP] Relationship already removed for {user_tag}")
                return

            else:
                log.error(f"[UNBLOCK HTTP {e.status}] {e.text} | {user_tag}")
                return

        except Exception as e:
            log.exception(f"[UNBLOCK UNEXPECTED] {e} | {user_tag}")
            return

    log.error(f"[UNBLOCK FAILED] Could not reverse '{reason}' after {MAX_RETRIES} attempts | {user_tag}")


async def safe_reopen_dm(user: discord.User) -> None:
    """
    Re-open a DM channel that was closed/hidden by a compromised account.
    Uses create_dm() which is idempotent — safe to call even if DM still exists.
    """
    user_tag = f"{user} (ID: {user.id})"
    MAX_RETRIES = 3

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            channel = await user.create_dm()
            stats["reopened"] += 1
            log.warning(
                f"[DM REOPENED #{stats['reopened']}] Restored hidden DM with {user_tag} "
                f"→ channel ID: {channel.id}"
            )
            return

        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, "retry_after", None) or (attempt * 2.5)
                log.warning(
                    f"[RATE-LIMIT/DM] Attempt {attempt}/{MAX_RETRIES}. "
                    f"Sleeping {retry_after:.2f}s... | {user_tag}"
                )
                await asyncio.sleep(retry_after)

            else:
                log.error(f"[DM REOPEN HTTP {e.status}] {e.text} | {user_tag}")
                return

        except Exception as e:
            log.exception(f"[DM REOPEN UNEXPECTED] {e} | {user_tag}")
            return

    log.error(f"[DM REOPEN FAILED] Could not re-open DM with {user_tag} after {MAX_RETRIES} attempts")


def print_stats() -> None:
    log.info(
        f"[STATS] Deleted={stats['deleted']} | "
        f"Failed={stats['failed']} | "
        f"Skipped={stats['skipped']} | "
        f"Unblocked={stats['unblocked']} | "
        f"DMs-Reopened={stats['reopened']}"
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
    log.info("=" * 60)
    log.info("   ⚠️  EMERGENCY LOCKDOWN BOT — ACTIVE (v2)")
    log.info(f"   User     : {bot.user} (ID: {bot.user.id})")
    log.info(f"   Watching : ALL servers, DMs, Group DMs")
    log.info(f"   Guards   : message-delete | unblock | dm-reopen")
    log.info("=" * 60)

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

    # ── Relationship sweep: unblock anyone already blocked at startup ──
    log.info("[STARTUP] Checking for pre-existing blocks/ignores...")
    sweep_count = 0
    try:
        for relationship in bot.user.relationships:
            rel_type = relationship.type

            # RelationshipType.blocked  → hacker blocked a victim
            # RelationshipType.ignored  → hacker silenced a victim (discord.py-self exposes this)
            if rel_type in (
                discord.RelationshipType.blocked,
                discord.RelationshipType.ignored,
            ):
                asyncio.ensure_future(
                    safe_unblock(relationship.user, reason=str(rel_type))
                )
                sweep_count += 1
    except AttributeError:
        # .relationships may not be available in all discord.py-self builds
        log.warning("[STARTUP] Could not read relationships list — skipping sweep.")

    if sweep_count:
        log.warning(f"[STARTUP] Queued {sweep_count} pre-existing block(s)/ignore(s) for reversal.")
    else:
        log.info("[STARTUP] No pre-existing blocks or ignores found.")


@bot.event
async def on_message(message: discord.Message):
    """Instantly wipe any new message sent by own account."""
    if message.author.id != bot.user.id:
        return

    asyncio.ensure_future(safe_delete(message, source="live"))


@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    """Wipe edited messages too — compromised accounts sometimes edit instead of send."""
    if after.author.id != bot.user.id:
        return

    asyncio.ensure_future(safe_delete(after, source="edit"))


# ── NEW: Auto Unblock / Unignore ───────────────────────────────────────────────
@bot.event
async def on_relationship_add(relationship: discord.Relationship):
    """
    Fires whenever a relationship is created (friend request, block, ignore, etc.).
    If the compromised account blocks or ignores someone, reverse it immediately.
    """
    rel_type = relationship.type
    user     = relationship.user

    # Only intercept hostile relationship types
    if rel_type not in (
        discord.RelationshipType.blocked,
        discord.RelationshipType.ignored,
    ):
        return

    log.warning(
        f"[ALERT] Hostile relationship detected: type='{rel_type}' "
        f"→ target={user} (ID: {user.id}). Reversing instantly..."
    )
    asyncio.ensure_future(safe_unblock(user, reason=str(rel_type)))


@bot.event
async def on_relationship_update(before: discord.Relationship, after: discord.Relationship):
    """
    Fires when a relationship changes type (e.g. friend → blocked).
    Catches the edge case where an existing relationship is escalated to a block.
    """
    if after.type not in (
        discord.RelationshipType.blocked,
        discord.RelationshipType.ignored,
    ):
        return

    user = after.user
    log.warning(
        f"[ALERT] Relationship escalated to '{after.type}' "
        f"→ target={user} (ID: {user.id}). Reversing instantly..."
    )
    asyncio.ensure_future(safe_unblock(user, reason=str(after.type)))


# ── NEW: Auto Re-open Closed DMs ──────────────────────────────────────────────
@bot.event
async def on_private_channel_delete(channel: discord.abc.PrivateChannel):
    """
    Fires when a DM or Group DM is closed/hidden.
    Re-opens it so the chat history stays visible to the account owner.
    Only handles 1-on-1 DMChannel; Group DMs cannot be re-opened via API.
    """
    if not isinstance(channel, discord.DMChannel):
        # Group DMs: log and skip — create_dm() doesn't apply
        log.warning(
            f"[DM CLOSED] Group DM (ID: {channel.id}) was closed. "
            f"Cannot auto-reopen group DMs via API."
        )
        return

    recipient = channel.recipient
    if recipient is None:
        log.warning(f"[DM CLOSED] DMChannel {channel.id} closed but recipient is unknown — skipping.")
        return

    log.warning(
        f"[ALERT] DM with {recipient} (ID: {recipient.id}) was closed/hidden. "
        f"Re-opening immediately..."
    )
    asyncio.ensure_future(safe_reopen_dm(recipient))


# ── Disconnect / Resume ────────────────────────────────────────────────────────
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
            sys.exit(1)

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
            if not bot.is_closed():
                await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
