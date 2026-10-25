# ممیزی مستقل پذیرش حسابداری مجزای مدار

**تاریخ بررسی:** 2026-10-22  
**دامنه:** فایل‌های موجود accounting.html، src/standalone_main.jsx،
src/standalone_accounting_workspace.jsx، standalone_accounting_desktop.py؛
برای راستی‌آزمایی مسیر ورود و قرارداد میزبان، src/App.jsx، native_app.py،
lan.py، standalone_accounting.py و vite.config.js فقط **خوانده شدند**.

**نتیجه نسخه فعلی پس از اصلاح‌های هم‌زمان Prime:** هسته مستقل، ورودی
HTML/React جداگانه، چرخه حسابداری پایه و محدودسازی دو سطحِ URL صفحه
index و wrapper جاوااسکریپت accounting.html **با داده مصنوعی PASS شدند**.
دو نقص مشاهده‌شده در ابتدای ممیزی طی همین مرحله توسط Prime اصلاح و
بازآزمایی شدند. بااین‌حال wrapper جاوااسکریپت به‌تنهایی sandbox امنیتی
نیست، مدیریت نقش‌ها ناهماهنگ است و تست تعاملی واقعی GUI انجام نشده است.
این گزارش تأیید تولید، امنیت جامع یا انتشار جدید نیست.

## معیارهای پذیرش و نتیجه

| معیار | نتیجه | شواهد |
| --- | --- | --- |
| صفحه HTML مستقل از index.html | PASS | accounting.html:1-10 فقط standalone_main.jsx را bootstrap می‌کند؛ vite.config.js:8-11 خروجی جداگانه دارد |
| React مستقل، بدون بارگذاری App.jsx یا ارسال task/project | PASS برای منطق اجرایی | src/standalone_main.jsx:1-18؛ src/standalone_accounting_workspace.jsx:160-161,187-225؛ props صرفاً api/onExit/canManage |
| دفتر پایدار مستقل از task/finance | PASS در سناریوی مصنوعی | standalone_accounting_desktop.py:34-69؛ standalone_accounting.py:185-223؛ SQLite فقط در TemporaryDirectory |
| گردش واقعی party → invoice → approve → issue، بدون task | PASS | tests/test_standalone_accounting_contract_acceptance.py؛ همچنین تست موجود desktop و آزمون Node UI |
| بسته شدن index.html و aliasهای شناخته‌شده در سرور solo | **PASS بعد از اصلاح** | standalone_accounting_desktop.py:82-104؛ مسیرهای encoded و normalized با 404 رد شدند |
| wrapper API روی accounting.html در برنامه اصلی | **PASS بعد از اصلاح، نه sandbox** | native_app.py:2275-2289,2317-2323؛ ACCOUNTING_JS_BRIDGE فقط دو نام را صادر می‌کند |
| دکمه ورود از برنامه اصلی | PASS مشروط | src/App.jsx:919-926، navigation به accounting.html؛ فقط برای admin و بعد از آماده شدن state تسک‌منیجر |
| همخوانی مجوز ورود و ثبت مالی برای کاربران editor | **P0 عملکردی / نیازمند تصمیم** | src/App.jsx:559,920؛ src/standalone_main.jsx:13؛ lan.py:38-53 |
| CAS، پاسخ معتبر، جلوگیری از تکرار شناسه رویداد | PASS قرارداد / بدون GUI واقعی | src/standalone_accounting_workspace.jsx:119-126,187-266؛ standalone_accounting.py:185-226 |
| استقلال کامل CSS/assets | PARTIAL | src/standalone_main.jsx:4 فایل styles.css مشترک را وارد می‌کند؛ به‌تنهایی تسک‌منیجر را اجرا نمی‌کند |

## P0-01: alias صفحه تسک در سرور solo

**وضعیت نهایی: رفع‌شده در کد جاری و تست منفی PASS.**

