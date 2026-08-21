import re
import rpyc
from telethon import TelegramClient, events

#Username: goldkillerhub OR goodbestsignal (myTestChannel)

# --- 1. DIRECT RPYC CONNECTION ---
print("Connecting directly to the Wine MT5 Server...")
try:
    conn = rpyc.classic.connect('127.0.0.1', 18812)
    conn.execute("import MetaTrader5 as mt5")
    mt5 = conn.modules.MetaTrader5
except Exception as e:
    print(f"Failed to connect to MT5 bridge: {e}")
    exit()

print("Connecting to MT5 Terminal...")

# --- UPDATE YOUR REAL ACCOUNT DETAILS HERE ---
real_account = 12345678              # Replace with your OLD account number
real_password = "YourExnessPassword" # Replace with your OLD account password
real_server = "Exness-MT5Trial9"     # Ensure this matches your broker server EXACTLY

# Force Python to log into the specific account
if not mt5.initialize(login=real_account, password=real_password, server=real_server):
    print(f"Failed to initialize MT5. Error: {mt5.last_error()}")
    exit()
else:
    print(f"MT5 Initialized Successfully on Account: {real_account}")

# --- 2. YOUR TELEGRAM CREDENTIALS ---
api_id = 39853867 
api_hash = '97ad6f46617781299a9e0b62db81a88c'

def parse_signal(message_text):
    signal_data = {'action': None, 'symbol': None, 'sl': None, 'tp_target_3': None, 'tp_target_runner': None}
    
    action_match = re.search(r'(BUY|SELL)', message_text, re.IGNORECASE)
    if action_match:
        signal_data['action'] = action_match.group(1).upper()
        
    symbol_match = re.search(r'(XAUUSD|GOLD)', message_text, re.IGNORECASE)
    if symbol_match:
        signal_data['symbol'] = 'XAUUSDm'
        
    sl_match = re.search(r'SL[\s:-]*([0-9.]+)', message_text, re.IGNORECASE)
    if sl_match:
        signal_data['sl'] = float(sl_match.group(1))
        
    tp_matches = re.findall(r'TP[0-9¹²³⁴⁵⁶⁷⁸⁹⁰]*[\s:-]*([0-9.]+)', message_text, re.IGNORECASE)
    if tp_matches:
        # TP3 = The 3rd TP in the Telegram message (Index 2)
        signal_data['tp_target_3'] = float(tp_matches[2]) if len(tp_matches) >= 3 else float(tp_matches[-1])
        # Runner TP = The second to last TP in the Telegram message (Index -2)
        signal_data['tp_target_runner'] = float(tp_matches[-2]) if len(tp_matches) >= 2 else float(tp_matches[-1])
            
    return signal_data

client = TelegramClient('forex_session', api_id, api_hash)
channel_username = 'goodbestsignal'

@client.on(events.NewMessage(chats=channel_username))
async def handler(event):
    raw_signal = event.message.message
    print("--------------------------------------------------")
    print(f"NEW SIGNAL RECEIVED:\n{raw_signal}")
    
    extracted_data = parse_signal(raw_signal)
    print("EXTRACTED DATA:", extracted_data)
    print("--------------------------------------------------")
    
    if all(extracted_data.values()):
        print("Ready to send to MT5!")
        
        symbol = extracted_data['symbol']
        action = extracted_data['action']
        
        # --- 3. FETCH PRICE ON THE WINDOWS SERVER ---
        fetch_code = f"""
tick = mt5.symbol_info_tick('{symbol}')
if tick:
    current_price = float(tick.ask if '{action}' == 'BUY' else tick.bid)
else:
    current_price = 0.0
"""
        conn.execute(fetch_code)
        price = conn.namespace['current_price']
        
        if price == 0.0:
            print(f"Error: Could not fetch live tick for {symbol}. Ensure it is in Market Watch!")
            return
            
        print(f"Live market price fetched: {price}")
        
        # Validation Checks for both TPs
        if action == 'BUY':
            if extracted_data['sl'] >= price:
                print(f"⚠️ Skipping Trade: For a BUY, SL ({extracted_data['sl']}) must be BELOW price ({price})")
                return
            if extracted_data['tp_target_3'] <= price or extracted_data['tp_target_runner'] <= price:
                print(f"⚠️ Skipping Trade: For a BUY, TPs must be ABOVE price ({price})")
                return
        if action == 'SELL':
            if extracted_data['sl'] <= price:
                print(f"⚠️ Skipping Trade: For a SELL, SL ({extracted_data['sl']}) must be ABOVE price ({price})")
                return
            if extracted_data['tp_target_3'] >= price or extracted_data['tp_target_runner'] >= price:
                print(f"⚠️ Skipping Trade: For a SELL, TPs must be BELOW price ({price})")
                return
                
        # --- 4 & 5. PREPARE AND EXECUTE DUAL TRADES ---
        conn.namespace['trade_sym'] = symbol
        conn.namespace['trade_act'] = action
        conn.namespace['trade_prc'] = price
        conn.namespace['trade_sl'] = extracted_data['sl']
        # Pass the newly mapped variables to the MT5 execution list
        conn.namespace['trade_tps'] = [extracted_data['tp_target_3'], extracted_data['tp_target_runner']]
        
        print(f"Sending Dual {action} orders for {symbol} at price {price}...")
        
        trade_code = """
import MetaTrader5 as mt5

order_type = mt5.ORDER_TYPE_BUY if trade_act == 'BUY' else mt5.ORDER_TYPE_SELL
results = []

# Loop through the two TPs and execute a 0.01 lot trade for each
for tp_target in trade_tps:
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": trade_sym,
        "volume": 0.01, 
        "type": order_type,
        "price": trade_prc,
        "sl": trade_sl,
        "tp": tp_target,
        "deviation": 500, 
        "magic": 123456,
        "comment": "Multi-TP Bot",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    res = mt5.order_send(request)
    if res is None:
        results.append(mt5.last_error()[0])
    else:
        results.append(res.retcode)
"""
        conn.execute(trade_code)
        retcodes = conn.namespace['results']
        
        # Analyze the results returned from Windows
        for i, retcode in enumerate(retcodes):
            tp_label = "TP3" if i == 0 else "Second-to-Last TP"
            
            if retcode == 10009: 
                print(f"✅ TRADE {i+1} EXECUTED: {action} on {symbol} successful ({tp_label})!")
            else:
                print(f"⚠️ Trade {i+1} rejected. Retcode: {retcode}")
                if retcode == 10016:
                    print(f"-> Reason (10016): INVALID STOPS for {tp_label}.")
        
print("Bot is starting... Listening for signals...")
client.start()
client.run_until_disconnected()
