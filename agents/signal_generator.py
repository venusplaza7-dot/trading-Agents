import asyncio, random
async def run():
    tid=566
    while True:
        tid+=1
        win = random.random() < 0.62
        if win:
            print(f"TICK #{tid} LTC SHORT +$0.016 net WIN Gross +0.022 Fee $0.006")
        else:
            print(f"TICK #{tid} BTC LONG -$0.024 net LOSS RED Gross -0.018 Fee $0.006")
        await asyncio.sleep(3)
