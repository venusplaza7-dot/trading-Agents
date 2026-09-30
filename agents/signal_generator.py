
"""
PROFESSIONAL - risk_manager.py - RiskGuard Agent - Professional risk desk
Not a trader, blocks risky trades
"""
import math

class RiskManager:
    def __init__(self, max_daily_loss=-15.0, max_atr_pct=2.5, max_vol_spike=4.0):
        self.max_daily_loss=max_daily_loss
        self.max_atr_pct=max_atr_pct
        self.max_vol_spike=max_vol_spike
        self.blocked=0
        self.approved=0

    def check(self, sym, price, klines, daily_pnl):
        closes=klines['closes']
        highs=klines['highs']
        lows=klines['lows']
        vols=klines['vols']

        # ATR calculation
        if len(closes) >= 15:
            tr=[max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])) for i in range(1,len(closes))]
            atr=sum(tr[-14:])/14 if tr else price*0.01
            atr_pct=atr/price*100
            if atr_pct > self.max_atr_pct:
                self.blocked+=1
                return False, f"ATR too high {atr_pct:.2f}% >{self.max_atr_pct}% - high volatility"

        vol_avg=sum(vols[-20:])/20 if len(vols)>=20 else 1
        vol_spike=vols[-1]/vol_avg if vol_avg>0 else 1
        if vol_spike > self.max_vol_spike:
            self.blocked+=1
            return False, f"Vol spike extreme {vol_spike:.1f}x - manipulation"

        # RSI extreme
        if len(closes) >= 15:
            gains=[max(0,closes[i]-closes[i-1]) for i in range(1,len(closes))]
            losses=[max(0,closes[i-1]-closes[i]) for i in range(1,len(closes))]
            avg_g=sum(gains[-14:])/14 if gains else 0.01
            avg_l=sum(losses[-14:])/14 if losses else 0.01
            rsi=100-(100/(1+avg_g/(avg_l+0.0001)))
            if r < 8 or r > 92:
                self.blocked+=1
                return False, f"RSI extreme {r:.1f} - wait normalization"

        if daily_pnl <= self.max_daily_loss:
            self.blocked+=1
            return False, f"Daily loss limit hit {daily_pnl:.2f} <= {self.max_daily_loss}"

        self.approved+=1
        return True, f"Risk OK ATR {atr_pct if 'atr_pct' in locals() else 0:.2f}% vol {vol_spike:.1f}x"
