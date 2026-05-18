"""
Lockdown Bot v5.1 — Multi-Account & Advanced Scam Filter
════════════════════════════════════════════════════════
• অল-টাইম একটিভ (টাইম শিডিউল অফ করা)।
• কোনো ব্যাকফিল (পুরোনো মেসেজ ডিলিট) হবে না।
• "bro" + (লিংক/ছবি), ক্রিপ্টো স্ক্যাম এবং ২টির বেশি 'Untitled' স্ক্রিনশট স্প্যাম হলেই ডিলিট করবে।
"""

import asyncio
import logging
import os
import random
import signal
import sys
from dataclasses import dataclass
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

# ── Stealth & Filter Config ────────────────────────────────────────────────────
DELETE_DELAY_MIN = 0.5
DELETE_DELAY_MAX = 2.0

SCAM_KEYWORDS = [
    "bonus", "usdt", "claim", "reward", "giveaway", 
    "mrbeast", "crypto", "casino", "stake", "free money"
]
LINK_INDICATORS = ["http://", "https://", "www."]


# ── Advanced Scam Filter Logic ──────────────────────────────────────────────────
def is_scam_msg(message: discord.Message) -> bool:
    """মেসেজটি স্ক্যাম কি না তা ফিল্টার করার অ্যাডভান্সড লজিক"""
    content_lower = message.content.lower()

    # ১. হাই-রিক্স ক্রিপ্টো কি-ওয়ার্ড চেক
    for word in SCAM_KEYWORDS:
        if word in content_lower:
            return True
        for embed in message.embeds:
            if embed.description and word in embed.description.lower():
                return True
            if embed.title and word in embed.title.lower():
                return True

    has_link = any(indicator in content_lower for indicator in LINK_INDICATORS)
    has_attachment = len(message.attachments) > 0 or len(message.embeds) > 0

    # ২. "bro" + (লিংক অথবা ইমেজ) কম্বিনেশন চেক
    if "bro" in content_lower and (has_link or has_attachment):
        return True

    # ৩. যেকোনো প্রকার লিংক এবং ইমেজ একসাথে থাকলে (স্ক্রিনশট স্ক্যাম)
    if has_link and has_attachment:
        return True

    # ৪. 'Untitled' ফাইলনেম অ্যাটাক ফিল্টার (রিনেম না করা ৪টা বা ২টা ইমেজের স্প্যাম)
    untitled_images = sum(1 for a in message.attachments if "untitled" in a.filename.lower())
    if untitled_images >= 2:
        return True

    # ৫. র‍্যান্ডম টেক্সট এভেশন ফিল্টার (যেমন: "meptluwx" + একাধিক ছবি)
    if len(message.attachments) >= 3:
        words = content_lower.split()
        # যদি মেসেজে কোনো কাজের কথা না থাকে, শুধু ১টি বড় র‍্যান্ডম শব্দ থাকে
        if len(words) == 1 and len(words[0]) > 6:
            return True
        # যদি কোনো টেক্সটই না থাকে, হ্যাকার শুধু ইমেজ ব্লাস্ট করে
        if len(words) == 0:
            return True

    return False


