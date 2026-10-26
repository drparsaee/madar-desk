# قرارداد امنیت و ادغام هویت حسابداری مستقل مدار

تاریخ بازبینی کد: ۱۴۰۵/۰۸/۰۴ (۲۰۲۶-۱۰-۲۶). دامنه: `accounting_core.py`، `standalone_accounting.py`، `standalone_accounting_desktop.py`، `standalone_accounting_identity.py`، `standalone_accounting_company_registry.py`، `lan.py` و بخش مستقل `native_app.py`. فقط کد فعلی و آزمون‌های مصنوعی بررسی شده‌اند؛ این نوشته گواه امنیت نسخه اجرایی یا انتشار نیست.

## وضعیت فعلی و مرز اعتماد

1. **موتور حسابداری:** در `accounting_core.py`، تابع‌های `_actor_role`، `_require` و `_require_view` با نقش‌های `admin/editor/viewer` و مجوزهای صریح `financeView/financeEdit` کار می‌کنند. `editor` تنها برای فهرست سفید `_EDITOR_FINANCE_COMMANDS` حق نوشتن دارد. `admin` به عملیات ساختاری و بستن دوره دسترسی دارد. `apply_accounting_command`، هویت و لیست حساب‌ها را **معتبر و تأمین‌شده توسط میزبان** فرض می‌کند؛ به خودی خود کاربر را احراز هویت نمی‌کند.
2. **ذخیره‌سازی:** `StandaloneAccountingStore.command` در `standalone_accounting.py` با `BEGIN IMMEDIATE` و `expected_revision` تغییرات را اعمال می‌کند. `accounting_view` نیز ACL را بررسی می‌کند. این کنترل‌ها مانع جعل هویت در میزبانِ ناامن نمی‌شوند؛ میزبان باید actor درست را بدهد.
3. **LAN مدار:** `LanService.account_for(token)` در `lan.py` نشست سروری را پیدا می‌کند. `standalone_finance_access` پیش از خواندن/نوشتن دسترسی را می‌سنجد و `standalone_finance_accounts` فقط فیلدهای مجوز را به reducer تحویل می‌دهد. `standalone_command_request` اجازه ارسال `actor`، `companyId` یا `role` در envelope را نمی‌دهد.
4. **برنامه مستقل پس از اصلاح هم‌زمان:** در `standalone_accounting_desktop.py`، تابع `_run_company_session` برای `--companies-dir` یا دفتر دارای `local-users.json`، پیش از اولین read و backup ورود بومی را فراخوانی می‌کند. `_native_accounting_login` اکنون `(principal, token)` برمی‌گرداند؛ `AccountingDesktopAPI` توکن را نگه می‌دارد و در `_require_authenticated` پیش از read، command، قالب‌ها، درخواست تغییر شرکت و مشاوره مالیاتی آن را مجدداً بررسی می‌کند. آزمون logout و خواندن/نوشتن پس از آن پاس شده است. **مسیر بدون identity همچنان `local/admin` است.**
5. **هویت جدید مستقل:** `LocalCompanyIdentity` در `standalone_accounting_identity.py`، فایل `local-users.json`، هش رمز PBKDF2، نشست تصادفی در حافظه، `require_session`، `logout` و `accounting_accounts` را ارائه می‌دهد. اتصال آن به API با revalidation در هر درخواستِ بررسی‌شده وجود دارد. پوشش تمام مسیرهای بازیابی و رابط گرافیکی هنوز آزموده نشده است.
6. **انتخاب شرکت:** `--companies-dir` مسیر هر دفتر را از `StandaloneCompanyRegistry` می‌گیرد و `CompanySessionGuard` قفل فعال آن دفتر را نگه می‌دارد. `--data-dir` امکان انتخاب یک مسیر مطلق دلخواه بدون عبور از registry و company lock را می‌دهد؛ اگر کنار دفتر `local-users.json` باشد برنامه ورود می‌خواهد، ولی اگر فایل موجود نباشد، مسیر legacy به `local/admin` برمی‌گردد.

## سیاست مجوزها در میزبان مستقل

