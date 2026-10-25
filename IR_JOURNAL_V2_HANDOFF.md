# هسته مستقل روزنامه ریالی مدار (P0 / IR-JOURNAL-V2.1)

**وضعیت:** pure candidate و آزمون مصنوعی؛ **هیچ اتصالی به accounting_core.py، finance.py، native_app.py، App.jsx، SQL، LAN یا UI انجام نشده است**. داده‌های واقعی، APPDATA، پارسیان و release دست‌نخورده‌اند.

**فایل‌های تحویل، فقط سه فایل جدید:** ir_journal_v2.py، tests/test_ir_journal_v2.py، IR_JOURNAL_V2_HANDOFF.md.

وابستگی‌های فقط خواندنی: money_policy.py (قبلاً frozen) و ir_chart_model.py (worker-9، موجود و قابل import).

## وضعیت قابلیت‌ها

| حوزه | قرارداد پیاده‌شده |
|---|---|
| ارز | فقط RIAL صحیح در تمام debit_rial/credit_rial؛ MAX_RIAL برابر 2^53-1؛ هیچ float یا گردکردن |
| تفکیک شرکت | company_id اجباری در State، Period، Chart، Journal Event و تمام Account PostingReferenceها |
| دوره مالی | FiscalPeriod با شناسه شرکت و start/end معتبر و بدون همپوشانی؛ سند فقط در تاریخ متعلق به دوره باز |
| سند دوبل | JournalLine با دقیقاً یک ستون مثبت، ۲ تا ۱۰۰ سطر؛ جمع بدهکار=بستانکار>0 |
| کدینگ حساب | اعتبارسنجی مستقیم ChartSnapshot و validate_posting_reference از ir_chart_model؛ حساب گروهی، غیرفعال، frozen یا بایگانی رد می‌شود |
| منبع | JournalSource به یکی از task/card/checklist/independent مقید است؛ مدارک مالکیت مستقل در VerifiedScopes |
| مرکز هزینه | اختیاری برای هر PostingReference، اما اجباری اگر حساب نیازمند باشد؛ هم‌پروژه‌ای بودن و ارتباط job/task بررسی می‌شود |
| ثبت تکراری | event_id + digest کاملِ فرمان و chart evidence؛ تکرار دقیق با revision فعلی no-op و تغییر payload با همان شناسه Conflict |
| CAS | expected_revision باید با revision state برابر باشد؛ تراکنش ذخیره‌سازی اتمیک هنوز در host نیست |
| replay | تمام eventهای immutable از ابتدا با hash chain، fingerprint، chart و scope تاریخی بررسی می‌شوند؛ مانده از cache خوانده نمی‌شود |
| بستن دوره | close_fiscal_period رویداد immutable می‌سازد؛ بستن زودهنگام/آینده یا دوره جدید قبل از دوره قبلی ممنوع |
| برگشت | reverse_journal سند اصلی را نگه داشته و سند وارونه جدید در دوره باز ثبت می‌کند؛ برگشت دوباره و برگشت سند برگشتی رد می‌شود |

## قرارداد API خالص

- new_journal_state(company_id, periods: tuple[FiscalPeriod,...]) -> JournalState
- post_journal(state, company_id, fiscal_period_id, event_id, actor_id, posting_date, source, lines, chart, scopes, money_policy, expected_revision, today) -> JournalState
- close_fiscal_period(state, company_id, fiscal_period_id, event_id, actor_id, closing_date, expected_revision, today) -> JournalState
- reverse_journal(state, company_id, original_event_id, event_id, actor_id, fiscal_period_id, posting_date, reason, expected_revision, today) -> JournalState
- replay_journal(state) -> ReplayResult شامل closed_period_ids، reversed_event_ids و positions ریالی.