# ── Shared Utilities ───────────────────────────────────────────────────────────
async def human_delay(min_s: float = DELETE_DELAY_MIN, max_s: float = DELETE_DELAY_MAX) -> None:
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
            acc.log.info(f"   LOCKDOWN BOT v5.1 — [{acc.label}] ACTIVE")
            acc.log.info(f"   User   : {instance.user} (ID: {instance.user.id})")
            acc.log.info(f"   Filter : Active (Advanced Scam & Anti-Evasion Mode)")
            acc.log.info("=" * 60)

            try:
                await instance.change_presence(status=discord.Status.invisible, activity=None)
            except Exception:
                pass

            # Block sweep
            swept = 0
            try:
                for rel in instance.user.relationships:
                    if rel.type in (discord.RelationshipType.blocked, discord.RelationshipType.ignored):
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
            if is_scam_msg(message):
                asyncio.ensure_future(acc._safe_delete(message, "live"))

        @instance.event
        async def on_message_edit(before: discord.Message, after: discord.Message):
            if after.author.id != instance.user.id:
                return
            if is_scam_msg(after):
                asyncio.ensure_future(acc._safe_delete(after, "edit"))

        @instance.event
        async def on_relationship_add(relationship: discord.Relationship):
            if relationship.type not in (discord.RelationshipType.blocked, discord.RelationshipType.ignored):
                return
            acc.log.warning(f"[ALERT] {relationship.type} on {relationship.user} — reversing...")
            asyncio.ensure_future(acc._safe_unblock(relationship.user, str(relationship.type)))

        @instance.event
        async def on_relationship_update(before: discord.Relationship, after: discord.Relationship):
            if after.type not in (discord.RelationshipType.blocked, discord.RelationshipType.ignored):
                return
            acc.log.warning(f"[ALERT] Escalated to {after.type} on {after.user} — reversing...")
            asyncio.ensure_future(acc._safe_unblock(after.user, str(after.type)))

        @instance.event
        async def on_private_channel_delete(channel: discord.abc.PrivateChannel):
            if not isinstance(channel, discord.DMChannel) or channel.recipient is None:
                return
            acc.log.warning(f"[ALERT] DM closed with {channel.recipient} — re-opening...")
            asyncio.ensure_future(acc._safe_reopen_dm(channel.recipient))

        @instance.event
        async def on_disconnect():
            acc.log.warning("[DISCONNECT]")
            acc.log.info(f"[STATS] {acc.stats.summary()}")

    # ── Action methods ──────────────────────────────────────────────────────────
    async def _safe_delete(self, message: discord.Message, source: str = "live") -> None:
        await human_delay(DELETE_DELAY_MIN, DELETE_DELAY_MAX)
        for attempt in range(1, 5):
            try:
                await message.delete()
                self.stats.deleted += 1
                self.log.info(f"[WIPED #{self.stats.deleted}] [{source.upper()}] {describe(message)}")
                return
            except discord.HTTPException as e:
                if e.status == 429:
                    wait = jitter(getattr(e, "retry_after", None) or attempt * 3.0)
                    await asyncio.sleep(wait)
                elif e.status in (403, 404):
                    self.stats.failed += 1 if e.status == 403 else 0
                    return
                else:
                    return
            except Exception:
                return
        self.stats.failed += 1

    async def _safe_unblock(self, user: discord.User, reason: str = "") -> None:
        await human_delay(0.5, 1.5)
        for attempt in range(1, 4):
            try:
                await user.remove_relationship()
                self.stats.unblocked += 1
                self.log.warning(f"[UNBLOCKED #{self.stats.unblocked}] '{reason}' reversed → {user}")
                return
            except discord.HTTPException as e:
                if e.status == 429:
                    await asyncio.sleep(jitter(3.0))
                else:
                    return
            except Exception:
                return

    async def _safe_reopen_dm(self, user: discord.User) -> None:
        await human_delay(0.5, 2.0)
        for attempt in range(1, 4):
            try:
                ch = await user.create_dm()
                self.stats.reopened += 1
                self.log.warning(f"[DM REOPENED #{self.stats.reopened}] Hidden DM with {user} restored.")
                return
            except discord.HTTPException as e:
                if e.status == 429:
                    await asyncio.sleep(jitter(3.0))
                else:
                    return
            except Exception:
                return

    # ── Public Lifecycle ────────────────────────────────────────────────────────
    async def run_session(self) -> None:
        bot = self._make_bot()
        self._bot = bot
        try:
            await bot.start(self.token)
        except discord.LoginFailure:
            self.log.critical("[FATAL] Bad token — skipping account.")
            raise  
        except Exception:
            await asyncio.sleep(5)
        finally:
            if not bot.is_closed():
                await bot.close()
            self._bot = None

    async def run_forever(self) -> None:
        self.log.info(f"[INIT] Session started.")
        while True:
            try:
                await self.run_session()
            except discord.LoginFailure:
                return
            await asyncio.sleep(5)


# ── Global Shutdown & Main ─────────────────────────────────────────────────────
_sessions: list[AccountSession] = []

def handle_exit(sig, frame):
    root_log.info(f"[SHUTDOWN] Signal {sig}. Printing Stats...")
    for s in _sessions:
        root_log.info(f"   [{s.label}] {s.stats.summary()}")
    sys.exit(0)

signal.signal(signal.SIGINT,  handle_exit)
signal.signal(signal.SIGTERM, handle_exit)

async def main():
    global _sessions
    _sessions = [AccountSession(token=tok, label=f"ACC-{i + 1}") for i, tok in enumerate(TOKENS)]
    root_log.info(f"[MAIN] Starting launcher for {[s.label for s in _sessions]}")
    await asyncio.gather(*[s.run_forever() for s in _sessions], return_exceptions=True)

if __name__ == "__main__":
    asyncio.run(main())
