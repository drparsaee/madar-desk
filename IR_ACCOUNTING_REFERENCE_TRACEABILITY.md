# ردیابی مرجع تاریخی حسابداری پارسیان به نیازمندی‌ها و سورس Madar Desk

**تاریخ snapshot:** ۲۰۲۶-۱۰-۲۱. **نوع بررسی:** خواندن آفلاین و فقط‌خواندنی راهنمای نصب‌شده **Parsian V10 / زمستان ۱۳۸۹**؛ تطبیق با سورس و تست‌های مدار. **هدف محصول:** حسابداری مستقل و متصل به تسک‌منیجر؛ نه مهندسی معکوس دیتابیس یا کپی رابط پارسیان.

## قوانین تفسیر این ماتریس

- **[M] مرجع تاریخی:** `C:\Program Files (x86)\Parsian\ParsianHelp.pdf` با ۲۱۲ صفحه. «PDF ۱۲» یعنی صفحه دوازدهم فایل؛ «چاپی ۱۱» یعنی عدد راهنمای تاریخی/فهرست. جدول صفحات را به صورت `PDF ... (چاپی ...)` نوشته است. ارجاع‌های بازه‌ای برای جست‌وجوی موضوع‌اند. PDF **نسخه ۱۰** است؛ `Parsian.EXE` نصب‌شده متادیتای **نسخه ۳۹** دارد، اما edition فعال و معادل بودن منوها معلوم نیست.
- **[C] در کد:** API/منطق در فایل واقعی پروژه مشاهده شده، اما نه الزاماً GUI قابل استفاده یا محصول پذیرفته‌شده. **[T] تست موضعی:** فایل تست در پروژه موجود یا نتیجه آزمون محدود قبلاً گزارش شده؛ معادل E2E روی EXE/داده واقعی نیست. **[G] شکاف:** اجرا نشده یا قابلیت مطابق نیازمندی تأیید نشده. **[U] مجهول:** نیازمند تصمیم دامنه، سند معتبر، تحقیق یا آزمون.
- ستون «**API/موجودیت پیشنهادی**» قرارداد **هدف** است، نه ادعای وجود فعلی endpointهای جدید. منبع حقیقت فعلی در بسیاری از جریان‌ها `Bridge.accountingCommand/Read` و `accounting_service.py` است.
- ارجاع `AC-n` به جدول **سناریوهای پذیرش** در `IR_ACCOUNTING_REQUIREMENTS_2026.md` است. پیوند مستقیم تسک در ستون آخر با `Task/Card`، `ChecklistStep`، `Project`، `CostSource` یا «مستقل» تعریف می‌شود؛ مستقل نیز می‌تواند cost-center/project dimension داشته باشد.
- هر جا PDF بخش تاریخی مالیات/حقوق دارد، **بند قانون و نرخ سال ۲۰۲۶ از آن نتیجه نمی‌شود**. «منو در راهنمای تاریخی» به معنای «فعال در Parsian v39» یا «قابل ورود از BAK» نیست.

## فهرست مسیرهای PDF و نسخه

| منبع دقیق | عنوان | شواهد/مرز کاربرد |
|---|---|---|
| **PDF ص۱** | جلد با شماره نگارش ۱۰ و زمستان ۱۳۸۹ | تاریخ و نسخه مرجع قدیمی، نه مستند نسخه ۳۹ |
| **PDF ص۴–۵** | فهرست فصل ۱ و آغاز فصل ۲ | سرفصل‌های حسابداری و چک/صندوق |
| **PDF ص۶–۷** | ادامه چک و فصل ۳ | چک، قسط، انبار، مرکز هزینه، کاردکس |
| **PDF ص۸–۹** | فصل ۴ و ۵ | انواع فاکتور، ماليات تاریخی، حقوق و دستمزد |
| **PDF ص۱۰** | فصل ۶ | بکاپ، سال مالی، کاربران و محافظ |
| **PDF ص۱۲–۶۸** | بدنه حسابداری؛ چاپی ۱۱–۶۷ | تعریف حساب‌ها، ثبت سند، دفتر و گزارش |
| **PDF ص۶۹–۱۰۱** | بدنه دریافت/پرداخت؛ چاپی ۶۸–۱۰۰ | خزانه، چک، اقساط |
| **PDF ص۱۰۲–۱۴۵** | بدنه انبار؛ چاپی ۱۰۱–۱۴۴ | کاردکس، انتقال/موجودی، انبارگردانی |
| **PDF ص۱۴۶–۱۸۹** | بدنه خرید/فروش؛ چاپی ۱۴۵–۱۸۸ | صدور، برگشت، مالیات، گزارش فاکتور |
| **PDF ص۱۹۰–۲۰۳** | حقوق و دستمزد؛ چاپی ۱۸۹–۲۰۲ | وابسته به نسخه/قوانین زمان خود |
| **PDF ص۲۰۴–۲۱۲** | سایر امکانات؛ چاپی ۲۰۳–۲۱۲ | پشتیبان، سال مالی، نقش‌ها |

