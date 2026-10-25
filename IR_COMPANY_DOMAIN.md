# مدل مستقل شرکت‌های حقوقی مدار (P0)

## وضعیت واقعی

فایل ir_company_registry.py یک هسته pure، immutable و مستقل برای هویت شرکت‌ها، تخصیص صریح پروژه‌ها، سال مالی، ارجاع بانک/صندوق/اشخاص، مجوزها، واحد نمایش و ارجاعات مهاجرت است. **این کد هنوز به native_app، finance، پایگاه داده، APPDATA، SQL، پارسیان، رابط کاربری یا ژورنال عملیاتی متصل نشده است.** مشکل محدودیت تک‌شرکتی سایه فقط پس از اتصال امن میزبان در فاز بعد حل می‌شود.

## شرکت ثبت‌شده، شناسه‌های حقوقی و ارز

RegisteredCompany دارای company_id، LegalEntity، fiscal_years و presentation_unit است.

- LegalEntity نام حقوقی اجباری دارد. national_id، registration_number، economic_code، tax_id و registered_address **اختیاری** هستند. اگر ارائه شوند به‌صورت رشته با حفظ صفر ابتدایی ثبت می‌شوند؛ هیچ شماره‌ای اختراع نمی‌شود. کنترل رشته، استعلام مرجع رسمی یا اثبات معتبر بودن کد ملی حقوقی نیست.
- ارز canonical حسابداری فقط RIAL است. شرکت می‌تواند نمایش RIAL یا TOMAN را برگزیند و هر کاربر دارای عضویت مالی همان شرکت با USER_DISPLAY ترجیح اختصاصی خود را ذخیره کند. company_money_policy خروجی CompanyMoneyPolicy با accounting_currency=RIAL است؛ هیچ تاریخچه قدیمی TOMAN خودکار تبدیل نمی‌شود.
- FiscalYear شامل company_id، fiscal_year_id و start_date/end_date به‌صورت **Gregorian ISO YYYY-MM-DD** است و ترتیب و عدم همپوشانی کنترل می‌شود. شناسه و تاریخ هر دوره باید صریح باشند؛ کد از نام سال، روز جاری یا تاریخ جلالی دوره استنباط نمی‌کند. برای ورود تاریخ جلالی مبدل جداگانه و مستند میزبان لازم است.

## قرارداد پروژه و دامنه شرکت

در سورس خوانده‌شده، native_app پروژه‌ها را در state["projects"] با id نگه می‌دارد و finance.py مجوزهای پروژه دارد؛ این ساختار هنوز مالک حقوقی شرکت هر پروژه را به‌طور معتبر اثبات نمی‌کند.

ProjectAssignment(company_id, project_id) فقط با گواهی دقیق (project_id, company_id) از VerifiedRegistryAuthority.project_company_pairs اضافه می‌شود. هر پروژه فقط به یک شرکت نسبت داده می‌شود و این ماژول هیچ عملیات انتقال پنهانی بین شرکت‌ها ندارد. مالکیت مبهم یا بدون نگاشت در resolve_project_company و در گیت مالی fail-closed می‌شود. حتی اگر فقط یک شرکت ثبت شده باشد، پروژه‌های تخت به آن خودکار منسوب نمی‌شوند.

CompanyBankRef شامل شرکت/بانک/حساب؛ CompanyCashRef شامل شرکت/صندوق؛ CompanyPartyRef شامل شرکت/شخص است. افزودن هر مورد به مجموعه معتبر میزبان نیاز دارد و هیچ داده بانکی یا شخص جدید به‌صورت خودکار ساخته نمی‌شود.

read_company_registry یک نمای ScopedCompanyView مخصوص شرکت درخواست‌شده به عضو مالی مجاز می‌دهد. replay_registry یک projection **کامل و مخصوص میزبان مورد اعتماد** است؛ نباید مستقیم به API کلاینت یا گزارش قابل دید عموم داده شود. شناسه‌های حقوقی و ارتباط اشخاص حریم خصوصی تجاری‌اند.

