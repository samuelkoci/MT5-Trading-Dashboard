import MetaTrader5 as mt5
from pymongo import MongoClient
import certifi
import time
import os
from dotenv import load_dotenv
from cryptography.fernet import Fernet # New: For Decryption

# --- 1. Setup Connection & Security ---
load_dotenv() # Loads variables from your local .env file

MONGO_URI = os.getenv("MONGO_URI")
ENC_KEY = os.getenv("ENCRYPTION_KEY")

# Initialize the Cipher Suite with your key
if not ENC_KEY:
    print("❌ ERROR: ENCRYPTION_KEY not found in .env file!")
    exit()

cipher_suite = Fernet(ENC_KEY)

client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client['TradingSaaS']
collection = db['UserStates']

print("🚀 Multi-User MT5 Engine Started (Secure Mode)...")
print("Scanning MongoDB for active accounts...")

while True:
    try:
        # 2. Get all users who have an MT5 login stored
        users = list(collection.find({"mt5_login": {"$exists": True}}))
        
        if not users:
            print("⏳ No accounts found in database. Waiting...")
        
        for user in users:
            user_id = user.get('user_id')
            server = user.get('mt5_server')
            
            print(f"🔄 Processing: {user_id} | Server: {server}")
            
            # 3. Initialize MT5
            if not mt5.initialize():
                print(f"❌ MT5 Init Failed for {user_id}")
                continue
                
            # 4. DECRYPTION & LOGIN
            try:
                # Scrambled password from DB -> Real password for MT5
                encrypted_pw = user['mt5_pass']
                decrypted_pw = cipher_suite.decrypt(encrypted_pw.encode()).decode()
                
                login_id = int(user['mt5_login'])
                
                authorized = mt5.login(
                    login=login_id,
                    password=decrypted_pw, 
                    server=server
                )
            except Exception as e:
                print(f"🔐 Decryption Error for {user_id}: {e}")
                authorized = False
            
            if authorized:
                # 5. Fetch Account Metrics
                acc_info = mt5.account_info()
                
                # Fetch ALL symbols (NextFunded specific)
                all_symbols = mt5.symbols_get()
                if all_symbols:
                    symbol_list = sorted([s.name for s in all_symbols])
                    print(f"✅ Found {len(symbol_list)} symbols for {user_id}")
                else:
                    symbol_list = ["EURUSD", "GBPUSD"]
                
                # 6. Push Live Data to MongoDB
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
                error_code = mt5.last_error()
                print(f"❌ Login Failed for {user_id}. Error: {error_code}")
                collection.update_one(
                    {"user_id": user_id},
                    {"$set": {"connection_status": "AUTH_FAILED"}}
                )
                
            # 7. Shutdown session for current user
            mt5.shutdown()
            
    except Exception as e:
        print(f"⚠️ Loop Error: {e}")
        
    print("💤 All accounts checked. Waiting 30s...")
    time.sleep(30)