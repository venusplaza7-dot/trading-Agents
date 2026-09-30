
"""
PROFESSIONAL - monitor.py - Monitoring for dashboard - real metrics
"""
import datetime

class Monitor:
    def __init__(self):
        self.logs=[]
        self.agent_stats={}

    def log(self, msg):
        entry=f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}"
        self.logs.append(entry)
        if len(self.logs)>200:
            self.logs.pop(0)
        print(entry)
        return entry

    def get_agent_report(self, signal_gen, accounting, risk_manager):
        report=[]
        for name, stats in signal_gen.agents.items():
            total=stats['trades']
            wr=stats['wins']/total*100 if total>0 else 0
            report.append(f"{name}: {stats['trades']} trades {stats['wins']}W {wr:.1f}% PnL ${stats['pnl']:.2f}")
        report.append(f"RiskGuard: Blocked {risk_manager.blocked} Approved {risk_manager.approved}")
        report.append(f"Accounting: Capital ${accounting.capital:.2f} Daily {accounting.daily_pnl:+.2f} WR {accounting.get_stats()['wr']:.1f}%")
        return report
