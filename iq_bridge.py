# iq_bridge.py - Servidor puente para IQ Option
# Despliega en Railway, Render, Heroku o cualquier VPS

from flask import Flask, request, jsonify
from flask_cors import CORS
from iqoptionapi.stable_api import IQ_Option
import threading
import time

app = Flask(__name__)
CORS(app)

# Cache de conexiones activas
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
        
        # Get balances
        demo_balance = iq.get_balance()
        iq.change_balance("REAL")
        real_balance = iq.get_balance()
        iq.change_balance("PRACTICE")
        
        profile = iq.get_profile_ansy498456464()
        
        return jsonify({
            "success": True,
            "connected": True,
            "balance_demo": demo_balance,
            "balance_real": real_balance,
            "currency": profile.get("currency", "USD") if profile else "USD",
            "name": profile.get("name", "") if profile else "",
            "user_id": profile.get("user_id", "") if profile else ""
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/balance', methods=['POST'])
def get_balance():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    mode = data.get('mode', 'PRACTICE')
    
    try:
        iq, error = get_connection(email, password)
        if not iq:
            return jsonify({"success": False, "error": error})
        
        iq.change_balance(mode)
        balance = iq.get_balance()
        
        return jsonify({
            "success": True,
            "balance": balance,
            "mode": mode
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
            
            # Check if asset is open
            all_assets = iq.get_all_open_time()
            asset_open = False
            
            # Check binary and turbo options
            for option_type in ['binary', 'turbo']:
                if asset in all_assets.get(option_type, {}):
                    if all_assets[option_type][asset].get('open'):
                        asset_open = True
                        break
            
            if not asset_open:
                return jsonify({"success": False, "error": f"Asset {asset} no está disponible"})
            
            # Execute trade
            check, trade_id = iq.buy(amount, asset, direction, duration)
            
            if check:
                return jsonify({
                    "success": True,
                    "trade_id": trade_id,
                    "asset": asset,
                    "direction": direction,
                    "amount": amount,
                    "duration": duration,
                    "mode": mode
                })
            else:
                return jsonify({"success": False, "error": "No se pudo ejecutar la operación", "details": trade_id})
                
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
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    try:
        iq, error = get_connection(email, password)
        if not iq:
            return jsonify({"success": False, "error": error})
        
        all_assets = iq.get_all_open_time()
        
        open_assets = []
        for option_type in ['binary', 'turbo']:
            for asset_name, asset_data in all_assets.get(option_type, {}).items():
                if asset_data.get('open'):
                    open_assets.append({
                        "name": asset_name,
                        "type": option_type
                    })
        
        return jsonify({
            "success": True,
            "assets": open_assets
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