در ابتدای ممیزی، serve_accounting_page فقط /index.html را به‌شکل دقیق
رد می‌کرد و SimpleHTTPRequestHandler در مسیر fallback می‌توانست alias
کدگذاری‌شده زیر را به صفحه تسک تبدیل کند:

    GET /%69ndex.html

**اصلاح Prime:** در standalone_accounting_desktop.py:84-89 اکنون URL با
unquote decode می‌شود و نام index.html/index.htm حتی از مسیرهای فرعی
و با حروف بزرگ به 404 منتهی می‌شود.

**تست پس از اصلاح:** /index.html، /%69ndex.html، /index%2Ehtml،
/./index.html، /folder/../index.html و /INDEX.HTML همگی 404 شدند؛
درخواست / و /accounting.html صفحه اختصاصی حسابداری را برگرداندند.

**محدودیت باقی‌مانده:** سرور solo هنوز برای سایر فایل‌های استاتیک از
SimpleHTTPRequestHandler استفاده می‌کند؛ allowlist فقط accounting.html
و assetهای آن فعلاً پیاده‌سازی نشده است. بنابراین ممنوعیت index.html
تأیید شد، اما عدم ارائه تمام HTMLهای بالقوه دیگر **تأیید نشده** است.

**تست جدید:** test_encoded_and_normalized_index_paths_must_not_expose_task_page
اکنون PASS معمولی است؛ دیگر expectedFailure ندارد.

## P0-02: پل عمومی جاوااسکریپت روی accounting.html

**وضعیت نهایی: wrapper محدود شده، PASS با ملاحظه مرز امنیتی.**

در ابتدای ممیزی native_app.py یک JS_BRIDGE عمومی را برای هر دو صفحه
استفاده می‌کرد. **اصلاح Prime:** اکنون ACCOUNTING_JS_BRIDGE مجزا در
native_app.py:2278-2289 تنها standaloneAccountingRead و
standaloneAccountingCommand را صادر می‌کند؛ StaticHandler در
native_app.py:2322 برحسب نام صفحه این wrapper را انتخاب می‌کند.
index.html همچنان wrapper اصلی را دریافت می‌کند.

**مرز دقیق تضمین:** این اصلاح سطح window.madar را محدود می‌کند،
نه underlying window.pywebview.api. در پنجره اصلی، همان Bridge
native_app.Bridge با js_api=api به pywebview داده شده و متدهای
دیگر همچنان در آن آبجکت وجود دارند. بنابراین این اصلاح **جداسازی
محکم بین پروسه‌ها یا sandbox امنیتی** نمی‌سازد و کنترل دسترسی
سمت میزبان همچنان ضروری است. این نکته را نباید با «کد React از
تسک API استفاده می‌کند» اشتباه گرفت؛ آن کد مستقل است.

**برای ایزولاسیون امنیتی سخت‌گیرانه در آینده:** به‌جای اتکا به
window.madar، یک پنجره/WebView با js_api مستقل و محدود یا یک
capability gateway قابل‌تأیید در سمت native نیاز است. در فاز
حسابداری مستقل، کنترل واقعی دسترسی مالی سرور برقرار بماند.

**تست جدید:** test_main_app_accounting_javascript_wrapper_is_page_scoped
اکنون PASS معمولی است؛ وجود wrapper اصلی برای index.html و عدم
وجود getState/saveState در ACCOUNTING_JS_BRIDGE بررسی می‌شود.

## P0-03: ناهماهنگی مجوز ورود از برنامه با ACL مستقل مالی

**وضعیت: شکاف عملکردی موجود؛ تصمیم محصول/مالک میزبان لازم است.**

- src/App.jsx:559، متغیر canManage فقط وقتی true می‌شود که نقش
  lanStatus.user.role برابر admin باشد. دکمه حسابداری مستقل در
  src/App.jsx:920-925 فقط در همین حالت نشان داده می‌شود.
- در lan.py:38-53، کاربر editor با financeEdit=true مجاز به نوشتن
  در حسابداری مستقل است و حساب financeView=true مجوز خواندن دارد.
  این کاربران ممکن است در UI اصلی دکمه ورود را نبینند.
