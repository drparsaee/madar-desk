# مدار: تبدیل نقاط ضعف رقبا به مزیت محصول

**تاریخ تحلیل:** ۲۱ اکتبر ۲۰۲۶  
**دامنه:** ابزارهای مدیریت پروژه و کار Trello، ClickUp، Asana، Jira، monday.com، Notion، Linear، Todoist، Microsoft Planner، OpenProject و Plane.  
**هدف:** حفظ قابلیت‌های پایه و پیشرفته Trello، و ساخت مزیت مستقل برای Madar Desk به‌عنوان برنامه Windows-first، Local-first، فارسی و مناسب تیم‌های کوچک و کارگاه‌ها.  
**نوع سند:** تحقیق رقابتی و بک‌لاگ محصول. هیچ ردیفی به معنی پیاده‌سازی یا QA موفق نیست.

**وضعیت ابزار مهندسی معکوس (اصلاحیه پس از نصب):** REA v6.7.0، Java 21.0.12.1+1 و Ghidra 12.1.4 در `D:\CoS-Test\rea-lab\tools` نصب‌اند. بسته‌های اصلی در اجرای قبلی با SHA256 رسمی مطابقت داشته‌اند. آزمون مستقل native PE و شبه‌کد قبلی موفق بوده؛ آزمون مجدد `rea doctor --client codex --skill` با تنظیم صریح `JAVA_HOME` و `GHIDRA_INSTALL_DIR` نیز در ۲۱ اکتبر موفق و Ghidra available=true بوده است. پنجره ترمینال عادی این متغیرها را به ارث نمی‌برد و فرآیندهای MCP از قبل بازشده ممکن است تا reconnect تنظیمات قدیمی داشته باشند. جزئیات نصب در `D:\CoS-Test\rea-lab\DOWNLOAD_RETRY_STATUS_2026-10-21.md` و شواهد مجدد در `doctor-current-ghidra-20261021.json` است.

## روش شواهد

- **D = سند رسمی/قیمت‌گذاری یا محدودیت اعلام‌شده**؛ بیشترین اطمینان درباره وجود محدودیت، نه درباره برتری کیفیت رقیب.
- **R = گزارش کاربر/Reddit**؛ سیگنال کیفی قابل تحقیق، نه نرخ واقعی خرابی یا آمار نماینده.
- **I = استنباط طراحی/فرصت فرضی**؛ برای اثبات بازار نیاز به آزمایش کاربر و آزمون نرم‌افزار دارد.
- **M = شواهد داخل مدار**؛ مبتنی بر README/roadmap و مطالعه محدود کد، نه تست یکپارچه تازه.
- نرم‌افزارها مرتب تغییر می‌کنند؛ قیمت‌ها و سقف‌ها صرفاً تصویری از تاریخ این بررسی‌اند. نبود شاهد درباره ویژگی، به معنی نبود آن ویژگی نیست.

## ۱. عیب‌یابی مشخص Trello: ۱۶ فرصت

