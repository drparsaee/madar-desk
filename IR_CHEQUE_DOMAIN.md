# دامنه مستقل خزانه و چک ریالی مدار

## محدوده و وضعیت

فایل `ir_treasury_cheques.py` یک هسته pure / immutable برای گردش چک‌های **دریافتی و پرداختی** است. وضعیت برنامه یا پایگاه داده را تغییر نمی‌دهد. ذخیره‌سازی، احراز هویت، کنترل واقعی بانک، فعال‌سازی در رابط کاربری، صدور سند حسابداری و تسویه خودکار پیاده‌سازی نشده‌اند. وجود PASS در تست‌های مصنوعی، اثبات امنیت host یا SQL/Windows EXE نیست.

- واحد: فقط **RIAL** با `int` دقیق، مثبت و در سقف مجاز `money_policy.require_rial_amount`. float، bool، مبلغ صفر و تومان خام رد می‌شوند.
- تقویم: **JALALI** با رشته ASCII دقیق `YYYY-MM-DD`، بازه سال 1200 تا 1600، تعداد روز معتبر ماه و سال کبیسه با روش break-year جلالی. هیچ `timestamp` یا تبدیل خودکار به تقویم میلادی وجود ندارد. `ir_journal_v2.py` فعلاً تاریخ **میلادی** می‌پذیرد؛ در adapter میزبان باید تبدیل معتبر با سیاست رسمی ثبت و تست شود.
- تفکیک: `company_id` روی state، instrument، command و scope؛ `fiscal_period_id` روی هر رویداد؛ تاریخ رویداد داخل دوره ثبت‌شده. لیست دوره‌ها مرتب، غیرهمپوشان و immutable است.
- ثبت با `ChequeBusinessSource(kind, source_id)` است. هر جفت منبع در کل تاریخچه همان شرکت دقیقاً یک بار مجاز است، **حتی با event_id متفاوت**. از این رو برای عملیات بانکی و وضعیت‌های جدید باید source ID مستقل، معتبر و قابل ردگیری ثبت شود. یک صورتحساب شامل چند چک باید **منبع در سطح سطر چک** داشته باشد، نه یک source ID مشترک برای کل صورتحساب.
- یک `instrument_id` در یک شرکت، مستقل از نوع RECEIVABLE/PAYABLE و حتی پس از لغو/بازگشت، دوباره ثبت نمی‌شود. میزبان باید این شناسه را از مشخصات قابل اتکای برگ چک (شناسه صیادی یا شناسه مرکب استاندارد خود) بسازد؛ برنامه هیچ شماره صیادی، بانک، سند فیزیکی یا حساب خارجی را به‌صورت برخط اعتبارسنجی نمی‌کند.

## قرارداد کاربردی

`new_cheque_state(company_id, periods: tuple[ChequePeriod, ...])` با تقویم و دوره‌های صریح اجرا می‌شود.

`append_cheque_event(state, command, *, scopes, expected_revision, today)`:

1. کل تاریخچه و زنجیره SHA-256 را از ابتدا replay می‌کند؛ دستکاری command، ترتیب، تکرار منبع و انتقال غیرمجاز رد می‌شوند.
2. revision کنونی را با `expected_revision` تطبیق می‌دهد؛ retry دقیق همان `event_id` و digest بدون تغییر state پذیرفته می‌شود؛ payload متعارض رد می‌شود.
3. `VerifiedChequeRefs` میزبان را برای تطبیق شرکت، شناسه شخص، بانک، حساب بانکی خود شرکت، گیرنده تأییدشده supplier و دوره‌های مالی بسته می‌خواهد.
4. تاریخ ثبت را با `today` صریح مقایسه می‌کند؛ عملیات آینده رد و ثبت چک از قبل سررسیدگذشته پذیرفته می‌شود.
5. رویداد جدید `ChequeEvent(command, command_digest, previous_hash, event_hash)` را به یک state **جدید** اضافه می‌کند.

`replay_cheques(state)` فقط ساختار و شواهد درون stream را بررسی می‌کند و `ChequeReplay` برمی‌گرداند: `positions`، `intents`، `reversed_event_ids`، `revision`. نگهداری mutable «مانده قابل اعتماد» وجود ندارد.

