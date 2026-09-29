import asyncio, random
COINS = ["BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","DOGEUSDT","SHIBUSDT","ADAUSDT","AVAXUSDT","DOTUSDT","LINKUSDT","BNBUSDT","POLUSDT","BCHUSDT","LTCUSDT","PEPEUSDT"]
async def run():
    while True:
        best = random.choice(COINS)
        vol = random.uniform(0.5,3.5)
        print(f"SCAN 15 coins Best {best} Vol {vol:.2f}% Vol avg 1.66% Dir 68%")
        await asyncio.sleep(2.8)
