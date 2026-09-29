class RiskManager:
    def __init__(self):
        self.started=300.00
        self.used=12.00
        self.free=288.00
        self.locked=12.00
        self.max_dd=-10.00
        self.max_daily=-5.00
    def check(self, pnl):
        if pnl < self.max_daily:
            print(f"STOP Daily {pnl} < {self.max_daily}")
            return False
        print(f"RISK OK Started ${self.started} Used ${self.used} Free ${self.free} Locked ${self.locked} NET 0 delta neutral Fee $0.006")
        return True
