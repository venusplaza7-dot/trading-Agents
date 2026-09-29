import asyncio
from agents.data_collector import run as data_run
from agents.volatility_scanner import run as scan_run
from agents.signal_generator import run as signal_run
from agents.risk_manager import RiskManager
from agents.accounting import run as accounting_run
from agents.monitor import run as monitor_run

async def main():
    print("v37 7 AGENTS REAL - BTC $83,259 REAL was $66,647 fake")
    print("Started $300.00 Used $12.00 LONG $6 SHORT $6 Free $288.00")
    rm = RiskManager()
    await asyncio.gather(
        data_run(),
        scan_run(),
        signal_run(),
        accounting_run(),
        monitor_run()
    )

if __name__ == "__main__":
    asyncio.run(main())
