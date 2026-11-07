# راهنمای آماده‌سازی استقرار عمومی Madar Web

**وضعیت این سند: بستهٔ استقرار آماده شده؛ سرور عمومی هنوز انتخاب یا provision نشده است.**

این بسته برای یک VPS لینوکسی با Node.js 26.8 یا جدیدتر، SQLite و Caddy طراحی شده است. نسخهٔ وب و API روی یک Origin ارائه می‌شوند. API فقط روی loopback گوش می‌دهد و Caddy مسئول HTTPS و ارائهٔ فایل‌های PWA است. این معماری به API نسخهٔ Windows/LAN متصل نمی‌شود.

## ۱. آنچه در بسته قرار می‌گیرد

- `www/`: خروجی build وب، بدون سورس یا فایل‌های حسابداری ویندوز.
- `server/`: API مستقل Node.js و SQLite و ابزار مدیریت حساب.
- `deploy/Caddyfile.example`: الگوی HTTPS، reverse proxy و headerهای مرورگر.
- `deploy/madar-web-api.service`: سرویس systemd با محدودیت دسترسی.
- `deploy/madar-web-backup.service` و `.timer`: پشتیبان‌گیری روزانه.
- `deploy/backup.sh`: ساخت پشتیبان SQLite، رمزگذاری با age، checksum و کپی اختیاری به فضای خارج از سرور.
- `SHA256SUMS.txt`: هش فایل‌های بسته.

هیچ حساب، رمز، دیتابیس، کلید خصوصی یا فایل محیط عملیاتی داخل بسته قرار نمی‌گیرد.

## ۲. پیش‌نیاز سرور

1. VPS لینوکسی پشتیبانی‌شده با دسترسی مدیریتی؛ Debian 12 یا Ubuntu 24.04 گزینه‌های هدف‌اند، اما این بسته روی سرور واقعی هنوز آزمایش نشده است.
2. Node.js نسخهٔ 26.8 یا جدیدتر با `node:sqlite`.
3. Caddy 2 برای HTTPS و reverse proxy.
4. ابزار `age` برای رمزگذاری پشتیبان. `rclone` فقط در صورت تنظیم فضای ذخیره‌سازی خارج از سرور لازم است.
5. یک دامنه با رکورد DNS به IP سرور و دسترسی ورودی TCP پورت‌های 80 و 443.

پیش از نصب، روی سرور اجرا شود:

```bash
node --version
node -e "const {DatabaseSync}=require('node:sqlite'); const db=new DatabaseSync(':memory:'); db.close(); console.log('node:sqlite ready')"
caddy version
```

Node قدیمی یا نبود `node:sqlite` مانع شروع سرویس است؛ از fallback دیتابیس یا API ویندوز استفاده نکنید.

## ۳. ساخت بسته از ویندوز

از ریشهٔ پروژه در PowerShell:

```powershell
npm.cmd run web:release:package
```

اسکریپت ابتدا `web:build` را اجرا می‌کند، سپس فقط `dist-web`، پوشهٔ `server`، فایل‌های `deploy` و مستندات API/استقرار را در ZIP قرار می‌دهد. ZIP بازگشایی و هش تک‌تک فایل‌ها بررسی می‌شود و فایل `.sha256` کنار آن ساخته می‌شود.

این بسته شامل نسخهٔ EXE یا دیتابیس محلی Windows نیست. خروجی را فقط پس از بررسی هش و انتقال امن به سرور کپی کنید.

## ۴. آماده‌سازی مسیرها و کاربر سرویس

نمونهٔ مسیرهای پیشنهادی:

```bash
sudo useradd --system --home /nonexistent --shell /usr/sbin/nologin madar-web
sudo install -d -o root -g root -m 0755 /opt/madar-web/server
sudo install -d -o root -g root -m 0755 /var/www/madar-web
sudo install -d -o madar-web -g madar-web -m 0700 /var/lib/madar-web
sudo install -d -o madar-web -g madar-web -m 0700 /var/backups/madar-web
sudo install -d -o root -g madar-web -m 0750 /etc/madar-web
```

