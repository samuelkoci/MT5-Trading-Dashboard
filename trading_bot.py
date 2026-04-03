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
MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"

print("🚀 MT5 Engine Started (Context-Aware Mode)...")

while True:
    try:
        users = list(collection.find({"mt5_login": {"$exists": True}}))
        
        if not users:
            print("⏳ No accounts found in database. Waiting...")

        # --- 2. PERSISTENT INITIALIZATION ---
        # We initialize ONCE per scan loop to check all users
        if not mt5.initialize(path=MT5_PATH, timeout=5000):
            print(f"❌ MT5 Global Init Failed: {mt5.last_error()}")
            time.sleep(10)
            continue

        for user in users:
            user_id = user.get('user_id')
            server = user.get('mt5_server')
            
            print(f"🔄 Processing: {user_id} | Server: {server}")
            
            try:
                # --- 3. DECRYPTION ---
                encrypted_pw = user['mt5_pass']
                decrypted_pw = cipher_suite.decrypt(encrypted_pw.encode()).decode()
                login_id = int(user['mt5_login'])
                
                # --- 4. SMART LOGIN (The "No-Boing" Logic) ---
                current_account = mt5.account_info()
                
                # Check if terminal is already logged into this specific user
                if current_account is not None and current_account.login == login_id:
                    print(f"🔗 Already attached to {login_id}. Skipping redundant login.")
                    authorized = True
                else:
                    # Switch account only if necessary
                    print(f"🔑 Switching terminal to Account: {login_id}...")
                    authorized = mt5.login(login=login_id, password=decrypted_pw, server=server)
                    # Give the "Bus" time to settle after a switch
                    time.sleep(3) 

            except Exception as e:
                print(f"🔐 Security Error for {user_id}: {e}")
                authorized = False
            
            # --- 5. DATA SYNC ---
            if authorized:
                acc_info = mt5.account_info()
                if acc_info:
                    # Optimized symbol fetch to keep IPC pipe clean
                    symbols = mt5.symbols_get(group="*,!*") 
                    if not symbols or len(symbols) < 5:
                        symbols = mt5.symbols_get(group="EUR*,USD*,GBP*,XAU*")
                    
                    symbol_list = sorted([s.name for s in symbols]) if symbols else ["EURUSD"]

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
                
        # --- 6. SHUTDOWN AFTER ALL USERS PROCESSED ---
        # We release the terminal once the full scan is done
        mt5.shutdown()
            
    except Exception as e:
        print(f"⚠️ Critical Loop Error: {e}")
        mt5.shutdown()
        
    print("💤 Scan complete. Waiting 30s...")
    time.sleep(30)