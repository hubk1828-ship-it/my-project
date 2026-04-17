# CryptoAnalyzer — منصة تحليل وتداول العملات الرقمية

منصة ويب داخلية متخصصة في تحليل أسواق العملات الرقمية بمنهجية محايدة وواقعية.

## المبادئ الأساسية
- تعتمد **حصرياً** على بيانات السوق الفعلية واللحظية
- تتجاهل كلياً الشائعات ووسائل التواصل الاجتماعي
- تُفصح صراحةً عندما لا توجد فرصة واضحة
- تربط الأخبار الموثوقة بحركة الأسعار الحقيقية

## التقنيات
| الطبقة | التقنية |
|---|---|
| Frontend | Next.js (TypeScript) |
| Backend | Python FastAPI |
| Database | PostgreSQL |
| Realtime | WebSocket |
| Trading | Binance API, Bybit API |
| Notifications | Telegram Bot, SMTP |
| Hosting | Hetzner VPS |

## هيكل المشروع
```
/frontend    → واجهة المستخدم (Next.js)
/backend     → خادم API (FastAPI)
/docs        → وثائق المشروع
/scripts     → سكربتات النشر والإعداد
```

## التشغيل المحلي

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## البيئة
انسخ `.env.example` إلى `.env` واملأ القيم المطلوبة.

## الفريق
أداة داخلية — الوصول بدعوة من الأدمن فقط.