پس از بازکردن ZIP و تأیید `SHA256SUMS.txt`:

```bash
sudo cp -a server/. /opt/madar-web/server/
sudo cp -a www/. /var/www/madar-web/
sudo chown -R root:root /opt/madar-web /var/www/madar-web
sudo find /opt/madar-web /var/www/madar-web -type d -exec chmod 0755 {} \;
sudo find /opt/madar-web /var/www/madar-web -type f -exec chmod 0644 {} \;
```

کد و فایل‌های استاتیک برای سرویس وب فقط خواندنی هستند. دیتابیس در `/var/lib/madar-web` می‌ماند و نباید زیر `www`، `public` یا پوشهٔ Git قرار گیرد.

## ۵. تنظیم Origin، دیتابیس و حساب‌ها

فایل نمونه را کپی کنید و دامنهٔ واقعی را جایگزین کنید:

```bash
sudo install -o root -g madar-web -m 0640 deploy/api.env.example /etc/madar-web/api.env
sudoedit /etc/madar-web/api.env
```

مقادیر ضروری:

```ini
MADAR_WEB_DB=/var/lib/madar-web/web.sqlite
MADAR_WEB_PUBLIC_ORIGIN=https://دامنه-واقعی
MADAR_WEB_HOST=127.0.0.1
MADAR_WEB_PORT=8781
MADAR_WEB_APP_ROOT=/opt/madar-web
```

`MADAR_WEB_PUBLIC_ORIGIN` باید دقیقاً Origin مرورگر باشد، بدون مسیر و slash انتهایی. HTTPS خارج از loopback اجباری است. مقدارهای نمونهٔ رمزگذاری پشتیبان نیز پیش از فعال‌کردن timer باید جایگزین شوند.

سپس حساب مدیر را با رمز تعاملی بسازید:

```bash
sudo -u madar-web env MADAR_WEB_DB=/var/lib/madar-web/web.sqlite \
  /usr/bin/node /opt/madar-web/server/admin.cjs init
sudo -u madar-web env MADAR_WEB_DB=/var/lib/madar-web/web.sqlite \
  /usr/bin/node /opt/madar-web/server/admin.cjs user:add admin admin team '*'
```

رمز را در command-line، فایل Git، history یا log قرار ندهید. ثبت‌نام عمومی وجود ندارد. نقش‌های editor و viewer باید مجوز پروژهٔ مشخص بگیرند؛ `*` فقط برای admin مجاز است.

## ۶. فعال‌کردن سرویس API

```bash
sudo install -o root -g root -m 0644 deploy/madar-web-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now madar-web-api.service
sudo systemctl status madar-web-api.service
sudo journalctl -u madar-web-api.service -n 80 --no-pager
```

سرویس با کاربر غیرممتاز اجرا می‌شود، کد را فقط می‌خواند و فقط در مسیر دیتابیس اجازهٔ نوشتن دارد. پورت 8781 نباید روی اینترنت باز شود.

## ۷. فعال‌کردن Caddy و HTTPS

`deploy/Caddyfile.example` را به `/etc/caddy/Caddyfile` کپی کنید و `madar.example.com` را با دامنهٔ واقعی جایگزین کنید. ریشهٔ فایل‌های وب باید `/var/www/madar-web` باشد. مسیر `/api/web/v1/*` باید بدون حذف prefix به `127.0.0.1:8781` proxy شود.

پس از تنظیم DNS و firewall:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

فقط پورت‌های 80 و 443 عمومی باشند؛ 8781 و SSH را در firewall محدود کنید. Caddy گواهی HTTPS را پس از دسترسی DNS/ACME دریافت و تمدید می‌کند. HSTS و Secure Cookie فقط در دامنهٔ HTTPS فعال می‌شوند.

## ۸. رمزگذاری و زمان‌بندی پشتیبان

کلید خصوصی age را روی یک دستگاه مدیریتی جدا از سرور تولید کنید و آن را روی سرور قرار ندهید:

```bash
age-keygen -o madar-web-backup-identity.txt
age-keygen -y madar-web-backup-identity.txt
```

