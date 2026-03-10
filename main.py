#!/usr/bin/env python3
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import sqlite3
import os
import urllib.parse
from datetime import datetime

DB_PATH = '/var/www/watchos/watchos.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        watch_id TEXT,
        brand TEXT,
        model TEXT,
        condition TEXT,
        mercari_url TEXT,
        listing_date TEXT,
        purchase_price REAL DEFAULT 0,
        shipping_cost REAL DEFAULT 0,
        shipping_method TEXT,
        other_cost REAL DEFAULT 0,
        destination TEXT,
        status TEXT DEFAULT '未出品',
        sales_url TEXT,
        sold_date TEXT,
        selling_price REAL DEFAULT 0,
        days_to_sell INTEGER,
        profit REAL DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_cors_headers()
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == '/api/health':
            self.send_json({'status': 'ok', 'timestamp': datetime.now().isoformat()})

        elif path == '/api/inventory':
            conn = get_db()
            rows = conn.execute('SELECT * FROM inventory ORDER BY id DESC').fetchall()
            conn.close()
            self.send_json([dict(row) for row in rows])

        elif path.startswith('/api/inventory/'):
            item_id = path.split('/')[-1]
            conn = get_db()
            row = conn.execute('SELECT * FROM inventory WHERE id = ?', (item_id,)).fetchone()
            conn.close()
            if row:
                self.send_json(dict(row))
            else:
                self.send_json({'error': 'Not found'}, 404)

        elif path == '/api/settings':
            conn = get_db()
            rows = conn.execute('SELECT * FROM settings').fetchall()
            conn.close()
            settings = {row['key']: json.loads(row['value']) for row in rows}
            self.send_json(settings)

        else:
            self.send_json({'error': 'Not found'}, 404)

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length).decode('utf-8')) if length else {}
        path = urllib.parse.urlparse(self.path).path

        if path == '/api/inventory':
            conn = get_db()
            c = conn.cursor()
            c.execute('''INSERT INTO inventory 
                (watch_id, brand, model, condition, mercari_url, listing_date,
                 purchase_price, shipping_cost, shipping_method, other_cost,
                 destination, status, sales_url, sold_date, selling_price,
                 days_to_sell, profit)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (body.get('watch_id'), body.get('brand'), body.get('model'),
                 body.get('condition'), body.get('mercari_url'), body.get('listing_date'),
                 body.get('purchase_price', 0), body.get('shipping_cost', 0),
                 body.get('shipping_method'), body.get('other_cost', 0),
                 body.get('destination'), body.get('status', '未出品'),
                 body.get('sales_url'), body.get('sold_date'),
                 body.get('selling_price', 0), body.get('days_to_sell'),
                 body.get('profit', 0)))
            new_id = c.lastrowid
            conn.commit()
            row = conn.execute('SELECT * FROM inventory WHERE id = ?', (new_id,)).fetchone()
            conn.close()
            self.send_json(dict(row), 201)

        elif path == '/api/settings':
            conn = get_db()
            for key, value in body.items():
                conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
                           (key, json.dumps(value)))
            conn.commit()
            conn.close()
            self.send_json({'status': 'saved'})

        else:
            self.send_json({'error': 'Not found'}, 404)

    def do_PUT(self):
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length).decode('utf-8')) if length else {}
        path = urllib.parse.urlparse(self.path).path

        if path.startswith('/api/inventory/'):
            item_id = path.split('/')[-1]
            conn = get_db()
            conn.execute('''UPDATE inventory SET
                watch_id=?, brand=?, model=?, condition=?, mercari_url=?,
                listing_date=?, purchase_price=?, shipping_cost=?, shipping_method=?,
                other_cost=?, destination=?, status=?, sales_url=?, sold_date=?,
                selling_price=?, days_to_sell=?, profit=?,
                updated_at=CURRENT_TIMESTAMP
                WHERE id=?''',
                (body.get('watch_id'), body.get('brand'), body.get('model'),
                 body.get('condition'), body.get('mercari_url'), body.get('listing_date'),
                 body.get('purchase_price', 0), body.get('shipping_cost', 0),
                 body.get('shipping_method'), body.get('other_cost', 0),
                 body.get('destination'), body.get('status'),
                 body.get('sales_url'), body.get('sold_date'),
                 body.get('selling_price', 0), body.get('days_to_sell'),
                 body.get('profit', 0), item_id))
            conn.commit()
            row = conn.execute('SELECT * FROM inventory WHERE id = ?', (item_id,)).fetchone()
            conn.close()
            self.send_json(dict(row) if row else {'error': 'Not found'})

        else:
            self.send_json({'error': 'Not found'}, 404)

    def do_DELETE(self):
        path = urllib.parse.urlparse(self.path).path

        if path.startswith('/api/inventory/'):
            item_id = path.split('/')[-1]
            conn = get_db()
            conn.execute('DELETE FROM inventory WHERE id = ?', (item_id,))
            conn.commit()
            conn.close()
            self.send_json({'status': 'deleted'})

        else:
            self.send_json({'error': 'Not found'}, 404)

if __name__ == '__main__':
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    init_db()
    print('🚀 WatchOS API Server starting on port 8000...')
    server = HTTPServer(('0.0.0.0', 8000), Handler)
    server.serve_forever()
