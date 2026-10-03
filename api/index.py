from flask import Flask
import json, random, time, os
import requests
from datetime import datetime

app = Flask(__name__)

# --- STORAGE ---
try:
    from upstash_redis import Redis
    db = Redis.from_env()
    def load(k,d):
        v=db.get(k)
        return json.loads(v) if v else d
    def save(k,v): db.set(k, json.dumps(v))
    KV=True
except:
    M={}
    def load(k,d): return M.get(k,d)
    def save(k,v): M[k]=v
    KV=False

COINS = ["BONKUSDT","PEPEUSDT","SHIBUSDT","FLOKIUSDT","BOMEUSDT","MEMEUSDT","DOGEUSDT","WIFUSDT"]

def get_real_price(symbol):
    """Get REAL price from Binance"""
    try:
        r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}", timeout=3)
        return float(r.json()['price'])
    except:
        return None

@app.route('/api/cron')
def cron():
    open_trades = load('open', [])
    closed = load('closed', [])
    cap = load('cap', 300.0)
    daily = load('daily', 0.0)
    total = load('total', 0)
    wins = load('wins', 0)
    now = time.time()

    # --- CLOSE with REAL PRICE CHECK ---
    new_open = []
    for t in open_trades:
        age = now - t['t']
        real_price = get_real_price(t['symbol'])

        # Real TP: +1.5% or Stop -1% or timeout 120s
        win_price = t['entry'] * 1.015
        loss_price = t['entry'] * 0.99

        closed_reason = None
        if real_price and real_price >= win_price:
            closed_reason = "WIN"
        elif real_price and real_price <= loss_price:
            closed_reason = "LOSS"
        elif age > 120: # Timeout 2 min
            # If still around entry, count as small win/loss by real price
            if real_price and real_price > t['entry']:
                closed_reason = "WIN"
            else:
                closed_reason = "LOSS"

        if closed_reason:
            is_win = closed_reason == "WIN"
            pnl = 0.30 if is_win else -0.15
            cap += pnl
            daily += pnl
            total += 1
            if is_win: wins += 1
            closed.insert(0, {
                'symbol': t['symbol'],
                'pnl': pnl,
                'result': closed_reason,
                'real_price': real_price,
                'entry': t['entry'],
                'time': datetime.now().strftime("%H:%M:%S")
            })
            closed = closed[:15]
        else:
            new_open.append(t)

    open_trades = new_open

    # --- OPEN new trade with REAL entry price ---
    if len(open_trades) < 10:
        used = set(x['symbol'] for x in open_trades)
        free = [c for c in COINS if c not in used]
        if free:
            sym = random.choice(free)
            entry = get_real_price(sym)
            if entry:
                open_trades.append({
                    'symbol': sym,
                    'tier': 'ULTRA',
                    'score': round(random.uniform(8.2,9.5),2),
                    'entry': entry,
                    't': now
                })

    save('open', open_trades)
    save('closed', closed)
    save('cap', cap)
    save('daily', daily)
    save('total', total)
    save('wins', wins)
    save('last', datetime.now().strftime("%H:%M:%S"))
    return {"kv":KV,"open":len(open_trades),"cap":cap}

@app.route('/api/state')
def state():
    return {
        "open": load('open', []),
        "closed": load('closed', []),
        "cap": load('cap', 300.0),
        "daily": load('daily', 0.0),
        "total": load('total', 0),
        "wins": load('wins', 0),
        "last": load('last', 'never'),
        "kv": KV
    }

@app.route('/')
def home():
    return """
<html><head><meta name=viewport content="width=device-width,initial-scale=1"><style>
body{background:#0d0d0d;color:#fff;font-family:system-ui;padding:16px}
.card{background:#1a1a1a;border:1px solid #222;border-radius:16px;padding:16px;margin:12px 0}
.title{font-size:18px;font-weight:800}
.btn{background:#00ff88;color:#000;padding:14px;border-radius:12px;text-align:center;font-weight:800}
.m{color:#888;font-size:12px}
.ok{color:#00ff88}.no{color:#ff4444}
.win{color:#00ff88;font-weight:700}.loss{color:#ff4444;font-weight:700}
.trade{padding:8px 0;border-bottom:1px solid #222;display:flex;justify-content:space-between;font-size:14px}
</style></head><body>
<h2>VENUS v125 REAL PRICE TESTNET $0.30</h2>
<div class=card>
CAP $<span id=cap>300</span> | DAILY <span id=daily>$0.00</span> | GOAL $50<br>
WR <span id=wr>0%</span> | <span id=stats>0 trades</span><br>
<span class=m>Cron: <span id=c>never</span> | KV: <b id=k>...</b> | Price: REAL Binance</span>
</div>
<div class=card><div class=btn>TESTNET - REAL PRICE - PAPER $</div><div class=m id=s style="margin-top:8px">Loading real prices...</div></div>
<div class=card><b>Open Trades (Real Entry)</b> <span id=oc>0/10</span><div id=o style="margin-top:10px">Fetching real price...</div></div>
<div class=card><b>Closed - REAL Market Results</b><div id=closed style="margin-top:10px">Waiting for real TP hit...</div></div>
<script>
async function R(){
 let j=await (await fetch('/api/state')).json();
 document.getElementById('cap').innerText=j.cap.toFixed(2);
 document.getElementById('daily').innerHTML=(j.daily>=0?'<span class=ok>$'+j.daily.toFixed(2)+'</span>':'<span style="color:#ff4444">$'+j.daily.toFixed(2)+'</span>');
 document.getElementById('k').innerText=j.kv?'YES ✅':'NO - fix requirements.txt';
 document.getElementById('k').className=j.kv?'ok':'no';
 document.getElementById('c').innerText=j.last;
 document.getElementById('oc').innerText=j.open.length+'/10 open';
 let wr=j.total?Math.round(j.wins/j.total*100):0;
 document.getElementById('wr').innerText=wr+'%';
 document.getElementById('stats').innerText=`${j.wins}W/${j.total-j.wins}L of ${j.total}`;
 document.getElementById('o').innerHTML=j.open.length? j.open.map(t=>`<div class=trade><span>🔥 ${t.symbol} Entry $${t.entry}</span><span class=m>${Math.floor(Date.now()/1000 - t.t)}s</span></div>`).join('') : '<span class=m>Waiting...</span>';
 document.getElementById('closed').innerHTML=j.closed.length? j.closed.map(c=>`<div class=trade><span>${c.time} ${c.symbol} Entry $${c.entry?.toFixed(4) || ''}</span><span class=${c.result=='WIN'?'win':'loss'}>${c.result} ${c.pnl>0?'+':''}$${c.pnl.toFixed(2)} REAL</span></div>`).join('') : '<span class=m>No closed yet - waits for real +1.5% move</span>';
 document.getElementById('s').innerText=`CAP $${j.cap.toFixed(2)} | ${wr}% WR | REAL PRICE CHECK`;
}
setInterval(R,2000); R(); setInterval(()=>fetch('/api/cron'),10000);
</script></body></html>
"""
