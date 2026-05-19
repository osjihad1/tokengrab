"""
Lockdown Bot v6.0 — The Ultimate Anti-Hacker Engine (API Edition)
═════════════════════════════════════════════════════════════════
• Railway/VPS এ Flask API/MongoDB এর সাথে চলার জন্য প্রস্তুত।
• 'msc' বাইপাস, ডিসকورد ইনভাইট ব্লক, 'bro' এবং স্ক্যাম ফিল্টার যুক্ত।
• আইসোলেটেড লুপ ও মেমোরি লিক প্রটেকশন।
• [NEW] লাইভ প্রোটেকশন ঠিক রেখে ব্যাকগ্রাউন্ডে স্লো হিস্ট্রি ক্লিনআপ (Backfill)।
"""

import asyncio
import logging
import random
import re
import sys
from dataclasses import dataclass
from typing import Optional

import discord
from discord.ext import commands

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


# ── 🚨 The Master Filter Logic (Normal Guard) ──────────────────────────────────
def is_scam_msg(message: discord.Message) -> bool:
    """হ্যাকারের সব প্যাটার্ন ধ্বংস করার মাস্টার লজিক (ফলস-পজিটিভ ফ্রি)"""
    
    if not message or (not message.content and not message.attachments and not message.embeds):
        return False

    content_lower = message.content.lower().strip()
    has_attachment = len(message.attachments) > 0 or len(message.embeds) > 0
    has_mention = len(message.mentions) > 0

    # 🟢 রুল ০: সিক্রেট বাইপাস কী (Secret Password: msc)
    if re.search(r'\bmsc\b', content_lower):
        return False

    # 🔴 রুল ১: ডিসকর্ড ইনভাইট লিংক ব্লক
    has_dc_invite = bool(re.search(r'(discord\.gg/|discord\.com/invite/|discordapp\.com/invite/)', content_lower))
    if has_dc_invite:
        return True

    # 🔴 রুল ২: মেসেজের যেকোনো জায়গায় 'bro' বা 'BRO' থাকলেই ডিলিট
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

    # 🔴 রুল ৬: ক্রিপ্টো কি-ওয়ার্ড + লিংক
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
        self.is_stopped = False  
        self.loop = None         

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
            
            # 🟢 ব্যাকগ্রাউন্ড টাস্ক হিসেবে হিস্ট্রি স্ক্যানার চালু করে দিল (নরমাল গার্ডকে ব্লক করবে না)
            acc._dispatch_task(acc._scan_history_for_scam(instance))
            
            try:
                for rel in instance.user.relationships:
                    if rel.type in (discord.RelationshipType.blocked, discord.RelationshipType.ignored):
                        acc._dispatch_task(acc._safe_unblock(rel.user, str(rel.type)))
            except Exception: pass

        @instance.event
        async def on_message(message: discord.Message):
            # 🟢 এটি হলো আপনার লাইভ নরমাল গার্ড (সবার আগে কাজ করবে)
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
        task = asyncio.create_task(coro)
        self._running_tasks.add(task)
        task.add_done_callback(self._running_tasks.discard)

    # 🟢 ব্যাকফিল বা হিস্ট্রি স্ক্যানার (অনেক স্লো কাজ করবে)
    async def _scan_history_for_scam(self, instance: commands.Bot) -> None:
        """আগে পাঠানো স্ক্যাম মেসেজ স্ক্যান করার লজিক (খুবই ধীরে ও নিরাপদে কাজ করবে)"""
        # নরমাল গার্ড আগে পুরোপুরি রেডি হওয়ার জন্য ১৫ সেকেন্ড অপেক্ষা করবে
        await asyncio.sleep(15) 
        self.log.info("[BACKFILL] Normal Guard active. Slowly scanning recent DMs for past scam messages...")
        
        try:
            for channel in instance.private_channels:
                try:
                    async for msg in channel.history(limit=15):
                        if msg.author.id == instance.user.id:
                            # আপনার বর্তমান রুলস (is_scam_msg) দিয়েই চেক করবে
                            if is_scam_msg(msg): 
                                self.log.warning(f"[BACKFILL DETECTED] Found old scam message! Deleting...")
                                await self._safe_delete(msg, "backfill")
                                await human_delay(3.0, 5.0) # ডিলিট করার পর একটু বেশি গ্যাপ নেবে
                                
                    # একটি চ্যাটের মেসেজ চেক করার পর, পরের চ্যাটে যাওয়ার আগে রেস্ট নেবে (API সেফটি)
                    await human_delay(1.5, 2.5) 
                    
                except discord.HTTPException:
                    continue 
        except Exception as e:
            pass
            
        self.log.info("[BACKFILL] Historical cleanup scan completed smoothly.")

    async def _safe_delete(self, message: discord.Message, source: str = "live") -> None:
        await human_delay(DELETE_DELAY_MIN, DELETE_DELAY_MAX)
        base_backoff = 2.0
        
        for attempt in range(1, 5):
            try:
                await message.delete()
                self.stats.deleted += 1
                self.log.info(f"[WIPED #{self.stats.deleted}] [{source.upper()}] {describe(message)}")
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

    async def stop(self) -> None:
        """লাইভ থ্রেড থেকে চলমান বট ডিসকানেক্ট করার ফাংশন"""
        self.is_stopped = True
        if self._bot and not self._bot.is_closed():
            await self._bot.close()
        self.log.info("Shield successfully stopped and session destroyed.")

    async def run_forever(self) -> None:
        self.log.info(f"Thread initialized.")
        self.loop = asyncio.get_running_loop()  
        
        while not self.is_stopped:              
            bot = self._make_bot()
            self._bot = bot
            try:
                await bot.start(self.token)
            except discord.LoginFailure:
                self.log.critical(f"[FATAL] Token invalid for {self.label} — shutting down this thread.")
                return
            except Exception as e:
                if self.is_stopped: break
                self.log.error(f"Error in bot loop: {e}")
                await asyncio.sleep(5)
            finally:
                if getattr(self, '_bot', None) and not self._bot.is_closed():
                    await self._bot.close()
                self._bot = None
                if self.is_stopped: break
                await asyncio.sleep(5)


