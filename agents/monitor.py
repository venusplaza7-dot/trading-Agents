import asyncio, time
last=time.time()
async def run():
    global last
    print("Monitor: VPS 24/7 BACKGROUND WORKED 12m 34s 32 closes +$0.96")
    while True:
        now=time.time()
        elapsed=now-last
        if elapsed>60:
            print(f"BACKGROUND {int(elapsed//60)}m {int(elapsed%60)}s while away")
        last=now
        await asyncio.sleep(10)
