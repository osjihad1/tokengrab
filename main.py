import asyncio
import logging
import os
import random
import re
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
    raise ValueError("No tokens found! Add DISCORD_TOKEN_1, DISCORD_TOKEN_2, ... to your .env")

# ── Logging Setup ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
root_log = logging.getLogger("system")

# ── Stealth & Safety Thresholds ────────────────────────────────────────────────
DELETE_DELAY_MIN = 0.8  
DELETE_DELAY_MAX = 2.4

SCAM_KEYWORDS = ["bonus", "usdt", "claim", "reward", "giveaway", "mrbeast", "crypto", "casino", "stake", "free money"]
LINK_RE = re.compile(r'(https?://[^\s]+|www\.[^\s]+)')
MARKDOWN_LINK_RE = re.compile(r'\[.*?\]\(https?://\S+\)')
GIBBERISH_RE = re.compile(r'^[a-zA-Z0-9]{7,15}$')


# ── 🚨 The Master Filter Logic ─────────────────────────────────────────────────
def is_scam_msg(message: discord.Message) -> bool:
    """হ্যাকারের সব প্যাটার্ন ধ্বংস করার মাস্টার লজিক (ফলস-পজিটিভ ফ্রি)"""
    
    if not message or (not message.content and not message.attachments and not message.embeds):
        return False

    content_lower = message.content.lower().strip()
    has_attachment = len(message.attachments) > 0 or len(message.embeds) > 0
    has_mention = len(message.mentions) > 0

    # 🟢 রুল ০: সিক্রেট বাইপাস কী (Secret Password: msc)
    # মেসেজে "msc" লেখা থাকলে বট কোনোভাবেই সেটা ডিলিট করবে না, সব ফিল্টার ইগনোর করবে।
    if re.search(r'\bmsc\b', content_lower):
        return False

    # 🔴 রুল ১: ডিসকর্ড ইনভাইট লিংক ব্লক
    has_dc_invite = bool(re.search(r'(discord\.gg/|discord\.com/invite/|discordapp\.com/invite/)', content_lower))
    if has_dc_invite:
        return True  # 'msc' পাসওয়ার্ড ছাড়া ইনভাইট লিংক পাঠালেই ডিলিট

    # 🔴 রুল ২: মেসেজের যেকোনো জায়গায় 'bro' বা 'BRO' থাকলেই ডিলিট
    if re.search(r'\bbro\b', content_lower):
        return True

    # 🔴 রুল ৩: মেসেজে ছবি আছে এবং সাথে কাউকে মেনশন (@ping) করেছে
    if has_attachment and has_mention:
        return True

    # 🔴 রুল ৪: 'Untitled' অ্যাটাক (রিনেম না করা ২টি বা তার বেশি স্ক্রিনশট)
    untitled_images = sum(1 for a in message.attachments if a.filename and "untitled" in a.filename.lower())
    if untitled_images >= 2:
        return True

    # 🔴 রুল ৫: হ্যাকারের ইমেজ ব্লাস্ট (৩টি বা তার বেশি স্ক্যাম ছবি ও র‍্যান্ডম টেক্সট)
    if len(message.attachments) >= 3:
        words = content_lower.split()
        if len(words) == 1 and bool(GIBBERISH_RE.match(words[0])):
            vowels = sum(1 for char in words[0] if char in 'aeiou')
            if vowels == 0 or (len(words[0]) / (vowels + 1) > 4.0):
                return True
        if len(words) == 0:
            return True

    # 🔴 রুল ৬: ক্রিপ্টো কি-ওয়ার্ড + লিংক
    has_link = bool(LINK_RE.search(content_lower)) or bool(MARKDOWN_LINK_RE.search(content_lower))
    for word in SCAM_KEYWORDS:
        if re.search(r'\b' + re.escape(word) + r'\b', content_lower):
            return True
        for embed in message.embeds:
            if embed.description and re.search(r'\b' + re.escape(word) + r'\b', embed.description.lower()): 
                return True
            if embed.title and re.search(r'\b' + re.escape(word) + r'\b', embed.title.lower()): 
                return True
                
    if has_link and has_attachment:
        return True

    return False


# ── Safety Utilities ───────────────────────────────────────────────────────────
async def human_delay(min_s: float = DELETE_DELAY_MIN, max_s: float = DELETE_DELAY_MAX) -> None:
    await asyncio.sleep(random.uniform(min_s, max_s))

def jitter(base: float) -> float:
    return base * random.uniform(0.85, 1.35)

def describe(message: discord.Message) -> str:
    parts = []
    if message.content: parts.append(f'text="{message.content[:35]}"')
    if message.attachments: parts.append(f"files={[a.filename for a in message.attachments]}")
    ch = getattr(message.channel, "name", None) or f"DM/{message.channel.id}"
    return f"ch={ch} | {', '.join(parts) or '(no text)'}"


# ══════════════════════════════════════════════════════════════════════════════
# AccountSession Instance (Isolated Loops)
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class AccountStats:
    deleted:   int = 0
    failed:    int = 0
    skipped:   int = 0
    unblocked: int = 0
    reopened:  int = 0
    def summary(self) -> str:
        return f"Deleted={self.deleted} | Failed={self.failed} | Unblocked={self.unblocked} | Reopened={self.reopened}"

