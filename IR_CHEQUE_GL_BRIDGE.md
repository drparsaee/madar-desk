# پل مستقل چک به دفتر روزنامه ریالی مدار

## محدوده

ماژول ir_cheque_journal_adapter.py فقط از هسته frozen چک و ژورنال ریالی و مدل کدینگ استفاده می‌کند. از رویداد چک یک proposal مستقل با دو خط متوازن می‌سازد و در صورت فراخوانی صریح، آن را به post_journal می‌دهد. هیچ ذخیره‌سازی، بانکداری واقعی، APPDATA، رابط کاربری، EXE یا finance قدیمی را تغییر نمی‌دهد.

## نگاشت صریح

ChequeGLAccounts برای یک شرکت، یک چک، یک شخص، یک حساب بانکی متعلق به شرکت، و کدهای حساب به صورت PostingReference کامل تنظیم می‌شود. حساب‌ها از ChartSnapshot واقعی انتخاب می‌شوند؛ fallback/حدس کدینگ وجود ندارد. حساب مسدود، آرشیوی، گروه، اشتباه از نظر نوع حساب، متعلق به شرکت دیگر یا با party/project/detail فاقد تأیید رد می‌شود.

| نقش | نوع حساب | معنی |
|---|---|---|
| in_hand | asset | چک‌های دریافتی در دست |
| transferred | asset | حساب معلق اسناد واگذارشده با policy صریح |
| deposited | asset | چک‌های در جریان وصول |
| bank | asset | وجه نقد نزد بانک |
| ar | asset | مطالبات از صادرکننده |
| ap | liability | بدهی به طرف تجاری |
| returned | asset | چک‌های برگشتی دریافتنی |
| payable | liability | چک‌های پرداختنی صادرشده |

## نگاشت گردش‌های حسابداری

هر ردیف دو خط با مبلغ **صحیح و مساوی RIAL** دارد؛ مگر موارد «بدون سند» که proposal آنها None است و post_journal اصلاً فراخوانی نمی‌شود.

| رویداد | بدهکار | بستانکار | وجه نقد |
|---|---|---|---|
| RECEIVE | in_hand | ar | ندارد |
| DEPOSIT | deposited | in_hand | ندارد |
| CLEAR دریافتی | bank | deposited | افزایش فقط هنگام CLEAR |
| BOUNCE دریافتی | returned | deposited | ندارد |
| REDEPOSIT | deposited | returned | ندارد |
| RETURN از RECEIVED | ar | in_hand | ندارد |
| RETURN از BOUNCED | ar | returned | ندارد |
| ENDORSE با PENDING_TRANSFER_ONLY | transferred | in_hand | ندارد |
| ISSUE پرداختی | ap | payable | ندارد |
| PRESENT / REPRESENT پرداختی | بدون سند | بدون سند | ندارد |
| BOUNCE پرداختی | بدون سند | بدون سند | ندارد |
| CLEAR پرداختی | payable | bank | کاهش فقط هنگام CLEAR |
| RETURN / CANCEL پرداختی | payable | ap | ندارد |
| REVERSE DEPOSIT | in_hand | deposited | ندارد |
| REVERSE BOUNCE دریافتی | deposited | returned | ندارد |
| REVERSE REDEPOSIT | returned | deposited | ندارد |
| REVERSE بانک‌گردشِ بدون سند پرداختی | بدون سند | بدون سند | ندارد |

### مفروضات ضروری

ثبت سند فاکتور پایه و شناسایی قبلی AR/AP باید در میزبان اتفاق افتاده باشد. مقدار prior_ar_ap_accrued=True در VerifiedChequeGLContext به‌تنهایی اثباتش نمی‌کند. میزبان باید وضعیت و مالکیت آن سند را مستقلاً از داده قفل‌شده خودش تأیید کند. واگذاری ENDORSE فقط با policy صریح PENDING_TRANSFER_ONLY به حساب معلق منتقل می‌شود؛ این انتقال تسویه بدهی به تأمین‌کننده یا تعیین مسئولیت حقوقی را اثبات نمی‌کند. RETURN بعد از ENDORSED عمداً رد می‌شود، زیرا domain frozen آن را terminal می‌کند و مالکیت چک برگشتی مبهم است.

## قرارداد API

تابع cheque_journal_source_id(company_id, cheque_id, cheque_event_id) شناسه پایدار chqsrc.<SHA256> ایجاد می‌کند. JournalSource از نوع independent با همان شناسه و event_id دفتر با قالب chq.<SHA256> ساخته می‌شود؛ شناسه به شرکت/چک/رویداد وابسته است، نه payload قابل تغییر. VerifiedScopes میزبان باید جفت دقیق ('',source_id) را مجاز کند. ثبت قبلی همین منبع حتی تحت journal event ID متفاوت رد می‌شود. host باید uniqueness را در DB هم enforce کند.

