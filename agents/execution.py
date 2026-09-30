
"""
PROFESSIONAL - volatility_scanner.py - ATR, Bollinger, Volume scanner
"""
import math

def atr(highs,lows,closes,period=14):
    if len(closes) < period+1: return closes[-1]*0.01
    tr=[max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])) for i in range(1,len(closes))]
    return sum(tr[-period:])/period

def bollinger_width(closes, period=20):
    if len(closes) < period: return 0
    sma=sum(closes[-period:])/period
    std=math.sqrt(sum((x-sma)**2 for x in closes[-period:])/period)
    return (2*std)/sma*100 if sma!=0 else 0

class VolatilityScanner:
    def __init__(self):
        self.scan_results={}

    def scan(self, sym, klines):
        closes=klines['closes']; highs=klines['highs']; lows=klines['lows']; vols=klines['vols']
        atr_val=atr(highs,lows,closes,14)
        bb_width=bollinger_width(closes,20)
        vol_avg=sum(vols[-20:])/20 if len(vols)>=20 else 1
        vol_spike=vols[-1]/vol_avg if vol_avg>0 else 1

        self.scan_results[sym]={
            'atr':atr_val,
            'atr_pct':atr_val/closes[-1]*100 if closes else 0,
            'bb_width':bb_width,
            'vol_spike':vol_spike,
            'is_high_vol': atr_val/closes[-1]*100 > 2.0 if closes else False
        }
        return self.scan_results[sym]
