# Hetzner VPS Setup Guide

## مواصفات السيرفر
| البند | القيمة |
|---|---|
| النوع | CX21 |
| المعالج | 2 vCPU |
| الذاكرة | 4GB RAM |
| التخزين | 40GB SSD |
| النظام | Ubuntu 22.04 LTS |
| الموقع | Falkenstein أو Helsinki |

## خطوات الإنشاء

### 1. إنشاء السيرفر
1. سجّل دخول على [Hetzner Cloud Console](https://console.hetzner.cloud)
2. أنشئ مشروع جديد: `CryptoAnalyzer`
3. أنشئ سيرفر: CX21, Ubuntu 22.04, أضف SSH Key

### 2. تشغيل سكربت الإعداد
```bash
ssh root@YOUR_SERVER_IP
curl -O https://raw.githubusercontent.com/YOUR_REPO/main/scripts/server-setup.sh
sudo bash server-setup.sh
```

أو انسخ الملف يدوياً:
```bash
scp scripts/server-setup.sh root@YOUR_SERVER_IP:/root/
ssh root@YOUR_SERVER_IP "bash /root/server-setup.sh"
```

### 3. بعد الإعداد
```bash
# سجّل دخول كـ deployer
ssh deployer@YOUR_SERVER_IP

# استنسخ المشروع
cd /opt/crypto-analyzer
git clone git@github.com:YOUR_USER/crypto-analyzer.git .

# أضف SSL
sudo certbot --nginx -d your-domain.com
```

### 4. ملف البيئة على السيرفر
```bash
cp .env.example .env
nano .env  # املأ القيم الحقيقية
```

## ما يُثبّته السكربت تلقائياً
- ✅ Git, Python 3, pip, venv
- ✅ Node.js 20 LTS, npm, PM2
- ✅ PostgreSQL (مع قاعدة بيانات جاهزة)
- ✅ Nginx (مع proxy pass)
- ✅ UFW Firewall (22, 80, 443)
- ✅ SSH Key only (بدون كلمة مرور)
- ✅ مستخدم deployer بصلاحيات sudo
