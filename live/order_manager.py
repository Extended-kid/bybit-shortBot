import math
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class OrderManager:
    @staticmethod
    def extract_filters(instrument_info: Dict[str, Any]) -> Dict[str, float]:
        result = instrument_info["result"]["list"][0]
        lot_size = result.get('lotSizeFilter', {})
        price_filter = result.get('priceFilter', {})
        
        return {
            'min_qty': float(lot_size.get('minOrderQty', 0)),
            'qty_step': float(lot_size.get('qtyStep', 0)),
            'min_notional': float(lot_size.get('minNotionalValue', 5)),
            'tick_size': float(price_filter.get('tickSize', 0)),
            'max_leverage': float(result.get('leverageFilter', {}).get('maxLeverage', 1))
        }
    
    @staticmethod
    def calculate_qty(notional: float, price: float, filters: Dict[str, float]) -> float:
        min_qty = filters['min_qty']
        qty_step = filters['qty_step']
        min_notional = filters['min_notional']
        
        qty = notional / price
        
        if qty_step > 0:
            qty = math.floor(qty / qty_step) * qty_step
        
        qty = max(qty, min_qty)
        
        if qty * price < min_notional:
            qty = math.ceil(min_notional / price / qty_step) * qty_step
        
        return qty
    
    @staticmethod
    def round_price(price: float, tick_size: float) -> float:
        if tick_size <= 0:
            return price
        return math.floor(price / tick_size) * tick_size
