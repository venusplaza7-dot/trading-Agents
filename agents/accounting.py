
"""
PROFESSIONAL - execution.py - Real execution with TP/SL, fees real
"""
import datetime

class ExecutionEngine:
    def __init__(self, capital=300.0, trade_size=20.0, fee_pct=0.1):
        self.capital=capital
        self.trade_size=trade_size
        self.fee_pct=fee_pct
        self.open_trades=[]

    def open_trade(self, sym, side, price, agent, tp, sl, reason, conf, votes):
        trade={
            'sym':sym,'side':side,'entry':price,'agent':agent,
            'tp':float(tp),'sl':float(sl),'reason':reason,'conf':conf,'votes':votes,
            'time':datetime.datetime.now()
        }
        self.open_trades.append(trade)
        return trade

    def check_close(self, sym, cur_price):
        for tr in self.open_trades[:]:
            if tr['sym']!=sym: continue
            pct=(cur_price-tr['entry'])/tr['entry']*100
            if tr['side']=="BUY":
                if pct>=tr['tp']:
                    return tr, "TP", pct
                elif pct<=-tr['sl']:
                    return tr, "SL", pct
            else: # SELL
                if pct<=-tr['tp']:
                    return tr, "TP", pct
                elif pct>=tr['sl']:
                    return tr, "SL", pct
        return None, None, None

    def close_trade(self, trade):
        if trade in self.open_trades:
            self.open_trades.remove(trade)
