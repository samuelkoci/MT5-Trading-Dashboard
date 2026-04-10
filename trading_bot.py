import MetaTrader5 as mt5
from pymongo import MongoClient
import certifi
import time
import os
from datetime import datetime
from dotenv import load_dotenv
from cryptography.fernet import Fernet

# --- 1. Setup ---
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
ENC_KEY = os.getenv("ENCRYPTION_KEY")

if not MONGO_URI:
    print("❌ ERROR: MONGO_URI not found in .env!")
    exit()

if not ENC_KEY:
    print("❌ ERROR: ENCRYPTION_KEY not found in .env!")
    exit()

cipher_suite = Fernet(ENC_KEY.encode())  # FIX: encode() ensures it's bytes-safe
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client['TradingSaaS']
collection = db['UserStates']

# FIX: Test MongoDB connection on startup so you know immediately if it's broken
try:
    client.admin.command('ping')
    print("✅ MongoDB Connected Successfully.")
except Exception as e:
    print(f"❌ MongoDB Connection Failed: {e}")
    exit()

# Path to your MT5 terminal — update this if your install path is different
MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"

current_active_user = None

def start_mt5():
    """Checks if MT5 bridge is active; if not, initializes it."""
    if mt5.terminal_info() is not None:
        return True
    print("🤖 Initializing MT5 Bridge...")
    if not mt5.initialize(path=MT5_PATH, timeout=10000):
        if not mt5.initialize():
            print(f"❌ MT5 Initialize Failed: {mt5.last_error()}")
            return False
    print("✅ MT5 Bridge Active.")
    return True

def get_filling_mode(symbol):
    """Detects the specific filling mode required by the broker."""
    s_info = mt5.symbol_info(symbol)
    if not s_info:
        return 2
    filling = s_info.filling_mode
    if filling & 1:
        return 0  # FOK
    elif filling & 2:
        return 1  # IOC
    return 2  # BOC

