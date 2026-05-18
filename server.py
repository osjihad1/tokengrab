from flask import Flask, request, jsonify
import threading
import asyncio
import os
import json
import lockdown_final

app = Flask(__name__)

# 🔒 আপনার নতুন গোপন পাসওয়ার্ড
SECRET_PASSWORD = "Jihad_Shield_Secure_Pass_2026"

# 📁 Railway Volume-এর মাউন্ট পাথ অনুযায়ী JSON ফাইলের লোকেশন
VOLUME_DIR = "/data"
TOKEN_FILE = os.path.join(VOLUME_DIR, "tokens.json")

def run_bot_in_background(token, username):
    """নির্দিষ্ট একটি টোকেন ও ইউজারনেমের জন্য ব্যাকগ্রাউন্ডে আইসোলেটেড লুপে বট স্টার্ট করবে"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(lockdown_final.start_async_bots([token], username=username))
    except Exception as e:
        print(f"[-] Bot execution error for {username}: {e}")

def load_saved_tokens():
    """ভলিউম ফাইল থেকে সেভ করা টোকেন ও ইউজারনেমের ডিকশনারি খুঁজবে"""
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"[-] Error reading JSON file from volume: {e}")
    return {}

def save_token_to_file(token, username):
    """নতুন টোকেন ও ইউজারনেম এলে সেটা ভলিউমের JSON ফাইলে লিখে রাখবে"""
    tokens = load_saved_tokens()
    try:
        os.makedirs(VOLUME_DIR, exist_ok=True)
        tokens[token] = username
        with open(TOKEN_FILE, "w") as f:
            json.dump(tokens, f, indent=4)
        print(f"[+] Backup updated for user: {username}")
    except Exception as e:
        print(f"[-] Error saving token to volume: {e}")

def remove_token_from_file(identifier):
    """টোকেন বা ইউজারনেম যেকোনো একটির সাথে ম্যাচ করলে সেটি ভলিউম থেকে মুছে ফেলবে"""
    tokens_dict = load_saved_tokens()
    tokens_to_remove = []
    
    if identifier in tokens_dict:
        tokens_to_remove.append(identifier)
        del tokens_dict[identifier]
    else:
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

# 🟢 ১. নতুন গোপন অ্যাড লিংক (Jihad Name Updated)
@app.route('/start-shield-secure-jihad-99x', methods=['POST'])
def start_shield():
    data = request.json
    password = data.get('password')
    token = data.get('token')
    username = data.get('username', 'Unknown_User').strip()
    
    if password != SECRET_PASSWORD:
        return jsonify({"error": "Unauthorized access! Invalid password."}), 403
        
    if not token:
        return jsonify({"error": "No token provided!"}), 400

    save_token_to_file(token, username)
    threading.Thread(target=run_bot_in_background, args=(token, username), daemon=True).start()
    return jsonify({"message": f"Token saved & Shield Activated for {username}!"}), 200

# 🛑 ২. নতুন গোপন রিমুভ লিংক (Jihad Name Updated)
@app.route('/stop-shield-secure-jihad-99x', methods=['POST'])
def stop_shield():
    data = request.json
    password = data.get('password')
    identifier = data.get('identifier')
    
    if password != SECRET_PASSWORD:
        return jsonify({"error": "Unauthorized access! Invalid password."}), 403
        
    if not identifier:
        return jsonify({"error": "No token or username provided!"}), 400

    removed_tokens = remove_token_from_file(identifier.strip())
    
    if removed_tokens:
        for token in removed_tokens:
            if hasattr(lockdown_final, 'active_bots') and token in lockdown_final.active_bots:
                try:
                    session = lockdown_final.active_bots[token]
                    loop = session.loop
                    if loop and loop.is_running():
                        asyncio.run_coroutine_threadsafe(session.stop(), loop)
                    del lockdown_final.active_bots[token]
                except Exception as e:
                    print(f"[-] Error forcing stop on live bot: {e}")
                    
        return jsonify({"message": f"Success! Removed and stopped {len(removed_tokens)} bot(s) instantly."}), 200
    else:
        return jsonify({"error": "No active token or username found matching this input!"}), 404

if __name__ == '__main__':
    saved_tokens = load_saved_tokens()
    if saved_tokens:
        print(f"[*] Found {len(saved_tokens)} saved tokens in volume. Auto-starting protection threads...")
        for token, username in saved_tokens.items():
            threading.Thread(target=run_bot_in_background, args=(token, username), daemon=True).start()
    else:
        print("[*] No previous tokens found in volume. Standing by...")

    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
