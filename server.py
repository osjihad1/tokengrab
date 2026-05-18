from flask import Flask, request, jsonify
import threading
import asyncio
import os
import time
import lockdown_final

app = Flask(__name__)

# 📁 Railway Volume-এর মাউন্ট পাথ অনুযায়ী ফাইলের লোকেশন
VOLUME_DIR = "/data"
TOKEN_FILE = os.path.join(VOLUME_DIR, "tokens.txt")

def run_bot_in_background(tokens):
    """ব্যাকগ্রাউন্ডে বট স্টার্ট করবে"""
    asyncio.run(lockdown_final.start_async_bots(tokens))

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
            # 'w' মোড দিয়ে ফাইলটি নতুন করে ওভাররাইট করা হচ্ছে (রিমুভ করা টোকেনটি বাদ দিয়ে)
            with open(TOKEN_FILE, "w") as f:
                for t in tokens:
                    f.write(t + "\n")
            print(f"[-] Token removed from volume backup: {token[:15]}...")
            return True
        except Exception as e:
            print(f"[-] Error updating volume file during removal: {e}")
    return False

def auto_restart_vps():
    """ক্লায়েন্টকে রেসপন্স পাঠানোর জন্য ২ সেকেন্ড ওয়েট করে সার্ভার কিল করবে, যা Railway অটো-রিস্টার্ট করে নেবে"""
    time.sleep(2)
    print("[*] Killing process for Railway Auto-Restart...")
    os._exit(0) # এটি পুরো পাইথন প্রসেস ইনস্ট্যান্ট বন্ধ করে দেবে

@app.route('/start-shield', methods=['POST'])
def start_shield():
    data = request.json
    token = data.get('token')
    
    if not token:
        return jsonify({"error": "No token provided!"}), 400

    save_token_to_file(token)
    threading.Thread(target=run_bot_in_background, args=([token],), daemon=True).start()
    
    return jsonify({"message": "Token saved & Active in Railway VPS!"}), 200

@app.route('/stop-shield', methods=['POST'])
def stop_shield():
    data = request.json
    token = data.get('token')
    
    if not token:
        return jsonify({"error": "No token provided!"}), 400

    # ফাইল থেকে টোকেনটি ডিলিট করা হচ্ছে
    is_removed = remove_token_from_file(token)
    
    if is_removed:
        # ⚡ ব্যাকগ্রাউন্ড থ্রেডে প্রসেস কিল করার ফাংশনটি রান করা হচ্ছে যেন বট ইনস্ট্যান্ট অফ হয়ে যায়
        threading.Thread(target=auto_restart_vps, daemon=True).start()
        return jsonify({"message": "Success! Token removed. VPS is restarting to kill the bot instantly!"}), 200
    else:
        return jsonify({"error": "Token not found in active protection list!"}), 404

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
