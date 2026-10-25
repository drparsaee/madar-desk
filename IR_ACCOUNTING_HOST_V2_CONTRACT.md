# قرارداد میزبان حسابداری ریالی V2 مدار

**وضعیت فعلی:** ماژول مستقل `ir_accounting_host_v2.py` ایجاد شده و با SQLite موقت و منبع داده ساختگی آزموده می‌شود. به `native_app.py`، `lan.py`، UI، دفتر قدیمی تومان، APPDATA واقعی یا SQL عملیاتی متصل نشده است. این ماژول **فاکتور صادر نمی‌کند** و سند TOMAN قدیمی را به RIAL منتقل نمی‌کند.

## API میزبان

```python
from ir_accounting_host_v2 import RIALAccountingHost

host = RIALAccountingHost(storage=dedicated_rial_storage, authority=server_authority)

# Read-only adapter for Bridge.rialJournalRead:
response = host.read(server_session, company_id="company-A", project_id="proj-1")

# Internal adapter for Bridge.rialJournalCommand (NOT enabled for legacy issuance):
response = host.command(server_session, command, today=trusted_server_date)
```

`RIALHostAuthority` **اجباری** است. متدهای موردنیاز:

| متد | نتیجه معتبر |
| --- | --- |
| `authenticate(session)` | `TrustedAccountingPrincipal` با `actor_id`, `company_id`, `authenticated`, `permissions`, `project_ids` از نشست احرازشده |
| `resolve_document(company_id, document_id)` | `VerifiedIssuedDocument` با سند قطعی و غیرقابل‌ویرایش، واحد RIAL و مبلغ دقیق، اصالت منبع و وضعیت مجوز ثبت قدیمی |
| `resolve_chart(company_id)` | `ChartSnapshot` متعلق به همان شرکت و نسخه معتبر |
| `resolve_scopes(company_id)` | `VerifiedScopes` از موجودیت‌های سروری معتبر شرکت |
| `resolve_money_policy(company_id)` | `CompanyMoneyPolicy` با ارز پایه RIAL و سقف دقیق |

ورودی UI حق ارسال principal، مجوز، project grant، scope، مبلغ، ارز، سطر حسابداری، وضعیت سند، شناسه actor یا کدینگ حساب را ندارد. همین اطلاعات باید فقط از resolver سروری به دست آیند. خود `TrustedAccountingPrincipal` یک dataclass است، نه گواه رمزنگاری؛ فقط کد میزبان مورد اعتماد مجاز است آن را بسازد. پیاده‌سازی resolver که داده‌های UI را مستقیماً به dataclass کپی کند، **فاقد احراز مالکیت** است.

## قرارداد فرمان‌ها

ورودی قابل قبول `command` تنها یکی از سه شیء زیر است؛ هر کلید اضافه یا حذف‌شده رد می‌شود:

```json
{"type":"document.post","companyId":"company-A","documentId":"sale-1","fiscalPeriodId":"FY26","postingDate":"2026-10-21","expectedRevision":"<64-hex-revision>"}
{"type":"journal.reverse","companyId":"company-A","originalEventId":"<posted-event-id>","fiscalPeriodId":"FY27","postingDate":"2027-01-03","reason":"Issued in error","expectedRevision":"<64-hex-revision>"}
{"type":"period.close","companyId":"company-A","fiscalPeriodId":"FY26","closingDate":"2027-01-01","expectedRevision":"<64-hex-revision>"}
```

توضیح: مقادیر angle-bracket بالا فقط placeholder مستندات‌اند و به عنوان شناسه معتبر پذیرفته نمی‌شوند. شناسه رویداد `document.post` از `(company_id, document_id)` به‌صورت قطعی توسط میزبان تولید می‌شود؛ دو فرمان با event ID دلخواه برای یک document امکان ایجاد ندارند. SQLite همچنین کلید `(company_id, source.kind, source.project_id, source.source_id)` را برای سند اولیه غیرقابل‌تکرار نگه می‌دارد. `card` به عنوان alias خطرناک `task` پذیرفته نمی‌شود و connector باید آن را به `task` canonical نگاشت و مالکیتش را مستقلاً اثبات کند.

برگشت سند (`journal.reverse`) یک سند معکوس جدید در دوره باز ایجاد می‌کند؛ اصل سند حذف یا بازنویسی نمی‌شود. دوره مالی فقط با مجوز سروری `rial.close_all` بسته می‌شود. عملیات به قفل `BEGIN IMMEDIATE` و CAS/append-only `RIALJournalStorage.mutate` متکی‌اند. Retry با `expectedRevision` به‌روز و payload یکسان idempotent است؛ retry با نسخه کهنه خطای تعارض می‌دهد و مستلزم تازه‌سازی است.