مقدار عمومی `age1...` را در `MADAR_WEB_BACKUP_AGE_RECIPIENT` قرار دهید. کلید خصوصی باید خارج از سرور، رمزگذاری‌شده و با دسترسی محدود نگهداری شود.

اگر مقصد خارج از سرور دارید، `rclone` را با فایل تنظیمات محدودشده در `/etc/madar-web/rclone.conf` آماده کنید، مالکیت آن را به `root:madar-web` و مجوزش را `0640` بدهید و `MADAR_WEB_BACKUP_REMOTE` را در env تنظیم کنید. بدون remote، پشتیبان فقط روی همان سرور باقی می‌ماند و disaster recovery مستقل فراهم نیست.

سرویس و timer:

```bash
sudo install -d -o root -g root -m 0755 /usr/local/lib/madar-web
sudo install -o root -g root -m 0755 deploy/backup.sh /usr/local/lib/madar-web/backup.sh
sudo install -o root -g root -m 0644 deploy/madar-web-backup.service /etc/systemd/system/
sudo install -o root -g root -m 0644 deploy/madar-web-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now madar-web-backup.timer
sudo systemctl start madar-web-backup.service
sudo systemctl status madar-web-backup.service
```

زمان‌بندی روزانه 03:17 UTC با تأخیر تصادفی حداکثر ۱۰ دقیقه است. نگهداری محلی پیش‌فرض ۱۴ روز است. فایل‌ها پیش از نگهداری با age رمزگذاری می‌شوند؛ checksum بررسی می‌شود و در صورت تنظیم remote، checksum نسخهٔ remote نیز مقایسه می‌شود. سیاست حذف/نسخه‌بندی مقصد remote باید جداگانه در همان سرویس ذخیره‌سازی تعریف شود.

## ۹. آزمون پس از استقرار

```bash
sudo systemctl is-active madar-web-api.service
sudo systemctl list-timers madar-web-backup.timer
bash deploy/smoke.sh https://دامنه-واقعی
```

در مرورگر، ورود حساب، bootstrap اولیه با تأیید صریح، ثبت تغییر، خروج، ورود در مرورگر دوم، تعارض و بازیابی را آزمایش کنید. برای نخستین انتشار از دادهٔ آزمایشی استفاده کنید؛ دیتابیس حسابداری Windows را import یا expose نکنید.

## ۱۰. بازیابی

1. فایل `.sqlite.age` را از remote یا پشتیبان خصوصی دریافت کنید.
2. روی دستگاه امن مدیریتی با کلید خصوصی age رمزگشایی کنید.
3. `node server/admin.cjs restore:verify <restored.sqlite>` را با نسخهٔ سرور اجرا کنید.
4. ابتدا سرویس API را متوقف کنید و از دیتابیس فعلی نسخهٔ جداگانه نگه دارید.
5. فایل بازیابی‌شده را به مسیر دیتابیس منتقل، مالکیت `madar-web:madar-web` و مجوز `0600` تنظیم کنید؛ سپس سرویس را روشن و health/login/sync را بررسی کنید.

هرگز روی دیتابیس فعال restore نکنید. پیش از اتکا به این فرایند، یک restore drill واقعی روی سرور جداگانه اجرا و زمان/نتیجه ثبت شود.

## ۱۱. مواردی که هنوز مانع انتشار نهایی‌اند

- انتخاب و خرید VPS، منطقهٔ میزبانی و پلن منابع.
- دامنهٔ واقعی و DNS.
- نصب Node/Caddy/age روی میزبان واقعی و اعتبارسنجی فایل‌های systemd/Caddy روی همان توزیع.
- تنظیم و آزمون مقصد off-site مستقل.
- firewall، مانیتورینگ، هشدار دیسک/backup و restore drill واقعی.
- آزمون با دو دستگاه فیزیکی و کاربران واقعی/مجوزهای پروژه.

این بسته عمداً سرور عمومی را شبیه‌سازی یا به‌جای آن معرفی نمی‌کند. تا زمانی که میزبان و دامنه مشخص نشده‌اند، هیچ DNS، خرید، اتصال SSH یا انتشار عمومی انجام‌شده محسوب نمی‌شود.
