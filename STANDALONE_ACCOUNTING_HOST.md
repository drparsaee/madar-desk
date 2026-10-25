# میزبان حسابداری مستقل مدار | قرارداد و وضعیت واقعی

## محدوده تحویل

این tranche فقط این چهار فایل را تغییر داده یا ایجاد کرده است:

- native_app.py: دو API جدید pywebview، انتخاب مسیر خواندن/نوشتن مستقل و Store lazy.
- lan.py: مجوزهای financeView/financeEdit، سرویس token-authenticated و GET/POST مستقل.
- tests/test_standalone_accounting_host.py: آزمون‌های مصنوعی tempdir و HTTP محلی با Store جعلی.
- STANDALONE_ACCOUNTING_HOST.md: این سند.

**نکته وضعیت:** در ابتدای کار فایل worker-10 موجود نبود؛ سپس فایل standalone_accounting.py به پروژه اضافه شد. امضای read/command آن بررسی و **۲ تست end-to-end واقعی با SQLite موقت** (Bridge solo و LAN HTTP) در کنار FakeStandaloneStore انجام شد. این شاهد فقط اتصال محلی مستقل را ثابت می‌کند؛ نه RIAL V2، انبار، تراکنش مشترک، داده واقعی یا production.

## قرارداد ورود/خروج

خواندن مستقیم از WebView:

    window.madar.standaloneAccountingRead()

خروجی عین داده مورد انتظار Store است:

    {"revision": 0, "view": { ... }}

اجرای فرمان:

    window.madar.standaloneAccountingCommand({
      command: {type: "...", ...},
      expectedRevision: 0
    })

Envelope دقیقاً دو کلید command (دیکشنری) و expectedRevision (عدد صحیح غیرمنفی، بدون bool) دارد. هیچ actor، accounts، company یا mode اضافی در Envelope مجاز نیست. نوع فرمان، اعتبار فیلدهای داخل command، کنترل نسخه CAS و تغییر داده بر عهده worker-10 Store است. API خروجی را بدون تغییر می‌فرستد:

    {"revision": 1, "result": { ... }, "view": { ... }}

امضاهای استفاده‌شده:

    StandaloneAccountingStore(db_path).read(*, actor, accounts)
    StandaloneAccountingStore(db_path).command(
        command, *, actor, accounts, expected_revision, now)

فایل محلی فقط با اولین فراخوانی واقعی حسابداری مستقل در مسیر **همان پوشه resolved داده‌های Bridge** ایجاد/باز می‌شود: sibling of tasks.json با نام standalone-accounting.sqlite3. سازنده Bridge این Store را ایجاد نمی‌کند؛ هیچ migrate/import/init برای آن انجام نمی‌شود. این DB از finance.json، madar-unified.sqlite3، task records، app_storage، accounting_core و RIAL V2 جداست.

## مجوزها و حریم خصوصی

| موقعیت | خواندن | نوشتن |
|---|---|---|
| Bridge محلی در حالت solo | principal محلی admin | admin |
| LAN principal با نقش admin | مجاز | مجاز |
| LAN editor با financeView=True | مجاز | فقط اگر financeEdit=True |
| LAN viewer با financeView=True | مجاز | همیشه ممنوع |
| بدون session معتبر، user حذف‌شده، viewer فاقد financeView | ممنوع | ممنوع |

LAN session از LanService.account_for(token) احراز می‌شود؛ username یا نقشِ داخل command هرگز ملاک اعتبار نیست. اکانت‌های داده‌شده به Store محدود به username، role، financeView و financeEdit هستند؛ passwordHash، scope پروژه و اطلاعات session به Store منتقل نمی‌شوند.

این tranche از سیستم user role موجود در lan.py استفاده می‌کند. UI فعلی مدیریت حساب‌های LAN الزاماً امکان تخصیص financeView/financeEdit به editor را ندارد؛ بنابراین editor بدون مجوز قبلاً موجود، به‌صورت پیش‌فرض دسترسی نمی‌گیرد. گسترش مدیریت grantها نیازمند tranche جداست. نقش admin دسترسی ضمنی هر دو مجوز را دارد.

## LAN و حالت Client

مسیر جدید شبکه: **/api/standalone-accounting**

- GET بدون query: خروجی دقیق read Store.
- POST با JSON Envelope دقیق: خروجی دقیق command Store.
- نبود bearer token، نشست منقضی یا فقدان دسترسی: پاسخ HTTP 403.
- درخواست نامعتبر، کلید اضافه، expectedRevision نامعتبر یا query اضافی: 400.
- مسیر ناشناخته / متد نامعتبر: مطابق قواعد عمومی handler، 404/405.