| عمل | admin | editor با `financeEdit=True` | viewer با `financeView=True` | بدون نشست |
|---|---|---|---|---|
| خواندن دفاتر و گزارش‌ها | مجاز | مجاز | مجاز | رد |
| ثبت فاکتور، دریافت/پرداخت، انبار و عملیات مجاز | مجاز | مجاز، مطابق فهرست سفید reducer | رد | رد |
| تغییر هویت حقوقی/مالیاتی شرکت، افتتاحیه سرمایه، بستن دوره | مجاز | رد | رد | رد |
| فهرست قالب‌ها | مجاز | مجاز | مجاز در صورت تصمیم محصول، فقط خواندنی | رد |
| ذخیره، حذف، پیش‌فرض‌کردن و کپی قالب‌ها | مجاز | مجاز | رد | رد |
| مدیریت کاربران، تغییر نقش، عملیات بازیابی دسترسی | مجاز | رد | رد | رد |
| جابه‌جایی شرکت | فقط پس از پایان امن نشست دفتر فعلی | با الزام ورود جداگانه به دفتر مقصد | با الزام ورود جداگانه به دفتر مقصد | فقط بازگشت به فهرست، بدون خواندن دفتر |

`financeEdit=True` برای کاربری با نقش `viewer` امتیاز نوشتن ایجاد نمی‌کند. نقش یا capability دریافتی از React، URL، JSON یا JS قابل اعتماد نیست. باید در هر درخواست از نشست سروری جاری محاسبه شود. اگر سیاست سازمانی خواندن را فقط به کاربران انتخاب‌شده بدهد، `financeView` مستقل باید در ماژول identity قابل تعریف شود؛ نسخه مشاهده‌شده `accounting_accounts()` فعلاً برای همه کاربران فعال `financeView=True` بازمی‌گرداند.

## قرارداد پیشنهادی ادغام در `standalone_accounting_desktop.py`

1. **پیش از دسترسی به دفتر:** ورود بومی اکنون در `_run_company_session` قبل از اولین read و backup برای حالت شرکت فعال شده است؛ این ترتیب باید در آزمون mock نیز ثابت شود. **دفتر ازقبل‌موجود که فایل کاربران آن مفقود شده است نباید مانند شرکت نو در اختیار اولین سازنده admin قرار بگیرد.** وجود ledger یا اسناد جانبی باید آغاز setup آزاد را مسدود و recovery امن را الزامی کند.
2. **ساخت API پس از ورود:** `_native_accounting_login` اکنون هم principal و هم token را برمی‌گرداند و سازنده `AccountingDesktopAPI` تطابق هویت را با `identity.require_session` می‌سنجد. `_require_authenticated(required)` نشست را در هر فراخوانی بررسی و `_accounts` را به‌روز می‌کند. این الگو را در افزوده‌های آینده حفظ کنید؛ نقش/توکن هیچ‌گاه از JavaScript پذیرفته نشود.
3. **ACL دوبل:** `standaloneAccountingRead` و `standaloneAccountingCommand` به‌ترتیب مجوز `viewer` و `editor` را قبل از ساخت Store بررسی می‌کنند. `actor` و `accounts` از همان هویت معتبر گرفته می‌شوند و `accounting_core._require` عملیات admin-only را مستقل کنترل می‌کند. capability برگشتی صرفاً راهنمای UI است.
4. **تمام متدهای pywebview:** `standaloneAccountingTemplateList/Save/Delete/Default/Duplicate` و `RequestCompanySwitch` در نسخه فعلی `_require_authenticated` را صدا می‌زنند؛ آزمون‌های مصنوعی مسیر قالب/خواندن/فرمان پس از logout اجرا شده‌اند. هر endpoint آینده، بازیابی یا عملیات مالیاتی نیز باید همین کنترل را داشته باشد. محدود بودن نام‌ها در `JS_BRIDGE` یک کنترل امنیتی محسوب نمی‌شود: JS ممکن است مستقیم `window.pywebview.api.*` را صدا بزند.
5. **تعویض دفتر/خروج:** قبل از آزادکردن lock و ایجاد API جدید، اجرای مالی متوقف، بکاپ نهایی معتبر تهیه، token قبلی invalidate و تمام ارجاع‌های session به دفتر قبلی حذف شوند. نشست شرکت A در شرکت B نباید قابل استفاده باشد، حتی وقتی نام کاربری مشابه است. شکست در هریک از مراحل باید اجرای دستور مالی را متوقف کند.
6. **تغییر نقش/غیرفعال‌سازی:** نقش باید در هر request مجدداً از رجیستری معتبر خوانده شود؛ revoke یا حذف کاربر، نشست موجود را نیز بی‌اثر کند. خروجی `accounting_accounts` هیچ هش، salt، رمز یا شیء حساس دیگری نداشته باشد. رخداد حسابداری actor تأییدشده را ثبت کند و گزارش تغییر نقش/کاربر مستقل از رخدادهای دفتر نگهداری شود.
7. **بازیابی:** نگهداری `local-users.json` کنار دفتر، سیاست backup/restore اختصاصی و کنترل دسترسی سیستم‌عامل می‌خواهد. بازگردانی دفتر بدون داده کاربران یا یک فایل هویت خراب نباید خودکار «admin محلی بی‌رمز» بسازد؛ جریان بازیابی خارج از نشست باید جدا، صریح و ممیزی‌پذیر باشد. هش رمزگذاری‌شده با رمزنگاری اطلاعات مالی اشتباه گرفته نشود: SQLite فعلی رمزگذاریِ محتوای دفتر را تضمین نمی‌کند.

