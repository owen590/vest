"""
Vest API - 美股交易记录系统 (支持交易逻辑和复盘)
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

class VestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        conn = get_db()
        c = conn.cursor()
        
        if path == '/api/trades':
            c.execute("SELECT * FROM trades ORDER BY created_at DESC")
            rows = [dict(r) for r in c.fetchall()]
            conn.close()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'trades': rows}).encode())
            
        elif path == '/api/stats':
            c.execute('''SELECT symbol, COUNT(*) as total, 
                         SUM(CASE WHEN status='CLOSED' THEN net_pnl ELSE 0 END) as total_pnl,
                         SUM(CASE WHEN status='OPEN' THEN 1 ELSE 0 END) as open_pos
                         FROM trades GROUP BY symbol''')
            rows = [dict(r) for r in c.fetchall()]
            conn.close()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'stats': rows}).encode())
            
        elif path == '/api/journals':
            trade_id = parse_qs(parsed.query).get('trade_id')
            if trade_id:
                c.execute("SELECT * FROM journals WHERE trade_id=? ORDER BY created_at DESC", (trade_id[0],))
            else:
                c.execute("SELECT * FROM journals ORDER BY created_at DESC")
            rows = [dict(r) for r in c.fetchall()]
            conn.close()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'journals': rows}).encode())
        else:
            conn.close()
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode()
        data = json.loads(body) if body else {}
        
        conn = get_db()
        c = conn.cursor()
        
        if path == '/api/trades':
            c.execute('''INSERT INTO trades (symbol, side, status, plan_buy_logic, target_price, stop_loss, entry_price, quantity, entry_at, exit_price, exit_at, net_pnl, pnl_ratio)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, datetime('now'), ?, ?)''',
                      (data.get('symbol'), data.get('side', 'LONG'), data.get('status', 'PLANNING'),
                       data.get('plan_buy_logic'), data.get('target_price'), data.get('stop_loss'),
                       data.get('entry_price'), data.get('quantity'),
                       data.get('exit_price'),
                       data.get('net_pnl'), data.get('pnl_ratio')))
            trade_id = c.lastrowid
            
            # 如果是平仓状态，自动添加复盘记录
            if data.get('status') == 'CLOSED' and data.get('journal_content'):
                c.execute('INSERT INTO journals (trade_id, content, tags) VALUES (?, ?, ?)',
                          (trade_id, data.get('journal_content'), data.get('tags', '')))
            
            result = {'status': 'ok', 'trade_id': trade_id}
            
        elif path == '/api/journals':
            c.execute('INSERT INTO journals (trade_id, content, tags) VALUES (?, ?, ?)',
                      (data.get('trade_id'), data.get('content'), data.get('tags', '')))
            journal_id = c.lastrowid
            result = {'status': 'ok', 'journal_id': journal_id}
            
        elif path.startswith('/api/trades/') and path.endswith('/journal'):
            # 添加复盘
            trade_id = path.split('/')[-2]
            c.execute('INSERT INTO journals (trade_id, content, tags) VALUES (?, ?, ?)',
                      (trade_id, data.get('content'), data.get('tags', '')))
            journal_id = c.lastrowid
            result = {'status': 'ok', 'journal_id': journal_id}
        else:
            result = {'error': 'not found'}
        
        conn.commit()
        conn.close()
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())

    def do_PUT(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path.startswith('/api/trades/'):
            trade_id = path.split('/')[-1]
            
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode()
            data = json.loads(body) if body else {}
            
            conn = get_db()
            c = conn.cursor()
            
            # 计算盈亏
            net_pnl = None
            pnl_ratio = None
            if data.get('exit_price') and data.get('entry_price') and data.get('quantity'):
                net_pnl = (data.get('exit_price') - data.get('entry_price')) * data.get('quantity')
                pnl_ratio = (data.get('exit_price') - data.get('entry_price')) / data.get('entry_price') * 100
            
            c.execute('''UPDATE trades SET 
                         symbol=?, side=?, status=?, plan_buy_logic=?, target_price=?, stop_loss=?,
                         entry_price=?, quantity=?, exit_price=?, net_pnl=?, pnl_ratio=?,
                         updated_at=datetime('now') WHERE id=?''',
                      (data.get('symbol'), data.get('side'), data.get('status'),
                       data.get('plan_buy_logic'), data.get('target_price'), data.get('stop_loss'),
                       data.get('entry_price'), data.get('quantity'), data.get('exit_price'),
                       net_pnl, pnl_ratio, trade_id))
            
            # 如果有复盘内容，添加复盘记录
            if data.get('journal_content'):
                c.execute('INSERT INTO journals (trade_id, content, tags) VALUES (?, ?, ?)',
                          (trade_id, data.get('journal_content'), data.get('tags', '')))
            
            conn.commit()
            conn.close()
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok'}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path.startswith('/api/trades/'):
            trade_id = path.split('/')[-1]
            
            conn = get_db()
            c = conn.cursor()
            c.execute('DELETE FROM journals WHERE trade_id=?', (trade_id,))
            c.execute('DELETE FROM trades WHERE id=?', (trade_id,))
            conn.commit()
            conn.close()
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok'}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass

def run_server(port=8765):
    server = HTTPServer(('', port), VestHandler)
    print(f"🚀 Vest API 运行在 http://localhost:{port}")
    server.serve_forever()

if __name__ == '__main__':
    run_server()