"""
Vest API - 美股交易记录系统
"""

import sqlite3
import json
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

DB_PATH = "/root/.openclaw/workspace/vest/db/vest.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def parse_symbol(text):
    """从文本中提取股票代码"""
    import re
    # 匹配 $NVDA 或 NVDA 格式
    match = re.search(r'\$?([A-Z]{1,5})\b', text.upper())
    return match.group(1) if match else None

def parse_price(text):
    """从文本中提取价格数字"""
    import re
    match = re.search(r'(\d+(?:\.\d+)?)', text)
    return float(match.group(1)) if match else None

# API Handlers

def handle_trades_create(data):
    """创建交易计划"""
    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT INTO trades (symbol, side, status, plan_buy_logic, target_price, stop_loss)
                 VALUES (?, ?, 'PLANNING', ?, ?, ?)''',
              (data.get('symbol'), data.get('side', 'LONG'), 
               data.get('plan_buy_logic'), data.get('target_price'), data.get('stop_loss')))
    trade_id = c.lastrowid
    conn.commit()
    conn.close()
    return {"status": "ok", "trade_id": trade_id}

def handle_trades_list(data):
    """列出交易"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM trades ORDER BY created_at DESC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return {"trades": rows}

def handle_trades_execute(data):
    """执行交易（入场）"""
    conn = get_db()
    c = conn.cursor()
    trade_id = data.get('trade_id')
    c.execute('''UPDATE trades SET 
                 status='OPEN', entry_price=?, quantity=?, entry_at=datetime('now')
                 WHERE id=?''', (data.get('entry_price'), data.get('quantity'), trade_id))
    conn.commit()
    conn.close()
    return {"status": "ok"}

def handle_trades_close(data):
    """平仓"""
    conn = get_db()
    c = conn.cursor()
    trade_id = data.get('trade_id')
    
    # 获取交易信息
    c.execute("SELECT entry_price, quantity FROM trades WHERE id=?", (trade_id,))
    row = c.fetchone()
    if row:
        entry_price = row['entry_price']
        quantity = row['quantity']
        exit_price = data.get('exit_price')
        
        # 计算盈亏
        net_pnl = (exit_price - entry_price) * quantity
        pnl_ratio = (exit_price - entry_price) / entry_price * 100
        
        c.execute('''UPDATE trades SET 
                     status='CLOSED', exit_price=?, exit_at=datetime('now'),
                     net_pnl=?, pnl_ratio=? WHERE id=?''',
                  (exit_price, net_pnl, pnl_ratio, trade_id))
    conn.commit()
    conn.close()
    return {"status": "ok"}

def handle_journals_create(data):
    """创建复盘"""
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT INTO journals (trade_id, content, tags) VALUES (?, ?, ?)',
              (data.get('trade_id'), data.get('content'), data.get('tags')))
    journal_id = c.lastrowid
    conn.commit()
    conn.close()
    return {"status": "ok", "journal_id": journal_id}

def handle_stats(data):
    """统计"""
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT symbol, COUNT(*) as total, 
                 SUM(CASE WHEN status='CLOSED' THEN net_pnl ELSE 0 END) as total_pnl,
                 SUM(CASE WHEN status='OPEN' THEN 1 ELSE 0 END) as open_pos
                 FROM trades GROUP BY symbol''')
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return {"stats": rows}

class VestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path == '/api/trades':
            result = handle_trades_list({})
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        elif path == '/api/stats':
            result = handle_stats({})
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode()
        data = json.loads(body)
        
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path == '/api/trades':
            result = handle_trades_create(data)
        elif path == '/api/trades/execute':
            result = handle_trades_execute(data)
        elif path == '/api/trades/close':
            result = handle_trades_close(data)
        elif path == '/api/journals':
            result = handle_journals_create(data)
        else:
            result = {"error": "not found"}
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())

    def log_message(self, format, *args):
        pass  # 静默日志

def run_server(port=8765):
    server = HTTPServer(('', port), VestHandler)
    print(f"🚀 Vest API 运行在 http://localhost:{port}")
    server.serve_forever()

if __name__ == '__main__':
    run_server()