### قرارداد توابع میزبان (برای پیاده‌ساز)

```python
# pseudocode: interfaces to implement in host, not existing tested functions
def _current_principal(self, required):
    # Native-only, company-bound token; not a JS argument.
    principal = self._identity.require_session(self._native_token, required)
    return principal["username"], self._identity.accounting_accounts()

def standaloneAccountingCommand(self, request):
    command, revision = standalone_command_request(request)
    with self._lock:
        actor, accounts = self._current_principal("editor")
        # Core still checks admin-only commands, viewer role and replay.
        return self._store().command(command, actor=actor, accounts=accounts,
                                     expected_revision=revision, now=trusted_utc())
```

این شبه‌کد الگوی طراحی است؛ معادل عملی آن اکنون با نام `_require_authenticated` در Host وجود دارد. توکن از ورودی درخواست دریافت نمی‌شود. مسیر سازنده بدون identity همچنان `local/admin` را نگه می‌دارد و باید تنها برای داده آزمایشی قابل استفاده بماند.

## تهدیدهای bypass و آزمون‌های پذیرش

| شناسه | سناریوی تهدید | کنترل موجود/آزمون | وضعیت اتصال نهایی |
|---|---|---|---|
| T01 | تزریق `actor`, `role`, `companyId`, `financeEdit`, `session` در درخواست command | `DesktopRequestBoundaryContracts` و `standalone_command_request`، رد قبل از IO | تست فعلی اجرا شده |
| T02 | viewer با `financeEdit=True` دستور مالی صادر کند | `FinanceAuthorityContracts`، رد در LAN و reducer | تست فعلی اجرا شده |
| T03 | editor به بستن دوره یا تغییر مالیات ارتقا یابد | فهرست سفید `_EDITOR_FINANCE_COMMANDS` و آزمون admin-only | تست فعلی اجرا شده |
| T04 | actor جدید رخداد دارای `eventId` قبلی را بازپخش کند | fingerprint شامل actor، آزمون تغییر actor | تست فعلی اجرا شده |
| T05 | salt/hash/password از registry به reducer نشت کند | projection و آزمون حذف secrets | تست فعلی اجرا شده |
| T06 | کاربر اولین بار خود را viewer ثبت کند یا admin بدون مجوز بسازد | `LocalCompanyIdentity` و آزمون راه‌اندازی و ارتقای نقش | تست مستقل هویت اجرا شده |
| T07 | token شرکت A در شرکت B، یا پس از logout/expiry استفاده شود | `LocalCompanyIdentity` و آزمون تبادل/انقضا | تست مستقل هویت اجرا شده |
| T08 | JS مستقیم API را صدا بزند یا بعد از logout/expiry ادامه دهد | ورود بومی، نگهداری توکن فقط در Host و revalidation هر call افزوده شده؛ آزمون logout قبل از IO پاس شد | **مسیر Python آزموده شد؛ GUI مستقیم هنوز آزموده نشده** |
| T09 | قالب‌ها و تعویض شرکت بعد از لغو نقش اجرا شوند | `Template*` و `RequestCompanySwitch` نشست live را بررسی می‌کنند؛ آزمون رد TemplateList/Save پس از logout پاس شد | **بخشی آزموده شد؛ GUI و بازیابی لازم است** |
| T10 | `--data-dir` دفتری بدون فایل identity را با admin ثابت باز کند | `--data-dir` با identity file ورود می‌خواهد؛ در نبود فایل fallback فعال است | **باز؛ تست expected failure** |
| T11 | read/backup قبل از login یا بعد از logout انجام شود | شرکت جدید ترتیب login→read→backup را دارد و read بعد از logout رد می‌شود؛ بررسی backup مستقل است | **بخشی آزموده شد؛ نیازمند آزمون GUI/mock** |
| T12 | فایل هویت مفقود از دفتر قدیمی موجب راه‌اندازی admin جدید شود | setup نخستین admin فعلی وجود SQLite را نمی‌سنجد | **باز؛ تست expected failure با دفتر مصنوعی داده‌دار** |

