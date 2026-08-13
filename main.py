import re # Add this at the very top of your file!
from mt5linux import MetaTrader5
mt5 = MetaTrader5(host="localhost", port=18812) # Add this at the top!
from telethon import TelegramClient, events

#search "LOT" to change lot side SUCCESS BOT!
#channel_username = 'goodbestsignal or goldkillerhub'

# --- YOUR TELEGRAM CREDENTIALS ---
# You must complete Stage 1 (my.telegram.org) to get these numbers!
api_id = 39853867 
api_hash = '97ad6f46617781299a9e0b62db81a88c'

def parse_signal(message_text):
    # Create a dictionary to hold extracted data
    signal_data = {
        'action': None,
        'symbol': None,
        'sl': None,
        'tp': None
    }
    
    # 1. Find Action (BUY or SELL - this will easily catch #BUY)
    action_match = re.search(r'(BUY|SELL)', message_text, re.IGNORECASE)
    if action_match:
        signal_data['action'] = action_match.group(1).upper()
        
    # 2. Find Symbol (This will catch #XAUUSD)
    symbol_match = re.search(r'(XAUUSD|GOLD)', message_text, re.IGNORECASE)
    if symbol_match:
        signal_data['symbol'] = 'XAUUSDm'
        
    # 3. Find Stop Loss (SL)
    sl_match = re.search(r'SL[\s:-]*([0-9.]+)', message_text, re.IGNORECASE)
    if sl_match:
        signal_data['sl'] = float(sl_match.group(1))
        
    # 4. Find Take Profit (TP)
    # The \d* ensures it safely ignores numbers like "1" in "TP1" and grabs the price
    tp_matches = re.findall(r'TP\d*[\s:-]*([0-9.]+)', message_text, re.IGNORECASE)
    
    if tp_matches:
        # Your format has 8 TPs. 
        # Index 0 = 1st TP, Index 1 = 2nd TP, Index 3 = 4th TP, Index -1 = Last TP
        if len(tp_matches) >= 4:
            signal_data['tp'] = float(tp_matches[3]) # Currently grabs the 4th TP
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
        
        # --- MT5 EXECUTION LOGIC ---
        if not mt5.initialize():
            print("Failed to initialize MT5")
            return
        
        symbol = extracted_data['symbol']
        action = extracted_data['action']
        
        # 1. Prepare MT5 variables
        order_type = mt5.ORDER_TYPE_BUY if action == 'BUY' else mt5.ORDER_TYPE_SELL
        
        # Get current price directly from MT5
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            print(f"Could not get tick data for {symbol}. Is it visible in your MT5 Market Watch?")
            return
            
        price = tick.ask if action == 'BUY' else tick.bid
        
        # 2. Validation checks for BUY/SELL logic
        if action == 'BUY' and extracted_data['tp'] <= price:
            print(f"Skipping Trade: TP ({extracted_data['tp']}) must be higher than current price ({price})")
            return

        if action == 'SELL' and extracted_data['tp'] >= price:
            print(f"Skipping Trade: TP ({extracted_data['tp']}) must be lower than current price ({price})")
            return
        
        # 3. Build order request dictionary
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": 0.01, # Fixed lot size for testing
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
        
        # 4. Execute the trade!
        result = mt5.order_send(request)
        print(f"TRADE RESULT: {result}")
        
    else:
        print("Could not extract all necessary data. Ignoring message.")

print("Bot is starting... Listening for signals...")
client.start()
client.run_until_disconnected()
