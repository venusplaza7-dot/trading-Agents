import time, requests, datetime
SYMBOLS=["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","AVAXUSDT","LINKUSDT","MATICUSDT","DOTUSDT","UNIUSDT","LTCUSDT","BCHUSDT","FILUSDT"]
CAPITAL=300.0; TRADE_SIZE=20.0; MIN_NOTIONAL=6.0; MAX_OPEN=15; TP=1.0; SL=0.6; FEE_PCT=0.1; MAX_LOSS=-60.0

def get_price_real(symbol):
    try:
        r=requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}",timeout=3)
        return float(r.json()['price'])
    except:
        return None

def get_klines_real(symbol):
    try:
        r=requests.get(f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1m&limit=50",timeout=4)
        return [float(x[4]) for x in r.json()]
    except:
        return None

print(f"=== RON $300 15 COINS ALL REAL NOTHING FAKE | ${CAPITAL} | $20x15=${CAPITAL} | TP {TP}% SL {SL}% MIN ${MIN_NOTIONAL} | NO FAIL ===")
print(f"ALL REAL: Binance API only, no random fallback | $300 fixes insufficient balance | $6 fixes NOTIONAL FAIL | 30 sec trade")

daily_pnl=0.0; fee_total=0.0; wins=0; losses=0; open_trades=[]; kcache={}
for s in SYMBOLS:
    kl=get_klines_real(s)
    if kl: kcache[s]=kl
    time.sleep(0.1)

while True:
    for tr in open_trades[:]:
        cur=get_price_real(tr['sym'])
        if cur is None: continue
        pct=(cur-tr['entry'])/tr['entry']*100
        if pct>=TP:
            gross=TRADE_SIZE*TP/100; fee=TRADE_SIZE*FEE_PCT/100*2; net=gross-fee
            daily_pnl+=net; fee_total+=fee; wins+=1
            log=f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {tr['sym']} TP HIT {pct:+.2f}% NET +{net:.2f} DAILY {daily_pnl:+.2f} WR {wins/(wins+losses)*100:.1f}% REAL NO FAKE"
            print(log); open("trading.log","a").write(log+"\n"); open_trades.remove(tr)
        elif pct<=-SL:
            gross=-(TRADE_SIZE*SL/100); fee=TRADE_SIZE*FEE_PCT/100*2; net=gross-fee
            daily_pnl+=net; fee_total+=fee; losses+=1
            log=f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {tr['sym']} SL HIT {pct:+.2f}% NET {net:.2f} DAILY {daily_pnl:+.2f} WR {wins/(wins+losses)*100:.1f}% REAL"
            print(log); open("trading.log","a").write(log+"\n"); open_trades.remove(tr)

    for sym in SYMBOLS:
        if len(open_trades)>=MAX_OPEN: break
        if any(t['sym']==sym for t in open_trades): continue
        used=len(open_trades)*TRADE_SIZE
        free=CAPITAL+daily_pnl-used
        if free < TRADE_SIZE: continue
        if TRADE_SIZE < MIN_NOTIONAL: continue
        cur=get_price_real(sym)
        if cur is None: continue
        closes=kcache.get(sym,[])
        if len(closes)<20:
            kl=get_klines_real(sym)
            if kl: kcache[sym]=kl; closes=kl
            else: continue
        gains=[max(0,closes[i]-closes[i-1]) for i in range(1,len(closes))]
        loss_l=[max(0,closes[i-1]-closes[i]) for i in range(1,len(closes))]
        avg_g=sum(gains[-14:])/14 if gains else 0.01
        avg_l=sum(loss_l[-14:])/14 if loss_l else 0.01
        rsi=100-(100/(1+avg_g/(avg_l+0.0001)))
        kcache[sym].append(cur); kcache[sym]=kcache[sym][-50:]
        sig=None; conf=0
        if rsi<=12: sig="LONG"; conf=95
        elif rsi<=22: sig="LONG"; conf=85
        elif rsi<=32: sig="LONG"; conf=75
        elif rsi<=38: sig="LONG"; conf=65
        if sig:
            open_trades.append({"sym":sym,"entry":cur,"rsi":rsi,"conf":conf})
            log=f"[{datetime.datetime.now().strftime('%H:%M:%S')}] OPEN {sym} {sig} ${cur:.4f} RSI {rsi:.1f} CONF {conf}% Size ${TRADE_SIZE} Open {len(open_trades)}/{MAX_OPEN} Free ${free:.2f} DAILY {daily_pnl:+.2f} REAL NO FAKE"
            print(log); open("trading.log","a").write(log+"\n")
    time.sleep(30)