مثال شفاف و ایزوله: شرکت company-1، دوره FY26، منبع مستقل سند invoice-1، دو خط بانک بدهکار 101 ریال و درآمد بستانکار 101 ریال، تاریخ ثبت در دوره باز؛ خروجی replay دارای مانده بدهکار 101 و بستانکار 101 است. **یک ریال نیز دقیق باقی می‌ماند**.

## یکپارچگی دقیق با مدل حساب ایرانی

ChartSnapshot و PostingReference **مستقیماً** از ir_chart_model.py وارد شده‌اند؛ هیچ fallback بدون کدینگ معتبر نیست.

برای هر خط، reference شامل company_id، account_code و ابعاد اختیاری detail_code، party_id، project_id، cost_center_code، job_id و task_id است. validate_posting_reference با مجموعه‌های host-verified از VerifiedScopes کنترل می‌کند که حساب واقعاً فعال و برگ قابل ثبت باشد، تفصیلی و طرف‌حساب معتبر باشد، و job/center/task با همان پروژه مطابقت داشته باشند.

VerifiedScopes باید در **میزبان احراز هویت‌شده** ساخته شود، نه براساس درخواست UI:

- party_ids: مجموعه معتبر اشخاص همان شرکت؛
- project_ids: پروژه‌های متعلق به همان شرکت؛
- task_scopes: جفت‌های دقیق (project_id, task_id)؛
- checklist_scopes: سه‌تایی‌های دقیق (project_id, task_id, checklist_id)، به‌همراه task scope؛
- independent_source_scopes: جفت‌های دقیق (project_id, document_id). پروژه خالی تنها برای سند مستقل سراسری که صریحاً با جفت ("",document_id) احراز شده معتبر است؛ **wildcard نیست**.

در هر رویداد، ChartEvidence شامل snapshot تاریخی chart، مجموعه scopes و سقف همان policy به‌صورت immutable نگهداری می‌شود و SHA-256 از آن ساخته می‌شود. replay دوباره تمام شواهد و ارجاع‌ها را تأیید می‌کند. ازاین‌رو آرشیو/غیرفعال‌شدن یک حساب بعد از ثبت، نباید تاریخچه را بازنویسی کند؛ برگشت تاریخی از evidence همان سند اولیه استفاده می‌کند.

**گیت باز:** میزبان باید chart snapshot و validate_chart_transition(old,new) را با هر نسخه تغییر کدینگ در تراکنش معتبر ذخیره کند، و پس از posting واقعی lock_posted_account را برای حساب مصرف‌شده اعمال کند. Kernel نمی‌تواند به‌تنهایی اصالت مجموعه‌های VerifiedScopes یا مجوز actor_id را اثبات کند.

## Immutable، idempotency و خطرات دیتابیس

تمام رکوردهای JournalState، PostedJournal، ClosedPeriod، JournalLine، FiscalPeriod و ChartEvidence از dataclassهای frozen و slots استفاده می‌کنند؛ توابع عملیاتی فقط State جدید برمی‌گردانند و سند/رویداد قبلی را ویرایش نمی‌کنند.

- زنجیره hash و command digest برای تشخیص تغییرات است، **امضای دیجیتال مستقل نیست**. کسی که DB را کامل بازنویسی می‌کند می‌تواند زنجیره جدید بسازد. Anchor کردن head hash در audit log امضاشده یا خارج از DB هنوز مسئولیت میزبان است.
- CAS این ماژول optimistic preflight است و atomic commit نیست. میزبان باید ذخیره رویداد، chart snapshot، شناسه یکتای event، revision و audit را در یک تراکنش SQL با rollback واقعی انجام دهد.
- جلوگیری از تکرار به event_id محدود است. دو فرمان با event_id متفاوت که به یک فاکتور تجاری یکسان اشاره کنند، هنوز ممکن است؛ **unique business-source constraint** و تطبیق صدور invoice در adapter میزبان ضروری است.
- «سند قطعی فاکتور» هنوز در این kernel موجودیت مستقل ندارد. هنگام اتصال، میزبان باید issued invoice/bill را به immutable posted snapshot با money_policy.freeze_posted_document و یک journal event معتبر پیوند بزند؛ اصلاح سند قطعی فقط با reversal + سند جدید باشد.
- این هسته هنوز cash liquidity، بدهکار/بستانکار اشخاص AR/AP، سررسید چک، مالیات، خرید انباری، گردش ارز یا وضعیت واقعی بانک را مدیریت نمی‌کند. تراز بدهکار/بستانکار جای این کنترل‌ها نیست.
- نمایش/ورود تومان از money_policy در boundary UI انجام می‌شود؛ هسته سند فقط صحیح ریال می‌پذیرد. سقف شامل مقدار سطر، جمع سند، مانده، جمع گردش و مجموع دفتر است تا JSON Number در client دقت را از دست ندهد.

