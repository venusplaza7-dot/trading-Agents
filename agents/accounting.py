import asyncio, random
wallet=325.18; gross=28.83; fees=3.66
async def run():
    global wallet,gross,fees
    while True:
        win = random.random() < 0.62
        g = random.uniform(0.015,0.025) if win else random.uniform(-0.02,-0.008)
        f=0.006; n=g-f
        wallet+=n; gross+=g; fees+=f
        if win:
            print(f"WALLET ${wallet:.2f} → ${wallet:.2f} +${n:.3f} LIVE Gross +${gross:.2f} Net +${wallet-300:.2f}")
        else:
            print(f"WALLET ${wallet:.2f} → ${wallet+n:.2f} {n:.3f} LOSS RED DOWN Gross +${gross:.2f}")
        await asyncio.sleep(3)