**یادآوری ارجاع صفحه:** مرز پایان فصل‌ها و صفحات فهرست/بدنه ممکن است یک صفحه همپوشانی داشته باشد. پیش از طراحی یک فرم مشخص، صفحه مرجع در **همان PDF نصب‌شده** کنترل شود؛ متن به دلیل فونت و bidi گاهی در خروجی استخراج واژگان یا ارقام را وارونه نشان می‌دهد. در این جدول بر شواهد فصل، متن نمونه و صفحه‌های کنترل‌شده تکیه شده، نه بر ترتیب خام نویسه‌ها.

## ماتریس ردیابی فازبندی‌شده

| فاز / شناسه نیاز | راهنمای پارسیان V10، صفحه **PDF** (صفحه چاپی) | وضعیت مشاهده‌شده در Madar ۲۰۲۶ | API/موجودیت هدف یا موجود | آزمون پذیرش | پیوند با تسک‌منیجر |
|---|---|---|---|---|---|
| **P0 / IR-FND-01** منبع حقیقت مالی | PDF **۲۸–۳۰** (۲۷–۲۹) سند حسابداری؛ **۱۴۷** (۱۴۶) فاکتور | [C,T] event-sourced GL در `accounting_core.py`، ارجاع منبع و CAS در `accounting_service.py/native_app.py`؛ [G] E2E کامل همه فرم‌ها | موجود `accountingCommand`، `JournalEvent`؛ هدف `FinanceSourceLink`, `AtomicPosting` | **AC-01, AC-02, AC-06** | `Task.id → SourceReference → Document.id` |
| **P0 / IR-FND-02** واحد پول و دامنه گزارش | PDF **۱۲۹** (۱۲۸) «موجودی ریالی»؛ **۱۶۵** (۱۶۴) مالیات | [C] GL فقط `TOMAN` صحیح؛ [G] واحد پول تاریخی پارسیان/تبدیل احرازنشده؛ project report سراسری باید صریح بماند | `Money(unit,amount)`, `CurrencyEvidence`, `ReportScope` | **AC-05, AC-23, AC-29** | مبلغ task/cost و invoice فقط با واحد آشکار |
| **P0 / IR-FND-05** دسترسی نقش/محرمانگی | PDF **۲۱۰** (۲۰۹) کاربران؛ **۲۱۲** (۲۱۲) محافظ | [C,T] `lan.py` مجوز read/write مالی را سمت میزبان کنترل می‌کند؛ `finance_visibility.py` redaction؛ [G] آزمایش چنددستگاهی/مدل ریزمجوز مالی | موجود `AuthenticatedActor`؛ هدف `FinancePermission`, `AuditAccess` | **AC-03, AC-11** | مجوز سطح `Project` و `Card.saleUnitPrice` |
| **P0 / IR-PERIOD-03** بکاپ و Restore قابل اتکا | PDF **۲۰۵–۲۰۶** (۲۰۴–۲۰۵) | [C,T] `Bridge.createLocalBackup/restoreLocalBackup` برای SQLite؛ `complete=false` و فاقد پیوست/LAN/Planner؛ `maintenance_recovery.py` مسیر آفلاین جامع‌تر | `BackupManifest(scope,omitted)`, `RestorePlan`, `RecoveryAudit` | **AC-04, AC-25** | بازیابی همزمان `Task` و مالی، بدون از دست دادن لینک |
| **P0 / IR-SALES-03** idempotency و جلوگیری از فروش تکراری | PDF **۱۴۷–۱۶۴** (۱۴۶–۱۶۳) فرم فاکتور؛ رفتار idempotency مدرن **در PDF اثبات نشده** | [C,T] شناسه event یکتا، fingerprint/source guard و برگشت تاریخی در GL؛ UI عملیاتی هنوز باید smoke شود | موجود `eventId`, `accountingSources`؛ هدف `InvoiceSourceUniqueness` | **AC-01, AC-06, AC-12** | صدور دوم برای `Task.id` قبلاً صادرشده مردود |
| **P1 / IR-ACCT-01a** حساب کل | PDF **۱۳–۱۶** (۱۲–۱۵) | [C] `account.create` با kind و کد دارد؛ [G] سلسله‌مراتب حساب کل با migration پدر/فرزند | هدف `ChartAccount(id,level='kol',parentId)` | **AC-07** | مستقل؛ بُعد پروژه فقط برای تحلیل |
| **P1 / IR-ACCT-01b** معین/اشخاص | PDF **۱۷–۲۱** (۱۶–۲۰)، **۱۸** هشدار سقف اعتبار | [C] `party.register` و حساب‌های AR/AP؛ [G] کد معین سلسله‌مراتبی و اعتبارسنجی سقف اعتبار مشتری | `SubledgerAccount`, `Counterparty`, `CreditLimitPolicy` | **AC-07, AC-11** | `Task.customerId` به person master؛ نه نام آزاد مبهم |
| **P1 / IR-ACCT-01c** تفصیلی و گروه حساب | PDF **۲۲–۲۴** (۲۱–۲۳)، **۲۲** وابستگی نگارش | [G] GL حساب قابل ساخت دارد؛ کد تفصیلی چندسطحی و طبقه‌بندی واقعی در سورس تأیید نشده | `AnalyticalAccount`, `AccountGroup`, `DimensionCode` | **AC-07** | تفصیلیِ شخص/پروژه/مرکز هزینه مستقل از تسک |
| **P1 / IR-ACCT-02** سند روزنامه دوبل | PDF **۲۸–۳۹** (۲۷–۳۸) | [C,T] `journal.manual` با ۲–۱۰۰ ردیف متوازن، `journal.reverse` و `period.close` در `accounting_core.py`؛ [G] گردش چاپ اسناد و شماره‌گذاری رسمی | موجود `journal.manual`؛ هدف `JournalEntry/Line/PostingSequence` | **AC-08** | `JournalLine.sourceCardId` اختیاری و غیرقابل جعل |
| **P1 / IR-ACCT-03** دفتر روزنامه/کل/معین | PDF **۴۰–۴۵** (۳۹–۴۴)؛ **PDF ۴۲** دفتر کل | [C,T] `accounting_reporting.ledger_reports` گزارش گردش حساب/تراز دارد؛ [G] دفتر معین/تفصیلی قانونی و خروجی معتبر چاپ | `JournalBook`, `GeneralLedgerReport`, `SubledgerReport` | **AC-09** | drilldown سند → شخص → `Task/ChecklistStep` |
| **P1 / IR-ACCT-04** سودوزیان، ترازنامه، مانده اشخاص | PDF **۴۶–۶۸** (۴۵–۶۷)؛ **۵۳–۵۴** کارت حساب/بدهکاران | [C,T] `accounting_reporting.py` گزارش تراز، سودوزیان، ترازنامه سراسری دارد؛ project filtered `reports=null`؛ [G] گزارش‌های تفصیلی/چاپ | `TrialBalance`, `IncomeStatement`, `BalanceSheet`, `PartyStatement` | **AC-09, AC-10, AC-11** | گزارش پروژه بدون double-count یا projection کاذب |
| **P1 / IR-SALES-01** صدور فاکتور فروش از تسک | PDF **۱۴۷–۱۶۵** (۱۴۶–۱۶۴)؛ **۱۴۷** انتخاب مشتری/کالا | [C,T] در `src/App.jsx` ارسال کارت به فروش، `accounting_service.py` `draft.sales.fromTask`؛ قیمت فروش مجزا از cost | `SalesInvoice`, `InvoiceLine`, `TaskSalesSource` | **AC-01, AC-14** | `Card.id`, `Project.id`, مقدار و قیمت صریح |
| **P1 / IR-SALES-02** فروش standalone و دریافت تخصیصی | PDF **۷۰–۷۱** (۶۹–۷۰) دریافت/تسویه؛ **۱۴۷** (۱۴۶) | [C,T] `document.create`, `receipt.record`، AR و مانده مشتری؛ [G] اثبات بانکی شبکه‌ای و فرم همه‌حالت‌ها | `SalesInvoice`, `Receipt`, `SettlementAllocation` | **AC-01, AC-14** | مستقل یا پیوند task؛ پیش‌دریافت ادعایی ≠ دریافت |
| **P1 / IR-PURCH-01** دریافت تأمین‌کننده روی گام بی‌قیمت | PDF **۱۷۹** (۱۷۸) فاکتور خرید؛ **۱۰۳–۱۱۳** کالا/خدمات. **الزام بی‌قیمت ویژه مدار است، نه ادعای PDF** | [C,T] `purchase_intake.py` ایجاد بی‌قیمت، `intake.price`, `intake.convert`; فاکتور ابتدا Draft | `PurchaseIntake`, `Supplier`, `TaskStepSource` | **AC-02** | `ChecklistStep.id → Intake.id` |
| **P1 / IR-PURCH-02** بستانکاری تأمین‌کننده و پرداخت | PDF **۱۷۹** (۱۷۸) خرید؛ **۷۲–۷۶** (۷۱–۷۵) پرداخت/تسویه | [C,T] `draft.purchase.fromCosts`, `bill.issue`, `payment.record`, AP و کنترل موجودی نقد در GL؛ [G] اثبات پرداخت بیرونی | `PurchaseBill`, `AccountsPayable`, `Payment` | **AC-02, AC-03** | `CostSource → Bill → AP → Payment` |
| **P1 / IR-PURCH-03** مرکز هزینه پروژه/تسک | PDF **۱۱۶–۱۲۱** (۱۱۵–۱۲۰)، **۱۱۶** شرط نگارش پیشرفته | [C] `Project.id` و cost task در `finance.py`؛ [G] مرکز هزینه مستقل متصل به تمامی JournalLineها | `CostCenter`, `CostAllocation`, `ProjectDimension` | **AC-13** | `Task.projectId`, `TaskStep.id`, تخصیص مالی |
| **P1 / IR-SALES-03b** برگشت/اصلاح و سند کاهنده | PDF **۱۸۰** (۱۷۹) برگشت از خرید/فروش | [C,T] `document.cancel` فقط پیش از صدور، `journal.reverse` پس از صدور؛ [G] Credit/Debit Note کامل با مالیات/انبار | `CreditNote`, `DebitNote`, `ReversalLink` | **AC-12** | برگشت همواره به invoice و source task قبلی ارجاع دهد |
| **P2 / IR-TRSY-01** خزانه نقد/بانک و تسویه | PDF **۷۰–۷۶** (۶۹–۷۵) | [C,T] `receipt.record`, `payment.record`, `funds.transfer` حساب‌های نقد و بانک داخلی؛ [G] تطبیق statement بانکی/بانک واقعی | `CashAccount`, `BankAccount`, `CashMovement`, `BankStatement` | **AC-19** | فاکتور منشأ task، receipt/pay تخصیص به سند |
| **P2 / IR-TRSY-02** تنخواه و اسناد هزینه | PDF **۶۹–۷۶** دریافت/پرداخت؛ **تنخواه مستقل صریح در این نمونه‌صفحات احراز نشده** | [G] تنخواه مسئول/سقف/تسویه مستقل ندارد | `PettyCashFund`, `ExpenseClaim`, `FundCustodian` | **AC-18** | هزینه/رسید می‌تواند به `Task.id` متصل باشد |
| **P2 / IR-TRSY-03** چک دریافتنی/پرداختنی | PDF **۶۹–۸۰** (۶۸–۷۹) صدور/دریافت، خرج، برگشت/پاس | [G] `funds.transfer` ≠ مدیریت چک؛ `Cheque` و state-machine تأیید نشده | `Cheque`, `ChequeStatusEvent`, `ChequeSettlementLink` | **AC-15, AC-16** | چک مرتبط با invoice و بدهی شخص متصل به task |
| **P2 / IR-TRSY-04** سررسید، دسته‌چک، رأس‌گیری و اقساط | PDF **۸۱–۱۰۱** (۸۰–۱۰۰)، **۹۴** رأس‌گیری | [G] هیچ API معتبر cheque due/installment schedule در هسته GL موجود دیده نشد | `ChequeBook`, `MaturityAlert`, `InstallmentSchedule` | **AC-17** | reminder فقط مجاز و بدون PII، لینک به source |
| **P2 / IR-STOCK-01** کاتالوگ کالا/خدمات | PDF **۱۰۳–۱۱۵** (۱۰۲–۱۱۴) | [C,T] `item.create/item.update` با SKU و `stockTracked=false`، شرح/واحد؛ [G] موجودی و چندواحدی عملیاتی | `CatalogItem`, `UnitOfMeasure`, `ItemGroup` | **AC-20** | سطر تسک `itemId` اختیاری؛ هویت SKU مستقل |
| **P2 / IR-STOCK-02** انبار و کاردکس | PDF **۱۰۲–۱۰۳** (۱۰۱–۱۰۲) تعریف انبار؛ **۱۲۶–۱۳۴** (۱۲۵–۱۳۳) کاردکس/موجودی | [G] ledger مقدار/ارزش و گزارش کاردکس وجود ندارد؛ catalog به‌اشتباه stock تلقی نشود | `Warehouse`, `StockMovement`, `KardexRow`, `ValuationLayer` | **AC-21** | خرید گام می‌تواند سند ورود جدا از `PurchaseBill` بسازد |
| **P2 / IR-STOCK-03** برگشت، انتقال، انبارگردانی | PDF **۱۴۳** (۱۴۲) انبارگردانی؛ **۱۸۰–۱۸۲** (۱۷۹–۱۸۱) برگشت/انتقال/تولید | [G] انبارگردانی و برگشت دوطرفه مالی-موجودی پشتیبانی تأییدشده ندارد | `StockCount`, `StockAdjustment`, `StockTransfer`, `ReturnDocument` | **AC-22** | source `TaskStep` و PO/Invoice حفظ شود |
| **P2 / IR-STOCK-04** موجودی امانی، نقطه سفارش | PDF **۱۳۵–۱۴۳** (۱۳۴–۱۴۲) | [G] فاقد `Consignment`/reorder alert واقعی | `ConsignmentStock`, `ReorderPoint`, `InventoryException` | **AC-23** | پیشنهاد خرید برای task/پروژه، نه ایجاد AP خودکار |
| **P3 / IR-PERIOD-01** سال مالی، افتتاحیه و اختتامیه | PDF **۲۰۷–۲۰۹** (۲۰۶–۲۰۸)؛ **PDF ۲۰۷** انتقال چک و اقساط | [C] `period.close` محدود و immutable؛ [G] سند اختتامیه/افتتاحیه و انتقال سال کامل | `FiscalYear`, `OpeningJournal`, `ClosingJournal`, `CarryForward` | **AC-24** | گردش مالی task بین دو سال با provenance ثابت |
| **P3 / IR-IRAN-01** تقویم جلالی و تاریخ | PDF **۱۹۰–۲۰۱** (۱۸۹–۲۰۰) مثال سال/ماه حقوق؛ **۲۰۷** سال مالی | [C] ورودی تاریخ حسابداری canonical؛ [U/G] تضمین رسمی conversion جلالی و سال کبیسه در تمام UIها اثبات نشده | `AccountingDate`, `JalaliPresentation`, `FiscalCalendar` | **AC-26** | مهلت Task و تاریخ سند مستقل، بدون جابه‌جایی روز |
| **P3 / IR-IRAN-02** مالیات و VAT زمان‌مند | PDF **۱۶۵–۱۶۶** (۱۶۴–۱۶۵) تنظیم تاریخی مالیات هر کالا/فاکتور | [C] مبلغ tax صریح به journal می‌رود؛ [G] موتور نرخ/سیاست/معافیت زمان‌مند و انطباق امروزی | `TaxPolicyVersion`, `TaxCode`, `TaxBreakdown` | **AC-27** | tax line به فاکتور task/کالا مربوط، نه task cost |
| **P3 / IR-IRAN-03** صورتحساب الکترونیکی/سامانه مؤدیان | **بدون مرجع نسخه ۱۳۸۹**؛ فقط قیاس UX فاکتور در PDF **۱۴۷–۱۶۶** | [G] اتصال مستند قانونی/e-invoicing فعلی در مدار احراز نشده؛ **هیچ حکم قانونی روز از این PDF نتیجه نشود** | `ElectronicInvoiceSubmission`, `TaxAuthorityAck`, `CredentialVault` | **AC-28** | فاکتور صادرشده task یا standalone با وضعیت ارسال |
| **P3 / IR-IRAN-04** حقوق و دستمزد | PDF **۱۹۰–۲۰۱** (۱۸۹–۲۰۰) | [G] ماژول payroll امن و مقررات‌تأییدشده حاضر نیست | `Employee`, `PayrollPeriod`, `PayrollJournal` | **AC-30** | مستقل از تسک مالی؛ فقط هزینه پروژه با اختیار صریح |
| **P3 / IR-MIG-01** مهاجرت رکوردهای تاریخی پارسیان | **هیچ schema/BAK mapping** در PDF وجود ندارد؛ فقط واژگان تاریخی PDF **۴–۱۰** | [C,T] `parsian_backup_probe.py` تشخیص `TAPE` و `parsian_migration_staging.py` manifest/validation آفلاین؛ [G] Import واقعی صفر؛ واحد RIAL/TOMAN نامعلوم | `MigrationManifest`, `VerifiedCurrencyUnit`, `SchemaMapping`, `Reconciliation`, `MigrationBatch` | **AC-29** | واردکردن مراجع به `Task` فقط پس از تطبیق و عدم دوبل |
| **P3 / IR-PERIOD-02** بازیابی جامع قبل از migration | PDF **۲۰۵–۲۰۶** (۲۰۴–۲۰۵) راهنمای تاریخی backup | [C,T] مسیر آفلاین `full_recovery.py/maintenance_recovery.py` برای دامنه‌های بیشتر؛ [G] تضمین بازگردانی Planner/تمام secrets و full user UAT ندارد | `RecoveryManifest`, `PreMigrationCheckpoint`, `RollbackPlan` | **AC-25, AC-29** | قبل از import، snapshot قابل‌تطبیق مالی+تسک |

