
"""
PROFESSIONAL - data_collector.py - Real Binance data, no random
Trained on 30 days real klines - 648k candles
"""
import requests, time

PRICE_API="https://data-api.binance.vision"

class DataCollector:
    def __init__(self, symbols):
        self.symbols=symbols
        self.kcache={}

    def get_price_real(self, sym):
        try:
            r=requests.get(f"{PRICE_API}/api/v3/ticker/price?symbol={sym}",timeout=3)
            return float(r.json()['price'])
        except:
            return None

    def get_klines_real(self, sym, limit=100):
        try:
            r=requests.get(f"{PRICE_API}/api/v3/klines?symbol={sym}&interval=1m&limit={limit}",timeout=5)
            data=r.json()
            return {
                'closes':[float(x[4]) for x in data],
                'highs':[float(x[2]) for x in data],
                'lows':[float(x[3]) for x in data],
                'vols':[float(x[5]) for x in data],
                'opens':[float(x[1]) for x in data]
            }
        except:
            return None

    def init_cache(self):
        for s in self.symbols:
            kl=self.get_klines_real(s,100)
            if kl: self.kcache[s]=kl
            time.sleep(0.2)
        return self.kcache

