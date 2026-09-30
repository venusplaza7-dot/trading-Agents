
"""
PROFESSIONAL - accounting.py - $300 15 coins = $300 NO FAIL - Real PnL
"""
class Accounting:
    def __init__(self, capital=300.0, trade_size=20.0):
        self.start_capital=capital
        self.capital=capital
        self.trade_size=trade_size
        self.daily_pnl=0.0
        self.fee_total=0.0
        self.wins=0
        self.losses=0
        self.trades=[]

    def add_trade(self, gross, fee, win):
        net=gross-fee
        self.daily_pnl+=net
        self.fee_total+=fee
        self.capital=self.start_capital+self.daily_pnl
        if win: self.wins+=1
        else: self.losses+=1
        self.trades.append({'gross':gross,'fee':fee,'net':net,'win':win})
        return net

    def get_stats(self):
        total=self.wins+self.losses
        wr=self.wins/total*100 if total>0 else 0
        return {
            'capital':self.capital,
            'daily_pnl':self.daily_pnl,
            'wins':self.wins,
            'losses':self.losses,
            'wr':wr,
            'fee_total':self.fee_total
        }