## تقدم‌ها و وابستگی‌های عملی

1. **قبل از هر دیتای واقعی:** AC-01..06 (فاکتور تسک/گام، دسترسی، restore، واحد پول و idempotency) + نسخه دقیق build و تست UI/Windows/LAN. سبزبودن unittest به‌تنهایی اجازه انتشار نیست.
2. **قبل از ادعای حسابداری عمومی کامل:** سلسله‌مراتب واقعی کل/معین/تفصیلی، سند دستی و دفتر/گزارش قابل reconcile با GL، افتتاحیه، داده شخص و کنترل حوزه شرکت. `account.create` ساده را با تفصیلی کامل یکی ندانید.
3. **قبل از ادعای بانک/انبار:** `funds.transfer` را جایگزین تسویه واقعی بانک، دفتر چک یا صورت‌حساب نکنید؛ `item.create` با `stockTracked=false` به معنای کاردکس نیست.
4. **قبل از ادعای انطباق در ایران:** منبع رسمی *به‌روز*، بازبینی مالیاتی/حقوقی، نسخه‌گذاری سیاست، آزمون صورتحساب و نگهداری امن مراجع قانونی. راهنمای سال ۱۳۸۹ هیچ تعهد ۲۰۲۶ را ثابت نمی‌کند.
5. **قبل از migration پارسیان:** فقط یک نسخه **مجاز و منفصل** در محیط SQL Server ایزوله توسط فرد مجاز بررسی شود؛ schema و روابط، واحد صحیح مبلغ، تقویم و تراز افتتاحیه/اختتامیه مستقلاً تصدیق شوند. Header `TAPE` **فاقد اطلاعات schema** است. هیچ دسترسی به BAK/MDF/SQL یا import در این تحلیل انجام نشده.

