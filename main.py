import re
import time
from mt5linux import MetaTrader5
from telethon import TelegramClient, events

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
channel_username = 'goodbestsignal'

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
        
        # 2. Validation Checks
        if action == 'BUY' and extracted_data['tp'] <= price:
            print(f"Skipping Trade: TP ({extracted_data['tp']}) must be higher than current price ({price})")
            return

        if action == 'SELL' and extracted_data['tp'] >= price:
            print(f"Skipping Trade: TP ({extracted_data['tp']}) must be lower than current price ({price})")
            return
        
        # 3. Order Dictionary (FIXED FILLING MODE FOR EXNESS)
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": 0.01, 
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
        
        # Safely count positions before the trade
        positions_before = mt5.positions_total()
        if positions_before is None:
            positions_before = 0
            
        print(f"Sending {action} order for {symbol} at exact price {price}...")
        
        try:
            result = mt5.order_send(request)
            
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"✅ TRADE EXECUTED: {action} on {symbol} successful!")
            else:
                print(f"⚠️ Trade rejected by broker. Retcode: {result.retcode}")
                
        except Exception as e:
            # We catch the bridge crash and verify the trade manually
            print(f"⚠️ Bridge serialization error intercepted: {e}")
            print("Verifying trade status...")
            time.sleep(2) # Give MT5 2 seconds to execute the order
            
            positions_after = mt5.positions_total()
            if positions_after is not None and positions_after > positions_before:
                print(f"✅ TRADE VERIFIED: {action} on {symbol} is LIVE in MT5!")
            else:
                print(f"❌ Trade failed. No new positions detected.")
                print("👉 CHECK MT5 JOURNAL: Open MT5 on the VPS, look at the 'Toolbox' at the bottom, and click the 'Journal' tab to see exactly why Exness rejected the trade.")
                
    else:
        print("Could not extract all necessary data. Ignoring message.")
        
print("Bot is starting... Listening for signals...")
client.start()
client.run_until_disconnected()
