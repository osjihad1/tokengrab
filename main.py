"""
Lockdown Bot v4.1 — Multi-Account (No Backfill)
═══════════════════════════════════════════════
• বট চালু হওয়ার আগের কোনো মেসেজ ডিলিট করবে না।
• শুধুমাত্র চালু থাকার সময়ে পাঠানো লাইভ মেসেজ ডিলিট হবে।
"""

import asyncio
import logging
import os
import random
import signal
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

import discord
from discord.ext import commands
from dotenv import load_dotenv

# ── Load .env ──────────────────────────────────────────────────────────────────
load_dotenv()

TOKENS: list[str] = []
index = 1
while True:
    tok = os.getenv(f"DISCORD_TOKEN_{index}")
    if not tok:
        break
    TOKENS.append(tok)
    index += 1

if not TOKENS:
    single = os.getenv("DISCORD_TOKEN")
    if single:
        TOKENS.append(single)

if not TOKENS:
    raise ValueError(
        "No tokens found! Add DISCORD_TOKEN_1, DISCORD_TOKEN_2, ... to your .env"
    )

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
root_log = logging.getLogger("lockdown")

# ── Stealth Config ─────────────────────────────────────────────────────────────
DELETE_DELAY_MIN = 0.8
DELETE_DELAY_MAX = 3.2

# ── Time Schedule (Bangladesh UTC+6) ──────────────────────────────────────────
BD_TZ        = timezone(timedelta(hours=6))
ACTIVE_START = 1   # রাত ১টা
ACTIVE_END   = 10  # সকাল ১০টা


# ── Schedule Helpers ──────────────────────────────────────────────────────────
def is_active_time() -> bool:
    return ACTIVE_START <= datetime.now(BD_TZ).hour < ACTIVE_END


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


# ── Shared Utilities ───────────────────────────────────────────────────────────
async def human_delay(min_s: float = DELETE_DELAY_MIN,
                     max_s: float = DELETE_DELAY_MAX) -> None:
    await asyncio.sleep(random.uniform(min_s, max_s))


def jitter(base: float) -> float:
    return base * random.uniform(0.7, 1.3)


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


# ══════════════════════════════════════════════════════════════════════════════
# AccountSession
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class AccountStats:
    deleted:   int = 0
    failed:    int = 0
    skipped:   int = 0
    unblocked: int = 0
    reopened:  int = 0

    def summary(self) -> str:
        return (
            f"Deleted={self.deleted} | Failed={self.failed} | "
            f"Skipped={self.skipped} | Unblocked={self.unblocked} | "
            f"Reopened={self.reopened}"
        )