| کد | ضعف/شکاف Trello با سطح شاهد | مزیت پیشنهادی مدار | اولویت | آزمون پذیرش |
|---|---|---|---|---|
| TR-01 | دسکتاپ بدون اتصال فعال کار نمی‌کند [D1] | Offline-first واقعی: مشاهده، افزودن، ویرایش، جابه‌جایی و پیوست محلی | P0 | قطع اینترنت/سرور، انجام ۳۰ عملیات و بازیابی دقیق پس از راه‌اندازی مجدد |
| TR-02 | همگام‌سازی آفلاین دسکتاپ ندارد [D1] | Outbox مقاوم + sync idempotent | P0 | دوبار ارسال یک رویداد تنها یک‌بار اعمال شود و حذف داده رخ ندهد |
| TR-03 | کندی بردهای پرتعداد؛ پیشنهاد رسمی کمتر از ۱۰۰۰ کارت باز، یا کمتر از ۵۰۰ با پیوست/چک‌لیست زیاد [D2] | Virtualized Kanban و indexed search | P0 | ۱۰۰۰/۵۰۰۰/۱۰۰۰۰ کارت با پروفایل تست مستقل، بودجه FPS/زمان بارگذاری سنجیده و ثبت شود |
| TR-04 | قابلیت وابستگی Task به‌صورت بومی ندارد [D3] | Dependency DAG: blocks/blocked by، تشخیص چرخه و مسیر بحرانی | P1 | ایجاد چرخه رد شود؛ تغییر موعد پیش‌نیاز هشدار قابل‌فهم بدهد |
| TR-05 | محدودیت ۱۰ برد باز و ۱۰ همکار در Free [D4] | تعداد برد محلی بدون سقف مصنوعی محصولی (با guardrail فنی) | P1 | ایجاد ۳۰ برد/۱۵ عضو تستی بدون از دست رفتن مرجع و مجوز |
| TR-06 | حجم پیوست هر فایل در Free برابر ۱۰MB [D4] | ذخیره فایل محلی/SMB با quota و policy آشکار | P1 | پیوست ۱۵۰MB با هش، سطح دسترسی، quota و بازیابی |
| TR-07 | گردش automation quota، ۲۵۰ اجرا/ماه Free و ۱۰۰۰ Standard [D5] | اجرای محلی قواعد با سقف قابل‌تنظیم منابع، بدون شمارنده تجاری مصنوعی | P1 | جلوگیری از حلقه، ثبت log، retry و dedup با آزمون زمان‌بندی |
| TR-08 | operation quota حتی در Premium وجود دارد [D5] | شمارش شفاف مصرف CPU/Task، نمایش guardrail و graceful limit | P2 | رفتار اشباع صف و اجرای Rule مشخص و قابل مشاهده باشد |
| TR-09 | تقویم/Timeline/Dashboard/Table/Map در Premium [D4] | نماهای اصلی بدون پراکندگی محصول و با datasource مشترک | P1 | تغییر کارت در Kanban فوراً در تقویم، جدول و داشبورد منطبق باشد |
| TR-10 | Timeline روی موبایل دردسترس نیست [D6] | مدل نمایش responsive با پوشش کارکردهای اصلی در فاز موبایل | P3 | یک سناریوی یکسان زمان‌بندی در دسکتاپ/موبایل بدون از دست رفتن اطلاعات |
| TR-11 | Mirror card فقط در workspace پولی [D7] | single-source multi-board projection بدون تکثیر رکورد | P2 | ویرایش در هر نما همان cardId را تغییر دهد؛ ACL هر نما را رعایت کند |
| TR-12 | خروجی کلی همراه فایل‌ها برای Premium [D8] | export و backup کامل قابل بازگردانی با schema version | P0 | restore حساب، پیوست، task، مالی و audit در نسخه مستقل PASS |
| TR-13 | فایل JSON خام برای کاربر غیر فنی دشوار است [D9] | CSV/PDF/HTML مفهومی و بسته قابل ورود/خروج | P1 | export/import round-trip و diff مالی/چک‌لیست صفر |
| TR-14 | کاربران از تغییرات اجباری UX سال ۲۰۲۵ انتقاد داشتند [R1] | حالت کلاسیک/متمرکز، progressive disclosure و اختیاری بودن ویژگی‌ها | P1 | تغییر نسخه بدون تغییر ناگهانی جریان اصلی؛ سناریوی بازگشت تنظیمات |
| TR-15 | قدرت زیاد Power-Upها + workflow وابسته به افزونه [D3,D4] | هسته feature برای dependencies، forms، reporting، rule و finance | P1 | سناریوی عمومی بدون سرویس ثالث اجرا شود |
| TR-16 | ابزار مالی/حسابداری دوبل جزو دامنه اصلی Trello نیست [I] | پروژه → هزینه و صورت‌وضعیت → فاکتور → دفتر کل | P1 | هیچ هزینه کارت مستقیماً و بدون دستور معتبر سند مالی نسازد |

## ۲. مقایسه دیگر رقبا: ضعف واقعی، محدودیت پلن یا ریسک UX

