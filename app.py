# app.py - Servidor puente para IQ Option
from flask import Flask, request, jsonify
from flask_cors import CORS
from iqoptionapi.stable_api import IQ_Option
import threading

app = Flask(__name__)
CORS(app)

connections = {}
connection_locks = {}

def get_connection(email, password):
    key = email
    if key not in connections or not connections[key].check_connect():
        iq = IQ_Option(email, password)
        check, reason = iq.connect()
        if check:
            connections[key] = iq
            connection_locks[key] = threading.Lock()
        else:
            return None, reason
    return connections[key], None

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "service": "iq-bridge"})

@app.route('/connect', methods=['POST'])
def connect():
    data = request.json or {}
    email = data.get('email', '')
    password = data.get('password', '')
    
    if not email or not password:
        return jsonify({"success": False, "error": "Credenciales requeridas", "connected": False})
    
    try:
        iq, error = get_connection(email, password)
        if not iq:
            return jsonify({"success": False, "error": error or "No se pudo conectar", "connected": False})
        
        demo_balance = iq.get_balance()
        iq.change_balance("REAL")
        real_balance = iq.get_balance()
        iq.change_balance("PRACTICE")
        
        return jsonify({
            "success": True,
            "connected": True,
            "balance_demo": demo_balance,
            "balance_real": real_balance,
            "currency": "USD"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "connected": False})

@app.route('/balance', methods=['POST'])
def get_balance():
    data = request.json or {}
    email = data.get('email', '')
    password = data.get('password', '')
    mode = data.get('mode', 'PRACTICE')
    
    try:
        iq, error = get_connection(email, password)
        if not iq:
            return jsonify({"success": False, "error": error})
        
        iq.change_balance(mode)
        balance = iq.get_balance()
        
        return jsonify({"success": True, "balance": balance, "mode": mode})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/trade', methods=['POST'])
def execute_trade():
    data = request.json or {}
    email = data.get('email', '')
    password = data.get('password', '')
    asset = data.get('asset', 'EURUSD')
    direction = data.get('direction', 'call')
    amount = data.get('amount', 1)
    duration = data.get('duration', 1)
    mode = data.get('mode', 'PRACTICE')
    
    try:
        iq, error = get_connection(email, password)
        if not iq:
            return jsonify({"success": False, "error": error})
        
        with connection_locks.get(email, threading.Lock()):
            iq.change_balance(mode)
            check, trade_id = iq.buy(amount, asset, direction, duration)
            
            if check:
                return jsonify({
                    "success": True,
                    "trade_id": trade_id,
                    "asset": asset,
                    "direction": direction,
                    "amount": amount
                })
            else:
                return jsonify({"success": False, "error": "No se pudo ejecutar", "details": trade_id})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/check_trade/<int:trade_id>', methods=['POST'])
def check_trade(trade_id):
    data = request.json or {}
    email = data.get('email', '')
    password = data.get('password', '')
    
    try:
        iq, error = get_connection(email, password)
        if not iq:
            return jsonify({"success": False, "error": error})
        
        result = iq.check_win_v4(trade_id)
        return jsonify({
            "success": True,
            "trade_id": trade_id,
            "profit": result if result else 0,
            "result": "win" if result and result > 0 else "loss" if result is not None else "pending"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/assets', methods=['POST'])
def get_assets():
    data = request.json or {}
    email = data.get('email', '')
    password = data.get('password', '')
    
    try:
        iq, error = get_connection(email, password)
        if not iq:
            return jsonify({"success": False, "error": error})
        
        all_assets = iq.get_all_open_time()
        profit_data = iq.get_all_profit()
        
        open_assets = []
        for option_type in ['binary', 'turbo']:
            for asset_name, asset_data in all_assets.get(option_type, {}).items():
                if asset_data.get('open'):
                    payout = 80
                    if asset_name in profit_data:
                        payout = int(profit_data[asset_name].get(option_type, 80) * 100)
                    open_assets.append({
                        "name": asset_name,
                        "type": option_type,
                        "payout": payout
                    })
        
        return jsonify({"success": True, "assets": open_assets})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/candles', methods=['POST'])
def get_candles():
    data = request.json or {}
    email = data.get('email', '')
    password = data.get('password', '')
    asset = data.get('asset', 'EURUSD')
    timeframe = data.get('timeframe', 60)  # 60 = 1min, 300 = 5min, etc
    count = data.get('count', 50)
    
    try:
        iq, error = get_connection(email, password)
        if not iq:
            return jsonify({"success": False, "error": error})
        
        import time
        end_time = time.time()
        candles = iq.get_candles(asset, timeframe, count, end_time)
        
        return jsonify({
            "success": True,
            "candles": candles,
            "asset": asset,
            "timeframe": timeframe
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/price', methods=['POST'])
def get_price():
    data = request.json or {}
    email = data.get('email', '')
    password = data.get('password', '')
    asset = data.get('asset', 'EURUSD')
    
    try:
        iq, error = get_connection(email, password)
        if not iq:
            return jsonify({"success": False, "error": error})
        
        # Subscribe to asset and get current price
        iq.subscribe_strike_list(asset, 1)
        import time
        time.sleep(0.5)
        
        # Get realtime candle
        candles = iq.get_realtime_candles(asset, 60)
        if candles:
            latest = list(candles.values())[-1] if candles else None
            if latest:
                return jsonify({
                    "success": True,
                    "price": latest.get('close', 0),
                    "asset": asset
                })
        
        return jsonify({"success": False, "error": "No se pudo obtener precio"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