## دوره‌های مالی

دوره‌های معتبر و بدون همپوشانی هنگام ساخت JournalState تعریف می‌شوند. close_fiscal_period فقط بعد از پایان دوره و پیش از زمان trusted today میزبان می‌تواند رویداد بستن ایجاد کند. پس از بستن، سند جدید یا برگشت سند در آن دوره ممنوع است؛ برگشت در دوره باز بعدی با دلیل صریح انجام می‌شود. بازکردن دوباره دوره و ایجاد دوره‌های آینده، به فرایند مدیریتی audited/CAS میزبان نیاز دارد و این ماژول فعلاً آن workflow را ارائه نمی‌کند.

## گیت‌های اتصال باقی‌مانده

1. **هویت شرکت و ACL:** company_id، actor_id، منبع task/card/checklist/independent، مالکیت شخص/پروژه از داده authoritative host استخراج شود. Client حق عرضه scope جعلی ندارد.
2. **Chart transition:** منبع chart معتبر و نسخه‌بندی‌شده، قفل‌کردن حساب دارای سند، کنترل نسخه به همراه رویداد و CAS اتمیک.
3. **Invoice workflow:** اتصال create/review/issue سند فروش/خرید و AR/AP، کنترل business source duplication، ثبت immutable snapshot و مشخص‌کردن سطرهای بدهکار/بستانکار واقعی.
4. **Period management:** تعیین و تمدید دوره‌ها، کنترل مجوز بستن، مستندکردن تقویم مالی/قوانین کشور و سیاست backdating.
5. **Database/CAS:** ذخیره immutable event و head hash، idempotent retry بعد از timeout، uniqueness و transaction isolation با آزمون دو کاربر هم‌زمان.
6. **Reports:** دفتر روزنامه، کل/معین/تفصیلی، مانده اشخاص و مرکز هزینه، تراز آزمایشی و گزارش‌های شرکت/دوره از ReplayResult؛ هنوز فقط account positions محاسبه می‌شود.
7. **Migration:** نگاشت صریح ledger قدیمی TOMAN و حساب تخت به RIAL + ChartSnapshot ایرانی، افتتاحیه با تراز تطبیق‌شده و manifest معتبر؛ **بدون تبدیل خودکار**.
8. **پذیرش:** backtest synthetic، تست SQL ایزوله، UX و Windows EXE، و مدرک audit قبل از استفاده روی داده واقعی.

## دستور تست

python -B -m unittest discover -s tests -p test_ir_journal_v2.py -q

پوشش synthetic: یک ریال دقیق، مبلغ بزرگ زیر سقف امن، تراز دوبل، گروه/حساب نامجاز، شرکت و پروژه متفاوت، cost-center و task، تکرار و تعارض digest، revision stale، دوره بسته، برگشت و برگشت دوباره، تغییر snapshot/hash و حتی سندی با fingerprint دوباره محاسبه‌شده ولی **تراز نامعتبر**.

هیچ تست واقعی روی SQL/APPDATA یا برنامه پارسیان انجام نشده است؛ فایل‌های موجود accounting_core.py، money_policy.py، finance.py، native_app.py، UI، Git و release تغییر نکرده‌اند.