| رقیب | محدودیت/شواهد | نقطه قوت بالقوه مدار | احتیاط |
|---|---|---|---|
| **ClickUp** | آفلاین ایجاد تسک دارد اما ویرایش تسک‌های ازقبل‌دیده‌شده و ساخت subtask آفلاین ندارد [D10] | offline CRUD یکپارچه با کنترل conflict | ClickUp را «بدون آفلاین» توصیف نکنید |
| ClickUp | ۶۰MB حجم Workspace رایگان [D11] و سقف‌های Automation براساس پلن [D12] | ذخیره محلی قابل ظرفیت‌سنجی و قوانین با اعتبار محلی | پرداخت برای سرویس ابری به‌خودی‌خود «باگ» نیست |
| ClickUp | گزارش‌های کاربران ۲۰۲۶ از کندی جست‌وجو/داشبورد و کندی عملیات [R2] | latency budget و تمرکز بر UI بدون ازدحام | گزارش موردی است؛ آزمون رقابتی کنترل‌شده لازم است |
| ClickUp | شکایت کاربران از نابرابری عملکرد موبایل و دسکتاپ [R3] | قرارداد عملیات همسان برای کلاینت‌ها | ادعای مطلق درباره همه نسخه‌ها نکنید |
| **Asana** | رایگان تا ۲ کاربر؛ Timeline/Gantt و automation در Starter، Portfolios/Goals/Resource در Advanced [D13] | ماژول‌های اصلی تیم کوچک با هزینه قابل پیش‌بینی | Asana پلن رایگان «فاقد پروژه/تقویم» نیست |
| Asana | Android آفلاین است ولی داده‌هایی که قبلاً باز نشده‌اند در دسترس آفلاین نیستند [D14] | prefetch کل پروژه انتخابی با وضعیت بارگذاری قابل مشاهده | قابلیت آفلاین Asana را نادیده نگیرید |
| Asana | یک گزارش کاربر از عدم برابری فیلتر چندگانه موبایل و دسکتاپ [R4] | parity عملیاتی موبایل و دسکتاپ | نسخه موبایل مدار هنوز محصول تحویل‌شده نیست |
| **Jira** | حدود و guardrail فنی از سپتامبر ۲۰۲۶ در حال اعمال‌اند [D15] | تجربه ساده برای تیم غیرفنی، مدل حداقلی و مسیر سفارشی | محدودیت‌ها برای مقیاس و پایداری‌اند، نه الزاماً نقص |
| Jira | برنامه‌ریزی پیشرفته dependency در Premium/Enterprise [D16] | وابستگی‌ها + مسیر بحرانی در حالت تیم کوچک | نیاز به تست load برای تضمین کیفیت |
| **monday.com** | Free بدون automation/integration [D17] | Automation محلی core + API مستقل | جایگزینی کامل اکوسیستم monday هدف اولیه نیست |
| monday.com | مستند رسمی موبایل می‌گوید تغییر آفلاین هنگام reconnect تغییر دیگری روی همان آیتم را override می‌کند و offline indicator ندارد [D18] | visible sync status + conflict merge/compare | اثر دقیق conflictها باید در مدار تست شود |
| **Notion** | دانلود دیتابیس آفلاین به طور پیش‌فرض ۵۰ ردیف اولین view [D19] | انتخاب صریح snapshot آفلاین کل workspace | Notion اکنون آفلاین دارد، نباید خلافش نوشته شود |
| Notion | AI blocks، embeds و بعضی عملکردهای پیشرفته آفلاین نیستند [D19] | هسته مستقل از AI و integration با graceful degradation | AI آنلاین مدار اختیاری باشد |
| **Linear** | می‌گوید offline failsafe است؛ بازنویسی تغییرات همکار در برخی ویرایش‌های آفلاین ممکن است [D20] | conflict-safe sync با causal revisions و diff | sync بی‌نقص بدون multi-client acceptance قابل ادعا نیست |
| Linear | تمرکز توسعه نرم‌افزار/issue؛ workflow کارگاهی نیاز به شخصی‌سازی دارد [I] | preset چاپ، تولید، طراحی، اداری و خدماتی | دسته‌بندی بازار، نه ضعف فنی مستقیم |
| **Todoist** | Free تا ۵ پروژه شخصی، ۳ فیلتر، تاریخچه فعالیت ۷ روز [D21] | پروژه‌ها و گزارش زمان/بازیابی جدی‌تر | Todoist عمداً تجربه تک‌کاربره سریع دارد |
| Todoist | ابزار تخصصی مدیریت مشتری/فاکتور/هزینه جایگزین ERP نیست [I] | project costing and billing end-to-end | عمداً با ERP رقابت نمی‌کند |
| **Microsoft Planner** | طبق مستندات نسخه Android برای کار به اینترنت نیاز دارد [D22] | دسکتاپ مستقل از اکانت Microsoft و اینترنت | ادعای عملکرد همه پلتفرم‌های Planner از یک صفحه قابل تعمیم نیست |
| **OpenProject** | self-hosting قدرتمند دارد؛ موبایل Beta بدون offline و push real-time [D23] | نصب سبک ویندوز + LAN اختیاری، offline | OpenProject در PM پیشرفته مزیت‌های جدی دارد |
| **Plane** | در self-hosted commercial فعال‌سازی لایسنس/آپدیت به اینترنت نیاز دارد؛ Airgapped جداگانه ارائه می‌کند [D24] | مسیر پیش‌فرض local بدون license heartbeat | وجود airgapped plane باید در مقایسه ذکر شود |

