import MetaTrader5 as mt5
from pymongo import MongoClient
import certifi
import time
import os
from dotenv import load_dotenv
from cryptography.fernet import Fernet

# --- 1. Setup Connection & Security ---
load_dotenv() 

MONGO_URI = os.getenv("MONGO_URI")
ENC_KEY = os.getenv("ENCRYPTION_KEY")

if not ENC_KEY:
    print("❌ ERROR: ENCRYPTION_KEY not found in .env file!")
    exit()

cipher_suite = Fernet(ENC_KEY)
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client['TradingSaaS']
collection = db['UserStates']

# --- PATH DEFINITION ---
# Pointing directly to your executable to stop the IPC timeout
MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"

print("🚀 MT5 Engine Started (Direct Path Mode)...")

while True:
    try:
        users = list(collection.find({"mt5_login": {"$exists": True}}))
        
        if not users:
            print("⏳ No accounts found in database. Waiting...")
        
        for user in users:
            user_id = user.get('user_id')
            server = user.get('mt5_server')
            
            print(f"🔄 Processing: {user_id} | Server: {server}")
            
            # 3. DIRECT INITIALIZE: Kill ghosts and start with explicit path
            mt5.shutdown() 
            time.sleep(1) 
            
            # This is the fix: Direct path + 5-second timeout allowance
            if not mt5.initialize(path=MT5_PATH, timeout=5000):
                print(f"❌ MT5 Init Failed for {user_id}: {mt5.last_error()}")
                # Fallback to default if path fails
                if not mt5.initialize():
                    continue
            
            # Give the "Bus" time to stabilize (Capacitor charge time analogy)
            time.sleep(3)
                
            # 4. DECRYPTION & LOGIN
            try:
                encrypted_pw = user['mt5_pass']
                decrypted_pw = cipher_suite.decrypt(encrypted_pw.encode()).decode()
                login_id = int(user['mt5_login'])
                
                authorized = False
                for attempt in range(3):
                    authorized = mt5.login(login=login_id, password=decrypted_pw, server=server)
                    if authorized:
                        break
                    print(f"⚠️ Login attempt {attempt + 1} failed. Retrying...")
                    time.sleep(3)

            except Exception as e:
                print(f"🔐 Security Error for {user_id}: {e}")
                authorized = False
            
            if authorized:
                time.sleep(2) 
                acc_info = mt5.account_info()
                
                if acc_info is None:
                    print(f"⚠️ Could not fetch account info for {user_id}")
                    continue

                # --- OPTIMIZED SYMBOL FETCH ---
                # Only grab Market Watch to keep IPC traffic low
                symbols = mt5.symbols_get(group="*,!*") 
                if not symbols or len(symbols) < 5:
                    symbols = mt5.symbols_get(group="EUR*,USD*,GBP*,XAU*")
                
                symbol_list = sorted([s.name for s in symbols]) if symbols else ["EURUSD"]
                print(f"✅ Found {len(symbol_list)} symbols for {user_id}")

                # 6. Push Live Data
                collection.update_one(
                    {"user_id": user_id},
                    {"$set": {
                        "balance": acc_info.balance,
                        "equity": acc_info.equity,
                        "profit": acc_info.profit,
                        "currency": acc_info.currency,
                        "mt5_catalog": symbol_list,
                        "last_update": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "connection_status": "ONLINE",
                        "request_sync": False
                    }}
                )
                print(f"💰 Account {user_id} Synced. Balance: {acc_info.balance}")
            else:
                error = mt5.last_error()
                print(f"❌ Login Failed for {user_id}. Error: {error}")
                collection.update_one(
                    {"user_id": user_id},
                    {"$set": {"connection_status": f"OFFLINE ({error[1]})"}}
                )
                
            mt5.shutdown()
            
    except Exception as e:
        print(f"⚠️ Critical Loop Error: {e}")
        
    print("💤 Scan complete. Waiting 30s...")
    time.sleep(30)