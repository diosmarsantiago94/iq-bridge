# iq_bridge.py - Servidor puente para IQ Option v2.0
# Con conexión persistente, auto-reconnect y heartbeat

from flask import Flask, request, jsonify
from flask_cors import CORS
from iqoptionapi.stable_api import IQ_Option
import threading
import time

app = Flask(__name__)
CORS(app)

# Conexión global persistente
iq_connection = None
iq_lock = threading.Lock()
iq_credentials = {"email": None, "password": None}
last_activity = time.time()

def ensure_connection(email, password):
    global iq_connection, iq_credentials, last_activity
    
    with iq_lock:
        last_activity = time.time()
        
        if iq_credentials["email"] != email:
            iq_connection = None
        
        if iq_connection is not None:
            if iq_connection.check_connect():
                return iq_connection, None
            else:
                print("[IQ] Conexión perdida, reconectando...")
                iq_connection = None
        
        print(f"[IQ] Conectando como {email}...")
        iq = IQ_Option(email, password)
        check, reason = iq.connect()
        
        if check:
            iq_connection = iq
            iq_credentials = {"email": email, "password": password}
            print("[IQ] Conectado exitosamente")
            return iq, None
        else:
            return None, reason

def heartbeat_thread():
    global iq_connection, iq_credentials, last_activity
    while True:
        time.sleep(30)
        with iq_lock:
            if iq_connection is not None:
                if time.time() - last_activity > 600:
                    iq_connection = None
                    continue
                if not iq_connection.check_connect():
                    try:
                        iq = IQ_Option(iq_credentials["email"], iq_credentials["password"])
                        check, _ = iq.connect()
                        if check:
                            iq_connection = iq
                    except:
                        pass

heartbeat = threading.Thread(target=heartbeat_thread, daemon=True)
heartbeat.start()

@app.route('/health', methods=['GET'])
def health():
    connected = iq_connection.check_connect() if iq_connection else False
    return jsonify({"status": "ok", "connected": connected})

@app.route('/connect', methods=['POST'])
def connect():
    data = request.json
    iq, error = ensure_connection(data.get('email'), data.get('password'))
    if not iq:
        return jsonify({"success": False, "error": error})
    
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

@app.route('/trade', methods=['POST'])
def execute_trade():
    data = request.json
    iq, error = ensure_connection(data.get('email'), data.get('password'))
    if not iq:
        return jsonify({"success": False, "error": error})
    
    with iq_lock:
        iq.change_balance(data.get('mode', 'PRACTICE'))
        check, trade_id = iq.buy(
            data.get('amount', 1),
            data.get('asset', 'EURUSD'),
            data.get('direction', 'call'),
            data.get('duration', 1)
        )
        
        if check:
            return jsonify({"success": True, "trade_id": trade_id})
        return jsonify({"success": False, "error": str(trade_id)})

@app.route('/check_trade/<int:trade_id>', methods=['POST'])
def check_trade(trade_id):
    data = request.json
    iq, error = ensure_connection(data.get('email'), data.get('password'))
    if not iq:
        return jsonify({"success": False, "error": error})
    
    try:
        result = iq.check_win_v3(trade_id)
        if result is not None:
            profit = float(result)
            return jsonify({
                "success": True,
                "status": "closed",
                "profit": profit,
                "result": "win" if profit > 0 else "tie" if profit == 0 else "loss"
            })
    except:
        pass
    
    return jsonify({"success": True, "status": "open", "profit": 0})

@app.route('/assets', methods=['POST'])
def get_assets():
    data = request.json
    iq, error = ensure_connection(data.get('email'), data.get('password'))
    if not iq:
        return jsonify({"success": False, "error": error})
    
    all_assets = iq.get_all_open_time()
    open_assets = []
    seen = set()
    
    for opt_type in ['turbo', 'binary']:
        for name, info in all_assets.get(opt_type, {}).items():
            if info.get('open') and name not in seen:
                seen.add(name)
                open_assets.append({"name": name, "type": opt_type})
    
    return jsonify({"success": True, "assets": open_assets})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)