class AccountSession:
    def __init__(self, token: str, label: str) -> None:
        self.token  = token
        self.label  = label  
        self.stats  = AccountStats()
        self.log    = logging.getLogger(f"lockdown.{label}")
        self._bot: Optional[commands.Bot] = None

    def _make_bot(self) -> commands.Bot:
        instance = commands.Bot(
            command_prefix="\x00",
            self_bot=True,
            status=discord.Status.invisible,
            activity=None,
        )
        self._register_events(instance)
        return instance

    def _register_events(self, instance: commands.Bot) -> None:
        acc = self 

        @instance.event
        async def on_ready():
            acc.log.info("=" * 60)
            acc.log.info(f"   LOCKDOWN BOT v4.1 — [{acc.label}] LIVE ACTIVE")
            acc.log.info(f"   User   : {instance.user} (ID: {instance.user.id})")
            acc.log.info(f"   Status : invisible | Delay: {DELETE_DELAY_MIN}-{DELETE_DELAY_MAX}s")
            acc.log.info(f"   Window : {ACTIVE_START:02d}:00-{ACTIVE_END:02d}:00 BD")
            acc.log.info("=" * 60)

            try:
                await instance.change_presence(
                    status=discord.Status.invisible, activity=None
                )
            except Exception:
                pass

            # 💡 [BACKFILL REMOVED] পুরোনো মেসেজ ডিলিট করার লুপটি এখান থেকে পুরোপুরি বাদ দেওয়া হয়েছে।

            # Block sweep
            swept = 0
            try:
                for rel in instance.user.relationships:
                    if rel.type in (
                        discord.RelationshipType.blocked,
                        discord.RelationshipType.ignored,
                    ):
                        asyncio.ensure_future(acc._safe_unblock(rel.user, str(rel.type)))
                        swept += 1
            except AttributeError:
                pass
            if swept:
                acc.log.warning(f"[STARTUP] {swept} pre-existing block(s) queued.")

        @instance.event
        async def on_message(message: discord.Message):
            if message.author.id != instance.user.id:
                return
            asyncio.ensure_future(acc._safe_delete(message, "live"))

        @instance.event
        async def on_message_edit(before: discord.Message, after: discord.Message):
            if after.author.id != instance.user.id:
                return
            asyncio.ensure_future(acc._safe_delete(after, "edit"))

        @instance.event
        async def on_relationship_add(relationship: discord.Relationship):
            if relationship.type not in (
                discord.RelationshipType.blocked,
                discord.RelationshipType.ignored,
            ):
                return
            acc.log.warning(
                f"[ALERT] {relationship.type} on {relationship.user} — reversing..."
            )
            asyncio.ensure_future(acc._safe_unblock(relationship.user, str(relationship.type)))

        @instance.event
        async def on_relationship_update(
            before: discord.Relationship, after: discord.Relationship
        ):
            if after.type not in (
                discord.RelationshipType.blocked,
                discord.RelationshipType.ignored,
            ):
                return
            acc.log.warning(
                f"[ALERT] Escalated to {after.type} on {after.user} — reversing..."
            )
            asyncio.ensure_future(acc._safe_unblock(after.user, str(after.type)))

        @instance.event
        async def on_private_channel_delete(channel: discord.abc.PrivateChannel):
            if not isinstance(channel, discord.DMChannel) or channel.recipient is None:
                return
            acc.log.warning(
                f"[ALERT] DM closed with {channel.recipient} — re-opening..."
            )
            asyncio.ensure_future(acc._safe_reopen_dm(channel.recipient))

        @instance.event
        async def on_disconnect():
            acc.log.warning("[DISCONNECT]")
            acc.log.info(f"[STATS] {acc.stats.summary()}")

        @instance.event
        async def on_resumed():
            acc.log.info("[RECONNECTED]")
            try:
                await instance.change_presence(
                    status=discord.Status.invisible, activity=None
                )
            except Exception:
                pass

    # ── Action methods ──────────────────────────────────────────────────────────

    async def _safe_delete(self, message: discord.Message, source: str = "live") -> None:
        delays = {
            "live":     (DELETE_DELAY_MIN, DELETE_DELAY_MAX),
            "edit":     (1.0, 4.0),
        }
        lo, hi = delays.get(source, (DELETE_DELAY_MIN, DELETE_DELAY_MAX))
        await human_delay(lo, hi)

        for attempt in range(1, 5):
            try:
                await message.delete()
                self.stats.deleted += 1
                self.log.info(
                    f"[WIPED #{self.stats.deleted}] [{source.upper()}] {describe(message)}"
                )
                return
            except discord.HTTPException as e:
                if e.status == 429:
                    wait = jitter(getattr(e, "retry_after", None) or attempt * 3.0)
                    self.log.warning(f"[RATE-LIMIT] Attempt {attempt}/4 → sleep {wait:.2f}s")
                    await asyncio.sleep(wait)
                elif e.status == 403:
                    self.stats.failed += 1
                    self.log.error(f"[FORBIDDEN] {describe(message)}")
                    return
                elif e.status == 404:
                    self.stats.skipped += 1
                    return
                else:
                    self.stats.failed += 1
                    return
            except discord.NotFound:
                self.stats.skipped += 1
                return
            except Exception as e:
                self.stats.failed += 1
                return

        self.stats.failed += 1

    async def _safe_unblock(self, user: discord.User, reason: str = "") -> None:
        await human_delay(0.5, 1.5)
        tag = f"{user} ({user.id})"
        for attempt in range(1, 4):
            try:
                await user.remove_relationship()
                self.stats.unblocked += 1
                self.log.warning(
                    f"[UNBLOCKED #{self.stats.unblocked}] '{reason}' reversed → {tag}"
                )
                return
            except discord.HTTPException as e:
                if e.status == 429:
                    wait = jitter(getattr(e, "retry_after", None) or attempt * 3.0)
                    await asyncio.sleep(wait)
                elif e.status == 404:
                    return
                else:
                    return
            except Exception:
                return

    async def _safe_reopen_dm(self, user: discord.User) -> None:
        await human_delay(0.5, 2.0)
        tag = f"{user} ({user.id})"
        for attempt in range(1, 4):
            try:
                ch = await user.create_dm()
                self.stats.reopened += 1
                self.log.warning(
                    f"[DM REOPENED #{self.stats.reopened}] {tag} → ch={ch.id}"
                )
                return
            except discord.HTTPException as e:
                if e.status == 429:
                    wait = jitter(getattr(e, "retry_after", None) or attempt * 3.0)
                    await asyncio.sleep(wait)
                else:
                    return
            except Exception:
                return

    # ── Public: session lifecycle ────────────────────────────────────────────────

    async def run_session(self) -> None:
        remaining = secs_to_end()
        self.log.info(
            f"[SCHEDULE] Active — {remaining / 3600:.2f}h remaining (until {ACTIVE_END:02d}:00 BD)"
        )

        bot = self._make_bot()
        self._bot = bot

        try:
            await asyncio.wait_for(bot.start(self.token), timeout=remaining)
        except asyncio.TimeoutError:
            self.log.info("[SCHEDULE] Active window ended — shutting down.")
            self.log.info(f"[STATS] {self.stats.summary()}")
        except discord.LoginFailure:
            self.log.critical("[FATAL] Bad token — this account will be skipped.")
            raise  
        except (discord.ConnectionClosed, discord.GatewayNotFound) as e:
            wait = jitter(5)
            await asyncio.sleep(wait)
        except Exception as e:
            wait = jitter(5)
            await asyncio.sleep(wait)
        finally:
            if not bot.is_closed():
                await bot.close()
            self._bot = None

    async def run_forever(self) -> None:
        self.log.info(f"[INIT] Account session started.")
        while True:
            if not is_active_time():
                sleep = secs_to_start()
                wake  = datetime.now(BD_TZ) + timedelta(seconds=sleep)
                self.log.info(
                    f"[SCHEDULE] Outside window — sleeping {sleep / 3600:.2f}h "
                    f"→ wake {wake.strftime('%H:%M BD')}"
                )
                await asyncio.sleep(sleep)
                continue

            try:
                await self.run_session()
            except discord.LoginFailure:
                return

            if not is_active_time():
                sleep = secs_to_start()
                await asyncio.sleep(sleep)


