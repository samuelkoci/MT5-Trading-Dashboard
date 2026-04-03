import MetaTrader5 as mt5
from pymongo import MongoClient
import certifi
import time

# --- 1. Setup Connection ---
# Replace with your actual URI string (make sure Avioni12 is in there)
MONGO_URI = "mongodb+srv://smlkoci_db_user:Avioni12@cluster0.wvogs9k.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client['TradingSaaS']
collection = db['UserStates']

print("🚀 Multi-User MT5 Engine Started...")
print("Scanning MongoDB for active accounts...")

while True:
    try:
        # 2. Get all users who have registered an MT5 account in the web app
        users = list(collection.find({"mt5_login": {"$exists": True}}))
        
        if not users:
            print("⏳ No accounts found in database. Waiting...")
        
        for user in users:
            user_id = user.get('user_id')
            print(f"🔄 Processing Account: {user_id}")
            
            # 3. Initialize MT5
            # We must initialize/shutdown for each user to switch servers/accounts cleanly
            if not mt5.initialize():
                print(f"❌ MT5 Init Failed for {user_id}")
                continue
                
            # 4. Attempt Dynamic Login
            login_id = int(user['mt5_login'])
            password = user['mt5_pass']
            server = user['mt5_server']
            
            authorized = mt5.login(
                login=login_id,
                password=password,
                server=server
            )
            
            if authorized:
                # 5. Fetch Account Metrics
                acc_info = mt5.account_info()
                
                # Fetch available symbols (limited to top 100 to save bandwidth)
                all_symbols = mt5.symbols_get()
                symbol_list = [s.name for s in all_symbols[:100]] if all_symbols else []
                
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
                        "connection_status": "ONLINE"
                    }}
                )
                print(f"✅ Successfully Synced: {user_id} (${acc_info.equity})")
            else:
                error_code = mt5.last_error()
                print(f"❌ Login Failed for {user_id} on {server}. Error: {error_code}")
                collection.update_one(
                    {"user_id": user_id},
                    {"$set": {"connection_status": "AUTH_FAILED"}}
                )
                
            # 7. Close session for this user before the next loop
            mt5.shutdown()
            
    except Exception as e:
        print(f"⚠️ Critical Loop Error: {e}")
        
    # Wait 30 seconds before checking all accounts again
    print("💤 Cycle complete. Sleeping for 30s...")
    time.sleep(30)