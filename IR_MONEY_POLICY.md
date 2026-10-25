# سیاست پول ایران برای دامنه مالی جدید مدار

**وضعیت: ماژول مستقل و آزمایش‌شده، نه متصل به میزبان یا رابط کاربری.**
فایل‌های این بسته: money_policy.py، tests/test_money_policy.py و IR_MONEY_POLICY.md.

## سیاست مرجع

- هر شرکت CompanyMoneyPolicy با accounting_currency برابر RIAL دارد. display_unit فقط RIAL یا TOMAN است و تغییر آن، هیچ مبلغ ثبت‌شده‌ای را تغییر نمی‌دهد.
- یک تومان دقیقاً ده ریال است. **تمام مقادیر ذخیره‌شده در دامنه مالی جدید، عدد صحیح ریال‌اند**. اعشار ریال، float، گرد کردن یا بریدن ریال‌های باقیمانده ممنوع است.
- مثال: مبلغ 101 ریال باید به صورت 101 RIAL یا 10.1 TOMAN نمایش داده شود. ورودی «۱۰٫۱» در حالت TOMAN دقیقاً 101 ریال است. مقدار 10.01 TOMAN مردود است، نه تبدیل تقریبی.
- جداکننده هزارگان فقط با گروه‌بندی معتبر پذیرفته می‌شود: 12,345 و ۱۲٬۳۴۵. ارقام لاتین، فارسی و عربی پذیرفته می‌شوند. اعشار تومان فقط یک رقم دارد، اعشار ریال هرگز مجاز نیست. منفی برای برگشت/مانده فقط با مجوز صریح allow_negative=True مجاز است؛ منفی صفر نیز رد می‌شود.
- ورودی‌ها باید متن باشند؛ مقدار Canonical در Python باید type(value) is int باشد، نه float، Decimal یا bool.
- سقف پیش‌فرض MAX_RIAL=9,007,199,254,740,991 معادل 2**53-1 است. این سقف، نمایش و انتقال با JSON Number در JavaScript را همچنان دقیق نگه می‌دارد؛ نیاز به ارقام بزرگ‌تر مستلزم طراحی wire format مبتنی بر رشته ده‌دهی و تست جداگانه است. در حال حاضر ورودی، جمع میانی، حاصل ضرب یا مهاجرت بالاتر از سقف قطع می‌شود.

## API خالص

    from money_policy import (
        CompanyMoneyPolicy, parse_money_input, format_money,
        require_rial_amount, sum_rial_amounts, multiply_rial,
        freeze_posted_document, assert_posted_document_unchanged,
        LegacySourceEvidence, snapshot_sha256,
        quote_legacy_toman_migration, verify_legacy_migration_quote,
    )

    policy = CompanyMoneyPolicy("company-1")            # پایه RIAL
    toman = policy.with_display_unit("TOMAN")           # فقط view
    toman.parse("۱٬۲۳۴٫۵")                              # 12345 RIAL
    toman.format(101)                                   # "10.1"
    format_money(101, "RIAL", persian_digits=True)       # "۱۰۱"
    multiply_rial(101, 3)                               # 303 RIAL
    sum_rial_amounts([101, 9])                          # 110 RIAL

واحد parse باید از policy تأییدشده همان شرکت به دست بیاید، نه تشخیص دلخواه از placeholder یا برچسب UI. متن قالب‌بندی‌شده همراه suffix واحد، صرفاً برای نمایش است و برای parser باید suffix را جداگانه و با هویت مشخص بفرستید.

## Snapshot immutable سند ثبت‌شده

    doc = {
        "companyId": "company-1", "eventId": "posted-1",
        "status": "posted", "currency": "RIAL", "amountRial": 101,
        "lines": [{"debitRial": 101, "creditRial": 0}],
    }
    frozen = freeze_posted_document(doc, policy)
    assert_posted_document_unchanged(frozen, doc, policy)
    assert_posted_document_unchanged(
        frozen, doc, policy.with_display_unit("TOMAN"))

- کل ساختار سند، نه فقط مبلغ، با JSON canonical و SHA-256 ثبت می‌شود. FrozenPostedDocument یک frozen dataclass است و تغییر اصل سند یا تاریخ/سطر/طرف حساب در assert_posted_document_unchanged رد می‌شود.
- برای همه فیلدهای با نام منتهی به Rial در سند ثبت‌شده، صحیح بودن و سقف دقیق کنترل می‌شود. float در هر قسمت snapshot، nesting بیش از حد و داده غیر JSON ممنوع‌اند.
- document_copy فقط یک نسخه مستقل برمی‌گرداند. تغییر این copy، اصل frozen را تغییر نمی‌دهد.
- **این freeze یک قرارداد خالص داخل حافظه است، قفل دیتابیس نیست.** فقط میزبان با تراکنش اتمیک، کنترل revision/CAS، ID رویداد یکتا، append-only persistence و hash معتبر می‌تواند immutable ماندن سند واقعی را تضمین کند. اصلاح سند ثبت‌شده باید از مسیر reversal + رویداد جدید باشد، نه update درجا. سند draft تا پیش از commitِ واقعی نباید posted شمرده شود.

## مرز مهاجرت داده‌های قدیمی TOMAN

