# Commercial Source Guard | قرارداد مستقل کنترل منشأ تجاری فروش و خرید

## وضعیت و نتیجه

فایل ir_commercial_source_guard.py فقط یک مدل و preflight **pure / read-only / fail-closed** است. آزمون مصنوعی در tests/test_ir_commercial_source_guard.py قرار دارد. این ماژول به میزبان فعال، APPDATA، پایگاه داده، پارسیان، Git، UI یا EXE وصل نشده، هیچ سندی صادر/ثبت نمی‌کند و هیچ کلیدی را در دیتابیس رزرو نمی‌کند. سه فایل این tranche جدیدند؛ فایل‌های مشترک و زیرسیستم‌های قدیمی تغییری نکرده‌اند.

## مشاهدات واقعی از سورس ۲۲ اکتبر ۲۰۲۶

| منبع | وضعیت صدور | شناسه سند و شناسه رویداد | ملاحظه |
|---|---|---|---|
| finance.py | ledger action = invoice.issue | invoiceId و eventId | فروش قدیمی با مانده و کل مبلغ TOMAN؛ مبلغ باید از invoice.sale.total معتبر در میزبان استخراج شود، نه از UI |
| accounting_core.py | journal sourceType = invoice.issue | sourceId = invoiceId؛ eventId | فروش موجود در accounting subledger؛ تکرار بین دو خانواده ledger قدیمی بدون قرارداد صریح مجاز نیست |
| accounting_core.py | journal sourceType = bill.issue | sourceId = billId؛ eventId | خرید قدیمی با کل مبلغ TOMAN؛ شناسه، قیمت و party باید با issued bill تطبیق داده شود |
| ir_journal_v2.py | PostedJournal | event_id و source (task/card/checklist/independent) | اصل ثبت RIAL است؛ source ممکن است کارت/تسک باشد و الزاماً شناسه invoice/bill نیست؛ reversing نباید مالکیت منبع را آزاد کند |
| ir_company_registry.py | stable_financial_source_id | co. + SHA-256(company, project, canonical kind, document) | شناسه هویت تجاری پایدار؛ یک رویداد V2 قدیمی ممکن است source متفاوتی داشته باشد و فقط با binding معتبر به این هویت ربط پیدا می‌کند |

app_storage.py اکنون از _protect_rial_finance_history و compose_finance_rial_snapshot برای sales mirror و compose_purchase_issue_with_rial برای purchase استفاده می‌کند؛ در بعضی مسیرها شرط محدودکننده «تنها یک شرکت فعال» دارد. نگاشت حقوقی واقعی project→company در host و اتصال گارد جدید موجود نیست. RIALAccountingHost.command(document.post) در ir_accounting_host_v2.py از مسیر مجزای RIALJournalStorage استفاده می‌کند و نیز به این گارد وصل نشده است.

## هویت canonical

CommercialIdentity(company_id, project_id, kind, document_id) immutable است. kind فقط یکی از sale، sales یا purchase است؛ sale و sales به sale تبدیل می‌شوند و purchase به purchase. عنوان مبهم مثل invoice، bill، item، credit، cost یا حروف بزرگ و whitespace رد می‌شود. این‌ها source type نیستند و بدون دانش زمینه نمی‌توان آنها را sale یا purchase فرض کرد.

محاسبه identity.registry_source_id به ir_company_registry.stable_financial_source_id واگذار می‌شود؛ الگوریتم hashing رجیستری اینجا بازنویسی نشده است. همچنین resolve_project_company موجود برای تطبیق project→company دقیق با registry و proof host فراخوانی می‌شود؛ اگر پروژه به هیچ شرکت یا به بیش از یک شرکت نسبت داده شده باشد، خطا می‌دهد.

CommercialV2Binding می‌گوید یک JournalSource دقیق متعلق به کدام CommercialIdentity است. میزبان باید این binding را از snapshot معتبر سند صادرشده، task/card یا intake تأییدشده بازیابی کند. اگر source با co. آغاز شود، باید از نوع independent و **دقیقاً** hash رجیستری همان company/project/kind/document باشد؛ تغییر حتی یک بعد رد می‌شود. task/card و سایر namespaceهای V2 نیز فقط با binding صریح قابل تطبیق‌اند. هیچ suffix یا نام نزدیک به شناسه فاکتور به‌عنوان اثبات استفاده نمی‌شود.