## ۳. ۳۲ درد مشترک و پاسخ پیشنهادی مدار

| شماره | درد کاربر/بازار | نتیجه مطلوب مدار | اولویت |
|---:|---|---|---|
| 01 | بازشدن کند پروژه و جست‌وجو | UI با virtualized rendering و فهرست indexشده؛ benchmark | P0 |
| 02 | قطع شبکه یا VPN | ۱۰۰٪ عملیات تک‌کاربره ضروری محلی | P0 |
| 03 | بازنویسی کار همکار | تغییرها هرگز silent overwrite نداشته باشند | P0 |
| 04 | ناواضح بودن وضعیت sync | سه حالت Pending / Synced / Conflict و شمارنده | P0 |
| 05 | ترس از از دست رفتن داده | backup کامل زمان‌بندی‌شده + restore test واقعی | P0 |
| 06 | دیتای حساس در ابر | offline local storage + TLS در شبکه و ACL واقعی | P0 |
| 07 | در هم آمیختن نقش‌ها و اطلاعات مالی | policy مستقل finance/view/edit همراه redaction | P0 |
| 08 | تغییرات غیر قابل ردیابی | append-only actor/time/event journal و history diff | P0 |
| 09 | وابستگی به اتصال ابری خارجی | LAN host + local cache + خروجی قابل انتقال | P0 |
| 10 | تجربه کاربری پیچیده | حالت Basic/Pro به‌صورت progressive disclosure | P0 |
| 11 | کندی ساخت تسک | Quick Capture کمتر از چند ثانیه به عنوان هدف آزمون | P1 |
| 12 | جابه‌جایی بین چند نرم‌افزار | inbox→task→project→invoice→payment ارتباط واقعی | P1 |
| 13 | گزارش‌ها با داده متفاوت | یک مدل داده برای برد، جدول، تقویم و گزارش | P1 |
| 14 | مدیریت ناقص زیرکار | checklist و nested subtasks پایدار با owner/date | P1 |
| 15 | وابستگی قابل اجرا بین کارها | DAG، blocker، critical path | P1 |
| 16 | مدیریت نامشخص وقت | time estimate/actual + timer + focus، اختیاری | P1 |
| 17 | پنهان ماندن فشار کاری تیم | workload و capacity با داده واقعی نه حدسی | P1 |
| 18 | هماهنگ نبودن برنامه روزانه | Personal Inbox، Today، Waiting، Follow-up | P1 |
| 19 | هجوم اعلان‌ها | digest، اولویت‌بندی، mute قابل کنترل | P1 |
| 20 | سختی مهاجرت از رقبا | Import از Trello JSON/CSV و CSV عمومی با preview | P1 |
| 21 | آشفتگی فایل‌ها | پیوست نسخه‌دار، thumbnail، checksum، SMB path و ACL | P1 |
| 22 | ناسازگاری شیوه تاریخ | ذخیره ISO، نمایش شمسی/میلادی، آزمون DST | P1 |
| 23 | ابهام هزینه و درآمد | قرارداد، برآورد، هزینه واقعی، طلب، دریافتی مجزا | P1 |
| 24 | خطای صدور فاکتور دوباره | شماره‌گذاری اتمیک، dedup و review قبل از issue | P1 |
| 25 | بازبودن مالی بدون سند | double-entry GL فقط پس از validation/approval | P1 |
| 26 | اتوماسیون خطرناک یا بی‌صدا | rule dry-run، log، stop-loss، rollback/compensation | P1 |
| 27 | خودکارسازی AI بدون اجازه | suggestion/diff + approval gate + traceability | P1 |
| 28 | هزینه نامعلوم مصرف AI | انتخاب مدل، سقف هزینه و خروجی احتمالاتی با provenance | P2 |
| 29 | نبود visibility میان بردها | unified search/reporting و mirror card | P2 |
| 30 | سفارشی‌سازی نامتناسب برای صنایع | template چاپ/بسته‌بندی/آژانس/کارگاه | P2 |
| 31 | وابستگی به قالب انحصاری | فرمت مستند و import/export loss report | P2 |
| 32 | پیچیدگی مدیریت سرور | Windows EXE، migration wizard، local diagnostics، restore wizard | P2 |