class AccountSession:
    def __init__(self, token: str, label: str) -> None:
        self.token  = token
        self.label  = label  
        self.stats  = AccountStats()
        self.log    = logging.getLogger(label)
        self._bot: Optional[commands.Bot] = None
        self._running_tasks: set[asyncio.Task] = set()

    def _make_bot(self) -> commands.Bot:
        instance = commands.Bot(command_prefix="\x00", self_bot=True, status=discord.Status.invisible, activity=None)
        self._register_events(instance)
        return instance

    def _register_events(self, instance: commands.Bot) -> None:
        acc = self 

        @instance.event
        async def on_ready():
            acc.log.info(f"LOCKDOWN SHIELD ACTIVE — System Secure.")
            try: await instance.change_presence(status=discord.Status.invisible, activity=None)
            except Exception: pass
            
            try:
                for rel in instance.user.relationships:
                    if rel.type in (discord.RelationshipType.blocked, discord.RelationshipType.ignored):
                        acc._dispatch_task(acc._safe_unblock(rel.user, str(rel.type)))
            except Exception: pass

        @instance.event
        async def on_message(message: discord.Message):
            if message.author.id != instance.user.id: return
            if is_scam_msg(message): 
                acc._dispatch_task(acc._safe_delete(message, "live"))

        @instance.event
        async def on_message_edit(before: discord.Message, after: discord.Message):
            if after.author.id != instance.user.id: return
            if is_scam_msg(after): 
                acc._dispatch_task(acc._safe_delete(after, "edit"))

        @instance.event
        async def on_relationship_add(relationship: discord.Relationship):
            if relationship.type not in (discord.RelationshipType.blocked, discord.RelationshipType.ignored): return
            acc._dispatch_task(acc._safe_unblock(relationship.user, str(relationship.type)))

        @instance.event
        async def on_relationship_update(before: discord.Relationship, after: discord.Relationship):
            if after.type not in (discord.RelationshipType.blocked, discord.RelationshipType.ignored): return
            acc._dispatch_task(acc._safe_unblock(after.user, str(after.type)))

        @instance.event
        async def on_private_channel_delete(channel: discord.abc.PrivateChannel):
            if not isinstance(channel, discord.DMChannel) or channel.recipient is None: return
            acc._dispatch_task(acc._safe_reopen_dm(channel.recipient))

    def _dispatch_task(self, coro) -> None:
        """মেমোরি লিক রোধ করার জন্য টাস্ক ডিসপ্যাচার"""
        task = asyncio.create_task(coro)
        self._running_tasks.add(task)
        task.add_done_callback(self._running_tasks.discard)

    # ── Safe Core Actions (Adaptive Exponential Backoff) ──────────────────────
    async def _safe_delete(self, message: discord.Message, source: str = "live") -> None:
        await human_delay(DELETE_DELAY_MIN, DELETE_DELAY_MAX)
        base_backoff = 2.0
        
        for attempt in range(1, 5):
            try:
                await message.delete()
                self.stats.deleted += 1
                self.log.info(f"[WIPED #{self.stats.deleted}] {describe(message)}")
                return
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = getattr(e, "retry_after", None) or (base_backoff ** attempt)
                    wait_time = jitter(retry_after)
                    self.log.warning(f"[RATE-LIMIT] Cooling down for {wait_time:.1f}s...")
                    await asyncio.sleep(wait_time)
                elif e.status in (403, 404):
                    self.stats.failed += 1 if e.status == 403 else 0
                    return
                else: return
            except Exception: return
        self.stats.failed += 1

    async def _safe_unblock(self, user: discord.User, reason: str = "") -> None:
        await human_delay(0.6, 1.8)
        for attempt in range(1, 4):
            try:
                await user.remove_relationship()
                self.stats.unblocked += 1
                self.log.warning(f"[AUTO-UNBLOCKED] Reversed block for {user.name}")
                return
            except discord.HTTPException as e:
                if e.status == 429: await asyncio.sleep(jitter(4.0))
                else: return
            except Exception: return

    async def _safe_reopen_dm(self, user: discord.User) -> None:
        await human_delay(0.6, 2.2)
        for attempt in range(1, 4):
            try:
                await user.create_dm()
                self.stats.reopened += 1
                self.log.warning(f"[DM REOPENED] Restored closed chat with {user.name}")
                return
            except discord.HTTPException as e:
                if e.status == 429: await asyncio.sleep(jitter(4.0))
                else: return
            except Exception: return

    async def run_forever(self) -> None:
        self.log.info(f"Thread initialized.")
        while True:
            bot = self._make_bot()
            self._bot = bot
            try:
                await bot.start(self.token)
            except discord.LoginFailure:
                self.log.critical("[FATAL] Token invalid — shutting down this thread.")
                return
            except Exception:
                await asyncio.sleep(5)
            finally:
                if not bot.is_closed(): await bot.close()
                self._bot = None
                await asyncio.sleep(5)

# ── Global Shutdown Handling ───────────────────────────────────────────────────
_sessions: list[AccountSession] = []

def handle_exit(sig, frame):
    root_log.info(f"\n[SHUTDOWN] Interrupted. Generating report...")
    for s in _sessions:
        root_log.info(f"   [{s.label}] {s.stats.summary()}")
    sys.exit(0)

signal.signal(signal.SIGINT,  handle_exit)
signal.signal(signal.SIGTERM, handle_exit)

async def main():
    global _sessions
    _sessions = [AccountSession(token=tok, label=f"ACC-{i + 1}") for i, tok in enumerate(TOKENS)]
    root_log.info(f"[LAUNCHER] Spawning {len(_sessions)} security threads.")
    await asyncio.gather(*[s.run_forever() for s in _sessions], return_exceptions=True)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
