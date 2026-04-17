# 🚀 دليل نشر وتشغيل منصة CryptoAnalyzer على cPanel

## معلومات السيرفر
- **الدومين:** `mk.drpc.sa`
- **المستخدم:** `drpcsa`
- **مسار المشروع:** `/home/drpcsa/repositories/my-project`
- **بورت الفرونت إند:** `33441`
- **بورت الباك إند:** `33442`
- **بايثون:** `/opt/alt/python311/bin/python3`

---

## الخطوة 1️⃣: سحب آخر التحديثات من GitHub

```bash
cd /home/drpcsa/repositories/my-project
git pull origin main
```

---

## الخطوة 2️⃣: تشغيل الباك إند (Python/FastAPI)

```bash
cd /home/drpcsa/repositories/my-project/backend

# إنشاء بيئة بايثون (مرة واحدة فقط، إذا لم تكن موجودة)
/opt/alt/python311/bin/python3 -m venv venv311

# تفعيل البيئة
source venv311/bin/activate

# تثبيت المكتبات (مرة واحدة فقط، أو عند إضافة مكتبة جديدة)
pip install --upgrade pip
pip install fastapi sqlalchemy[asyncio] aiosqlite python-jose[cryptography] bcrypt cryptography httpx pandas numpy aiosmtplib apscheduler pydantic[email] pydantic-settings python-multipart a2wsgi uvicorn[standard]

# إنشاء سكربت التشغيل
cat << 'EOF' > start-backend.sh
#!/bin/bash
cd /home/drpcsa/repositories/my-project/backend
source venv311/bin/activate
exec python -m uvicorn app.main:app --host 127.0.0.1 --port 33442
EOF
chmod +x start-backend.sh

# تشغيل الباك إند عبر PM2
pm2 start ./start-backend.sh --name "CryptoBackend"
```

---

## الخطوة 3️⃣: بناء وتشغيل الفرونت إند (Next.js)

```bash
cd /home/drpcsa/repositories/my-project/frontend

# تثبيت المكتبات (مرة واحدة فقط، أو عند إضافة مكتبة جديدة)
npm config set legacy-peer-deps true
npm install

# ضبط رابط الـ API
echo 'NEXT_PUBLIC_API_URL=https://mk.drpc.sa' > .env.local

# بناء المشروع
npm run build

# إنشاء سكربت التشغيل
cat << 'EOF' > start-frontend.sh
#!/bin/bash
cd /home/drpcsa/repositories/my-project/frontend
export PORT=33441
export NODE_ENV=production
exec node_modules/.bin/next start -p 33441
EOF
chmod +x start-frontend.sh

# تشغيل الفرونت إند عبر PM2
pm2 start ./start-frontend.sh --name "CryptoPlatform"
```

---

## الخطوة 4️⃣: إعداد ملف .htaccess

```bash
cat << 'EOF' > /home/drpcsa/public_html/repositories/my-project/.htaccess
DirectoryIndex disabled
RewriteEngine On

# للـ WebSocket المباشر
RewriteCond %{HTTP:Upgrade} websocket [NC]
RewriteCond %{HTTP:Connection} upgrade [NC]
RewriteRule ^(.*)$ ws://127.0.0.1:33442/$1 [P,L]

# للباك إند (API)
RewriteCond %{REQUEST_URI}  ^/api/ [OR]
RewriteCond %{REQUEST_URI}  ^/ws/
RewriteRule ^(.*)$ http://127.0.0.1:33442/$1 [P,L]

# للفرونت إند (Next.js)
RewriteCond %{REQUEST_URI} !^/api/
RewriteCond %{REQUEST_URI} !^/ws/
RewriteRule ^(.*)$ http://127.0.0.1:33441/$1 [P,L]
EOF
```

---

## الخطوة 5️⃣: حفظ العمليات وتفعيل التشغيل التلقائي

```bash
pm2 save
pm2 startup
```

---

## 🔧 أوامر الصيانة المفيدة

### التحقق من حالة العمليات
```bash
pm2 status
```

### عرض سجلات الأخطاء
```bash
pm2 logs CryptoPlatform --lines 30    # سجلات الفرونت إند
pm2 logs CryptoBackend --lines 30     # سجلات الباك إند
```

### إعادة تشغيل الخدمات
```bash
pm2 restart CryptoPlatform    # إعادة تشغيل الفرونت إند
pm2 restart CryptoBackend     # إعادة تشغيل الباك إند
pm2 restart all               # إعادة تشغيل الكل
```

### إيقاف الخدمات
```bash
pm2 stop all       # إيقاف مؤقت
pm2 delete all     # حذف العمليات
```

### التحقق من عمل الخدمات
```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:33441/login    # الفرونت: يجب يرجع 200
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:33442/api/health  # الباك إند: يجب يرجع 200
```

---

## 👤 إنشاء/تحديث حساب أدمن

```bash
cd /home/drpcsa/repositories/my-project/backend
sqlite3 crypto_analyzer.db 'INSERT INTO users (id, username, email, password_hash, role, is_active, created_at, updated_at) VALUES (lower(hex(randomblob(16))), "hu_bokheder", "hu.bokheder@gmail.com", "$2b$12$KUvmXeIm6F5YDWgV6dJI.ufnTyFaO490QTzcl.4p59yy2riMfjKZ6", "admin", 1, datetime("now"), datetime("now"));'
```
- **الإيميل:** `hu.bokheder@gmail.com`
- **الباسوورد:** `Hum@12341234`

---

## ⚠️ ملاحظات مهمة

1. **ملف `.env`**: يجب إنشاء ملف `.env` في مجلد `backend` يحتوي على مفاتيح API الخاصة (Binance وغيرها). هذا الملف لا يتم رفعه لـ GitHub لأسباب أمنية.
2. **ملف `.env.local`**: يجب أن يكون موجوداً في مجلد `frontend` ويحتوي على `NEXT_PUBLIC_API_URL=https://mk.drpc.sa`.
3. **قاعدة البيانات**: ملف `crypto_analyzer.db` يتم إنشاؤه تلقائياً عند أول تشغيل للباك إند.
4. **الأمان**: غيّر `JWT_SECRET_KEY` و `ENCRYPTION_KEY` في ملف `.env` قبل الإطلاق الرسمي.
