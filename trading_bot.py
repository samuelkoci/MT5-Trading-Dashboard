import MetaTrader5 as mt5
from pymongo import MongoClient
import certifi
import time

# --- 1. Setup Connection ---
MONGO_URI = "mongodb+srv://smlkoci_db_user:Avioni12@cluster0.wvogs9k.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client['TradingSaaS']
collection = db['UserStates']

print("🚀 Multi-User MT5 Engine Started...")
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
            
            print(f"🔄 Syncing: {user_id} | Server: {server}")
            
            # 3. Initialize MT5
            if not mt5.initialize():
                print(f"❌ MT5 Init Failed for {user_id}")
                continue
                
            # 4. Attempt Dynamic Login
            login_id = int(user['mt5_login'])
            password = user['mt5_pass']
            
            authorized = mt5.login(
                login=login_id,
                password=password,
                server=server
            )
            
            if authorized:
                # 5. Fetch Account Metrics
                acc_info = mt5.account_info()
                
                # --- UPDATED SYMBOL LOGIC ---
                # Fetching ALL symbols from the server (No limit)
                # This ensures your NextFunded pairs show up in the web app
                all_symbols = mt5.symbols_get()
                
                if all_symbols:
                    # Get all names and sort them alphabetically for the web dropdown
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
                        "mt5_catalog": symbol_list, # Pushing the full list
                        "last_update": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "connection_status": "ONLINE",
                        "request_sync": False # Reset the sync flag
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
                
            # 7. Shutdown to allow the next user to log in on a different server/account
            mt5.shutdown()
            
    except Exception as e:
        print(f"⚠️ Loop Error: {e}")
        
    print("💤 All accounts checked. Waiting 30s...")
    time.sleep(30)