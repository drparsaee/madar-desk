# Madar Desk | Initial source modernization assessment

> این برگه خروجی ممیزی ساختاری و شواهد عملیاتی است، نه نتیجهٔ اجرای خودکار تمام فرمان‌های افزونه یا گواهی امنیت.

## Inventory

- **۹۰۱ فایل ردیابی‌شده در Git** در کامیت مبنا، بر اساس `git ls-files`.
- **۳۵۳ فایل Python ردیابی‌شده:** ۱۸۶ فایل خارج از `tests/`، تعداد ۱۶۷ در `tests/`.
- بزرگ‌ترین فایل‌های Python: `native_app.py` حدود ۳۱۲۳ خط، `accounting_core.py` حدود ۱۴۷۶ خط، `lan.py` حدود ۱۳۰۳ خط.
- خروجی ارزیابی ماشینی: `analysis/modernization/assessment.json`.

## Major modules, pending deeper rule extraction

| دامنه | فایل‌های شاهد | اولویت |
| --- | --- | --- |
| پوسته برنامه و پل بومی | `native_app.py`, `src/features.jsx` | بالا؛ فایل درشت و سطح ورودی زیاد |
| همگام‌سازی و دسترسی LAN | `lan.py`, `tests/test_lan_tls.py` | بالا؛ وابسته به TLS و مجوزها |
| حسابداری و دفتر مالی | `accounting_core.py`, `app_storage.py`, `ir_finance_v2_extension.py` | بحرانی؛ حفظ صحت مالی |
| ذخیره، بکاپ و انتشار | `scripts/Madar-Upgrade-Preflight.ps1`, `scripts/madar-update.iss` | بحرانی؛ عدم از دست رفتن داده |
| frontend و آزمون‌های رابط | `src/`, `tests/*.test.cjs` | متوسط تا بالا |

## Observations with evidence

1. Python AST parser روی همهٔ فایل‌های `.py` ردیابی‌شده بدون `SyntaxError` تمام شد. این بررسی فایل‌های بیرون Git و runtime/branch coverage را شامل نمی‌شود.
2. هیچ فراخوانی مستقیم به نام‌های `eval` یا `exec` در ASTهای جست‌وجوشده پیدا نشد؛ این بررسی امنیت یا نام‌های غیرمستقیم را اثبات نمی‌کند.
3. ۱۶ اسکریپت QA دارای یک escape نامعتبر `\/` بودند. در شاخهٔ نوسازی متن سورس به `\\/` اصلاح شد؛ AST متناظر قبل و بعد برابر بود و `py_compile` با SyntaxWarning به‌صورت error برای این فایل‌ها موفق شد.
4. یک رگرسیون جامع قبلی Python ناموفق بوده است. بدون اصلاح و اجرای مجدد، ادعای modernized/proven نادرست است.
5. ادعاهای امنیتی پیشین فقط شامل آزمون‌های منتخب و Gitleaks با یک یافتهٔ کلید fixture در تاریخچه است؛ این نتیجه ممیزی کامل امنیت محسوب نمی‌شود.

## Priority sequence

1. بازتولید و طبقه‌بندی دقیق شکست‌های Python در محیط ایزوله؛ حذف وابستگی تست‌ها به نمونه‌های خودکار بدون تغییر رفتار نصب تازه.
2. استخراج و تست قواعد حفظ داده و حسابداری به‌عنوان P0.
3. کوچک کردن تدریجی فایل‌های بزرگ پس از test characterization و اثبات برابری رفتاری، نه با جابه‌جایی گسترده و بدون تست.
4. بررسی dependency update و سیاست امنیتی LAN؛ بدون تضعیف certificate pinning.
5. ساخت نسخه شماره‌دار جدید، نصب آزمایشی، Snapshot و restore و مقایسهٔ هش؛ نصب واقعی فقط پس از پذیرش.

## Release verdict

**NOT PROVEN / NOT DEPLOYED.** تمام کدها بررسی عمیق یا به‌روزرسانی نشده‌اند؛ این فقط فاز بازشناسی ساختار و یک اصلاح محدود و قابل آزمون است.