## نقش‌ها و مجوزها

| نقش | خواندن | صدور فروش/خرید | مدیریت شرکت و مجوز |
|---|---|---|---|
| finance_admin | بله | بله | بله |
| finance_issuer | بله | بله | خیر |
| finance_reader | بله | خیر | خیر |

REGISTER فقط به عامل دارای حق ثبت شرکت در host اجازه داده می‌شود و همان عامل به‌صورت مشخص نخستین مدیر مالی آن شرکت می‌شود. تنها finance_admin می‌تواند GRANT و REVOKE کند. تغییر نقش فعلی مستلزم revoke دقیق و grant مستقل جدید است؛ حذف آخرین مدیر ممنوع است. issuer و reader قادر به ارتقای نقش خود یا تغییر وضعیت قانونی شرکت نیستند. کاربر فقط می‌تواند ترجیح نمایش واحد پول خودش را تغییر دهد.

**مرز اعتماد:** VerifiedRegistryAuthority به‌عنوان داده ورودی از میزبان لازم است؛ صرف ساختن آن در Python اثبات احراز هویت نیست. میزبان باید actor، حق ثبت شرکت، مالکیت پروژه، بانک، صندوق، شخص، نگاشت legacy و مدرک سند قطعی را از رکوردهای معتبر و در محدوده مجوز کاربر تعیین کند. مقادیر ارسالی UI به این عنوان معتبر نیستند.

## تغییرناپذیری، CAS و قفل سند قطعی

داده‌ها frozen و slots هستند. رویدادهای RegistryEvent شامل command digest، previous_hash، event_hash و business source_id هستند. replay_registry تمام رویدادها را از ابتدا بازسازی کرده و hash chain، ترتیب، یکتایی منبع و قوانین مجوز را بررسی می‌کند. apply_registry_command فقط با expected_revision از نوع SHA-256 و CAS خوش‌بینانه snapshot جدید می‌سازد. retry با فرمان دقیق همان source id بدون تغییر state پذیرفته و payload متفاوت تحت همان (company_id, source_id) رد می‌شود.

LEGAL_UPDATE و YEAR_REPLACE تا قبل از اولین POSTED_LOCK آن شرکت مجازند. POSTED_LOCK باید از گواهی معتبر و قطعی میزبان برای (company_id, project_id, fiscal_year_id, business_source_id) حاصل شود؛ پس از وجود lock، تغییر هویت قانونی و اصلاح سال مالی شرکت ممنوع است، ولی سال مستقل آینده بدون همپوشانی می‌تواند اضافه شود. حذف/جابجایی شرکت یا پروژه، حذف سال و تغییر ثبت قطعی ارائه نشده است.

SHA-256 امضای مستقل نیست؛ حمله‌کننده‌ای که کل تاریخچه را بازنویسی کند می‌تواند hash chain تازه بسازد. میزبان باید head hash را در audit خارجی یا سیستم مستقل anchor کند. رجیستری فعلاً نمی‌تواند از روی JournalState بفهمد سندی قبلاً ثبت شده ولی POSTED_LOCK آن جا افتاده است؛ host باید lock و GL را در **یک تراکنش** ایجاد کند و سابقه پیش از فعال‌سازی را تطبیق دهد.

## گیت ثبت مالی فروش/خرید

verify_sale_purchase_gl_gate یک تابع فقط خواندنی است که بدون شرکت ثبت‌شده، پروژه صریح و host-verified، نقش issuer/admin، شخص معتبر همان شرکت، ChartSnapshot و VerifiedScopes هم‌شرکت، سال مالی و دوره باز ژورنال و تاریخ داخل بازه، مجوز پیشنهادی نمی‌دهد. مجموعه **تمام** پروژه‌ها و اشخاص موجود در chart/scopes نیز باید به همان شرکت تعلق داشته باشد، نه فقط پروژه انتخاب‌شده.

