import re
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
        
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            print(f"Could not get tick data for {symbol}. Is it visible in your MT5 Market Watch?")
            return
            
        price = tick.ask if action == 'BUY' else tick.bid
        
        if action == 'BUY' and extracted_data['tp'] <= price:
            print(f"Skipping Trade: TP ({extracted_data['tp']}) must be higher than current price ({price})")
            return

        if action == 'SELL' and extracted_data['tp'] >= price:
            print(f"Skipping Trade: TP ({extracted_data['tp']}) must be lower than current price ({price})")
            return
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": 0.01, 
            "type": order_type,
            "price": price,
            "sl": extracted_data['sl'],
            "tp": extracted_data['tp'],
            "deviation": 20,
            "magic": 123456,
            "comment": "Telegram Bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        print(f"TRADE RESULT: {result}")
        
    else:
        print("Could not extract all necessary data. Ignoring message.")

print("Bot is starting... Listening for signals...")
client.start()
client.run_until_disconnected()
