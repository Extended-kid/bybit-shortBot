import time
import logging
from typing import Dict, Any, Optional
from pybit.unified_trading import HTTP
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

class BybitClient:
    """Обертка для Bybit API с retry и обработкой ошибок"""
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        self.session = HTTP(
            testnet=testnet,
            api_key=api_key,
            api_secret=api_secret
        )
        self.rate_limit_remaining = 50
        self.rate_limit_reset = 0
        self.category = "linear"
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    def get_instruments(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Получить информацию об инструменте с retry"""
        params = {"category": "linear"}
        if symbol:
            params["symbol"] = symbol
            
        response = self.session.get_instruments_info(**params)
        
        if response.get("retCode") != 0:
            raise RuntimeError(f"API Error: {response.get('retMsg')}")
            
        self._update_rate_limits(response)
        return response
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    def get_tickers(self) -> Dict[str, Any]:
        """Получить все тикеры"""
        response = self.session.get_tickers(category="linear")
        
        if response.get("retCode") != 0:
            raise RuntimeError(f"API Error: {response.get('retMsg')}")
            
        self._update_rate_limits(response)
        return response
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    def get_klines(self, symbol: str, interval: str, limit: int = 5) -> Dict[str, Any]:
        """Получить свечи"""
        response = self.session.get_kline(
            category="linear",
            symbol=symbol,
            interval=interval,
            limit=limit
        )
        
        if response.get("retCode") != 0:
            raise RuntimeError(f"API Error: {response.get('retMsg')}")
            
        self._update_rate_limits(response)
        return response
    
    def _update_rate_limits(self, response: Dict[str, Any]):
        """Обновить информацию о rate limits"""
        headers = getattr(response, 'headers', {})
        remaining = headers.get('X-Bapi-Limit-Status', '50')
        reset = headers.get('X-Bapi-Limit-Reset-Timestamp', '0')
        
        try:
            self.rate_limit_remaining = int(remaining)
            self.rate_limit_reset = int(reset)
        except:
            pass
    
    def wait_if_needed(self):
        """Подождать если близко rate limit"""
        if self.rate_limit_remaining < 5:
            wait_time = max(0, (self.rate_limit_reset / 1000) - time.time())
            if wait_time > 0:
                logger.warning(f"Rate limit low, waiting {wait_time:.1f}s")
                time.sleep(min(wait_time, 5))
    
    def get_wallet_balance(self, **kwargs) -> Dict[str, Any]:
        """Получить баланс кошелька"""
        response = self.session.get_wallet_balance(**kwargs)
        if response.get("retCode") != 0:
            raise RuntimeError(f"API Error: {response.get('retMsg')}")
        self._update_rate_limits(response)
        return response
    
    def place_order(self, **kwargs) -> Dict[str, Any]:
        """Разместить ордер"""
        response = self.session.place_order(**kwargs)
        if response.get("retCode") != 0:
            raise RuntimeError(f"API Error: {response.get('retMsg')}")
        self._update_rate_limits(response)
        return response
    
    def get_position_info(self, symbol: str) -> List[Dict[str, Any]]:
        """Получить информацию о позиции по символу"""
        try:
            response = self.session.get_position_info(
                category=self.category,
                symbol=symbol
            )
            if response.get("retCode") == 0:
                return response["result"]["list"]
            else:
                logger.error(f"Ошибка получения позиции {symbol}: {response.get('retMsg')}")
                return []
        except Exception as e:
            logger.error(f"Ошибка получения позиции {symbol}: {e}")
            return []