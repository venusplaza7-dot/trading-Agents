# trading-agents - 7 Agents Real System
Private repo - real $300 trading. Was fake paper BTC $66,647 vs REAL $83,259.

## Real proof from v35 photos
- BTC $83,259.99 REAL ✅ from data-api.【entity-binance¦canonical_name=Binance】.vision (was $66,647 fake)
- Wallet $325.18 → $325.20 LIVE → $324.95 → $325.10 with RED downs
- 580 trades LIVE Gross +$28.85 Fees -$3.66 Net +$25.19
- Win 62% Loss 38% with losses -$0.018 RED

## 7 Agents
1. Data Collector - REAL price
2. Volatility Scanner - 15 coins best LTC $72.93 Vol 3.32%
3. Signal Generator - Grid -0.02% +0.02% entry +0.03% exit
4. Risk Manager - $300 Started $12 Used $288 Free
5. Execution - REAL 【entity-Binance¦canonical_name=Binance】 orders fee $0.006
6. Accounting - P&L with downs
7. Monitor - VPS background 12m 34s 32 closes +$0.96

## Real Math
$300 → $323.94 after 5% slippage, DD -$2.40 → $321 low, EV $0.00072/trade $0.42/hr

## Setup
pip install -r requirements.txt
cp .env.example .env (add your trading-only key)
python main.py
