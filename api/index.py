from flask import Flask, jsonify
import json, random, time
from datetime import datetime

app = Flask(__name__)

try:
    from upstash_redis import Redis
    redis = Redis.from_env()
    def kv_get(k,d):
        v=redis.get(k)
        return json.loads(v) if v else d
    def kv_set(k,v): redis.set(k, json.dumps(v))
    USE_KV=True
except:
    D={}
    def kv_get(k,d): return D.get(k,d)
    def kv_set(k,v): D.__setitem__(k,v)
    USE_KV=False

@app.route('/api/cron')
def cron():
    o=kv_get('o',[]); cap=kv_get('c',0.0)
    o=[t for t in o if time.time()-t['at']<120]
    if len(o)<10:
        o.append({'symbol':random.choice(['BONKUSDT','FLOKIUSDT','MEMEUSDT']),'tier':'ULTRA','score':round(random.uniform(6,9),2),'conf':85,'at':time.time()})
    kv_set('o',o); kv_set('c',cap); kv_set('last',datetime.now().isoformat())
    return jsonify({'ok':True,'kv':USE_KV,'open':len(o),'trades':o})

@app.route('/api/state')
def state():
    return jsonify({'open':kv_get('o',[]),'cap':kv_get('c',0.0),'last':kv_get('last','never'),'kv':USE_KV})

@app.route('/')
def home():
    html=open('public/index.html').read() if __name__!='__main__' else 'VENUS v123'
    try:
        with open('../public/index.html') as f: html=f.read()
    except:
        try:
            with open('public/index.html') as f: html=f.read()
        except:
            html='<h1>VENUS v123 BEST</h1><div id=open></div><script>setInterval(async()=>{let s=await (await fetch("/api/state")).json(); document.getElementById("open").innerText=JSON.stringify(s.open)},2000)</script>'
    return html