## ۴. تمایز محصول: ساخت همزمان «ساده» و «قدرتمند»

### شعار پیشنهادی داخلی

**مدار: مدیریت کار بدون وابستگی اجباری به اینترنت، با کنترل واقعی داده و پیوند مستقیم اجرای پروژه به مالی.**

این یک positioning پیشنهادی است، نه ادعای اثبات‌شده نسبت به کل رقبا.

### سه حالت کاربری، یک هسته داده

- **Basic:** برد، کارت، مسئول، موعد، یادآور، جست‌وجو. آشنا برای کاربر Trello، بدون تنظیمات سنگین.
- **Team/Operations:** وابستگی، زمان، workflow، automation، client approvals، گزارش و workload.
- **Finance/AI:** هزینه پروژه، قرارداد، فاکتور، دفتر کل قابل اعتماد، ایجنت با approval و audit.

مودها ویژگی‌ها را مخفی/آشکار می‌کنند، ولی هیچ‌گاه داده را حذف یا مبنای امنیت سمت سرور را دور نمی‌زنند.

### ضدالگوهایی که مدار نباید تکرار کند

1. افزودن ۳۰ ویژگی قبل از بستن تست backup/restore و conflict.
2. ارائه داده مالی به بیننده از طریق API عمومی پروژه.
3. استفاده از SQLite جداگانه برای فاکتور و تسک با فرض consistency خودکار.
4. ادعای «کاملاً آفلاین» در حالی که comment/attachment/calendar یا ورود کاربر بدون شبکه از کار می‌افتد.
5. معرفی گزارش سود بدون تفکیک وجه دریافت‌شده، درآمد تعهدی و هزینه واقعی.
6. اجرای ایجنت روی اطلاعات مشتری بدون permission و تأیید انسانی.
7. تقلید ظاهر و رفتار Trello به بهای از دست رفتن هویت فارسی/مالی/آفلاین.
8. معرفی سرعت/امنیت/قابلیت backup بدون آزمون EXE و دو سیستم واقعی.

## ۵. وضعیت واقعی مدار و اولویت اصلاح، مبتنی بر مستندات موجود

بر اساس `ROADMAP_EXECUTION_2026-10-21.md` و `README-FA.md`:

