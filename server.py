from flask import Flask, request, jsonify
import threading
import asyncio
import os
import lockdown_final

app = Flask(__name__)

# 📁 Railway Volume-এর মাউন্ট পাথ অনুযায়ী ফাইলের লোকেশন
VOLUME_DIR = "/data"
TOKEN_FILE = os.path.join(VOLUME_DIR, "tokens.txt")

def run_bot_in_background(token):
    """নির্দিষ্ট একটি টোকেনের জন্য ব্যাকগ্রাউন্ডে আইসোলেটেড লুপে বট স্টার্ট করবে"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(lockdown_final.start_async_bots([token]))
    except Exception as e:
        print(f"[-] Bot execution error for token {token[:15]}: {e}")

def load_saved_tokens():
    """ভলিউম ফাইল থেকে সেভ করা টোকেনগুলো খুঁজবে"""
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r") as f:
                return [line.strip() for line in f.readlines() if line.strip()]
        except Exception as e:
            print(f"[-] Error reading token file from volume: {e}")
    return []

def save_token_to_file(token):
    """নতুন টোকেন এলে সেটা ভলিউম ফাইলে লিখে রাখবে"""
    tokens = load_saved_tokens()
    if token not in tokens:
        try:
            os.makedirs(VOLUME_DIR, exist_ok=True)
            with open(TOKEN_FILE, "a") as f:
                f.write(token + "\n")
            print(f"[+] Token successfully backed up to volume: {token[:15]}...")
        except Exception as e:
            print(f"[-] Error saving token to volume: {e}")

def remove_token_from_file(token):
    """টোকেন রিমুভ করার সময় ভলিউম ফাইল থেকে সেটি মুছে ফেলবে"""
    tokens = load_saved_tokens()
    if token in tokens:
        tokens.remove(token)
        try:
            os.makedirs(VOLUME_DIR, exist_ok=True)
            with open(TOKEN_FILE, "w") as f:
                for t in tokens:
                    f.write(t + "\n")
            print(f"[-] Token removed from volume backup: {token[:15]}...")
            return True
        except Exception as e:
            print(f"[-] Error updating volume file during removal: {e}")
    return False

@app.route('/start-shield', methods=['POST'])
def start_shield():
    data = request.json
    token = data.get('token')
    
    if not token:
        return jsonify({"error": "No token provided!"}), 400

    save_token_to_file(token)
    
    # প্রতিটি টোকেনকে আলাদা থ্রেডে পাঠানো হচ্ছে যেন ইন্ডিপেন্ডেন্টলি স্টপ করা যায়
    threading.Thread(target=run_bot_in_background, args=(token,), daemon=True).start()
    
    return jsonify({"message": "Token saved & Bot Activated successfully!"}), 200

@app.route('/stop-shield', methods=['POST'])
def stop_shield():
    data = request.json
    token = data.get('token')
    
    if not token:
        return jsonify({"error": "No token provided!"}), 400

    # ১. ভলিউম ফাইল থেকে টোকেন ডিলিট করা হচ্ছে
    is_removed = remove_token_from_file(token)
    
    if is_removed:
        # ২. ⚡ সার্ভার রিস্টার্ট ছাড়া লাইভ বট বন্ধ করার মূল লজিক
        if hasattr(lockdown_final, 'active_bots') and token in lockdown_final.active_bots:
            try:
                session = lockdown_final.active_bots[token]
                loop = session.loop
                
                # ফ্লাস্কের থ্রেড থেকে বটের অ্যাসিনক্রোনাস লুপে স্টপ কমান্ড পুশ করা হচ্ছে
                if loop and loop.is_running():
                    asyncio.run_coroutine_threadsafe(session.stop(), loop)
                
                # মেমরি বা ট্র্যাক ডিকশনারি থেকে ক্লিনআপ করা হচ্ছে
                del lockdown_final.active_bots[token]
                
                print(f"[+] Instantly stopped live bot for token: {token[:15]}...")
                return jsonify({"message": "Success! Bot stopped and token removed instantly without restart."}), 200
            except Exception as e:
                print(f"[-] Error forcing stop on live bot: {e}")
                return jsonify({"message": "Token removed from backup, but error stopping live bot.", "error": str(e)}), 200
        else:
            return jsonify({"message": "Success! Token removed from backup (Bot was not running in memory)."}), 200
    else:
        return jsonify({"error": "Token not found in active protection list!"}), 404

if __name__ == '__main__':
    # 🟢 সার্ভার বুট হওয়ার সাথে সাথে আগের সব সেভ থাকা বট রান করবে
    saved_tokens = load_saved_tokens()
    if saved_tokens:
        print(f"[*] Found {len(saved_tokens)} saved tokens in volume. Auto-starting protection threads...")
        for token in saved_tokens:
            threading.Thread(target=run_bot_in_background, args=(token,), daemon=True).start()
    else:
        print("[*] No previous tokens found in volume. Standing by...")

    # Railway-এর ডায়নামিক পোর্ট সেটআপ
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
