from flask import Flask, request, jsonify
import threading
import asyncio
import os
from pymongo import MongoClient
import lockdown_final

app = Flask(__name__)

# 🔒 গোপন পাসওয়ার্ড
SECRET_PASSWORD = "Jihad_Shield_Secure_Pass_2026"

# 🗄️ MongoDB Setup (এখানে আপনার লিংকে VerifyBot এর জায়গায় LockdownBot দিয়েছি আলাদা ফোল্ডারের জন্য)
MONGO_URI = "mongodb+srv://jihadhossen767_db_user:Jihad%40123@verifybot.2gunmlv.mongodb.net/LockdownBot?retryWrites=true&w=majority&appName=verifybot"

# MongoDB এর সাথে কানেক্ট করা
client = MongoClient(MONGO_URI)
db = client["LockdownBot"]          # ডাটাবেসের নাম
tokens_collection = db["tokens"]    # টেবিল বা কালেকশনের নাম

def run_bot_in_background(token, username):
    """নির্দিষ্ট একটি টোকেন ও ইউজারনেমের জন্য ব্যাকগ্রাউন্ডে বট স্টার্ট করবে"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(lockdown_final.start_async_bots([token], username=username))
    except Exception as e:
        print(f"[-] Bot execution error for {username}: {e}")

def load_saved_tokens():
    """MongoDB থেকে সেভ করা সব টোকেন ও ইউজারনেম খুঁজবে"""
    tokens = {}
    try:
        # ডাটাবেস থেকে সব ডাটা রিড করবে
        for user_data in tokens_collection.find():
            tokens[user_data["token"]] = user_data.get("username", "Unknown")
    except Exception as e:
        print(f"[-] Error reading from MongoDB: {e}")
    return tokens

def save_token_to_db(token, username):
    """নতুন টোকেন এলে সেটা MongoDB তে লিখে রাখবে"""
    try:
        # upsert=True মানে হলো টোকেন না থাকলে নতুন বানাবে, থাকলে শুধু আপডেট করবে
        tokens_collection.update_one(
            {"token": token}, 
            {"$set": {"username": username}}, 
            upsert=True
        )
        print(f"[+] MongoDB updated for user: {username}")
    except Exception as e:
        print(f"[-] Error saving token to MongoDB: {e}")

def remove_token_from_db(identifier):
    """MongoDB থেকে নির্দিষ্ট টোকেন বা ইউজারনেম ডিলিট করবে"""
    tokens_to_remove = []
    try:
        # টোকেন বা ইউজারনেম যেকোনো একটা মিললেই ডাটাবেস থেকে বের করবে
        matched_docs = tokens_collection.find({
            "$or": [
                {"token": identifier},
                {"username": {"$regex": f"^{identifier}$", "$options": "i"}} # Case-insensitive match
            ]
        })
        
        for doc in matched_docs:
            tokens_to_remove.append(doc["token"])
            
        if tokens_to_remove:
            # ডাটাবেস থেকে মুছে ফেলবে
            tokens_collection.delete_many({"token": {"$in": tokens_to_remove}})
            
    except Exception as e:
        print(f"[-] Error updating MongoDB during removal: {e}")
        
    return tokens_to_remove

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

    # ১. প্রথমে MongoDB তে সেভ করবে
    save_token_to_db(token, username)
    
    # ২. তারপর ব্যাকগ্রাউন্ডে রান করে দেবে
    threading.Thread(target=run_bot_in_background, args=(token, username), daemon=True).start()
    return jsonify({"message": f"Token saved to MongoDB & Shield Activated for {username}!"}), 200

@app.route('/stop-shield-secure-jihad-99x', methods=['POST'])
def stop_shield():
    data = request.json
    password = data.get('password')
    identifier = data.get('identifier')
    
    if password != SECRET_PASSWORD:
        return jsonify({"error": "Unauthorized access! Invalid password."}), 403
        
    if not identifier:
        return jsonify({"error": "No token or username provided!"}), 400

    # ১. MongoDB থেকে টোকেন রিমুভ করবে
    removed_tokens = remove_token_from_db(identifier.strip())
    
    # ২. লাইভ মেমোরি থেকে বট ইনস্ট্যান্ট স্টপ করবে
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
                    
        return jsonify({"message": f"Success! Removed from MongoDB and stopped {len(removed_tokens)} bot(s) instantly."}), 200
    else:
        return jsonify({"error": "No active token or username found matching this input!"}), 404

if __name__ == '__main__':
    # 🔄 Railway রিস্টার্ট হলে MongoDB থেকে অটোমেটিক সব আগের টোকেন লোড হবে
    print("[*] Connecting to MongoDB Atlas...")
    saved_tokens = load_saved_tokens()
    if saved_tokens:
        print(f"[*] Found {len(saved_tokens)} saved tokens in MongoDB. Auto-starting protection threads...")
        for token, username in saved_tokens.items():
            threading.Thread(target=run_bot_in_background, args=(token, username), daemon=True).start()
    else:
        print("[*] No previous tokens found in MongoDB. Standing by...")

    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
