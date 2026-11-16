# ممیزی ۱۸ بستهٔ C01–C18

بسته‌ها کاندید طراحی‌اند، نه قابلیت تمام‌شده. شمارش ردیف‌ها بر اساس نگاشت معنایی غیررسمی است.
هر status در این جدول **وضعیت بسته** است، نه ادعای اجرای تمامی ایده‌های داخل آن.

| C-ID | Title | Proposed Version | Phase | Ideas mapped | Verified | Partial | Source only | Planned | Blocked | Not verified | Package Status | Evidence / Next gate |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| C01 | هسته مدیریت سفارش و گردش کار مدار | نسخه ۱ | P2 / Madar | 5 | 0 | 1 | 1 | 0 | 0 | 3 | PARTIAL_IMPLEMENTATION | T:src/accounting_invoice_wizard.jsx / M:src/taskops.js; NEXT: احراز تغییر وضعیت، نقش‌ها و عدم تغییر غیرمجاز با چند کاربر |
| C02 | دستیار هوشمند ثبت سفارش و تکمیل پیش‌نویس | نسخه ۱.۱ | P3 | 7 | 0 | 0 | 1 | 0 | 0 | 6 | SOURCE_ONLY | M:madar_ai_draft.py; NEXT: تفکیک مقدار معلوم/نامعلوم و عدم ایجاد مبلغ ساختگی در نمونه‌های واقعی مجاز |
| C03 | هوش مصنوعی مستقل و حافظه محلی | نسخه ۲ | P3 | 6 | 0 | 0 | 1 | 0 | 0 | 5 | SOURCE_ONLY | T:taraz_aaas_agent.py; NEXT: ارزیابی آفلاین روی سخت‌افزار هدف با داده ساختگی و بدون خروج اطلاعات |
| C04 | هوش سازمانی و مهندسی گردش کار | نسخه ۲ | P3 | 7 | 0 | 2 | 0 | 0 | 0 | 5 | PARTIAL_IMPLEMENTATION | M:src/gantt_model.js; NEXT: تعریف گلوگاه و تطبیق نتیجه پیشنهادی با نمونه‌های دارای حقیقت مرجع |
| C05 | ایجنت‌های عملیاتی و دستیار مدیریت | نسخه ۲ | P3 | 5 | 0 | 0 | 1 | 0 | 0 | 4 | SOURCE_ONLY | T:taraz_aaas_agent.py; NEXT: اثبات مرز اختیار عامل، ثبت اقدام و تأیید انسانی قبل از تغییر حساس |
| C06 | پرونده جامع و حافظه ارتباطی مشتری | نسخه ۱ | P4 / Radar | 2 | 0 | 2 | 0 | 0 | 0 | 0 | PARTIAL_IMPLEMENTATION | M:radar_crm_store.py; NEXT: شناسه مشتری مستقل از شماره تماس، تشخیص تکرار و جداسازی دسترسی |
| C07 | رادار فروش و پیگیری هوشمند مشتری | نسخه ۲ | P4 / Radar | 13 | 0 | 0 | 1 | 0 | 0 | 12 | SOURCE_ONLY | M:radar_crm_store.py; NEXT: ارزیابی نرخ پیگیری مفید بدون ارسال خودکار یا استفاده خارج از رضایت |
| C08 | موتور کشف و ارزیابی تأمین‌کنندگان | نسخه ۲ | P4 / Radar | 9 | 0 | 0 | 0 | 0 | 0 | 9 | NOT_VERIFIED | No item-specific implementation evidence; NEXT: منشأ قابل پیگیری و تأیید انسانی کیفیت هر معرفی تأمین‌کننده |
| C09 | شبکه تجاری و بازار فرصت‌های رادار | نسخه ۳ | P4 / Radar | 6 | 0 | 0 | 0 | 6 | 0 | 0 | PLANNED | No item-specific implementation evidence; NEXT: مجوز استفاده/اشتراک داده و کنترل کیفیت لید با مشارکت طرفین |
| C10 | اتصال دوطرفه مدار و تراز و مدیریت اطلاعات پایه | نسخه ۱ | P4 | 5 | 0 | 1 | 3 | 0 | 0 | 1 | PARTIAL_IMPLEMENTATION | M:radar_party_match_preview.py / T:taraz_madar_data_reader.py; NEXT: نگاشت موقت-رسمی، retry بدون ثبت تکراری، ردیابی تعارض و بازرسی ACL |
| C11 | گردش کار مالی و صف تأیید تراز | نسخه ۱ | P4 | 6 | 0 | 4 | 2 | 0 | 0 | 0 | PARTIAL_IMPLEMENTATION | M:mtr_e2_send_journal.py / M:src/order_finance_fields.jsx; NEXT: هیچ سندی پیش از تأیید مجاز ثبت نشود؛ بازگشت نقص دارای مسئول و audit باشد |
| C12 | مدیریت اسناد و چرخه فاکتور | نسخه ۱ | P1 | 4 | 0 | 1 | 2 | 0 | 0 | 1 | PARTIAL_IMPLEMENTATION | T:src/taraz_madar_dashboard.jsx / T:src/taraz_order_workspace.jsx; NEXT: پیوند یک‌به‌چند سند با سفارش و تطابق آخرین نسخه رسمی تراز |
| C13 | مرکز ارتباط و ارسال اسناد به مشتری | نسخه ۱ | P4 | 13 | 0 | 0 | 0 | 0 | 0 | 13 | NOT_VERIFIED | No item-specific implementation evidence; NEXT: تفکیک بازشدن پیام‌رسان/تأیید کاربر/رسید قابل‌اعتماد |
| C14 | سیستم نصب و استقرار چندمحیطی | نسخه ۱ | P7 | 6 | 0 | 0 | 0 | 0 | 2 | 4 | BLOCKED | T:scripts/qa_taraz_fresh_reset_rollback_20261115.py / T:scripts/build_taraz_v106_aaas_20261111.py; NEXT: آزمون نصب و ارتقا و بازیابی در سه محیط یک‌سیستم، LAN و اینترنت امن |
| C15 | زیرساخت همگام‌سازی، پشتیبان‌گیری و به‌روزرسانی | نسخه ۱ | P5 | 9 | 0 | 3 | 1 | 0 | 0 | 5 | PARTIAL_IMPLEMENTATION | T:taraz_madar_order_sync.py / T:taraz_three_root_backup_20261114.py; NEXT: restore قابل‌آزمون، قطعی شبکه، conflict و عدم ازدست‌رفتن داده واقعی |
| C16 | امنیت سازمانی و مدیریت دسترسی | نسخه ۱ | P5 | 16 | 0 | 5 | 3 | 0 | 0 | 8 | PARTIAL_IMPLEMENTATION | M:role_profiles.py / M:radar_crm_store.py; NEXT: تست مجوز سرور، محدودسازی سازمان/پروژه و تفکیک محرمانگی در دو محصول |
| C17 | هوش عملیاتی و داشبورد مدیریت | نسخه ۱.۱ | D1 | 11 | 0 | 0 | 5 | 0 | 0 | 6 | SOURCE_ONLY | T:src/taraz_madar_dashboard.jsx / M:src/host_backup_health.js; NEXT: تطبیق گزارش با داده مرجع و نمایش صریح تازگی/منبع هر KPI |
| C18 | هوش مالی و شبیه‌سازی تصمیم‌های تجاری | نسخه ۳ | D1 / P3 | 5 | 0 | 0 | 1 | 4 | 0 | 0 | SOURCE_ONLY | T:taraz_order_store.py; NEXT: محاسبات با ورودی رسمی و سناریوهای ناقص؛ ممنوعیت نمایش فرض به‌عنوان واقعیت |

## مرحلهٔ بعد و وابستگی

- P0: مرجع سورس و نوت‌های نسخه‌دار حفظ شدند؛ هیچ پیاده‌سازی از ثبت ایده استنتاج نمی‌شود.
- P1/P2: پذیرش Frozen فاکتور، PDF و سفارش از شواهد قبلی تراز؛ نصب عملیاتی ۱.۰.۶ هنوز انجام نشده است.
- D1: مدل مشترک داده و KPI باید روی دادهٔ مرجع واقعی و با ACL ممیزی شود.
- P3: Provider واقعی فعلاً غیرفعال است؛ تاریخچهٔ Chat به معنی اجرای مدل نیست.
- P4: یکپارچگی دو برنامه و Radar مستلزم قرارداد واقعی دوطرفه، نقش و رسید مالی است.
- P5/P6: Recovery، Writer quiescence و آزمون ایزوله/نصب مستقل ضروری‌اند.
- P7: Release Gate و Rollback Production تا عبور همهٔ پیش‌شرط‌ها باید Fail-closed بمانند.

**درصد پیشرفت ارائه نشده است:** تعریف وزن و معیار پذیرش ۱۳۵ مورد و ۱۸ بسته هنوز تصویب نشده است.
