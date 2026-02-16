import logging
import requests
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = bool(bot_token and chat_id)
        
        if self.enabled:
            self.base_url = f"https://api.telegram.org/bot{bot_token}"
    
    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        if not self.enabled:
            return False
        
        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode
            }
            response = requests.post(url, data=data, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Telegram error: {e}")
            return False
    
    def send_trade_open(self, symbol: str, entry: float, tp: float, sl: float, 
                        size_usdt: float, multiplier: float):
        if not self.enabled:
            return
        
        text = f"""
рџџў NEW TRADE
Symbol: {symbol}
Entry: 
TP:  ({((tp/entry - 1)*100):.1f}%)
SL:  ({((sl/entry - 1)*100):.1f}%)
Size:  ({multiplier:.1f}x)
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        self.send_message(text)
    
    def send_trade_close(self, symbol: str, entry: float, exit_price: float, 
                         pnl_usdt: float, pnl_percent: float, reason: str, duration: str):
        if not self.enabled:
            return
        
        emoji = "рџџў" if pnl_usdt > 0 else "рџ”ґ"
        sign = "+" if pnl_usdt > 0 else ""
        
        text = f"""
{emoji} TRADE CLOSED
Symbol: {symbol}
Reason: {reason}
Entry: 
Exit: 
PnL: {sign} ({sign}{pnl_percent:.1f}%)
Duration: {duration}
"""
        self.send_message(text)