در وضعیت واقعی فعلی، accounting_core.py خطوط 106-108 و accounting_service.py خطوط 392-408 هنوز currency=TOMAN را ثبت/برمی‌گردانند. finance.py نیز از همین دامنه قدیمی استفاده می‌کند. تغییر لفظ currency یا جابه‌جایی ضریب واحد روی اسناد قبلی باعث فساد تراز و hash/replay می‌شود.

    legacy = {"invoices": [{"sale": {"due": 250}}]}
    evidence = LegacySourceEvidence(
        source_id="finance-v1",
        declared_unit="TOMAN",
        verified_unit="TOMAN",
        source_snapshot_sha256=snapshot_sha256(legacy),
        verifier_id="trusted-admin",
        verification_reference="approval-42",
    )
    quote = quote_legacy_toman_migration(
        legacy, ("invoices", 0, "sale", "due"), evidence, policy)
    assert quote.converted_rial == 2500
    verify_legacy_migration_quote(quote, legacy, evidence, policy)

- واحد source باید **صریحاً و مستقلاً** TOMAN تایید شده باشد؛ declared_unit و verified_unit هر دو دقیقاً TOMAN باشند و digest snapshot کامل مطابقت کند. مقدار UNKNOWN یا RIAL به‌عنوان legacy TOMAN رد می‌شود.
- LegacySourceEvidence صرفاً ساختار داده است. وارد کردن نام verifier یا hash توسط کاربر **اثبات احراز واحد نیست**. میزبان باید در منبع مستقل قابل اعتماد، واحد تک‌تک فیلدهای هدف، احراز هویت بازبین، اصالت فایل، نسخه snapshot و approval manifest را تایید کند.
- تبدیل فقط روی مسیر مشخص داخل snapshot دارای digest یکسان انجام می‌شود. LegacyMigrationQuote منجمد صرفاً پیشنهاد تبدیل است؛ نه سند افتتاحیه، نه ثبت دفترکل، نه import. قبل از commit دوباره verify_legacy_migration_quote اجرا شود. عدد نامعتبر یا overflow رد می‌شود. مقادیر منفی اصلاحی فقط با allow_negative=True پذیرفته می‌شوند.
- میزبان باید کلید idempotency مهاجرت از (source snapshot hash + source ID + field path) به سند جدید نگهدارد تا دو بار شناسایی نشود. تاریخچه قدیمی باید دست‌نخورده بماند. افتتاحیه و تطبیق دفتر جدید تنها پس از تأیید اقلام، تراز بدهکار/بستانکار و اختلاف‌های مستند، با رویدادهای مجزا و تراکنش اتمیک صورت گیرد.
- «ارزش» یک فیلد، عدد «تعداد»، «مالیات»، «پیش‌دریافت»، «هزینه» یا «قیمت» را نمی‌توان صرفاً با نام کلید حدس زد؛ واحد source و معنی تجاری هر کدام جداگانه اعتبارسنجی شود.

## قرارداد لازم برای اتصال (هنوز انجام نشده)

1. شرکت/کاربر/واحد: policy معتبر، کنترل مجوز و ذخیره نسخه policy؛ نمایش RIAL/TOMAN فقط تنظیم UI باشد، نه تغییر نوع ذخیره.
2. ورود پول: تمام قیمت‌ها، فروش و خرید، هزینه، تسویه، خزانه و سند دستی در رابط به parse_money_input منتقل شده و فقط RIAL صحیح به API جدید ارسال شود؛ بدون جابه‌جایی پنهان TOMAN/RIAL.
3. دفترکل: برای ارز RIAL schema/domain **جدید** طراحی شود. accounting_core.py فعلی TOMAN است و نباید به‌طور مستقیم reinterpret شود. journal، AR/AP، هویت طرف حساب، تاریخ، گزارش‌ها و hash/replay در واحد جدید تست شوند.
4. ثبت immutable: ثبت واقعا posted با full event snapshot و hash، revision/CAS، retry idempotency و reversal؛ تغییر واحد نمایش سند ثبت‌شده را تغییر ندهد.
5. مهاجرت: source unit manifest معتبر و مستقل، تفکیک مالیات/تعداد/قیمت، preview، تراز و مقایسه با snapshot، dedupe، تأیید انسانی و commit یکپارچه؛ بدون شواهد واقعی source واحد، import متوقف شود.
6. اجرای بعدی: تست GUI، LAN/Windows، اعداد نزدیک سقف JS، مانده ریال‌های فرد در تومان، دفترکل متوازن، دوره بسته، پایداری حساب‌ها و بازپخش eventها. این بسته هیچ‌یک از این عملیات واقعی را انجام نداده است.

## آزمون مستقل

    python -B -m unittest discover -s tests -p test_money_policy.py -v

مجموعه تست‌های مصنوعی: parse دقیق با رقم‌های فارسی/عربی، grouping، round-trip دقیق، اعشار تومانی باقیمانده ریال، صفر و منفی، overflow و عملیات، اسناد frozen و تغییر تاریخچه، اصالت snapshot، واحد اعلامی/تأییدشده TOMAN و پیش‌نمایش مهاجرت بدون side effect. هیچ فایل مشترک، DB، APPDATA، Git، UI یا release تغییر نمی‌کند.