stable_financial_source_id(company_id, project_id, kind, document_id) برای kind=sale یا purchase یک شناسه پایدار co.<SHA256> تولید می‌کند. خروجی GLCompanyGate شامل شرکت، پروژه، fiscal_year_id، fiscal_period_id، posting_date، actor، business source از نوع JournalSource(independent) و نسخه‌های رجیستری/ژورنال است. VerifiedScopes باید شامل جفت صریح (project_id,source_id) باشد. اگر همین منبع با event ID دیگری در دفتر ثبت شده باشد یا posted lock قبلی داشته باشد، گیت آن را رد می‌کند. این تابع **فاکتور یا سند حسابداری نمی‌سازد**.

### قرارداد اتصال عملیاتی Prime / میزبان

1. برای پروژه‌های تخت موجود در native_app نقشه حقوقی پروژه به شرکت را از داده معتبر و تأیید انسانی بسازد. ناشناخته‌ها را بدون پیش‌فرض مسدود کند؛ Company ID را از session/account مجاز میزبان و رابطه معتبر پروژه دریافت کند.
2. ChartSnapshot.company_id و project_ids و مراجع CostCenter/Job و PartyDetailLink باید به همین شرکت تعلق داشته باشند. VerifiedScopes مستقل از درخواست UI و تنها با رکوردهای host verified ساخته شود.
3. JournalState.company_id و بازه FiscalPeriod باید با شرکت و بازه سال مالی ثبت‌شده سازگار باشند. ir_journal_v2.post_journal همچنان مسئول توازن دوطرفه، سرفصل حساب، مبلغ و تاریخ سند است. هر سند فروش/خرید باید فاکتور معتبر و هویت طرف‌حساب قطعی داشته باشد.
4. finance.py legacy TOMAN و ir_finance_v2_extension فعلی بدون composer و reconciliation مستقل به RIAL ادغام نشوند. مهاجرت قدیمی با LegacyProjectLink(company,project,legacy_project_id) فقط بعد از اثبات دقیق پروژه و نگاشت مرجع توسط میزبان ممکن است؛ این مدل هیچ تراکنش یا مانده قدیمی را مهاجرت نمی‌دهد.
5. تغییر رجیستری، POSTED_LOCK، سند ژورنال، invoice/bill، idempotency business source، audit/hash و revision باید زیر یک SQL transaction با unique constraints، CAS واقعی و rollback ذخیره شود. در این فایل atomic commit/SQL concurrency آزمون یا پیاده‌سازی نشده است.
6. اعتبار قانونی شماره ملی حقوقی/شماره ثبت، تطبیق شبا و بانک، مجوز واقعی کاربر و کنترل تاریخ جلالی به مراجع معتبر و تست‌های host نیاز دارند. این فایل هیچ استعلام آنلاین یا تعامل با داده واقعی ندارد.

## شواهد آزمون و محدودیت

دستور اجرای آزمون:

    python -B -m unittest discover -s tests -p test_ir_company_registry.py -v

پوشش مصنوعی شامل ثبت شرکت، شماره حقوقی اختیاری، پروژه نامعلوم/مبهم/چندشرکتی، سال‌های غیرهمپوشان، نقش‌های finance، نقش‌افزایی غیرمجاز، scope بانک/صندوق/اشخاص، نمایش RIAL/TOMAN، idempotency و CAS، ثبت منبع پایدار، قفل هویت پس از سند مالی، نمای خواندن محدود به شرکت، chart/journal ناسازگار، دوره بسته، و ثبت تکراری source زیر شناسه رویداد متفاوت است.

**بررسی انجام‌نشده:** آزمون شبکه و احراز هویت واقعی، SQL/rollback، APPDATA، پارسیان، Windows EXE، مهاجرت legacy یا فعال‌سازی چندشرکتی در میزبان اجرا نشده‌اند.
