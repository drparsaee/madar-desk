# مدار: گزارش پذیرش عملیاتی بستهٔ R5، ۱۴۰۵/۰۸/۰۳

## حکم

**آمادهٔ نصب و ارزیابی آزمایشی روی ویندوز با دادهٔ مصنوعی/مستقل**: بله، در
حدود آزمون‌های ثبت‌شده در این گزارش. **آمادهٔ جایگزینی بی‌قیدوشرط حسابداری
پارسیان و ثبت/ارسال قانونی با داده‌های واقعی**: خیر. پذیرش واقعی وابسته به
تطبیق اسناد و مانده‌ها، تأیید حسابدار، الزامات قانونی و تست روی دستگاه دوم است.

این گزارش نتیجهٔ اجرای مستقیم ابزارها روی ماشین کاری همین پروژه است؛ گزارش‌های
قدیمی `ACCOUNTING_ALL_MODULES_ACCEPTANCE_20261025.md` و R2/R3/R4 جایگزین
شواهد R5 نیستند. فایل‌های قدیمی و داده‌های حقیقی در این انتشار بازنویسی نشدند.

## اصلاحات انجام‌شده در tranche نهایی

- ACL حسابداری مستقل: جدول مجوز ۵۹ فرمان عملیاتی editor دارای `financeEdit`
  و هفت فرمان ساختاری فقط admin، کنترل bypass از راه journal/inventory، و
  همسان‌سازی read در LAN برای finance writer؛ viewer ارتقا نمی‌یابد.
- پاسخ قابلیت‌های میزبان شامل `canAdmin` است و frontend به capability معتبر
  پاسخ host اتکا می‌کند، نه صرف وجود bridge یا نقش ساخته‌شده در client.
- تست قدیمی proforma با ACL جدید همسو شد؛ عملیات تجاری editor اکنون مجاز و
  عملیات admin-only و کاربر بدون grant ممنوع سنجیده می‌شوند.
- تست‌های legacy ناسازگار با `financeEdit => read` و capability جدید اصلاح شدند.
- فرایند مرجوعی جزئی به‌ازای سطر/تعداد، credit note مستقل، کنترل سقف تجمعی و
  محاسبهٔ بدهی با کسر `returnedAmount` با GUI و event-replay بررسی شد.
- اعتبارسنجی پیش‌نمایش CSV بانک، راهنمای بازیابی آفلاین و کنترل‌های snapshot
  مستقل نیز در R5 بسته‌بندی شدند. recovery از طریق `--recovery` جدا از برنامه
  اصلی اجرا می‌شود.
- تست تازهٔ مسیر بازیابی با mock روی دیالوگ، تأییدهای دوگانه، رد backup خراب
  و رد overwrite افزوده شد. همچنین smoke از EXE واقعی دیالوگ بازیابی را باز
  کرد، بدون ایجاد پایگاه داده یا بازکردن task database.

## شواهد اجرا در R5

| آزمون | نتیجه | دامنه و محدودیت |
| --- | --- | --- |
| `py -3.12 scripts/release_qa.py --full` | PASS | ۱۹ تست release، ۱۴۱۳ تست Python، ۳۶۰ تست JavaScript؛ همه با APPDATA ایزوله |
| `py -3.12 -B -m unittest tests.test_standalone_finance_acl_comprehensive tests.test_standalone_proforma_flow tests.test_standalone_recovery_wizard tests.test_standalone_recovery_wizard_flow -q` | ۲۳ PASS | ACL، proforma و restore مصنوعی |
| `py -3.12 -B -m unittest tests.test_standalone_accounting_host tests.test_standalone_accounting_desktop -q` | ۳۰ PASS | host مستقل، ACL و SQLite؛ synthetic |
| `node_modules\\.bin\\vite.cmd build --outDir .qa-accounting-r5-20261025 --emptyOutDir` | PASS | بستهٔ HTML/JS رابط R5 |
| PyInstaller: `Madar-Accounting-Fixes-R5-20261025.spec` | PASS | EXE حسابداری جدید |
| PyInstaller: `Madar-Desk-Fixes-R5-20261025.spec` | PASS | EXE مدیریت کارها جدید |
| `scripts/operational_r5_candidate_exe_qa.py` | ۱۴/۱۴ PASS | بازشدن GUI دو EXE، SQLite مستقل، نسخهٔ پشتیبان شروع/خروج و replay آن |
| `scripts/operational_r5_recovery_exe_qa.py` | ۴/۴ PASS | بازشدن پنجرهٔ `--recovery` از EXE و عدم ایجاد task/finance database |
| `scripts/operational_partial_return_gui_qa.py` | ۱۴/۱۴ PASS | بازگشت جزئی از فرم GUI، credit note و ماندهٔ ۶۰۰۰ از ۷۰۰۰ |
| `scripts/operational_all_accounting_modules_r5_bundle_gui_qa.py` | ۱۵۸/۱۵۸ PASS | GUI واقعی pywebview و front-end ویژه R5؛ دادهٔ مصنوعی |
| `scripts/operational_r5_package_install_qa.py` | ۷/۷ PASS | نصب مستقل temp، سه میانبر در هر محل، عدم overwrite، صحت hash و fail-closed |
| `scripts/finalize_accounting_r5.py` | PASS | صحت ZIP/CRC و SHA-256 سه payload در بازخوانی ZIP |

