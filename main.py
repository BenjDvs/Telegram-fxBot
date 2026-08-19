import re
import rpyc
from telethon import TelegramClient, events

# search "volume/lot" to change lot size SUCCESS BOT!
# channel_username = 'goodbestsignal or goldkillerhub'

# --- 1. DIRECT RPYC CONNECTION (Bypassing mt5linux) ---
print("Connecting directly to the Wine MT5 Server...")
try:
    # Connect directly to mt5server.exe running in Wine
    conn = rpyc.classic.connect('127.0.0.1', 18812)
    # Import MetaTrader5 inside the Windows environment
    conn.execute("import MetaTrader5 as mt5")
    # Create a local reference to the remote module
    mt5 = conn.modules.MetaTrader5
except Exception as e:
    print(f"Failed to connect to MT5 bridge: {e}")
    exit()

print("Connecting to MT5 Terminal...")
if not mt5.initialize():
    print(f"Failed to initialize MT5")
    exit()
else:
    print("MT5 Initialized Successfully!")

# --- 2. YOUR TELEGRAM CREDENTIALS ---
api_id = 39853867 
api_hash = '97ad6f46617781299a9e0b62db81a88c'

def parse_signal(message_text):
    signal_data = {'action': None, 'symbol': None, 'sl': None, 'tp': None}
    
    # 1. Action (BUY / SELL)
    action_match = re.search(r'(BUY|SELL)', message_text, re.IGNORECASE)
    if action_match:
        signal_data['action'] = action_match.group(1).upper()
        
    # 2. Symbol Mapping
    symbol_match = re.search(r'(XAUUSD|GOLD)', message_text, re.IGNORECASE)
    if symbol_match:
        signal_data['symbol'] = 'XAUUSDm'
        
    # 3. Stop Loss (SL)
    sl_match = re.search(r'SL[\s:-]*([0-9.]+)', message_text, re.IGNORECASE)
    if sl_match:
        signal_data['sl'] = float(sl_match.group(1))
        
    # 4. Take Profit (TP) -> Second to the last
    tp_matches = re.findall(r'TP\d*[\s:-]*([0-9.]+)', message_text, re.IGNORECASE)
    if tp_matches:
        if len(tp_matches) >= 2:
            signal_data['tp'] = float(tp_matches[-2])  # Grabs second to last TP
        else:
            signal_data['tp'] = float(tp_matches[-1])  # Fallback if only 1 TP is present
            
    return signal_data

client = TelegramClient('forex_session', api_id, api_hash)
channel_username = 'goldkillerhub'

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
        
        # Validation Checks
        if action == 'BUY':
            if extracted_data['sl'] >= price:
                print(f"⚠️ Skipping Trade: For a BUY, SL ({extracted_data['sl']}) must be BELOW price ({price})")
                return
            if extracted_data['tp'] <= price:
                print(f"⚠️ Skipping Trade: For a BUY, TP ({extracted_data['tp']}) must be ABOVE price ({price})")
                return
        if action == 'SELL':
            if extracted_data['sl'] <= price:
                print(f"⚠️ Skipping Trade: For a SELL, SL ({extracted_data['sl']}) must be ABOVE price ({price})")
                return
            if extracted_data['tp'] >= price:
                print(f"⚠️ Skipping Trade: For a SELL, TP ({extracted_data['tp']}) must be BELOW price ({price})")
                return
                
        # --- 4 & 5. PREPARE AND EXECUTE TRADE ON THE WINDOWS SERVER ---
        conn.namespace['trade_sym'] = symbol
        conn.namespace['trade_act'] = action
        conn.namespace['trade_prc'] = price
        conn.namespace['trade_sl'] = extracted_data['sl']
        conn.namespace['trade_tp'] = extracted_data['tp']
        
        print(f"Sending {action} order for {symbol} at exact price {price}...")
        
        trade_code = """
import MetaTrader5 as mt5

order_type = mt5.ORDER_TYPE_BUY if trade_act == 'BUY' else mt5.ORDER_TYPE_SELL

request = {
    "action": mt5.TRADE_ACTION_DEAL,
    "symbol": trade_sym,
    "volume": 0.01, 
    "type": order_type,
    "price": trade_prc,
    "sl": trade_sl,
    "tp": trade_tp,
    "deviation": 500, 
    "magic": 123456,
    "comment": "Telegram Bot",
    "type_time": mt5.ORDER_TIME_GTC,
    "type_filling": mt5.ORDER_FILLING_IOC,
}

result = mt5.order_send(request)
if result is None:
    retcode = mt5.last_error()[0]
else:
    retcode = result.retcode
"""
        conn.execute(trade_code)
        retcode = conn.namespace['retcode']
        
        if retcode == 10009: 
            print(f"✅ TRADE EXECUTED: {action} on {symbol} successful!")
        else:
            print(f"⚠️ Trade rejected by broker. Retcode: {retcode}")
            if retcode == 10016:
                print("-> Reason (10016): INVALID STOPS. SL or TP is impossible at current market price!")
            elif retcode == 10013:
                print("-> Reason (10013): INVALID REQUEST. Check volume or filling mode.")
        
print("Bot is starting... Listening for signals...")
client.start()
client.run_until_disconnected()