## منابع بازبینی‌شده (فقط‌خواندنی)

### مرجع تاریخی نصب‌شده

- `C:\Program Files (x86)\Parsian\ParsianHelp.pdf`، ۲۱۲ صفحه. فهرست PDF ص۴–۱۰، متن نمونه PDF ص۱۲، ۱۸، ۲۲، ۲۸، ۴۲، ۵۳، ۵۴، ۶۹، ۷۰، ۷۷، ۸۱، ۹۴، ۱۰۲، ۱۰۳، ۱۱۶، ۱۲۶، ۱۴۶، ۱۴۷، ۱۶۵، ۱۷۹، ۱۹۰، ۲۰۴، ۲۰۵، ۲۰۷ و ۲۱۲.
- `C:\Program Files (x86)\Parsian\Parsian.EXE` **صرفاً** متادیتای نسخه (39.0.0.0؛ نسخه راهنما 10). هیچ باینری اجرایی برای استخراج کد باز نشده است.

### قراردادها/سورس فعلی مدار

- `ACCOUNTING_REARCHITECTURE_2026-10-21.md`: تفکیک محیط حسابداری، intake بی‌قیمت، گزارش‌ها، داده ناقص و migration gate.
- `ACCOUNTING_CORE_API.md`, `ACCOUNTING_MADAR_IMPLEMENTATION_2026-10-21.md`: هسته GL و مسیریابی task→فروش و expense→خرید؛ **یادداشت‌های قدیمیِ وضعیت integration در فایل‌های worker نباید جدیدتر از سورس تلقی شوند.**
- `accounting_core.py`, `accounting_service.py`, `purchase_intake.py`, `accounting_reporting.py`, `finance.py`, `finance_visibility.py`, `finance_reference_guard.py`, `native_app.py`, `lan.py`.
- `src/accounting_workspace.jsx`, `src/App.jsx`; آزمون‌های `tests/test_accounting_catalog_standalone.py`, `tests/test_accounting_reporting.py`, `tests/test_accounting_manual_bank.py`, `tests/test_purchase_intake.py` و `tests/test_user_acceptance_workflows.py` (وجود در سورس، نتایج کامل release باید جدا کنترل شوند).
- `BACKUP_SCOPE_V1.md`, `MAINTENANCE_RECOVERY.md`, `PARSIAN_MIGRATION_STAGING.md`.

## نتیجه ردیابی

**پایه در کد مدار:** حسابداری دوبل با رویداد، مشتری/تأمین‌کننده، دریافت/پرداخت تخصیصی، draft→issue، پیوند کارت به فروش، گام/هزینه به خرید، کاتالوگ ساده، انتقال نقد داخلی، سند دستی و گزارش سراسری. **پیش از تکمیل و ادعای تولید:** تفصیلی چندسطحی، انبار/کاردکس و valuation، دفتر چک/اقساط و بانک واقعی، بستن سال کامل، چاپ قانونی/صورتحساب الکترونیکی، مهاجرت قابل تطبیق و پذیرش GUI+LAN+Backup.

**نتیجه منبع‌شناسی:** قابلیت‌های فوق از راهنمای **V10، سال ۱۳۸۹** به‌عنوان هدف نیازمندی استخراج شده‌اند. اینکه کدام‌یک در نصب **Parsian V39** فعال‌اند، از PDF قابل اثبات نیست. نبود داده مالی خصوصی در این تحلیل عمدی است؛ ردیابی «نیاز» جای اثبات «سازگاری بکاپ و جداول» را نمی‌گیرد.
