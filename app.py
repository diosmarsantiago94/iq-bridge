# iq_bridge.py - Servidor puente para IQ Option
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
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({"success": False, "error": "Credenciales requeridas"})
    
    try:
        iq, error = get_connection(email, password)
        if not iq:
            return jsonify({"success": False, "error": error or "No se pudo conectar"})
        
        demo_balance = iq.get_balance()
        iq.change_balance("REAL")
        real_balance = iq.get_balance()
        iq.change_balance("PRACTICE")
        
        return jsonify({
            "success": True,
            "connected": True,
            "balance_demo": demo_balance,
            "balance_real": real_balance
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/trade', methods=['POST'])
def execute_trade():
    data = request.json
    email = data.get('email')
    password = data.get('password')
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
                return jsonify({"success": False, "error": "No se pudo ejecutar"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/check_trade/<int:trade_id>', methods=['POST'])
def check_trade(trade_id):
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    try:
        iq, error = get_connection(email, password)
        if not iq:
            return jsonify({"success": False, "error": error})
        
        # Fast method: check_win_v3 (instant response)
        try:
            result = iq.check_win_v3(trade_id)
            if result is not None:
                profit = float(result)
                return jsonify({
                    "success": True,
                    "trade_id": trade_id,
                    "status": "closed",
                    "profit": profit,
                    "result": "win" if profit > 0 else "tie" if profit == 0 else "loss"
                })
        except:
            pass
        
        # Fallback: get_async_order (also fast)
        try:
            order = iq.get_async_order(trade_id)
            if order and order.get("name") == "option-closed":
                msg = order.get("msg", {})
                win = float(msg.get("win_enrolled_amount", 0))
                enrolled = float(msg.get("enrolled_amount", 0))
                profit = win - enrolled
                return jsonify({
                    "success": True,
                    "trade_id": trade_id,
                    "status": "closed",
                    "profit": profit,
                    "result": "win" if profit > 0 else "tie" if profit == 0 else "loss"
                })
        except:
            pass
        
        # Still open
        return jsonify({
            "success": True,
            "trade_id": trade_id,
            "status": "open",
            "profit": 0
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/assets', methods=['POST'])
def get_assets():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    try:
        iq, error = get_connection(email, password)
        if not iq:
            return jsonify({"success": False, "error": error})
        
        all_assets = iq.get_all_open_time()
        open_assets = []
        for t in ['binary', 'turbo']:
            for name, data in all_assets.get(t, {}).items():
                if data.get('open'):
                    open_assets.append({"name": name, "type": t})
        
        return jsonify({"success": True, "assets": open_assets})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