## شواهد معتبر میزبان

CommercialEvidence باید توسط host **پس از احراز هویت و در یک snapshot قفل‌شده** ساخته شود:

- authenticated_actor_id و authenticated، نه رشته‌های دلخواه request؛ dataclass یا boolean به‌تنهایی اثبات رمزنگاری‌شده نیست.
- registry واقعی از CompanyRegistry و verified_project_company_pairs با تکیه بر مالکیت حقوقی حقیقی.
- legacy_postings به‌صورت tuple از LegacyCommercialPosting برای **فقط رویدادهای issue واقعی**: ledger دقیق finance.sales یا accounting.invoice یا accounting.bill، company/project/kind/doc، issue_event_id، amount_toman صحیح و مثبت و party_id تأییدشده. اسناد draft، review، cancel، payment، settlement و reversal مبنای ثبت تازه نیستند.
- journals به‌صورت immutable JournalStateهای V2؛ هر کدام از طریق replay_journal تأیید می‌شود. هر PostedJournal ثبت اولیه باید با یک CommercialV2Binding مشخص یا noncommercial_v2_sources که میزبان واقعاً اثبات کرده، طبقه‌بندی شود. رویدادهای ClosedPeriod و reverse posting، یک فروش/خرید جدید شمرده نمی‌شوند.
- mirrors به‌صورت tuple از MirrorAuthorization برای pairing عمدی و دقیق هر invoice/bill با ثبت RIAL آن: company/project/kind/document، legacy ledger/event، V2 event/source، مقدار RIAL و party باید **همه** منطبق باشند. صرف اینکه دو سند برای یک پروژه هستند کافی نیست.

تأیید صحت ریشه شواهد (از جمله اینکه مجموعه legacy کامل است یا source غیرتجاری واقعاً غیرتجاری است) مسئولیت host است. مدل pure به client proof اعتماد ندارد و در خود ماژول به service session یا DB دسترسی ندارد. عنوان Verified در کلاس، مجوز یا credential ایجاد نمی‌کند.

## تصمیم preflight

preflight_commercial_source(evidence, CommercialCandidate(...)) یک CommercialDecision immutable برمی‌گرداند:

| disposition | مفهوم | ثبت عملیاتی میزبان |
|---|---|---|
| NEW | هویت تجاری در هر دو ledger حاضر نیست | میزبان می‌تواند پس از سایر کنترل‌ها تحت transaction اقدام کند |
| RETRY | همان سند دقیق، همان side/event ID، همان amount، party و source قبلاً موجود است | بدون ثبت مالی تکراری به نتیجه موجود ارجاع دهد |
| PAIRED_MIRROR | همان تجارت در ledger مقابل موجود است و MirrorAuthorization دقیقاً هر دو طرف را تأیید می‌کند | فقط به‌عنوان نیمه دوم یک commit آینه‌ای و **نه تراکنش مالی مستقل** ادامه دهد |

در شرایط زیر fail-closed: شرکت/پروژه ناشناخته یا مبهم؛ چند شرکت با یک پروژه؛ شناسه سند شرکت که از پروژه‌ای به پروژه دیگر نسبت داده شده؛ واحد پول مبهم/عدد اعشاری یا bool؛ source co.hash جعلی؛ مجوز فروش برای ledger خرید؛ دو صدور در یک ledger با event ID متفاوت؛ تکرار event ID برای سند دیگر؛ تعارض مبلغ/party؛ عدم تطبیق میرور؛ دوره V2 یا hash history خراب؛ طبقه‌بندی نامعلوم منبع V2؛ POSTED_LOCK رجیستری بدون اصل سند V2 مربوطه؛ و تاریخچه دوطرفه بدون مجوز صریح mirror.

