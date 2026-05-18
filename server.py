from flask import Flask, request, jsonify
import threading
import asyncio
import os
import lockdown_final

app = Flask(__name__)

# 📁 Railway Volume-এর মাউন্ট পাথ অনুযায়ী ফাইলের লোকেশন সেট করা হয়েছে
# আপনার Railway ভলিউমের Mount Path যদি ড্যাশবোর্ডে /data দেওয়া থাকে, তবে এটাই থাকবে।
VOLUME_DIR = "/data"
TOKEN_FILE = os.path.join(VOLUME_DIR, "tokens.txt")

def run_bot_in_background(tokens):
    """ব্যাকগ্রাউন্ডে বট স্টার্ট করবে"""
    asyncio.run(lockdown_final.start_async_bots(tokens))

def load_saved_tokens():
    """রিস্টার্টের পর ভলিউম ফাইল থেকে সেভ করা টোকেনগুলো খুঁজবে"""
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r") as f:
                # ফাঁকা স্পেস বা লাইন বাদ দিয়ে টোকেনগুলো লিস্টে নেবে
                return [line.strip() for line in f.readlines() if line.strip()]
        except Exception as e:
            print(f"[-] Error reading token file from volume: {e}")
    return []

def save_token_to_file(token):
    """নতুন টোকেন এলে সেটা ভলিউম ফাইলে লিখে রাখবে"""
    tokens = load_saved_tokens()
    if token not in tokens:
        try:
            # ভলিউম ডিরেক্টরি তৈরি না থাকলে আগে সেটি তৈরি করবে
            os.makedirs(VOLUME_DIR, exist_ok=True)
            with open(TOKEN_FILE, "a") as f:
                f.write(token + "\n")
            print(f"[+] Token successfully backed up to volume: {token[:15]}...")
        except Exception as e:
            print(f"[-] Error saving token to volume: {e}")

@app.route('/start-shield', methods=['POST'])
def start_shield():
    data = request.json
    token = data.get('token')
    
    if not token:
        return jsonify({"error": "No token provided!"}), 400

    # টোকেনটি স্থায়ীভাবে ভলিউমে সেভ করা হচ্ছে
    save_token_to_file(token)

    # নতুন টোকেনের জন্য ব্যাকগ্রাউন্ডে বট চালু করা হচ্ছে
    threading.Thread(target=run_bot_in_background, args=([token],), daemon=True).start()
    
    return jsonify({"message": "Token saved & Active in Railway VPS!"}), 200

if __name__ == '__main__':
    # 🟢 সার্ভার অন হওয়ার সাথে সাথেই ভলিউম চেক করবে আগে কোনো টোকেন সেভ করা ছিল কি না
    saved_tokens = load_saved_tokens()
    if saved_tokens:
        print(f"[*] Found {len(saved_tokens)} saved tokens in volume. Starting bots automatically...")
        threading.Thread(target=run_bot_in_background, args=(saved_tokens,), daemon=True).start()
    else:
        print("[*] No previous tokens found in volume. Standing by...")

    # Railway-এর ডায়নামিক পোর্ট সেটআপ
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