`overdue_cheques(state, *, today)` فقط چک‌هایی را که `maturity_date < today` هستند و در وضعیت فعال/معوق قرار دارند، بر اساس سررسید و شناسه مرتب می‌کند؛ CLEARED، RETURNED، CANCELLED و ENDORSED حذف می‌شوند. سررسید **امروز** معوق محسوب نمی‌شود. چک ظهرِ امروز را بدون تأیید بانک «برگشتی» فرض نمی‌کند.

## انتقال وضعیت‌ها

| نوع | وضعیت قبلی | اقدام | وضعیت جدید |
|---|---|---|---|
| دریافتی | وجود ندارد | RECEIVE | RECEIVED |
| دریافتی | RECEIVED | ENDORSE به supplier معتبر | ENDORSED |
| دریافتی | RECEIVED | DEPOSIT به حساب بانکی معتبر شرکت | DEPOSITED |
| دریافتی | DEPOSITED | CLEAR | CLEARED |
| دریافتی | DEPOSITED | BOUNCE با دلیل | BOUNCED |
| دریافتی | BOUNCED | REDEPOSIT به حساب بانکی شرکت | DEPOSITED |
| دریافتی | RECEIVED / BOUNCED / ENDORSED | RETURN با دلیل | RETURNED |
| پرداختی | وجود ندارد | ISSUE از حساب معتبر شرکت | ISSUED |
| پرداختی | ISSUED | PRESENT | PRESENTED |
| پرداختی | PRESENTED | CLEAR | CLEARED |
| پرداختی | PRESENTED | BOUNCE با دلیل | BOUNCED |
| پرداختی | BOUNCED | REPRESENT | PRESENTED |
| پرداختی | ISSUED / BOUNCED | RETURN با دلیل و تحویل اصل چک | RETURNED |
| پرداختی | ISSUED | CANCEL با دلیل | CANCELLED |
| هر دو | آخرین اقدام مؤثر DEPOSIT / PRESENT / BOUNCE / REDEPOSIT / REPRESENT | REVERSE با target و دلیل | وضعیت قبل از اقدام |

**قیدهای برگشت:** فقط آخرین اقدام بانکی مؤثر، با اشاره دقیق به رویداد هدف، قابل برگشت است. امکان برگشت ثبت اولیه، تسویه CLEARED، واگذاری ENDORSED، لغو، یا برگشت نهایی وجود ندارد. تاریخ هیچ عملیات بعدی نباید پیش از عملیات قبلی همان چک باشد. ارائه/وصول بانکی قبل از سررسید رد می‌شود؛ ثبت اولیه چک پس از سررسید مجاز است. اصلاح تسویه وصول‌شده به workflow مستقل برگشت سند حسابداری/مغایرت بانکی و مجوز میزبان نیاز دارد. `REVERSE` نیازمند مدرک واقعی بانک است که این هسته نمی‌تواند آن را اثبات کند.

## مرز دفتر روزنامه و نقدینگی

`PostingIntent` دارای `event_id`، شرکت، دوره، شناسه چک، منبع تجاری، `kind`، مقدار صحیح `amount_rial` و `cash_effect` است. **هیچ تابعی در این ماژول `post_journal` را اجرا نمی‌کند.**

- دریافت، صدور، واگذاری، برگشت و لغو، فقط رویداد نیازمند تحلیل حسابداری تولید می‌کنند. آثار بدهکار/بستانکار AR/AP، حساب واسط اسناد دریافتنی/پرداختنی و انتقال تعهد واگذاری بر اساس سرفصل واقعی شرکت تصمیم‌گیری می‌شوند.
- DEPOSIT، REDEPOSIT، PRESENT و REPRESENT فقط `BANK_*_MEMO` با `cash_effect=NONE` و `requires_accounting_review=False` تولید می‌کنند. صرف ارائه به بانک، «وجه نقد وصول‌شده» نیست.
- تنها **CLEAR** دارای `cash_effect=DEBIT_BANK` برای دریافتی یا `CREDIT_BANK` برای پرداختی است. چون CLEARED پایانی است، یک چک نمی‌تواند دوباره CLEAR شود و مجموع intentهای نقدی برای آن حداکثر یک است.
- خود intent **سند حسابداری قطعی، مانده بانکی یا ضمانت تسویه نیست**. میزبان باید قبل از ثبت، رسید بانک را تصدیق، مجوز actor را بررسی، سرفصل‌های معتبر ChartSnapshot/PostingReference را انتخاب، تراز بدهکار و بستانکار را کنترل و سپس در `ir_journal_v2.post_journal` سند بزند.

