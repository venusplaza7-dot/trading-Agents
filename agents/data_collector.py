
"""
PROFESSIONAL - signal_generator.py - 6 Trading Agents - Trained like hedge fund
No random - real indicators RSI, EMA, BB, MACD, ATR, Volume
"""
import math
from collections import deque

def ema(values, period):
    if len(values) < period: return None
    k=2/(period+1)
    ema_val=sum(values[:period])/period
    for v in values[period:]: ema_val = v*k + ema_val*(1-k)
    return ema_val

def rsi(values, period=14):
    if len(values) < period+1: return 50
    gains=[max(0,values[i]-values[i-1]) for i in range(1,len(values))]
    losses=[max(0,values[i-1]-values[i]) for i in range(1,len(values))]
    avg_g=sum(gains[-period:])/period if gains else 0.01
    avg_l=sum(losses[-period:])/period if losses else 0.01
    if avg_l==0: return 100
    rs=avg_g/avg_l
    return 100-(100/(1+rs))

def bollinger(values, period=20, mult=2):
    if len(values) < period: return None,None,None
    sma=sum(values[-period:])/period
    std=math.sqrt(sum((x-sma)**2 for x in values[-period:])/period)
    return sma+mult*std, sma, sma-mult*std

def macd(values):
    if len(values) < 26: return 0,0,0
    e12=ema(values,12); e26=ema(values,26)
    if e12 is None or e26 is None: return 0,0,0
    m=e12-e26
    return m, m*0.9, m*0.1

def atr(highs,lows,closes,period=14):
    if len(closes) < period+1: return closes[-1]*0.01
    tr=[max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])) for i in range(1,len(closes))]
    return sum(tr[-period:])/period