تابع propose_cheque_journal به ChequeState معتبر، JournalState معتبر، شناسه رویداد، ChequeGLAccounts، ChartSnapshot، VerifiedScopes، CompanyMoneyPolicy و VerifiedChequeGLContext احتیاج دارد. تابع post_cheque_journal همان proposal را با snapshotهای فعلی دوباره محاسبه می‌کند و پس از تطبیق کامل، post_journal موجود را اجرا می‌کند. نتیجه فقط JournalState جدید حافظه‌ای است.

VerifiedChequeGLContext حامل company_id، cheque_id، cheque_event_id، تاریخ جلالی رویداد، تاریخ میلادی ثبت، fiscal_period_id، actor_id، prior_ar_ap_accrued و transfer_policy است. این آبجکت فقط یک **ورودی ادعایی** است؛ بدون attestation معتبر میزبان، نه تبدیل تاریخ و نه مجوز قانونی اثبات نمی‌شود. تبدیل جلالی به میلادی توسط این ماژول انجام نمی‌شود. میزبان باید تاریخ جلالی/میلادی را با تبدیل دقیق و نسخه‌بندی‌شده تأیید کند؛ کد تنها تطبیق هویت، تاریخ معتبر میلادی، ممنوعیت آینده، و بازه دوره مالی ژورنال را کنترل می‌کند. بسته بودن دوره را replay_journal و post_journal رد می‌کنند.

پیش از سند مالی جدید، پل تمام مراحل **مالی قبلی همان چک** را با شناسه منبع canonical در JournalState جست‌وجو می‌کند و سمت بدهکار/بستانکار، مبلغ، حساب، actor و دوره مالی را تطبیق می‌دهد. سند مالی جعلی روی مراحل memo-only رد می‌شود. تغییر نگاشت حسابداری تاریخی باعث fail-closed می‌شود تا host شواهد تاریخی chart و حساب‌های واقعی را reconcile کند.

## گیت‌های اتصال میزبان و تراکنش

1. احراز actor، مالکیت شرکت و طرف‌حساب، چک صیادی، حساب بانکی، وضعیت قطعی بانک، سند مبنای AR/AP، احراز supplier و مدارک CANCEL/REVERSE/RETURN فقط از منبع معتبر host. ساخت VerifiedScopes از درخواست کاربر مجاز نیست.
2. ذخیره تغییر ChequeState، JournalState، finance snapshot، شماره منبع تجاری، سند بانکی، audit hash و CAS در **یک تراکنش واقعی SQL**. در هر خطا rollback کامل. optimistic CAS هسته جای transaction isolation و unique indexes را نمی‌گیرد.
3. uniqueness بر کلیدهای شرکت+شناسه چک فیزیکی، شرکت+نوع/شناسه منبع تجاری، شرکت+event ID چک، و شناسه source و event دفتر روزنامه به شکل اتمیک اعمال شود. بعد از timeout همان رویداد باید با سند موجود reconcile شود.
4. مالی موجود ir_finance_v2_extension فقط برای workflow محدود صدور فاکتور است. اتصال عمومی cheque + finance + journal نیازمند composer مجزا و آزمون concurrent CAS، قطعی برق و rollback است.
5. تاریخ جلالی باید به میلادی با الگوریتم حسابرسی‌شده تبدیل شود. fiscal period هر دو حوزه باید به واقع یک دوره باشد؛ برابری صرف ID یا معتبر بودن تاریخ در بازه journal اثبات انطباق تقویم نیست.
6. تسویه واگذاری اسناد، رسیدگی به برگشت ENDORSED، استرداد چک پس از CLEAR، اصلاح نقدینگی پس از تسویه، کارمزد بانکی، اسناد تضمینی/ارزی و چند ذینفع خارج از این قرارداد هستند و بدون سیاست حسابداری و داده کافی **رد** می‌شوند.

## آزمون

اجرای تست از ریشه پروژه:

    python -B -m unittest discover -s tests -p test_ir_cheque_journal_adapter.py -v

آزمون‌های مستقل و مصنوعی صحت ریال صحیح و توازن دوطرفه، حساب‌های معتبر، stages، قرارداد فرضی فاکتور از پیش شناسایی‌شده، تکرار source با event جدید، جعل شرکت/شخص/بانک، دوره، تاریخ میلادی، memo-only، ردیابی مراحل قبلی و fail-closed را پوشش می‌دهند. **هیچ تست rollback واقعی یا host/SQL/APPDATA/Windows EXE/بانک واقعی انجام نشده است.** اثبات atomic coupling و authorization به میزبان سپرده شده است.
