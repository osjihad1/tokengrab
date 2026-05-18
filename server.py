from flask import Flask, request, jsonify
import threading
import asyncio
import os
import json
import lockdown_final

app = Flask(__name__)

# 📁 Railway Volume-এর মাউন্ট পাথ অনুযায়ী JSON ফাইলের লোকেশন
VOLUME_DIR = "/data"
TOKEN_FILE = os.path.join(VOLUME_DIR, "tokens.json")

def run_bot_in_background(token, username):
    """নির্দিষ্ট একটি টোকেন ও ইউজারনেমের জন্য ব্যাকগ্রাউন্ডে আইসোলেটেড লুপে বট স্টার্ট করবে"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        # lockdown_final মডিউলে টোকেন ও লেবেল হিসেবে ইউজারনেম পাঠানো হচ্ছে
        loop.run_until_complete(lockdown_final.start_async_bots([token], username=username))
    except Exception as e:
        print(f"[-] Bot execution error for {username}: {e}")

def load_saved_tokens():
    """ভলিউম ফাইল থেকে সেভ করা টোকেন ও ইউজারনেমের ডিকশনারি খুঁজবে"""
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r") as f:
                return json.load(f) # {"token": "username"} ফরম্যাটে ডাটা লোড করবে
        except Exception as e:
            print(f"[-] Error reading JSON file from volume: {e}")
    return {}

def save_token_to_file(token, username):
    """নতুন টোকেন ও ইউজারনেম এলে সেটা ভলিউমের JSON ফাইলে লিখে রাখবে"""
    tokens = load_saved_tokens()
    try:
        os.makedirs(VOLUME_DIR, exist_ok=True)
        tokens[token] = username # টোকেনকে Key এবং ইউজারনেমকে Value হিসেবে সেভ রাখা হচ্ছে
        with open(TOKEN_FILE, "w") as f:
            json.dump(tokens, f, indent=4)
        print(f"[+] Backup updated for user: {username}")
    except Exception as e:
        print(f"[-] Error saving token to volume: {e}")

def remove_token_from_file(identifier):
    """টোকেন বা ইউজারনেম যেকোনো একটির সাথে ম্যাচ করলে সেটি ভলিউম থেকে মুছে ফেলবে এবং ডিলিট হওয়া টোকেনের লিস্ট দেবে"""
    tokens_dict = load_saved_tokens()
    tokens_to_remove = []
    
    # ১. চেক করা হচ্ছে ইনপুটটি সরাসরি কোনো টোকেন (Key) কি না
    if identifier in tokens_dict:
        tokens_to_remove.append(identifier)
        del tokens_dict[identifier]
    else:
        # ২. চেক করা হচ্ছে ইনপুটটি কোনো ইউজারনেম (Value) কি না (কেস-ইনসেনসিটিভ)
        matched_tokens = [tok for tok, user in tokens_dict.items() if user.lower() == identifier.lower()]
        for tok in matched_tokens:
            tokens_to_remove.append(tok)
            del tokens_dict[tok]
            
    if tokens_to_remove:
        try:
            os.makedirs(VOLUME_DIR, exist_ok=True)
            with open(TOKEN_FILE, "w") as f:
                json.dump(tokens_dict, f, indent=4)
            return tokens_to_remove
        except Exception as e:
            print(f"[-] Error updating volume file during removal: {e}")
            
    return []

@app.route('/start-shield', methods=['POST'])
def start_shield():
    data = request.json
    token = data.get('token')
    username = data.get('username', 'Unknown_User').strip()
    
    if not token:
        return jsonify({"error": "No token provided!"}), 400

    # টোকেন ও ইউজারনেম ভলিউমে স্থায়ীভাবে সেভ করা হচ্ছে
    save_token_to_file(token, username)
    
    # ব্যাকগ্রাউন্ড থ্রেডে বট রান করানো হচ্ছে
    threading.Thread(target=run_bot_in_background, args=(token, username), daemon=True).start()
    return jsonify({"message": f"Token saved & Shield Activated for {username}!"}), 200

@app.route('/stop-shield', methods=['POST'])
def stop_shield():
    data = request.json
    identifier = data.get('identifier') # এখানে ম্যানেজার থেকে টোকেন অথবা ইউজারনেম যেকোনো একটি আসবে
    
    if not identifier:
        return jsonify({"error": "No token or username provided!"}), 400

    # ফাইল থেকে টোকেনটি খুঁজে রিমুভ করা হচ্ছে
    removed_tokens = remove_token_from_file(identifier.strip())
    
    if removed_tokens:
        # ডিলিট হওয়া টোকেনগুলোর লাইভ রানিং বট মেমরি থেকে বন্ধ করা হচ্ছে (রিস্টার্ট ছাড়া)
        for token in removed_tokens:
            if hasattr(lockdown_final, 'active_bots') and token in lockdown_final.active_bots:
                try:
                    session = lockdown_final.active_bots[token]
                    loop = session.loop
                    
                    # লাইভ অ্যাসিনক্রোনাস লুপে স্টপ কমান্ড পাঠানো হচ্ছে
                    if loop and loop.is_running():
                        asyncio.run_coroutine_threadsafe(session.stop(), loop)
                    
                    # মেমরি ট্র্যাক থেকে মুছে ফেলা হচ্ছে
                    del lockdown_final.active_bots[token]
                except Exception as e:
                    print(f"[-] Error forcing stop on live bot: {e}")
                    
        return jsonify({"message": f"Success! Removed and stopped {len(removed_tokens)} bot(s) instantly."}), 200
    else:
        return jsonify({"error": "No active token or username found matching this input!"}), 404

if __name__ == '__main__':
    # 🟢 সার্ভার বুট/রিস্টার্ট হওয়ার সাথে সাথে ভলিউম চেক করে আগের সব বট অটো-স্টার্ট করবে
    saved_tokens = load_saved_tokens()
    if saved_tokens:
        print(f"[*] Found {len(saved_tokens)} saved tokens in volume. Auto-starting protection threads...")
        for token, username in saved_tokens.items():
            threading.Thread(target=run_bot_in_background, args=(token, username), daemon=True).start()
    else:
        print("[*] No previous tokens found in volume. Standing by...")

    # Railway-এর ডায়নামিক পোর্ট সেটআপ
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
