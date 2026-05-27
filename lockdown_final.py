"""
Lockdown Bot v8.0 — The Ultimate Anti-Hacker Engine (API Edition)
═════════════════════════════════════════════════════════════════
• Railway/VPS/Render a Flask API/MongoDB er shathe cholar jonno prostut.
• 'msc' bypass, discord invite block, 'bro' ebong scam filter jukto.
• [NEW KILL-SWITCH] Chobi load howar agei Hacker-er text (Code + Mention) dekhe instant wipe korbe!
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


# ── 🚨 1. LIVE MASTER FILTER LOGIC (Normal Guard) ──────────────────────────────
def is_scam_msg(message: discord.Message) -> bool:
    if not message or (not message.content and not message.attachments and not message.embeds):
        return False

    content_lower = message.content.lower().strip()
    original_content = message.content.strip()
    total_pics = len(message.attachments)
    
    has_mention = len(message.mentions) > 0 or "@" in content_lower
    has_bro = bool(re.search(r'\bbro\b', content_lower))
    has_any_text = len(content_lower) > 0

    # 🟢 রুল ০: সবার আগে বাইপাস চেক (মেসেজে safe, sf বা msc থাকলে সরাসরি ইগনোর করবে)
    if content_lower == 'msc' or bool(re.search(r'\b(safe|sf)\b', content_lower)):
        return False

    # 🔴 RULE 1: User Logic - Shudhu 'bro' thaklei delete
    if has_bro:
        return True

    # 🔴 RULE 2: SUPER KILL-SWITCH (Chobi charai Hacker er text dhore felbe)
    if has_mention and has_any_text:
        words = original_content.split()
        for w in words:
            w_clean = re.sub(r'[^a-zA-Z]', '', w)
            if 6 <= len(w_clean) <= 15 and not w_clean.islower() and not w_clean.isupper():
                return True

    # 🔴 RULE 3: শুধুমাত্র 'untitled.jpg' নামের ৩টি বা তার বেশি ফাইল (অ্যাটাচমেন্ট) থাকলে ডিলিট
    if total_pics >= 3:
        untitled_count = 0
        for a in message.attachments:
            if a.filename and a.filename.lower() == "untitled.jpg":
                untitled_count += 1
        if untitled_count >= 3:
            return True

    # 🔴 RULE 4: মেসেজের টেক্সটে সরাসরি ৩টি বা তার বেশি 'untitled.jpg' লিংক থাকলে ডিলিট
    if content_lower.count("untitled.jpg") >= 3:
        return True

    # 🔴 RULE 5: Discord Media লিংক এবং 'KtbggMqI' এর মতো র‍্যান্ডম টেক্সট একসাথে থাকলে ডিলিট
    if "discordapp.net/attachments" in content_lower and has_any_text:
        words = original_content.split()
        for w in words:
            w_clean = re.sub(r'[^a-zA-Z]', '', w)
            # শব্দটিতে ছোট-বড় হাতের অক্ষর মেশানো থাকলে এবং অন্তত ৩ অক্ষরের হলেই ডিলিট করবে
            if len(w_clean) >= 3 and not w_clean.islower() and not w_clean.isupper():
                return True

    # ── 🚨 Links (Live only) Rule 🚨 ──────────────────────────────────────────
    # ডিসকর্ড ইনভাইট লিংকন ব্লক
    if bool(re.search(r'(discord\.gg/|discord\.com/invite/|discordapp\.com/invite/)', content_lower)):
        return True

    # স্ক্যাম কি-ওয়ার্ড ও অন্যান্য লিংক চেক
    has_link = bool(LINK_RE.search(content_lower)) or bool(MARKDOWN_LINK_RE.search(content_lower))
    for word in SCAM_KEYWORDS:
        if re.search(r'\b' + re.escape(word) + r'\b', content_lower):
            return True
        for embed in message.embeds:
            if embed.description and re.search(r'\b' + re.escape(word) + r'\b', embed.description.lower()): 
                return True
            if embed.title and re.search(r'\b' + re.escape(word) + r'\b', embed.title.lower()): 
                return True
                
    if has_link and total_pics >= 1:
        return True

    return False

    # ── 🚨 Links (Live only) Rule 🚨 ──────────────────────────────────────────
    # ডিসকর্ড ইনভাইট লিংকন ব্লক
    if bool(re.search(r'(discord\.gg/|discord\.com/invite/|discordapp\.com/invite/)', content_lower)):
        return True

    # স্ক্যাম কি-ওয়ার্ড ও অন্যান্য লিংক চেক
    has_link = bool(LINK_RE.search(content_lower)) or bool(MARKDOWN_LINK_RE.search(content_lower))
    for word in SCAM_KEYWORDS:
        if re.search(r'\b' + re.escape(word) + r'\b', content_lower):
            return True
        for embed in message.embeds:
            if embed.description and re.search(r'\b' + re.escape(word) + r'\b', embed.description.lower()): 
                return True
            if embed.title and re.search(r'\b' + re.escape(word) + r'\b', embed.title.lower()): 
                return True
                
    if has_link and total_pics >= 1:
        return True

    return False


# ── 🚨 2. DEDICATED BACKFILL FILTER LOGIC (History Scanner) ────────────────────
def is_backfill_scam(message: discord.Message) -> bool:
    if not message:
        return False

    content_lower = message.content.lower().strip()
    original_content = message.content.strip()
    total_pics = len(message.attachments)
    
    has_mention = len(message.mentions) > 0 or "@" in content_lower
    has_bro = bool(re.search(r'\bbro\b', content_lower))
    has_any_text = len(content_lower) > 0

    # 🟢 ব্যাকফিল বাইপাস চেক
    if content_lower == 'msc' or bool(re.search(r'\b(safe|sf)\b', content_lower)):
        return False

    if has_bro:
        return True
        # 🔴 BACKFILL MASTER RULES: লিংক এবং ফাইল দুটোর জন্যই

    # ১. মেসেজের টেক্সটে ৩ বা তার বেশিবার 'untitled.jpg' লিংক বা লেখা থাকলে সরাসরি ডিলিট
    if content_lower.count("untitled.jpg") >= 3:
        return True

    # ২. মেসেজে ডিসকর্ডের মিডিয়া লিংক এবং KtbggMqI-এর মতো র‍্যান্ডম টেক্সট একসাথে থাকলে ডিলিট
    if "discordapp.net/attachments" in content_lower or "discordapp.com/attachments" in content_lower:
        words = original_content.split()
        for w in words:
            if "http" in w: # লিংকের অংশটুকু স্কিপ করে শুধু মূল টেক্সট চেক করবে
                continue
            w_clean = re.sub(r'[^a-zA-Z]', '', w)
            if len(w_clean) >= 3 and not w_clean.islower() and not w_clean.isupper():
                return True

    # ৩. যদি লিংক না দিয়ে সরাসরি ৩টি বা তার বেশি ফাইল আপলোড করে (আপনার অ্যাড করা রুল)
    if total_pics >= 3:
        untitled_count = 0
        for a in message.attachments:
            if a.filename and a.filename.lower() == "untitled.jpg":
                untitled_count += 1
        if untitled_count >= 3:
            return True

    # 🔴 BACKFILL KILL-SWITCH: Hacker mixed case code + mention
    if has_mention and has_any_text:
        words = original_content.split()
        for w in words:
            w_clean = re.sub(r'[^a-zA-Z]', '', w)
            if 6 <= len(w_clean) <= 15 and not w_clean.islower() and not w_clean.isupper():
                return True

    if total_pics >= 1:
        has_scam_name = False
        for a in message.attachments:
            if a.filename:
                fname_lower = a.filename.lower()
                if "untitled" in fname_lower or bool(re.search(r'img[-_]?\d+', fname_lower)):
                    has_scam_name = True
                    break
        if has_scam_name and has_any_text:
            return True

        if has_any_text:
            words = original_content.split()
            for w in words:
                w_clean = re.sub(r'[^a-zA-Z]', '', w)
                if 6 <= len(w_clean) <= 15 and not w_clean.islower() and not w_clean.isupper():
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
            
            acc._dispatch_task(acc._scan_history_for_scam(instance))
            
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
        task = asyncio.create_task(coro)
        self._running_tasks.add(task)
        task.add_done_callback(self._running_tasks.discard)

    async def _scan_history_for_scam(self, instance: commands.Bot) -> None:
        await asyncio.sleep(15) 
        self.log.info("[BACKFILL] Scanner active. Checking DMs and Server channels for old image-scams...")
        
        try:
            for channel in instance.private_channels:
                try:
                    async for msg in channel.history(limit=15):
                        if msg.author.id == instance.user.id:
                            if is_backfill_scam(msg): 
                                self.log.warning(f"[BACKFILL DM] Found old image-scam! Deleting...")
                                await self._safe_delete(msg, "backfill_dm")
                                await human_delay(3.0, 5.0) 
                    await human_delay(1.5, 2.5) 
                except discord.HTTPException:
                    continue 
        except Exception:
            pass

        try:
            for guild in instance.guilds:
                for channel in guild.text_channels:
                    perms = channel.permissions_for(guild.me)
                    if perms.read_messages and perms.read_message_history:
                        try:
                            async for msg in channel.history(limit=25):
                                if msg.author.id == instance.user.id:
                                    if is_backfill_scam(msg):
                                        self.log.warning(f"[BACKFILL SERVER] Found old image-scam in {guild.name} -> #{channel.name}! Deleting...")
                                        await self._safe_delete(msg, "backfill_server")
                                        await human_delay(3.0, 5.0)
                            await human_delay(1.5, 2.5)
                        except discord.HTTPException:
                            continue
        except Exception:
            pass
            
        self.log.info("[BACKFILL] Historical cleanup scan completed smoothly for DMs and All Channels.")

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


# ── API Integration ────────────────────────────────────────────────────────────
active_bots = {}  

async def start_async_bots(tokens: list[str], username: str = None):
    global active_bots
    new_sessions = []
    
    for tok in tokens:
        if tok in active_bots:
            continue
        
        suffix = tok[-4:] if len(tok) > 4 else str(len(active_bots) + 1)
        label = f"{username}-{suffix}" if username else f"ACC-{suffix}"
        
        session = AccountSession(token=tok, label=label)
        active_bots[tok] = session  
        new_sessions.append(session)
        
    if new_sessions:
        root_log.info(f"[LAUNCHER] Spawning and holding security thread for: {username}")
        await asyncio.gather(*[s.run_forever() for s in new_sessions], return_exceptions=True)

async def stop_async_bot(token: str):
    global active_bots
    if token in active_bots:
        session = active_bots[token]
        await session.stop()
        del active_bots[token]
        root_log.info(f"[STOPPED] Bot session for token ending in ...{token[-4:]} has been terminated.")
        return True
    return False


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
                    await asyncio.sleep(1)
            asyncio.run(main())
        except KeyboardInterrupt: 
            pass
