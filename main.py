#!/usr/bin/env python3
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import sqlite3
import os
import urllib.parse
import urllib.request
import re
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, 'data', 'watchos.db')
DB_PATH = os.environ.get('WATCHOS_DB_PATH', DEFAULT_DB_PATH)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

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

        elif path == '/api/ebay-auto-list':
            # eBay認証情報をDBから取得
            conn = get_db()
            rows = conn.execute('SELECT * FROM settings').fetchall()
            conn.close()
            db_settings = {row['key']: json.loads(row['value']) for row in rows}
            ebay = db_settings.get('ebay', {})

            app_id   = ebay.get('appId', '')
            dev_id   = ebay.get('devId', '')
            cert_id  = ebay.get('certId', '')
            auth_token = ebay.get('authToken', '')

            if not all([app_id, dev_id, cert_id, auth_token]):
                self.send_json({'error': 'eBay認証情報（DEV ID・CERT ID・Auth Token）が設定されていません'}, 400)
                return

            title               = body.get('title', '')
            description         = body.get('description', '')
            price_usd           = float(body.get('price_usd', 0))
            brand               = body.get('brand', 'Unbranded')
            shipping_profile_id = body.get('shipping_profile_id', ebay.get('shipProfileId', ''))
            return_profile_id   = body.get('return_profile_id',  ebay.get('returnProfileId', ''))
            payment_profile_id  = body.get('payment_profile_id', ebay.get('paymentProfileId', ''))
            category_id         = body.get('category_id', ebay.get('category', '281'))

            xml_payload = f'''<?xml version="1.0" encoding="utf-8"?>
<AddFixedPriceItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials><eBayAuthToken>{auth_token}</eBayAuthToken></RequesterCredentials>
  <Item>
    <Title><![CDATA[{title}]]></Title>
    <Description><![CDATA[{description}]]></Description>
    <PrimaryCategory><CategoryID>{category_id}</CategoryID></PrimaryCategory>
    <StartPrice>{price_usd:.2f}</StartPrice>
    <ConditionID>3000</ConditionID>
    <Country>JP</Country>
    <Currency>USD</Currency>
    <DispatchTimeMax>3</DispatchTimeMax>
    <ListingDuration>GTC</ListingDuration>
    <ListingType>FixedPriceItem</ListingType>
    <Location><![CDATA[Tokyo, Japan]]></Location>
    <Quantity>1</Quantity>
    <ItemSpecifics>
      <NameValueList><Name>Brand</Name><Value><![CDATA[{brand}]]></Value></NameValueList>
      <NameValueList><Name>Department</Name><Value>Men</Value></NameValueList>
      <NameValueList><Name>Type</Name><Value>Wristwatch</Value></NameValueList>
      <NameValueList><Name>UPC</Name><Value>Does not apply</Value></NameValueList>
    </ItemSpecifics>
    <SellerProfiles>
      <SellerShippingProfile><ShippingProfileID>{shipping_profile_id}</ShippingProfileID></SellerShippingProfile>
      <SellerReturnProfile><ReturnProfileID>{return_profile_id}</ReturnProfileID></SellerReturnProfile>
      <SellerPaymentProfile><PaymentProfileID>{payment_profile_id}</PaymentProfileID></SellerPaymentProfile>
    </SellerProfiles>
  </Item>
</AddFixedPriceItemRequest>'''

            headers = {
                'Content-Type': 'text/xml',
                'X-EBAY-API-COMPATIBILITY-LEVEL': '967',
                'X-EBAY-API-DEV-NAME': dev_id,
                'X-EBAY-API-APP-NAME': app_id,
                'X-EBAY-API-CERT-NAME': cert_id,
                'X-EBAY-API-SITEID': '0',
                'X-EBAY-API-CALL-NAME': 'AddFixedPriceItem'
            }
            if auth_token.startswith('v^'):
                headers['X-EBAY-API-IAF-TOKEN'] = auth_token

            try:
                req = urllib.request.Request(
                    'https://api.ebay.com/ws/api.dll',
                    data=xml_payload.encode('utf-8'),
                    headers=headers
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    response_text = resp.read().decode('utf-8')
            except Exception as e:
                self.send_json({'error': f'eBay API接続エラー: {str(e)}'}, 500)
                return

            if '<Ack>Success</Ack>' in response_text or '<Ack>Warning</Ack>' in response_text:
                m = re.search(r'<ItemID>(.*?)</ItemID>', response_text)
                item_id = m.group(1) if m else ''
                self.send_json({'item_id': item_id, 'status': 'success'})
            else:
                m = re.search(r'<LongMessage>(.*?)</LongMessage>', response_text)
                error_msg = m.group(1) if m else '不明なエラー'
                self.send_json({'error': error_msg}, 400)

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
    print('WatchOS API Server starting on port 8000...')
    server = HTTPServer(('0.0.0.0', 8000), Handler)
    server.serve_forever()