وجود اسناد با شناسه نمایشی یکسان در دو **شرکت حقوقی متفاوت** به‌خودی‌خود تکرار نیست. اصل سندی که reverse شده همچنان business source خود را نگه می‌دارد؛ ابطال و صدور مجدد باید فرآیند جداگانه و هویت جدیدِ مستند داشته باشد. pairهای تاریخی متعدد فقط اگر هر کدام proof مستقل و کامل داشته باشند مجازند.

## محل دقیق اتصال توسط Prime

1. در مرز احراز هویت و خواندن داده از native_app.Bridge و finance.py، پیش از اعمال invoice.issue؛ و در accounting_service.py / accounting_core.py پیش از bill.issue و invoice.issue، resolver سمت میزبان باید source tuple را **از ledger و issued document ذخیره‌شده** بسازد. باید status، مبلغ TOMAN، event_id، party، document ID و رابطه پروژه با company ثبت‌شده را تأیید کند. عبارت sourceType در accounting_core مستقل از kind تجاری است.
2. در مسیر مشترک commit در app_storage.py داخل validation/transaction یگانه، پس از تولید snapshot candidate از finance reducer و V2 composer ولی پیش از persist/CAS، host باید evidence را از before (و intended pair را از before/after معتبر) بازسازی و preflight_commercial_source را برای هر سند issue جدید صدا بزند. اتصال به _protect_rial_finance_history کنار بررسی current finance ledger و accounting events، نه جایگزینی controlهای آنهاست. از NEXT snapshot نباید «اثبات اختیار» استخراج شود؛ آن فقط موضوع تطبیق است.
3. در ir_accounting_host_v2.RIALAccountingHost.command مسیر document.post، دقیقاً پس از _validate_document و resolve_chart/scopes و **پیش از** RIALJournalStorage.mutate باید identity و binding host-side استخراج شوند. preflight نیز باید **درون همان عملیات CAS/lock ذخیره‌ساز** دوباره اجرا شود؛ چک بیرون transaction یا قفل، race را حل نمی‌کند.
4. مسیر sales composer در ir_finance_v2_extension.compose_finance_rial_snapshot و purchase در ir_purchase_joint_issue.compose_purchase_issue_with_rial دو قرارداد mirror کنونی هستند. host باید تفاوت sourceهای invoice ID، card ID، bill ID و co.hash را با binding دقیق بپوشاند؛ اجازه auto-pair فقط با MirrorAuthorization مبتنی بر issued evidence و مقدار TOMAN×10 داده شود. پیاده‌سازی pure جدید هیچ جایگزینی برای reconciliation فعلی نیست.
5. در مرحله بعدی دیتابیس باید (company_id,project_id,kind,document_id) را به‌صورت کلید commercial واحد مستقل از eventId، و (company_id,ledger,event_id) را مستقل یکتا کند. registry posted lock، invoice/bill، legacy accounting و RIAL V2 event باید در یک CAS transaction ذخیره شوند. اگر mirror pending و counterpart موجود نیست، host transaction باید هر دو بخش را کنار هم commit کند یا کل عملیات را rollback کند؛ گارد نه reservation دارد، نه guarantee atomicity.
6. برای استقرار چندشرکتی باید حالت single-company shadow در مسیر جاری app_storage/purchase جایگزین نگاشت قانونی واقعی شود، ledgerهای پیشین TOMAN و posted sources reconciliation و migration جداگانه داشته باشند، و negative tests همزمان و crash/retry با SQLite موقت اجرا شوند. این tranche چنین تغییری ایجاد نکرد.

## اجرای آزمون مستقل

    python -B -m unittest discover -s tests -p test_ir_commercial_source_guard.py -q

آزمون‌های synthetic سناریوهای happy-path، sale/sales normalize، خرید، تکرار سند با event ID جدید، retry دقیق، change amount/party، mirror کامل و نامعتبر، تفاوت source task با invoice، registry hash ناسازگار، company/project mismatch، journal reversal، classifying noncommercial events، تغییر مالک پروژه و overflow ریال را بررسی می‌کنند. هیچ داده واقعی مشتری، سند حقوقی حقیقی، اتصال شبکه یا SQL استفاده نشده است.