| نقطه تمایز | وضعیت مشاهده‌شده در مدار تا مستند موجود | اقدام بعدی |
|---|---|---|
| Windows app و Kanban فارسی | نسخه EXE آزمایشی وجود دارد | آزمون گردش‌کار کامل و نصب/آپدیت روی سیستم تازه |
| Local data | JSON legacy و SQLite opt-in با تست ماژول | ۰.۶.۱: storage اصلی، migration و rollback به همراه attachment/account |
| LAN roles، TLS و queued offline | بخشی پیاده؛ دو رایانه واقعی و conflict نیازمند پذیرش | ۰.۶.۳: QA دو سیستم، قطع/وصل، ACL و redaction |
| Project/card costing | کد و نمای اولیه، جدا از حسابداری دوبل | واحد پول/فرمت، جلوگیری از افشای هزینه، گزارش دقیق |
| Invoice drafts و event idempotency | ماژول `finance.py` و workflow داخلی | single atomic commit با task, finance, outbox, GL |
| Double-entry accounting | نمونه مستقل در `rea-lab/accounting-prototype`؛ به مدار وصل نشده | مدل حساب‌ها، دوره مالی، سند و دفتر کل در same-store |
| Multiple workspaces، cover، checklists | بخش‌هایی موجود؛ UX/QA کامل نیست | ۰.۶.۲ acceptance |
| Personal Planner | ناقص | Inbox و تقویم/تکرار در ۰.۷ |
| Table/Timeline/reporting | جزئی و ناقص | ۰.۸ |
| Automation | rule core اولیه؛ runtime و safety کامل نیست | ۰.۹ |
| Trello import/REST/MCP | در roadmap، نه اثبات‌شده | ۰.۱۰ |
| AI agent workflow | گزینه آینده | ۱.۱ بعد از data integrity |

**مهم:** README و roadmap گزارش تاریخی هستند. این تحقیق اجرای مجدد تست فعلی مدار نیست. هر ادعای «آماده است» نیاز به شواهد آخرین نسخه دارد.

## ۶. اولویت ارزش/ریسک: بسته‌های توسعه

| بسته | ارزش رقابتی | وابستگی و معیار Done | اولویت |
|---|---|---|---|
| M-01 Data Trust | مالکیت داده، بکاپ و آفلاین | SQLite unified + backup all domains + real restore + crash/CAS | P0 |
| M-02 Offline Sync Trust | حل قاطع درد Linear/monday در تداخل | revision/vector metadata؛ conflict UI؛ عدم silent loss در آزمون ۲ کلاینت | P0 |
| M-03 Large Board Performance | پیشی گرفتن از محدودیت Trello | ۱k/۵k/۱۰k card fixture، جست‌وجو، virtual scrolling، measurement logs | P0 |
| M-04 Simple Mode | اجتناب از شلوغی ClickUp | زمان انجام ۵ کار رایج با ۵ کاربر، روش قبل/بعد | P0 |
| M-05 Project Finance Safety | تمایز واقعی مدار | داده مالی محفوظ، cost vs sale، invoice approval، idempotent issue | P1 |
| M-06 Dependency & Planner | پوشش کاستی Trello | DAG and cycle checks + Today/Waiting + calendar | P1 |
| M-07 Rule Engine Safe | مزیت automation محلی | dry-run/replay/log/retry/loop cutout + restore | P1 |
| M-08 Independent Accounting GL | ترکیب عملیات و مالی | chart, journals, double-entry, trial balance, cancellation events, ACL | P1 |
| M-09 Migration Freedom | هزینه تغییر کمتر از رقبا | Trello JSON import, preview, export, attachment manifests | P1 |
| M-10 AI With Provenance | ارزش واقعی AI بدون غافل‌گیری | AI opt-in, inspectable change plan, approval/undo, budget caps | P2 |

### معیار پذیرش تجاری، نه فقط تست فنی

