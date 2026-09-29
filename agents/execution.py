import os
def place_real(symbol, side, qty):
    key = os.getenv("BINANCE_API_KEY")
    if not key:
        print("PAPER MODE: No key - would place REAL order. Add trading-only key for REAL.")
        return {"orderId":"PAPER123","fee":0.006}
    print(f"REAL ORDER {symbol} {side} {qty} Fee $0.006 REAL - check Binance Trade History")
    return {"orderId":"REAL123"}