در حالت Bridge client، هر دو متد **فقط** از _remote_request و session token شبکه استفاده می‌کنند. اگر LAN قطع شود یا server خطا بدهد، هیچ ذخیره یا خواندن از standalone-accounting.sqlite3 محلی، task/finance cache، offline queue یا last-known-state انجام نمی‌شود. اتصال HTTPS موجود از fingerprint-pin فعلی استفاده می‌کند، که پیش از ارسال اطلاعات حساس برقرار می‌شود؛ تنظیم Transport/TLS فعلی تغییر نکرده است.

## صفحه جداگانه حسابداری

Prime صفحه accounting.html را جداگانه اضافه می‌کند تا مستقل از bootstrap تسک‌منیجر بارگذاری شود. در native_app.main.StaticHandler تزریق محدود JS_BRIDGE برای سه path مجاز /، /index.html و **/accounting.html** انجام می‌شود؛ صفحه accounting.html فایل خودش را می‌خواند، نه index.html. دو متد standaloneAccountingRead و standaloneAccountingCommand به allowlist جاوااسکریپت window.madar افزوده شده‌اند.

توجه: این فایل تضمین نمی‌کند که صفحه accounting.html در بسته dist یا EXE ساخته یا منتشر شده است. سازگاری Vite build و صفحه مستقل در مالکیت Prime است. تزریق فقط در مسیرهای exact انجام می‌شود؛ assetها و سایر HTMLها inject نمی‌شوند.

## مسیر داخلی و نقاط عدم‌اتصال

Native solo:

    Bridge.standaloneAccountingRead/Command
       → standalone_finance_access(local admin)
       → standalone_finance_accounts (sanitized)
       → StandaloneAccountingStore(db_path).read/command

Native LAN server:

    Bridge.standaloneAccountingRead/Command
       → LanService authenticated owner token
       → account_for(token) + ACL
       → Bridge._standalone_accounting_*_local
       → Store

Remote:

    Bridge.standaloneAccountingRead/Command
       → _remote_request (/api/standalone-accounting)
       → LAN Handler, account_for(token), ACL
       → Store

هیچ یک از این مسیرها _load_finance، getState، tasks، cards یا projects را برای عملیات حسابداری مستقل صدا نمی‌زند؛ transaction مشترک با داده‌های قبلی وجود ندارد. احراز هویت LAN در سرور است، نه روی اطلاعات کاربر cached در کلاینت.

## تست‌ها

    python -B -m unittest discover -s tests -p test_standalone_accounting_host.py -q

آزمون‌ها از TemporaryDirectory استفاده می‌کنند و Bridge را بدون __init__ می‌سازند تا APPDATA/داده واقعی لمس نشود. StandaloneAccountingStore با ماژول fake در sys.modules تزریق می‌شود؛ چند آزمون سرور HTTP در localhost:0 را اجرا می‌کنند. موارد کنترل‌شده: lazy initialization، مسیر صحیح فایل، عدم ایجاد/دسترسی به finance/tasks، clock، Envelope strict، عدم عبور password hashes، role و grants، token معتبر، HTTP GET/POST، query اضافی، خروجی مستقل client و قطع ارتباط بدون fallback.

اجرای نهایی این tranche: **۲۵ آزمون اختصاصی PASS/۰ FAIL** (۲۳ تست Fake/HTTP synthetic و ۲ تست با worker-10 SQLite واقعی در مسیر موقت). خود تست‌های Store worker-10 تعداد **۱۵ PASS**، رگرسیون‌های LAN مالی ۴، نمایش مالی ۱۲، Finance Bridge تعداد ۳ و اتصال خرید RIAL تعداد ۲ نیز PASS شدند؛ جمعاً **۶۱ آزمون منتخب PASS/۰ FAIL**. این نتایج صرفاً روی tempdir/fixtures انجام شده‌اند.

## بلوکرهای معتبر

1. قرارداد فعلی worker-10 با host در tempdir/SQLite تأیید شد. پذیرش UI/Vite accounting.html و build قابل اجرا **در مالکیت Prime** است؛ این tranche build یا انتشار EXE انجام نداده است.
2. امنیت عملیاتی شبکه و تنظیمات TLS همچنان از LanService موجود به ارث می‌رسد؛ این کار audit عمومی شبکه انجام نداده است.
3. مدیریت financeView/financeEdit برای editor از UI فعلی LAN احتمالاً نیاز به توسعه دارد. تا پیش از مدیریت صریح نقش‌ها، editor پیش‌فرض فاقد مجوز است و دسترسی نمی‌گیرد.
4. این حسابداری فعلاً **مستقل** است. نتایج آن نباید موجودی RIAL V2 یا سیستم مالی/انبار دیگر قلمداد شود. مهاجرت داده یا ایجاد پیوند مشترک مجاز نشده است.