### adapter مورد نیاز در میزبان

1. فقط از هویت احراز‌شده میزبان `company_id` و `actor_id` استخراج شود. `VerifiedChequeRefs` از بانک/اشخاص/حساب‌ها و `closed_period_ids` از مرجع معتبر ساخته شود؛ درخواست UI حق تعیین دامنه مجاز را ندارد.
2. مالکیت منبع invoice/task/expense/bank به همراه `(source_kind, source_id)` و `instrument_id` در همان تراکنش snapshot با unique constraint ثبت و کنترل شود. شناسه رویداد چک و شناسه سند مالی idempotency مستقل و به هم لینک شوند. برای هر intent متقاضی ثبت، کلید مستقل `cheque:event_id` بسازید.
3. مبدل تاریخ جلالی → میلادی معتبر و versioned بسازید؛ `fiscal_period_id` تقویم و دامنه ژورنال باید با قرارداد fiscal period متعلق به همان شرکت تطبیق داده شود. تطبیق رشته جلالی با رشته Gregorian مجاز نیست.
4. نوع منبع ژورنال فقط `task/card/checklist/independent` است و در `VerifiedScopes` نیاز به تأیید میزبان دارد. برای عملیات چک مستقل، adapter باید سند/منبع مستقل تأییدشده و `JournalSource(kind="independent", source_id=<verified cheque intent id>)` بسازد؛ مقدار خام `ChequeBusinessSource(kind="bank")` قابل عبور مستقیم به ژورنال نیست.
5. commit اتمیک: تغییر immutable ChequeState + snapshot مالی/دفتر/رسید + head revision/hash + unique keys + ثبت audit در **یک SQL transaction** با CAS و rollback. optimistic CAS در کد، به‌تنهایی atomic نیست. سازگاری با Snapshot مالی legacy TOMAN باید صریح و بدون بازتفسیر مبلغ باشد.
6. تأیید تاریخ واقعی بانک، تصدیق شناسه صیادی و مالکیت حساب خارجی، حقوق واگذاری، بازگشت فیزیکی اصل سند و سطح دسترسی برای CANCEL/REVERSE/CLEAR باید در host اجرا شود. زنجیره hash بدون anchor امضاشده/خارج پایگاه داده، مقاومت در برابر بازنویسی عمدی کل تاریخچه ندارد.

## آزمون

```powershell
python -B -m unittest discover -s tests -p test_ir_treasury_cheques.py -v
```

آزمون‌ها فقط داده ساختگی و حافظه را درگیر می‌کنند؛ نه فایل مالی عملیاتی، نه APPDATA، نه SQL/Parsian، نه رابط کاربری یا EXE. پوشش: مبلغ یک ریال و MAX_RIAL، ممنوعیت float/bool، شرکت و شخص/بانک غیرمجاز، منبع تجاری تکراری با event_id متفاوت، شماره چک تکراری در دو جهت، CAS stale، retry دقیق، نقل و انتقال به supplier، ارائه/وصول/برگشت/تکرار بانکی، محدودیت لغو و معکوس‌سازی، تاریخ جلالی و کبیسه، دوره بسته، تاریخچه دستکاری‌شده حتی با hash دوباره محاسبه‌شده، گزارش معوقات قطعی و منع double-cash recognition.

**محدودیت شواهد:** PASS واحد فقط صحت رفتار توابع pure را در ورودی‌های پوشش‌داده‌شده نشان می‌دهد. تست live host، احراز مجوز عملیاتی، ذخیره‌سازی اتمیک، rollback واقعی، حمله هم‌زمان کاربران، اتصال به GL، مهاجرت TOMAN و تأیید بانک هنوز اجرا نشده‌اند.
