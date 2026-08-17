import re
import time
from mt5linux import MetaTrader5
from telethon import TelegramClient, events

#search "LOT" to change lot side SUCCESS BOT!
#channel_username = 'goodbestsignal or goldkillerhub'

# Connect to the mt5server.exe running in Wine
mt5 = MetaTrader5(host='localhost', port=18812)

# --- MT5 INITIALIZATION ---
print("Connecting to MT5 Terminal...")
if not mt5.initialize():
    print(f"Failed to initialize MT5, error code: {mt5.last_error()}")
    exit()
else:
    print("MT5 Initialized Successfully!")

# --- YOUR TELEGRAM CREDENTIALS ---
api_id = 39853867 
api_hash = '97ad6f46617781299a9e0b62db81a88c'

def parse_signal(message_text):
    signal_data = {
        'action': None,
        'symbol': None,
        'sl': None,
        'tp': None
    }
    
    action_match = re.search(r'(BUY|SELL)', message_text, re.IGNORECASE)
    if action_match:
        signal_data['action'] = action_match.group(1).upper()
        
    symbol_match = re.search(r'(XAUUSD|GOLD)', message_text, re.IGNORECASE)
    if symbol_match:
        signal_data['symbol'] = 'XAUUSDm'
        
    sl_match = re.search(r'SL[\s:-]*([0-9.]+)', message_text, re.IGNORECASE)
    if sl_match:
        signal_data['sl'] = float(sl_match.group(1))
        
    tp_matches = re.findall(r'TP\d*[\s:-]*([0-9.]+)', message_text, re.IGNORECASE)
    
    if tp_matches:
        if len(tp_matches) >= 4:
            signal_data['tp'] = float(tp_matches[3]) 
        else:
            signal_data['tp'] = float(tp_matches[-1]) 
            
    return signal_data

client = TelegramClient('forex_session', api_id, api_hash)
channel_username = 'goldkillerhub'

@client.on(events.NewMessage(chats=channel_username))
async def handler(event):
    raw_signal = event.message.message
    print("--------------------------------------------------")
    print(f"NEW SIGNAL RECEIVED:\n{raw_signal}")
    
    extracted_data = parse_signal(raw_signal)
    
    print("EXTRACTED DATA:")
    print(extracted_data)
    print("--------------------------------------------------")
    
    if all(extracted_data.values()):
        print("Ready to send to MT5!")
        
        symbol = extracted_data['symbol']
        action = extracted_data['action']
        
        order_type = mt5.ORDER_TYPE_BUY if action == 'BUY' else mt5.ORDER_TYPE_SELL
        
        # 1. Fetch exact LIVE Ask/Bid directly as a raw float to bypass the Pickling Bug!
        try:
            if action == 'BUY':
                price = mt5._container.eval(f"mt5.symbol_info_tick('{symbol}').ask")
            else:
                price = mt5._container.eval(f"mt5.symbol_info_tick('{symbol}').bid")
                
            price = float(price)
            if price == 0.0:
                print(f"Error: {symbol} market is closed or not in Market Watch.")
                return
        except Exception as e:
            print(f"Could not fetch live tick for {symbol}. Error: {e}")
            return
        
        # 2. Validation Checks (Ensuring SL and TP are logically valid before sending)
        if action == 'BUY':
            if extracted_data['sl'] >= price:
                print(f"⚠️ Skipping Trade: For a BUY, SL ({extracted_data['sl']}) must be BELOW current price ({price})")
                return
            if extracted_data['tp'] <= price:
                print(f"⚠️ Skipping Trade: For a BUY, TP ({extracted_data['tp']}) must be ABOVE current price ({price})")
                return

        if action == 'SELL':
            if extracted_data['sl'] <= price:
                print(f"⚠️ Skipping Trade: For a SELL, SL ({extracted_data['sl']}) must be ABOVE current price ({price})")
                return
            if extracted_data['tp'] >= price:
                print(f"⚠️ Skipping Trade: For a SELL, TP ({extracted_data['tp']}) must be BELOW current price ({price})")
                return
        
        # 3. Order Dictionary (FIXED FILLING MODE FOR EXNESS)
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": 0.02, 
            "type": order_type,
            "price": price,
            "sl": extracted_data['sl'],
            "tp": extracted_data['tp'],
            "deviation": 500, 
            "magic": 123456,
            "comment": "Telegram Bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,  # Must be IOC for Exness!
        }
        
        print(f"Sending {action} order for {symbol} at exact price {price}...")
        
        try:
            # 4. Bypass the Pickling Bug!
            # We convert the request dictionary to a string, send it to the Windows Wine environment,
            # execute the order_send over there, and only return the integer 'retcode' back to Linux.
            req_str = str(request)
            retcode = mt5._container.eval(f"mt5.order_send({req_str}).retcode")
            
            if retcode == 10009: # 10009 is the MT5 success code
                print(f"✅ TRADE EXECUTED: {action} on {symbol} successful!")
            else:
                print(f"⚠️ Trade rejected by broker. Retcode: {retcode}")
                if retcode == 10016:
                    print("-> Reason (10016): INVALID STOPS. Your SL or TP is impossible at the current market price!")
                elif retcode == 10013:
                    print("-> Reason (10013): INVALID REQUEST. Check your volume or filling mode.")
                elif retcode == 10027:
                    print("-> Reason (10027): ALGO TRADING DISABLED. Ensure the 'Algo Trading' button in MT5 is green!")
                
        except Exception as e:
            print(f"⚠️ Execution error: {e}")
                
    else:
        print("Could not extract all necessary data. Ignoring message.")
        
print("Bot is starting... Listening for signals...")
client.start()
client.run_until_disconnected() # <-- ADDED THE MISSING PARENTHESES HERE!