# ── Global summary ────────────────────────────────────────────────────────────
def print_all_stats(sessions: list[AccountSession]) -> None:
    root_log.info("=" * 60)
    root_log.info("   FINAL STATS — ALL ACCOUNTS")
    for s in sessions:
        root_log.info(f"   [{s.label}] {s.stats.summary()}")
    root_log.info("=" * 60)


# ── Graceful Shutdown ──────────────────────────────────────────────────────────
_sessions: list[AccountSession] = []

def handle_exit(sig, frame):
    root_log.info(f"[SHUTDOWN] Signal {sig}.")
    print_all_stats(_sessions)
    sys.exit(0)

signal.signal(signal.SIGINT,  handle_exit)
signal.signal(signal.SIGTERM, handle_exit)


# ── Entry Point ────────────────────────────────────────────────────────────────
async def main():
    global _sessions

    _sessions = [
        AccountSession(token=tok, label=f"ACC-{i + 1}")
        for i, tok in enumerate(TOKENS)
    ]

    root_log.info(f"[MAIN] Starting {len(_sessions)} account(s): "
                  f"{[s.label for s in _sessions]}")

    results = await asyncio.gather(
        *[s.run_forever() for s in _sessions],
        return_exceptions=True,
    )

    for session, result in zip(_sessions, results):
        if isinstance(result, Exception):
            root_log.error(f"[{session.label}] Exited with error: {result}")

    print_all_stats(_sessions)
    root_log.info("[MAIN] All account sessions ended.")


if __name__ == "__main__":
    asyncio.run(main())