- در src/standalone_main.jsx:13، canManage با Boolean(window.madar)
  تعیین می‌شود؛ این صرفاً وجود bridge است، **نه** financeEdit کاربر.
  کاربر view-only ممکن است فرم‌های ثبت را ببیند، اما سرور درخواست‌های
  فاقد مجوز را رد می‌کند.
- App.jsx:859 پیش از در دسترس قرار گرفتن data از تسک‌منیجر یک loading
  page نشان می‌دهد. بنابراین ورود «از داخل اپ» به سلامت بارگذاری
  state تسک وابسته است؛ اجرای solo این وابستگی را ندارد.

**اثر:** کاربران دارای ACL مالی مستقل، UI دسترسی همسان با میزبان
ندارند. این مورد به‌خودی‌خود رخنه امنیتی نیست، چون مجوز واقعی در
LAN/Store اجرا می‌شود. برای پذیرش نقش‌های مالی غیرادمین باید ورودی
براساس financeView/financeEdit معتبر و canManage مبتنی بر ACL واقعی
پیاده شود؛ یا اگر فاز P0 واقعاً admin-only است، در مشخصات فاز صریح
تثبیت شود. همچنین بهتر است مسیر startup حسابداری از خطای load
تسک جدا بماند.

## قرارداد دستور و وضعیت‌های قابل اتکا

1. در حالت solo، AccountingDesktopAPI یک data root **مطلق و صریح**
   می‌گیرد و تنها پس از read/command، دیتابیس
   standalone-accounting.sqlite3 را می‌سازد؛ import یا constructor
   به‌تنهایی دیتابیسی ایجاد نمی‌کند.
2. API خواندن نتیجه revision عدد صحیح غیرمنفی و view با currency=TOMAN
   دارد؛ فرمان فقط envelope دارای command و expectedRevision را
   می‌پذیرد، نه actor/company/proof. actor و نقش را میزبان تزریق می‌کند.
3. پاسخ فرمان شامل revision/result/view است. درخواست نامعتبر و
   revision قدیمی در Store رد می‌شود. eventId برای عملیات مالی
   جدید ساخته می‌شود و idempotent replay همان eventId+payload
   در نسخه جاری است. UI در صورت conflict بازخوانی می‌کند و برای
   پاسخ نامشخص فرمان قبلی را با همان شناسه نگه می‌دارد.
4. موتور مستقل از party.register، item.create،
   invoice/bill.create/approve/issue/cancel، receipt/payment.record،
   funds.deposit/transfer، account.create، journal.manual/reverse و
   period.close استفاده می‌کند؛ فرمان صدور با وضعیت approved
   محدود است و تسویه به سند issued تخصیص داده می‌شود.
5. حساب‌ها و مبالغ **flat/TOMAN** هستند. ناموجودبودن داده با empty
   state صادقانه نمایش داده می‌شود، نه با اعداد نمایشی.

**محدودیت تست:** JSX و فرمان‌ها با SSR، بررسی متن منبع و اجرای
reducer در حافظه پوشش دارند؛ کلیک واقعی همه تب‌ها، پویایی کامل
React، تجربه WebView، اتصال شبکه واقعی، نصب روی سیستم دیگر و
اجرای برنامه نصب‌شده در این ممیزی بررسی نشده‌اند.

## ویژگی‌های ERP پیشرفته که بلوکر P0 مستقل نیستند

این موارد در این فاز **نباید به‌عنوان نقص در هسته حسابداری مستقل**
شمرده شوند، مگر محصول دامنه MVP را صریحاً گسترش دهد:

- کل/معین/تفصیلی ایرانی، حساب‌های شناور و دفتر RIAL V2
  (در پروژه دامنه‌های جدا دارند؛ این UI فقط ledger تخت تومان را می‌خواند).