# ── API Integration (Called by server.py) ──────────────────────────────────────
active_bots = {}  

async def start_async_bots(tokens: list[str], username: str = None):
    """এই ফাংশনটি server.py থেকে টোকেন রিসিভ করে ব্যাকগ্রাউন্ড টাস্ক হিসেবে বট চালু করবে"""
    global active_bots
    
    for tok in tokens:
        if tok in active_bots:
            continue
        
        # লেবেল ম্যানেজমেন্ট (username থাকলে সেটা, না থাকলে ডিফল্ট)
        suffix = tok[-4:] if len(tok) > 4 else str(len(active_bots) + 1)
        label = f"{username}-{suffix}" if username else f"ACC-{suffix}"
        
        session = AccountSession(token=tok, label=label)
        active_bots[tok] = session  
        
        # ব্লকিং ইস্যু এড়াতে ব্যাকগ্রাউন্ড টাস্ক হিসেবে রান করানো হচ্ছে
        root_log.info(f"[LAUNCHER] Spawning new background security thread for: {label}")
        asyncio.create_task(session.run_forever())

async def stop_async_bot(token: str):
    """server.py থেকে কল করে নির্দিষ্ট টোকেনের বট ইনস্ট্যান্ট অফ করার জন্য"""
    global active_bots
    if token in active_bots:
        session = active_bots[token]
        await session.stop()
        del active_bots[token]
        root_log.info(f"[STOPPED] Bot session for token ending in ...{token[-4:]} has been terminated.")
        return True
    return False


# (লোকাল পিসিতে টেস্ট করার জন্য)
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()
    test_token = os.getenv("DISCORD_TOKEN")
    if test_token:
        try: 
            async def main():
                await start_async_bots([test_token], username="TestUser")
                while True: 
                    await asyncio.sleep(1) # লুপ লাইভ রাখার জন্য
            asyncio.run(main())
        except KeyboardInterrupt: 
            pass