برای تکمیل T08 تا T12، آزمون فعلی Python را به GUI/WebView و چرخه واقعی `--companies-dir` گسترش دهید؛ قبل از ورود و بعد از revoke همهٔ `Read/Command/Template*/Switch` باید `PermissionError` یا `IdentityError` بدهند. سپس cross-company switch و بازگردانی بکاپ را در پوشه‌های مصنوعی اجرا کنید؛ آزمون فعلی تنها بخشی از این مسیر را پوشش می‌دهد.

## `--data-dir` قدیمی و خطر انتشار

`--data-dir` در حالت کنونی هر مسیر مطلق معتبر را قبول می‌کند؛ در `main` وقتی `--companies-dir` استفاده شود، ترکیب با `--data-dir` رد می‌شود. اجرای جداگانه `--data-dir=<registry>/books/<company-id>` **در صورت وجود `local-users.json` ورود می‌خواهد**؛ بنابراین ادعای دسترسی admin بدون رمز در این شرایط درست نیست. با این حال، `CompanySessionGuard` فقط در حالت `--companies-dir` فعال می‌شود. اگر فایل هویت شرکت حذف یا از بازیابی جا مانده باشد، مسیر `--data-dir` با `local/admin` کار می‌کند؛ انتخاب مسیر دیگرِ بدون identity نیز همین مشکل را دارد. این ضعف منطق fallback از کد استنباط شده و حمله به داده واقعی اجرا نشده است.

شرط انتشار امن: همهٔ روش‌های بازکردن دفتر، از جمله `--data-dir`، باید به احراز هویت بومی شرکت متصل شوند؛ یا برنامه باید این مسیر legacy را به یک اجرای کاملاً آزمایشی و جدا از دفاتر واقعی محدود کند. مهاجرت باید دادهٔ موجود را بدون ایجاد admin بی‌رمز حفظ کند. قفل registry و بررسی symlink/reparse point باید برای هر مسیر ورودی اعمال شود. صرف افزودن پیام اخطار یا پنهان‌کردن آرگومان CLI این bypass را برطرف نمی‌کند.

## شواهد اجرا و محدودیت‌ها

فرمان اجرا شده روی داده و پوشه‌های موقت:

```text
python -m unittest -v tests.test_standalone_accounting_authorization_contract
Ran 17 tests in 0.431s
OK (expected failures=2)

python -m unittest -q tests.test_standalone_accounting_desktop tests.test_standalone_accounting_host
Ran 30 tests in 4.028s
OK
```

آزمون‌ها علاوه بر reducer و identity، نقش viewer در API دسکتاپ، کنترل قالب‌ها، جعل principal و قطع دسترسی پس از logout قبل از IO را بررسی می‌کنند. **دو آزمون `expectedFailure`** برای fallback بدون هویت در legacy و امکان ساخت admin جدید روی دفتر دارای ledger ولی فاقد `local-users.json` باقی مانده‌اند؛ موفق‌بودن کل suite به معنای بسته‌شدن این دو نقص نیست. آزمون GUI، نصب EXE، مهاجرت دفتر واقعی و امنیت فایل‌های سیستم‌عامل انجام نشده است.
