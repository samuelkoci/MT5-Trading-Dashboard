import MetaTrader5 as mt5
from pymongo import MongoClient
import certifi
import time
import os
from dotenv import load_dotenv
from cryptography.fernet import Fernet

# --- 1. Setup ---
load_dotenv() 
MONGO_URI = os.getenv("MONGO_URI")
ENC_KEY = os.getenv("ENCRYPTION_KEY")

if not ENC_KEY:
    print("❌ ERROR: ENCRYPTION_KEY not found!")
    exit()

cipher_suite = Fernet(ENC_KEY)
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client['TradingSaaS']
collection = db['UserStates']

# Path to your MT5 terminal
MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"

def start_mt5():
    if not mt5.initialize(path=MT5_PATH):
        print(f"❌ MT5 Init Failed: {mt5.last_error()}")
        return False
    return True

print("🚀 MT5 Engine Online - Multi-Account Mode...")

while True:
    try:
        if not start_mt5():
            time.sleep(10)
            continue

        # Get all users from DB that have MT5 credentials
        users = list(collection.find({"mt5_login": {"$exists": True}}))
        
        if not users:
            print("⏳ No accounts found in Database. Waiting...")

        for user in users:
            user_id = user.get('user_id')
            server = user.get('mt5_server')
            active_symbols = user.get('active_symbols', ["EURUSD"])
            
            # Decrypt Password
            encrypted_pw = user['mt5_pass']
            decrypted_pw = cipher_suite.decrypt(encrypted_pw.encode()).decode()
            login_id = int(user['mt5_login'])
            
            print(f"\n🔄 Switching to Account: {login_id} | Server: {server}")

            # --- SESSION HANDSHAKE ---
            # Physically log in to the account to check its specific state
            authorized = mt5.login(login=login_id, password=decrypted_pw, server=server)
            
            if authorized:
                # Critical: Give the terminal a moment to sync bits with the broker
                time.sleep(2) 
                
                acc_info = mt5.account_info()
                term_info = mt5.terminal_info()

                if acc_info is None:
                    print(f"⚠️ Could not fetch account info for {login_id}")
                    continue

                print(f"--- 🛡️ Permissions for {login_id} ---")
                print(f"Algo Trading Button: {term_info.trade_allowed}")
                print(f"Expert Permission:    {acc_info.trade_expert}")

                # Check if trading is allowed for this specific session
                if term_info.trade_allowed and acc_info.trade_expert:
                    
                    # --- TRADING LOGIC PER SYMBOL ---
                    for symbol in active_symbols:
                        mt5.symbol_select(symbol, True)
                        
                        # Check for existing positions to avoid double-trading
                        positions = mt5.positions_get(symbol=symbol)
                        
                        if positions is not None and len(positions) == 0:
                            # 15-Minute Momentum Strategy
                            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 2)
                            
                            if rates is not None and len(rates) >= 2:
                                # Logic: Current candle closed higher than previous
                                if rates[-1]['close'] > rates[-2]['close']:
                                    print(f"📈 Signal Detected for {symbol} on Account {login_id}")
                                    
                                    tick = mt5.symbol_info_tick(symbol)
                                    s_info = mt5.symbol_info(symbol)
                                    
                                    if tick and s_info:
                                        # Handle Broker-Specific Filling Modes (FOK vs IOC)
                                        f_mode = mt5.ORDER_FILLING_IOC
                                        if s_info.filling_mode & 1: f_mode = mt5.ORDER_FILLING_FOK
                                        elif s_info.filling_mode & 2: f_mode = mt5.ORDER_FILLING_IOC

                                        request = {
                                            "action": mt5.TRADE_ACTION_DEAL,
                                            "symbol": symbol,
                                            "volume": 0.01,
                                            "type": mt5.ORDER_TYPE_BUY,
                                            "price": tick.ask,
                                            "magic": 123456,
                                            "type_filling": f_mode,
                                            "type_time": mt5.ORDER_TIME_GTC,
                                        }
                                        
                                        res = mt5.order_send(request)
                                        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                                            print(f"✅ Trade Successful on {symbol}")
                                        else:
                                            err = res.comment if res else "No response"
                                            print(f"❌ Trade Failed: {err}")
                else:
                    print(f"⚠️ BLOCK: Expert bit is LOW for {login_id}. Check MT5 settings!")

                # --- SYNC DATA TO MONGODB ---
                collection.update_one(
                    {"mt5_login": str(login_id)},
                    {"$set": {
                        "balance": acc_info.balance, 
                        "equity": acc_info.equity, 
                        "connection_status": "ONLINE"
                    }}
                )
            else:
                print(f"❌ Login Failed for {login_id}: {mt5.last_error()}")
                collection.update_one(
                    {"mt5_login": str(login_id)},
                    {"$set": {"connection_status": "OFFLINE"}}
                )

    except Exception as e:
        print(f"⚠️ System Error: {e}")
    
    print("\n💤 Cycle complete. Resting 30s...")
    time.sleep(30)