# ECOSYSTEM PRIME | ممیزی تبار سورس و نصب مدار | ۱۴۰۵/۰۸/۲۵

**نتیجهٔ گیت A: PARTIAL / NO-GO برای Build و Upgrade مدار.**

## شواهد مستقیم

- Worktree فعلی: `D:\CoS-Test\000- Madar\madar-p2-gantt-notifications-20261107`
- HEAD: `b90ec8b2573e20ac0185f5a25d2578a206b27335`
- `package.json` و `package-lock.json`: نسخه `1.0.23`
- اشاره‌گر نصب: `1.0.28`
- EXE نصب‌شده: `%LOCALAPPDATA%\Programs\MadarDesk\versions\1.0.28\Madar-Desk.exe`
- SHA-256 مستقل EXE: `2bb04e2aa9c770469615d0716991fea8fcfc6b887b92003eeaa1ce565696ab49`
- در زمان بررسی: ۱۹ فایل Tracked در Worktree تغییرکرده بودند؛ هیچ‌کدام Reset/Clean یا Stage نشدند.

## بررسی بایت‌کد بدون اجرای EXE

ساختار واقعی PyInstaller با `CArchiveReader` و `PYZ.pyz` باز شد. کدهای Python استخراج‌شده با Compile کدهای Worktree فعلی و `git show HEAD`، بر پایه `co_code`، ثابت‌ها، نام‌ها و جدول Exception تطبیق داده شدند؛ این **مقایسهٔ کدهای Python** است، نه اثبات تطبیق همهٔ سورس، HTML/JS/CSS یا فرآیند Build.

| ماژول | توابع سطح ماژول نصب‌شده | اختلاف با Working | اختلاف با HEAD |
|---|---:|---|---|
| `native_app` | ۲۳ | فقط `Bridge` | فقط `Bridge` |
| `lan` | ۱۴ | `LanService` و `make_account` | صفر در سطح توابع ماژول |
| `taraz_exchange` | ۱۲ | صفر | اختلاف `queue_saved_task` و شش Helper اضافه‌شده در باینری |

تفکیک متدهای کلاس‌ها:

- `Bridge`: نصب‌شده ۱۴۳ متد، Worktree فعلی ۱۴۵؛ دو متد `aiDraftSuggest` و `mtrNoticeCommand` فقط در Worktree فعلی‌اند. چهار متد مشترک `_drain_finance_outbox`، `_taraz_actor_scope`، `tarazIntegrationHistory` و `tarazIntegrationPrepare` پیاده‌سازی متفاوت دارند.
- `LanService`: نصب‌شده ۴۷ متد، Worktree فعلی ۵۲؛ پنج متد جدید مربوط به Pilotهای AI/MTR/CRM در سورس‌اند، هفت متد مشترک نیز تغییر کرده‌اند.

**نتیجهٔ فنی:** شمارهٔ نسخهٔ `1.0.23` تنها اختلاف نیست. ساختار توابع اصلی نزدیک است، ولی Source و Binary دقیقاً یکسان نیستند. باینری `1.0.28` نمی‌تواند بدون تطبیق کد Frontend و مسیر ساخت، به این HEAD نسبت داده شود. تغییر شمارهٔ نسخه یا نصب مستقیم ممنوع است.

## اقدام بعدی

## ممیزی باندل وب نصب‌شده در برابر Build سورس فعلی

از `CArchiveReader`، فایل واقعی `dist/assets/main-saN9yJMv.js` داخل EXE خوانده شد. سپس Worktree تغییرکردهٔ فعلی، فقط در مسیر QA مستقل `D:\CoS-Test\ECOSYSTEM-PRIME-20261116\madar-web` با Vite Build شد (۱۶۹۳ ماژول، PASS، هشدار Chunk بزرگ).

| شاهد | JS نصب‌شده 1.0.28 | JS سورس فعلیِ تغییرکرده |
|---|---|---|
| فایل | `main-saN9yJMv.js` | `main-34ZktLKA.js` |
| بایت | ۱٬۰۲۹٬۱۳۸ | ۸۶۸٬۴۹۳ |
| SHA-256 | `6401496b1c1d602b0d8158681201a4b1a1f3696a56b2503ee532dbd323267740` | `8af17ded6f5bdbba8c931cc795124e5c2b25fc73fd501efc63c776ccdfeaf3c5` |
| وجود `mtrNoticeCommand` | خیر | بله |
| وجود `aiDraftSuggest` | خیر | بله |

**عدم تطابق بایت‌به‌بایت تأیید شد.** تفاوت حجم و Hash به‌تنهایی اثبات نمی‌کند کدام قابلیت دقیقاً حذف شده، اما نسبت‌دادن Build سورس فعلی به باینری نصب‌شده بی‌پشتوانه است. بنابراین گیت عدم عقب‌گرد **هنوز باز** است.

۱. منشأ قابل بازتولید باندل `dist/assets/main-saN9yJMv.js` داخل EXE `1.0.28` و فایل‌های Stage/Release آن کشف و با سورس فعلی تطبیق داده شود.

۲. تغییرهای ۱۹ فایل فعلی و ویژگی‌های فقط موجود در EXE با آزمون‌های Version-specific ادغام/بازیابی شوند؛ هیچ فایل Untracked دیگری تغییر نکند.

۳. Build دارای Manifest و Hash مستقل، Clone/Backup/Restore، سپس آزمون Frozen GUI و عدم عقب‌گرد انجام شود. **فعلاً نصب مدار دست‌نخورده است.**