- از ۵ کاربر هدف (کارگاه چاپ/بسته‌بندی، آژانس یا تیم ۳ تا ۲۰نفره) ۳ سناریو عملی «از درخواست تا تسویه» اجرا شود.
- ۳ کاربر تازه‌وارد باید برد/تسک/زمان/مسئول را بدون آموزش مفصل تکمیل کنند؛ زمان و خطا ثبت گردد.
- در قطع LAN/اینترنت، ۲۵ ویرایش از دو کلاینت شبیه‌سازی و پس از reconnect با no-data-loss و explicit conflict تطبیق داده شود.
- Restore داده مرجع شامل فایل‌ها، کاربران، مجوزها و حسابداری پس از یک crash مصنوعی با چک‌سام و گزارش اختلاف صفر انجام شود.
- درآمد شناسایی‌شده و وجه دریافتی متفاوت باقی بمانند؛ اعداد از بودجه/هزینه‌های کارت به‌طور ناخواسته فاکتور نشوند.
- باز شدن برد ۱۰۰۰ کارت و ۵۰۰۰ کارت روی دستگاه هدف کاربر با معیار performance ثبت‌شده ارزیابی شود، نه عدد ساختگی در بازاریابی.

## ۷. منابع پایه با تاریخ بررسی

**مستندات رسمی (D):**