- FIFO واقعی، قیمت تمام‌شده انبار، رسید/حواله، GRNI و کنترل سفارش خرید.
- خزانه‌داری چک، سررسیدها، مغایرت بانکی، مالیات خودکار، مؤدیان و حقوق‌ودستمزد.
- اشخاص حقوقی چندشرکتی، سال مالی رسمی پیشرفته، واردکردن داده پارسیان
  و مهاجرت معکوس‌پذیر ساختار حساب‌های بیرونی.
- **اتصال آینده به تسک‌منیجر:** هنوز هیچ قرارداد قابل‌اتکای
  task→commercial source→accounting posting با شناسه پایدار، تفکیک
  مجوز و idempotency انتهابه‌انتها تصویب نشده است. مستقل‌بودن فعلی
  درست است؛ نباید با یکپارچه‌سازی ضمنی یا کپی‌کردن رویدادهای مالی
  داخل JSON کارت‌ها مخدوش شود.

## شواهد اجرا، فقط مصنوعی

فایل جدید:

    tests/test_standalone_accounting_contract_acceptance.py

اجرا:

    python -B -m unittest tests.test_standalone_accounting_contract_acceptance -v

خروجی پس از اصلاح Prime: **۶ PASS / ۰ FAIL / ۰ expectedFailure**.

    python -B -m unittest tests.test_standalone_accounting_desktop tests.test_standalone_accounting_host tests.test_standalone_accounting_contract_acceptance -q

خروجی بازاجرا بعد از اصلاح Prime: **۳۵ PASS، ۰ FAIL،
۰ expectedFailure**.

    node --test tests/standalone_accounting_workspace_ui.test.cjs

خروجی: **۱۳ PASS، صفر FAIL**؛ شامل آزمایش مصنوعی end-to-end
فرمان‌ها مقابل accounting_core واقعی و بدون داده تولیدی.

ساخت Vite ایزوله:

    ./node_modules/.bin/vite.cmd build --outDir $env:TEMP\madar-accounting-acceptance-worker9 --emptyOutDir

خروجی: PASS، تبدیل ۱۶۴۹ ماژول و تولید accounting.html مستقل و
assetهای JS/CSS. خروجی داخل TEMP است؛ dist اصلی، EXE و release
دستکاری نشده‌اند.

**مسیر تست‌های شبکه:** HTTP فقط 127.0.0.1 با پورت تصادفی،
فایل HTML فیک در TemporaryDirectory، سرور متوقف‌شده در finally.
تست SQLite تنها دیتابیس TemporaryDirectory ساخت و تمیز کرد.
هیچ APPDATA، فایل واقعی مالی یا Git لمس نشد.

## اولویت نهایی برای Prime

1. **رفع‌شده و تست‌شده:** بستن aliasهای index.html در سرور solo.
   برای ایزولاسیون asset/HTML فراتر از index، allowlist دقیق لازم است.
2. **رفع‌شده در wrapper:** دو API روی accounting.html؛ اصل backend
   permission و محدودیت pywebview.api باید همچنان مدنظر باشد.
3. **P0 پذیرش نقش یا P1 UX بسته به scope:** تعیین سیاست admin-only
   در برابر نقش‌های financeView/financeEdit، نمایش متناسب مسیر ورود
   و write controls؛ حذف وابستگی غیرضروری دسترسی به حسابداری به
   موفقیت startup تسک‌منیجر، اگر استقلال launch از داخل اپ الزامی باشد.
4. تست تعاملی WebView/ذخیره و قطع اتصال
   با دیتابیس تست مستقل، پیش از هر تأیید عملیاتی.

**جمع‌بندی پذیرش نهایی:** هسته مستقل = PASS؛ رابط/Build جدا = PASS؛
entry از اپ = PASS مشروط به admin و بارگذاری تسک؛ فیلتر alias صفحه
تسک و wrapper اختصاصی = PASS پس از اصلاح Prime؛ **sandbox مستقل
واقعی / پذیرش desktop E2E هنوز تأیید نشده**؛ ERP پیشرفته و اتصال
به task = خارج از دامنه این فاز.