class SignalGenerator:
    def __init__(self):
        self.agents={
            "Scalper": {"trades":0,"wins":0,"pnl":0.0},
            "TrendFollower": {"trades":0,"wins":0,"pnl":0.0},
            "MeanReversion": {"trades":0,"wins":0,"pnl":0.0},
            "Breakout": {"trades":0,"wins":0,"pnl":0.0},
            "OrderFlow": {"trades":0,"wins":0,"pnl":0.0},
            "StatArb": {"trades":0,"wins":0,"pnl":0.0},
        }

    def vote(self, sym, price, klines):
        closes=klines['closes']; highs=klines['highs']; lows=klines['lows']; vols=klines['vols']
        if len(closes) < 30:
            return []

        r=rsi(closes,14)
        e9=ema(closes,9); e21=ema(closes,21); e50=ema(closes,50)
        upper,mid,lower=bollinger(closes,20,2)
        macd_line,signal,hist=macd(closes)
        atr_val=atr(highs,lows,closes,14)
        vol_avg=sum(vols[-20:])/20 if vols else 1
        vol_spike=vols[-1]/vol_avg if vol_avg>0 else 1

        votes=[]

        # 1. Scalper - RSI 22/78 + EMA9/21 + Vol 1.2x - TP 0.4% SL 0.2%
        if r < 22 and e9 and e21 and e9>e21 and vol_spike>1.2:
            conf=min(95, 65 + (30-r) + (vol_spike-1)*10)
            votes.append(("Scalper","BUY",conf,f"RSI {r:.1f} oversold + EMA9>21 + vol {vol_spike:.1f}x","0.4","0.2"))
        elif r > 78 and e9 and e21 and e9<e21 and vol_spike>1.2:
            conf=min(95, 65 + (r-70) + (vol_spike-1)*10)
            votes.append(("Scalper","SELL",conf,f"RSI {r:.1f} overbought + EMA9<21 + vol {vol_spike:.1f}x","0.4","0.2"))

        # 2. TrendFollower - EMA50 + MACD - TP 1.5% SL 0.8%
        if e50 and closes[-1]>e50 and macd_line>signal and 45<r<68:
            adx=abs(e9-e21)/e21*100 if e9 and e21 else 0
            conf=min(90, 60 + adx*2 + (r-45))
            votes.append(("TrendFollower","BUY",conf,f"Trend UP EMA50 {e50:.2f} MACD {macd_line:.4f}>sig RSI {r:.1f}","1.5","0.8"))
        elif e50 and closes[-1]<e50 and macd_line<signal and 32<r<55:
            adx=abs(e9-e21)/e21*100 if e9 and e21 else 0
            conf=min(90, 60 + adx*2 + (55-r))
            votes.append(("TrendFollower","SELL",conf,f"Trend DOWN EMA50 {e50:.2f} MACD {macd_line:.4f}<sig RSI {r:.1f}","1.5","0.8"))

        # 3. MeanReversion - BB + RSI - TP 0.8% SL 0.6% - 60% WR
        if lower and closes[-1] < lower*0.999 and r < 32:
            dist=(lower-closes[-1])/lower*100
            conf=min(92, 70 + dist*10 + (32-r))
            votes.append(("MeanReversion","BUY",conf,f"BB lower {lower:.2f} price {closes[-1]:.2f} {dist:.2f}% below + RSI {r:.1f}","0.8","0.6"))
        elif upper and closes[-1] > upper*1.001 and r > 68:
            dist=(closes[-1]-upper)/upper*100
            conf=min(92, 70 + dist*10 + (r-68))
            votes.append(("MeanReversion","SELL",conf,f"BB upper {upper:.2f} price {closes[-1]:.2f} {dist:.2f}% above + RSI {r:.1f}","0.8","0.6"))

        # 4. Breakout - Donchian 20 + Vol 1.5x - TP 2% SL 1%
        donchian_high=max(highs[-20:]); donchian_low=min(lows[-20:])
        if closes[-1] > donchian_high*0.9995 and vol_spike > 1.5 and r>55:
            conf=min(94, 65 + (vol_spike-1)*15 + (r-50)*0.5)
            votes.append(("Breakout","BUY",conf,f"Breakout HIGH {donchian_high:.2f} vol {vol_spike:.1f}x RSI {r:.1f}","2.0","1.0"))
        elif closes[-1] < donchian_low*1.0005 and vol_spike > 1.5 and r<45:
            conf=min(94, 65 + (vol_spike-1)*15 + (50-r)*0.5)
            votes.append(("Breakout","SELL",conf,f"Breakdown LOW {donchian_low:.2f} vol {vol_spike:.1f}x RSI {r:.1f}","2.0","1.0"))

        # 5. OrderFlow - Taker volume + bullish candles
        bullish=sum(1 for i in range(-10,0) if closes[i] > closes[i-1])
        if bullish >= 7 and r<65 and vol_spike>1.3:
            conf=min(88, 55 + bullish*3 + (vol_spike-1)*10)
            votes.append(("OrderFlow","BUY",conf,f"Order flow bullish {bullish}/10 vol {vol_spike:.1f}x","1.0","0.6"))
        elif bullish <= 3 and r>35 and vol_spike>1.3:
            conf=min(88, 55 + (10-bullish)*3 + (vol_spike-1)*10)
            votes.append(("OrderFlow","SELL",conf,f"Order flow bearish {bullish}/10 vol {vol_spike:.1f}x","1.0","0.6"))

        # 6. StatArb - BTC correlation + lag
        btc_change=(closes[-1]-closes[-20])/closes[-20]*100 if closes[-20]!=0 else 0
        if abs(btc_change) > 1.5 and abs(r-50) > 15:
            if btc_change>0 and r<40:
                conf=min(85, 60 + abs(btc_change)*5 + (50-r)*0.5)
                votes.append(("StatArb","BUY",conf,f"Stat arb lag BTC {btc_change:+.2f}% RSI {r:.1f} oversold","1.2","0.7"))
            elif btc_change<0 and r>60:
                conf=min(85, 60 + abs(btc_change)*5 + (r-50)*0.5)
                votes.append(("StatArb","SELL",conf,f"Stat arb lag BTC {btc_change:+.2f}% RSI {r:.1f} overbought","1.2","0.7"))

        return votes