- [D1 Trello desktop online requirement](https://support.atlassian.com/trello/docs/trello-desktop-apps/)
- [D2 Trello slow board guidance, <1000 cards](https://support.atlassian.com/trello/docs/troubleshooting-a-slow-board/)
- [D3 Trello dependency management not native](https://support.atlassian.com/trello/docs/creating-and-managing-task-dependencies/)
- [D4 Trello plan limits October 2026](https://trello.com/en-US/pricing)
- [D5 Trello automation quotas](https://support.atlassian.com/trello/docs/butler-quotas-and-limits/)
- [D6 Trello Timeline availability/mobile](https://support.atlassian.com/trello/docs/timeline-view/)
- [D7 Trello mirror cards](https://support.atlassian.com/trello/docs/card-types/)
- [D8 Trello premium export](https://support.atlassian.com/trello/docs/trello-premium-user-guide/)
- [D9 Trello JSON-export caveats](https://support.atlassian.com/trello/docs/making-sense-of-trellos-json-export/)
- [D10 ClickUp offline feature/limits](https://help.clickup.com/hc/en-us/articles/6308895791127-Offline-Mode)
- [D11 ClickUp storage caps](https://help.clickup.com/hc/en-us/articles/33463620625559-Workspace-storage-limits)
- [D12 ClickUp automation quotas](https://help.clickup.com/hc/en-us/articles/23477062949911-Automations-feature-availability-and-limits)
- [D13 Asana official pricing](https://asana.com/pricing)
- [D14 Asana Android offline](https://help.asana.com/s/article/android-basics?language=en_US)
- [D15 Jira config limits enforced starting Sep 2026](https://support.atlassian.com/jira-cloud-administration/docs/data-limits-and-guardrails/)
- [D16 Jira advanced dependency planning](https://support.atlassian.com/jira-software-cloud/docs/view-all-of-an-issues-dependencies-on-your-timeline/)
- [D17 monday free plan](https://support.monday.com/hc/en-us/articles/360010487220-Understanding-the-Free-Plan)
- [D18 monday mobile offline conflict behavior](https://support.monday.com/hc/en-us/articles/360017712819-Mobile-app-Offline-Mode)
- [D19 Notion official offline coverage](https://www.notion.com/en-gb/help/use-pages-offline)
- [D20 Linear official offline limitations](https://linear.app/docs/get-the-app)
- [D21 Todoist plan and limits](https://www.todoist.com/pricing/)
- [D22 Microsoft Planner Android Internet requirement](https://support.microsoft.com/en-us/planner/microsoft-planner-for-android-help)
- [D23 OpenProject mobile beta limitations](https://www.openproject.org/docs/mobile-app-guide/help-reference/known-limitations/)
- [D24 Plane self-hosted/airgapped](https://plane.so/self-hosted)

**شواهد جامعه (R)، برای آزمون فرضیه نه ادعای نرخ خرابی:**

- [R1 Reddit Trello UX rollout criticism, July 2025](https://www.reddit.com/r/trello/comments/1m1wmjd/congratulations_trello_is_now_hot_garbage/)
- [R2 Reddit ClickUp performance issues, Sep 2026](https://www.reddit.com/r/clickup/comments/1w89ps5/clickup_is_so_slow_that_im_about_to_look_hard_at/)
- [R3 Reddit ClickUp mobile/offline complaints, Apr 2026](https://www.reddit.com/r/clickup/comments/1sez7gt/clickup_is_my_world_since_years_but_i_am/)
- [R4 Reddit Asana mobile functional parity, Aug 2026](https://www.reddit.com/r/Asana/comments/1vzaa85/extremely_annoyed_with_the_lack_of_features_on/)

## ۸. اصل نهایی

در فاز اول **قابل‌اعتمادتر** شویم؛ در فاز دوم **ساده‌تر و سریع‌تر**؛ در فاز سوم **قدرتمندتر**. رقابت بر سر طولانی‌تر شدن فهرست قابلیت‌ها بدون سنجش کاربری، دقیقاً همان خطایی است که از رقبا درس می‌گیریم.

## ۹. پیگیری مبتنی بر کد پس از نصب REA، ۲۱ اکتبر

این بخش از بررسی مجدد فایل‌های موجود، و نه از ادعای تحقق Trello parity، اضافه شده است:

- **ابزار:** Temurin Java `21.0.12.1+1` و Ghidra `12.1.4` در آزمایشگاه نصب شده‌اند؛ در آزمایش مجدد با env صریح، `rea doctor --client codex --skill --json` با `healthy=true` و provider `ghidra.available=true` پایان یافت. شواهد `rea-lab/doctor-current-ghidra-20261021.json` است. اتصال *فرآیند MCP از قبل فعال* بدون reconnect جداگانه تأیید نشده است.
- **CD05 حذف امن کارت:** کد فعلی `src/App.jsx` از `src/cardtrash.js` استفاده می‌کند و زباله‌دان بازیابی دارد. آزمون متمرکز همین نشست: `node --test tests/cardtrash.test.cjs tests/cardtrash_ui_contract.test.cjs` برابر **29/29 PASS** و `py -3.12 -m unittest tests.test_card_trash_contract -v` برابر **10/10 PASS**؛ شامل اعتبارسنجی داده، JSON/SQLite، فاکتور/پیوست، ACL و CAS. این **تأیید در کد و تست خودکار** است، نه تست کلیک واقعی یا ۲ کامپیوتر.
- **کاندیدای اجرایی:** در فضای مشترک `release/Madar-Desk-v1.0-rc5-cardtrash-candidate.exe` ساخته شده و گزارش `.qa-rc5-cardtrash-gui-smoke.log` برای smoke عمومی برد موجود است. وجود فایل یا عبور smoke عمومی هنوز تست تعاملی زباله‌دان یا انتشار پایدار را ثابت نمی‌کند.
- **TR03 عملکرد برد بزرگ:** `src/App.jsx` در تابع filtered برای هر کارت `workspaceBoards.some(...)` و `boards.find(...).stages.some(...)` انجام می‌دهد و در Kanban، `items.map(...<TaskCard />)` کل کارت‌های هر ستون را رندر می‌کند (حدود خطوط 525–539 و 842–849). این یک **ریسک الگوریتمی قابل مشاهده** برای هزاران کارت است، نه benchmark واقعی. گام P0 پیشنهادی بعدی: indexed board visibility + رندر مجازی مرحله‌ای و سنجش ۱هزار، ۵هزار و ۱۰هزار کارت با داده ساختگی بدون هزینه واقعی.
- **مرز انتشار:** `MADAR_CONTINUITY.md` هنوز وضعیت‌های کد، QA، GUI و پذیرش واقعی دو ماشین را جدا می‌کند. پس از هر تغییر در سورس، full isolated QA و EXE جدید باید دوباره آزموده شود؛ هیچ‌کدام از نتایج بالا به معنی parity ۱۰۰٪ نیست.
