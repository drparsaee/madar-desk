# Preflight | Madar Desk

## Source and toolchain

- منبع در `D:\CoS-Test\madar-modernization-20261101` در worktree جداگانه و شاخهٔ اختصاصی قرار دارد. این مسیر یک کپی اجرایی محصول نیست.
- Node.js و npm و Python 3.12 در محیط ویندوز موجودند؛ ابزارهای PyInstaller و Inno Setup طبق عملیات قبلی استفاده شده‌اند.
- `package.json` نسخهٔ برنامه را ۱.۰.۲ اعلام می‌کند. مکانیزم انتشار Inno و مسیر داده در `docs/MADAR_VERSIONED_RELEASE_POLICY.md` مستند شده‌اند.
- ارزیابی static AST روی ۳۵۳ فایل Python ردیابی‌شده بدون SyntaxError بوده است؛ این بررسی به معنی صحت اجرایی همه فایل‌ها نیست.
- آزمون کامل Python در آخرین اجرای مستند قبل از این بازبینی: ۱۵۸۱ تست، ۱۱ failure و ۱۶۷ error، ۳ skipped و ۲ expected failure. اجرای مجدد کامل هنوز نیاز به نتیجهٔ قطعی در این workspace دارد.
- اجرای قبلی JavaScript روی سورس اصلی کامیت مبنا: ۵۲۸ از ۵۲۸ موفق با اجرای ترتیبی؛ اجرای مجدد روی شاخهٔ جدید هنوز انجام نشده است.

## Answers to five preflight questions

1. **Scope:** این مخزن کد اصلی برنامه را شامل می‌شود؛ داده‌های تاریخی مستقل حسابداری و Parsian در بیرون آن هستند. پوشش آن‌ها در نوسازی هنوز کامل نیست.
2. **Build and test:** ساخت Vite در نوبت قبل موفق بود. تست جامع Python همچنان در وضعیت ناموفق قرار دارد؛ زمان یا نتیجهٔ اجرای تازه از پیش فرض نمی‌شود.
3. **Bespoke build tooling:** `scripts/build_inno_update.py`، `scripts/madar-update.iss`، اسکریپت‌های Snapshot و PyInstaller وجود دارند؛ بررسی کامل تمام مراحل Release باز است.
4. **Prior attempts:** رفع مشکل نصب ۱.۰.۱ و ۱.۰.۲، QA ارتباط LAN و اصلاح fixtures قدیمی در گزارش قبلی مستند است.
5. **Off limits:** پروفایل واقعی، بکاپ‌ها، اطلاعات تاریخی حسابداری، Parsian، و نسخهٔ نصب‌شده؛ فایل‌های ثالث Trello نیز نباید بدون تعیین تکلیف مجوز کپی شوند.

## Readiness verdict

**PARTIAL / NOT RELEASE-READY.** نقشه و ممیزی مقدماتی ممکن است؛ نوسازی سراسری بدون تست معتبر و مقایسهٔ رفتار، هنوز پشت گیت اعتبارسنجی قرار دارد.