مجوزهای معتبر: `rial.read`, `rial.read_all`, `rial.post`, `rial.post_all`, `rial.reverse`, `rial.close_all`. خواندن بی‌فیلتر فقط برای `rial.read_all` مجاز است. خواندن پروژه‌ای نیازمند project grant یا دسترسی کلی است؛ نوشته/برگشت نیز به منبع پروژه‌ای مطابق grant محدود است.

## گیت ضروری تومان / ریال

`VerifiedIssuedDocument` فقط در شرایط زیر برای ثبت journal قابل قبول است:

* وضعیت معتبر سروری `status="issued"` و `currency="RIAL"` باشد؛ `amount_rial` از نوع `int` دقیق و مثبت باشد و جمع دو سمت سند دقیقاً با مبلغ فاکتور برابر شود. سطر دریافتنی فروش باید حساب `asset`، بدهکار و متعلق به همان شخص باشد؛ سطر پرداختنی خرید باید حساب `liability`، بستانکار و متعلق به همان شخص باشد.
* `source_verified=True`, `ledger_origin="rial_v2_only"`, `legacy_finance_status="none_verified"`. معنای `none_verified` این است که resolver سروری با شواهد پایدار ثابت کرده هیچ عملیات TOMAN همزمان یا سابقه معارض برای همان سند نیاز نیست. مقادیر `unknown`, `linked`, `legacy_toman` یا وضعیت `approved/draft` رد می‌شوند.
* Document، Chart، VerifiedScopes، CompanyMoneyPolicy و مرجع هر سطر برای همان شرکت و پروژه احراز شده باشند. Scope منبع task/checklist/independent باید دقیقاً به مالک معتبرش بخورد.

**توجه مهم به Prime:** `document.post` تنها journal posting برای سند RIAL که **قبلاً** توسط authority صادر و قفل شده است انجام می‌دهد؛ صدور فاکتور و ایجاد وضعیت `issued` خارج از دامنه آن است. اگر صدور سند فروش یا خرید باید همزمان در `accounting_service.py` / `accounting_core.py` فعلی (`TOMAN`) تغییر ایجاد کند، این endpoint باید **fail closed** باشد. ثبت در `UnifiedAppStorage` و SQLite ریالی دو تراکنش جدا هستند و crash-atomicity ایجاد نمی‌کنند. یک صفحه UI تازه با عنوان RIAL V2 نمی‌تواند این تفاوت مالی را رفع کند.

مسیر آینده برای صدور یکپارچه باید **یک مرز تراکنش** داشته باشد: یا تمام snapshot مالی و journal V2 با schema افزایشی و validator/rollback در همان `UnifiedAppStorage` ذخیره شوند، یا source invoice + journal را در یک SQLite connection/transaction واحد مدل کنیم، همراه با migration manifest و reconciliation مستقل اسناد TOMAN قبلی. هیچ‌کدام در این tranche پیاده‌سازی نشده‌اند؛ فعال‌سازی command برای invoice issuance پیش از آن مجاز نیست. اتصال **read-only** به Bridge با ACL معتبر می‌تواند جداگانه بررسی شود.

## شکل خروجی و حد آزمون

`read` شیء JSON-safe با `companyId`, `projectId`, `currency="RIAL"`, `revision`, `postingCount`, `closedFiscalPeriodIds`, `positions`, `entries` تولید می‌کند. `positions` برای پروژه انتخاب‌شده از سطرهای همان پروژه بازتجمیع می‌شود و مانده شرکت دیگر یا پروژه غیرمجاز برنمی‌گرداند. هر سطر در entry با `debitRial`, `creditRial` و ارجاعات هزینه/شخص/task برگردانده می‌شود. این خروجی API اختصاصی V2 است، نه `read_madar_accounting` قدیمی با `currency="TOMAN"`.

آزمون‌های مصنوعی: `python -B -m unittest discover -s tests -p test_ir_accounting_host_v2.py -v` با **۱۶ آزمون موفق**. تست هم‌زمانی آن هشت سند با شناسه‌های متفاوت و یک منبع تجاری را رقابتی ثبت می‌کند و موفقیت حداکثر یکی را می‌پذیرد. آزمون‌های وابسته `python -B -m unittest tests.test_ir_journal_sqlite tests.test_ir_journal_v2 tests.test_ir_chart_model tests.test_money_policy -q` نیز **۷۵ آزمون موفق** داشتند. اجرای آزمون‌ها روی دیتابیس موقت `TemporaryDirectory` است. هیچ آزمون E2E در EXE، LAN، دیتای واقعی، جریان فاکتور قدیمی یا مهاجرت انجام نشده؛ مجوزهای سمت desktop bridge و استحکام resolver واقعی هنوز نیازمند بررسی عملی هستند.