def process_account(user):
    """Handles login, trading logic, and telemetry for a single account."""
    global current_active_user

    login_raw = str(user.get('mt5_login', ''))
    if not login_raw:
        return

    # FIX: Guard against missing password field — don't crash the whole cycle
    if 'mt5_pass' not in user or not user['mt5_pass']:
        print(f"⚠️  [{login_raw}] No password stored yet. Skipping.")
        return

    try:
        login_id = int(login_raw)
    except ValueError:
        print(f"⚠️  Invalid login ID format: {login_raw}. Skipping.")
        return

    server = user.get('mt5_server', '')
    active_symbols = user.get('active_symbols', [])
    force_relogin = user.get('force_relogin', False)

    try:
        actual_account = mt5.account_info()
        is_already_logged_in = (
            actual_account is not None and
            actual_account.login == login_id and
            not force_relogin  # FIX: Honour the force_relogin flag
        )

        if not is_already_logged_in:
            print(f"🔄 [LOGIN] Connecting to account: {login_id} on {server}...")

            # FIX: Safely decrypt — if decryption fails, mark offline and skip
            try:
                decrypted_pw = cipher_suite.decrypt(user['mt5_pass'].encode()).decode()
            except Exception as dec_err:
                print(f"❌ [{login_id}] Decryption failed: {dec_err}. Password may be corrupt.")
                collection.update_one(
                    {"mt5_login": login_raw},
                    {"$set": {"connection_status": "OFFLINE", "last_error": "Decryption failed"}}
                )
                return

            login_success = False
            for attempt in range(3):
                if mt5.login(login=login_id, password=decrypted_pw, server=server):
                    login_success = True
                    current_active_user = login_id
                    print(f"✅ Logged in: {login_id}")
                    break
                print(f"  ⚠️  Login attempt {attempt + 1}/3 failed. Retrying in 2s...")
                time.sleep(2)

            if not login_success:
                err = mt5.last_error()
                print(f"❌ [{login_id}] Login Failed (Code {err[0]}: {err[1]})")
                collection.update_one(
                    {"mt5_login": login_raw},
                    {"$set": {
                        "connection_status": "OFFLINE",
                        "last_error": f"MT5 Error {err[0]}: {err[1]}"
                    }}
                )
                return

            # FIX: Clear force_relogin flag now that we've successfully re-authenticated
            collection.update_one(
                {"mt5_login": login_raw},
                {"$set": {"force_relogin": False}}
            )
        else:
            current_active_user = login_id

        # --- TRADING LOGIC ---
        acc_info = mt5.account_info()
        if not acc_info:
            print(f"⚠️  [{login_id}] Could not retrieve account info.")
            return

        print(f"📊 [{login_id}] Balance: ${acc_info.balance:,.2f} | Equity: ${acc_info.equity:,.2f} | Symbols: {active_symbols}")

        risk_value = float(user.get('risk_value', 1.0))
        lot_size = round(0.01 * risk_value, 2)  # FIX: Apply risk multiplier to lot size

        for symbol in active_symbols:
            try:
                if not mt5.symbol_select(symbol, True):
                    print(f"  ⚠️  [{symbol}] Symbol not available on this broker. Skipping.")
                    continue

                rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 1, 3)

                if rates is None or len(rates) < 3:
                    print(f"  ⚠️  [{symbol}] Not enough candle data. Skipping.")
                    continue

                b1, b2, b3 = rates[0], rates[1], rates[2]
                signal = None

                # 3-Bar Reversal Logic
                if (b1['close'] < b1['open']) and (b2['low'] < b1['low']) and (b3['close'] > b2['high']):
                    signal = mt5.ORDER_TYPE_BUY
                elif (b1['close'] > b1['open']) and (b2['high'] > b1['high']) and (b3['close'] < b2['low']):
                    signal = mt5.ORDER_TYPE_SELL

                if signal is not None:
                    open_positions = mt5.positions_get(symbol=symbol)
                    if open_positions is not None and len(open_positions) == 0:
                        tick = mt5.symbol_info_tick(symbol)
                        if not tick:
                            print(f"  ⚠️  [{symbol}] No tick data. Skipping trade.")
                            continue

                        price = tick.ask if signal == mt5.ORDER_TYPE_BUY else tick.bid
                        request = {
                            "action": mt5.TRADE_ACTION_DEAL,
                            "symbol": symbol,
                            "volume": lot_size,
                            "type": signal,
                            "price": price,
                            "magic": 2026,
                            "type_filling": get_filling_mode(symbol),
                            "type_time": mt5.ORDER_TIME_GTC,
                        }
                        result = mt5.order_send(request)
                        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                            direction = "BUY" if signal == mt5.ORDER_TYPE_BUY else "SELL"
                            print(f"  🔥 [{symbol}] {direction} @ {price} | Lot: {lot_size}")
                        else:
                            comment = result.comment if result else "No result returned"
                            retcode = result.retcode if result else "N/A"
                            print(f"  ❌ [{symbol}] Trade Failed | Code: {retcode} | {comment}")

            except Exception as sym_err:
                # FIX: Per-symbol error handling — one bad symbol won't skip the rest
                print(f"  ⚠️  [{symbol}] Symbol error: {sym_err}")
                continue

        # --- Telemetry Update ---
        collection.update_one(
            {"mt5_login": login_raw},
            {"$set": {
                "balance": acc_info.balance,
                "equity": acc_info.equity,
                "connection_status": "ONLINE",
                "last_sync": datetime.now(),
                "last_error": None  # FIX: Clear previous errors on success
            }}
        )

    except Exception as e:
        print(f"⚠️  Execution Error [{login_raw}]: {e}")
        collection.update_one(
            {"mt5_login": login_raw},
            {"$set": {"connection_status": "OFFLINE", "last_error": str(e)}}
        )


# --- MAIN LOOP ---
print("🚀 MT5 Cloud Engine Online — Sequential Mode")
print(f"   MT5 Path: {MT5_PATH}")
print("-" * 50)

while True:
    try:
        cycle_time = datetime.now().strftime('%H:%M:%S')
        print(f"\n--- 🛰️  CYCLE: {cycle_time} ---")

        if not start_mt5():
            print("❌ MT5 Bridge Failed. Retrying in 15s...")
            time.sleep(15)
            continue

        users = list(collection.find({"mt5_login": {"$exists": True}}))

        if users:
            print(f"👥 Processing {len(users)} account(s)...")
            for user in users:
                process_account(user)
        else:
            print("⏳ No accounts in database yet. Waiting...")

    except Exception as e:
        print(f"⚠️  Global Error: {e}")

    print(f"💤 Sleeping 30s...")
    time.sleep(30)