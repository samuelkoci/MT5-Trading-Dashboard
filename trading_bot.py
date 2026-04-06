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

MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"

print("🚀 MT5 Engine Started (Strategy Enabled)...")

while True:
    try:
        users = list(collection.find({"mt5_login": {"$exists": True}}))
        
        if not users:
            print("⏳ No accounts found. Waiting...")

        if not mt5.initialize(path=MT5_PATH, timeout=5000):
            print(f"❌ MT5 Global Init Failed: {mt5.last_error()}")
            time.sleep(10)
            continue

        for user in users:
            user_id = user.get('user_id')
            server = user.get('mt5_server')
            active_symbols = user.get('active_symbols', []) # Loaded from Dashboard
            risk_percent = user.get('risk_value', 1.0)      # Loaded from Dashboard
            
            print(f"🔄 Processing: {user_id} | Server: {server}")

            # --- SYNC ACKNOWLEDGMENT ---
            if user.get("request_sync") == True:
                print(f"📡 SYNC ACKNOWLEDGED for {user_id}")
                collection.update_one({"user_id": user_id}, {"$set": {"request_sync": False}})
            
            try:
                encrypted_pw = user['mt5_pass']
                decrypted_pw = cipher_suite.decrypt(encrypted_pw.encode()).decode()
                login_id = int(user['mt5_login'])
                
                # --- SMART LOGIN ---
                current_account = mt5.account_info()
                if current_account is not None and current_account.login == login_id:
                    authorized = True
                else:
                    authorized = mt5.login(login=login_id, password=decrypted_pw, server=server)
                    time.sleep(2) 

            except Exception as e:
                print(f"🔐 Security Error for {user_id}: {e}")
                authorized = False
            
            # --- TRADING & DATA SYNC ---
            if authorized:
                acc_info = mt5.account_info()
                
                # --- [START] TRADING STRATEGY SECTION ---
                for symbol in active_symbols:
                    # 1. Check if we already have a position open for this symbol
                    positions = mt5.positions_get(symbol=symbol)
                    
                    if len(positions) == 0: # Only trade if no position is open
                        print(f"🔍 Analyzing {symbol}...")
                        
                        # 2. Get Price Data (Fetch last 100 candles)
                        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 100)
                        if rates is None: continue
                        
                        # Placeholder: Simple "Last close > Previous close" logic
                        # REPLACE THIS WITH YOUR REAL ALGO
                        last_close = rates[-1]['close']
                        prev_close = rates[-2]['close']
                        
                        if last_close > prev_close: # TRIGGER CONDITION
                            print(f"📈 Signal Detected for {symbol}! Sending Order...")
                            
                            # 3. Calculate Lot Size (Basic example: 0.01 lot)
                            lot = 0.01 
                            price = mt5.symbol_info_tick(symbol).ask
                            
                            request = {
                                "action": mt5.TRADE_ACTION_DEAL,
                                "symbol": symbol,
                                "volume": lot,
                                "type": mt5.ORDER_TYPE_BUY,
                                "price": price,
                                "magic": 123456,
                                "comment": "Bot Trade",
                                "type_time": mt5.ORDER_TIME_GTC,
                                "type_filling": mt5.ORDER_FILLING_IOC,
                            }
                            
                            result = mt5.order_send(request)
                            if result.retcode != mt5.TRADE_RETCODE_DONE:
                                print(f"❌ Trade Failed: {result.comment}")
                            else:
                                print(f"✅ Trade Opened successfully on {symbol}")

                # --- [END] TRADING STRATEGY SECTION ---

                # Update DB with current account state
                if acc_info:
                    collection.update_one(
                        {"user_id": user_id},
                        {"$set": {
                            "balance": acc_info.balance,
                            "equity": acc_info.equity,
                            "profit": acc_info.profit,
                            "connection_status": "ONLINE"
                        }}
                    )

        mt5.shutdown()
            
    except Exception as e:
        print(f"⚠️ Critical Error: {e}")
        mt5.shutdown()
        
    print("💤 Scan complete. Waiting 30s...")
    time.sleep(30)