در دو اجرای GUI یک هشدار پاکسازی پوشهٔ موقت WebView2 گزارش شد؛ تست‌ها exit=0
داشتند. این هشدار به‌عنوان تضمین نبود هرگونه عیب GUI تعبیر نمی‌شود.

## خروجی‌ها

پوشهٔ انتشار:

`D:\\CoS-Test\\madar-desk\\release`

فایل نهایی قابل انتقال:

`Madar-Suite-Accounting-R5-20261025.zip`

- اندازهٔ ZIP: **245,549,317 bytes**.
- SHA-256 واقعی ZIP: `A27B936EFA5C072881CC9DCFF0FCCD67C7BC5794D2DCF88F4A568DFCF87BAAC6`.
- SHA-256 برنامهٔ مدیریت کارها: `31417BE917B9C14A311D601E26B64F3D01E740FAFA32A33B427DA737B39FE675`.
- SHA-256 برنامهٔ حسابداری: `A9F6307124CF67680D79E1C1DEEFF0274026346B1BAA7D3E4629EEABB375B802`.
- SHA-256 پیش‌نیاز WebView2: `9B0142E22E8DAA92855D746AE4D1E9EEEF561CCAF67D1DD452165C4AF3DF3191`.
- وضعیت Windows Authenticode پیش‌نیاز: `Valid`، امضاکننده `Microsoft Corporation`.

ZIP شامل دو برنامه با نام R5، `Setup.ps1`، `INSTALL.cmd`،
`manifest.json`، راهنمای فارسی و WebView2 runtime است. نصب‌کننده به‌طور
پیش‌فرض مسیر برنامه و اطلاعات R5 را از نسخه‌های قدیمی جدا می‌کند، قبل از
نصب hash را کنترل می‌کند، روی فایل متفاوت overwrite نمی‌کند و میانبر
بازیابی آفلاین را مستقل می‌سازد. نصب واقعی روی سیستم دیگر هنوز آزموده نشده است.

## محدودیت‌ها و شروط پذیرش دادهٔ واقعی

1. **انتقال پارسیان ۳۹**: restore بکاپ واقعی `.bak` در SQL Server ایزوله و
   با مجوز، استخراج جامع، تطبیق فاکتور/دفترکل/اشخاص و امضای حسابدار هنوز
   ثبت نشده است. هیچ بکاپ پارسیان در این tranche روی SQL واقعی restore نشد.
2. **مالیات قانونی**: ارسال به سامانه مؤدیان، هویت و امضای معتبر، توکن، نوع
   صورتحساب، استثناهای دوره‌ای و پاسخ‌های قانونی هنوز پذیرش نشده‌اند.
3. **حقوق واقعی**: محاسبات کامل قانونی بیمه/عیدی/سنوات و قراردادهای کارکنان
   خارج از پذیرش عملیاتی کنونی‌اند؛ ثبت ledger با محاسبه قانونی یکی نیست.
4. **مرجوعی جزئی**: credit note و ماندهٔ مالی تست شده‌اند؛ تمام سناریوهای
   FIFO موجودی واقعی، استرداد بانکی و سند مالیاتی باید جداگانه بررسی شوند.
5. **بازیابی GUI**: اجرای تمام انتخاب‌های انسانی روی EXE منتشرشده به‌صورت
   خودکار با real clicks آزموده نشده است. دیالوگ واقعی باز شد و گردش
   بازیابی با mocked dialog و SQLite واقعی تست شد. تأیید آفلاینِ اپراتور
   مکانیزم شناسایی قطعی همهٔ writerها نیست.
6. **سخت‌افزار و شبکه**: نصب و LAN/failover روی دو ویندوز فیزیکی، چاپگرهای
   متنوع و بازیابی اطلاعات واقعی آزمون و پذیرش نشده‌اند.
7. **امنیت اطلاعات**: فایل‌های حسابداری و backupها در این گردش کار plaintext
   هستند؛ محل نگهداری، دسترسی‌ها و رمزنگاری در سطح سیستم/سازمان باید مدیریت شود.

**حکم نهایی این tranche:** خطاهای regression شناخته‌شده و مانع بسته‌بندی
R4 برطرف شدند و نسخهٔ مستقل R5 با تست واحد، یکپارچه، GUI، executable، نصب
ایزوله و بازیابی ایمن آزمایشی آماده شده است. تبدیل آن به انتشار production
برای اطلاعات مالی واقعی بدون شروط بالا تأیید نمی‌شود.
