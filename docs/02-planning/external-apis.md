# External APIs Reference

---

## 1. Binance API

### أسعار لحظية (WebSocket)
```
WSS: wss://stream.binance.com:9443/ws/{symbol}@ticker
مثال: wss://stream.binance.com:9443/ws/btcusdt@ticker
```
**الاستجابة:** سعر آخر، أعلى/أدنى 24h، حجم التداول، نسبة التغير

### بيانات الشارت (Klines)
```
GET https://api.binance.com/api/v3/klines
Params: symbol, interval (1m,5m,1h,4h,1d), limit
```

### تنفيذ صفقة
```
POST https://api.binance.com/api/v3/order
Headers: X-MBX-APIKEY: {API_KEY}
Params: symbol, side (BUY/SELL), type (MARKET/LIMIT), quantity
توقيع: HMAC SHA256 على جميع Parameters
```

### الرصيد
```
GET https://api.binance.com/api/v3/account
Headers: X-MBX-APIKEY: {API_KEY}
توقيع: HMAC SHA256
```

### Rate Limits
- 1200 request/min (weight-based)
- WebSocket: 5 messages/sec per connection

---

## 2. Bybit API

### أسعار لحظية (WebSocket)
```
WSS: wss://stream.bybit.com/v5/public/spot
Subscribe: {"op":"subscribe","args":["tickers.BTCUSDT"]}
```

### بيانات الشارت
```
GET https://api.bybit.com/v5/market/kline
Params: category=spot, symbol, interval, limit
```

### تنفيذ صفقة
```
POST https://api.bybit.com/v5/order/create
Headers: X-BAPI-API-KEY, X-BAPI-TIMESTAMP, X-BAPI-SIGN
Body: {"category":"spot","symbol":"BTCUSDT","side":"Buy","orderType":"Market","qty":"0.01"}
```

### الرصيد
```
GET https://api.bybit.com/v5/account/wallet-balance
Params: accountType=UNIFIED
```

---

## 3. CoinGecko API (مجاني)

### أسعار متعددة
```
GET https://api.coingecko.com/api/v3/simple/price
Params: ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true
```

### Rate Limit
- 10-30 calls/min (بدون API key)

### الاستخدام
بيانات إضافية فقط — ليست المصدر الرئيسي

---

## 4. CryptoPanic API (أخبار)

### جلب أخبار موثوقة
```
GET https://cryptopanic.com/api/v1/posts/
Params: auth_token={API_KEY}&filter=important&currencies=BTC,ETH
```

### فلتر المصادر الموثوقة
```python
TRUSTED_SOURCES = [
    "CoinDesk",
    "Reuters",
    "Bloomberg",
    "The Block",
    "Decrypt",
    "CoinTelegraph"
]
```

### Rate Limit
- Free: 5 requests/min

---

## 5. Telegram Bot API

### إنشاء البوت
1. أرسل `/newbot` لـ `@BotFather` على Telegram
2. احفظ `TOKEN` في `.env`

### إرسال رسالة
```
POST https://api.telegram.org/bot{TOKEN}/sendMessage
Body: {"chat_id": "{CHAT_ID}", "text": "📊 فرصة: BUY BTCUSDT", "parse_mode": "HTML"}
```

### الحصول على Chat ID
```
GET https://api.telegram.org/bot{TOKEN}/getUpdates
```

---

## 6. SMTP (Email)

### Gmail SMTP
```
Host: smtp.gmail.com
Port: 587
TLS: مفعّل
User: your-email@gmail.com
Password: App Password (ليس كلمة المرور العادية)
```

### Python Usage
```python
import smtplib
from email.mime.text import MIMEText

msg = MIMEText(body, 'html')
msg['Subject'] = subject
msg['From'] = SMTP_FROM
msg['To'] = recipient

with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
    server.starttls()
    server.login(SMTP_USER, SMTP_PASSWORD)
    server.send_message(msg)
```

---

## ⚠️ أمان المفاتيح

- **كل المفاتيح** تُحفظ في `.env` فقط
- `.env` مضاف في `.gitignore` — لا يُرفع أبداً على GitHub
- API keys المستخدمين تُشفّر بـ **AES-256** قبل حفظها في قاعدة البيانات
- استخدم **Read-only API keys** عند الإمكان (بدون صلاحية سحب)
