# بازیابی آفلاین حسابداری مستقل مدار

## دامنه و وضعیت

این ابزار یک عملیات **دستی، صریح، فقط آفلاین و یک‌طرفه** است که بکاپ SQLite معتبر حسابداری مستقل TOMAN را به یک دیتابیس **جدید و از قبل ناموجود** برمی‌گرداند. نام ماژول standalone_accounting_restore.py است و فایل‌های NEW این tranche عبارت‌اند از:

- standalone_accounting_restore.py
- tests/test_standalone_accounting_restore.py
- STANDALONE_ACCOUNTING_RESTORE.md

فایل‌های Store حسابداری، backup قبلی، native_app، LAN، رابط کاربری، task manager، unified finance، RIAL V2، PARSIAN و دیتابیس‌های عملیاتی تغییر نکرده‌اند. هیچ restore خودکار، migration، startup hook، پیدا کردن APPDATA، اتصال تسک یا انتشار برنامه اضافه نشده است.

## شرط حیاتی: اجرای واقعی در حالت OFFLINE

**قبل از هر اجرای واقعی، همه نمونه‌های مدار، سرور LAN و هر برنامه دیگری که دیتابیس مقصد را باز می‌کند متوقف باشند.** ابزار نمی‌تواند به‌صورت قطعی ثابت کند که هیچ فرایند خارجی دیتابیس را بعداً باز نمی‌کند. گزینه --offline صرفاً اعلام صریح مسئول عملیات است، نه قفل سراسری سیستم یا بررسی processها.

هر دو تأیید الزامی‌اند: --acknowledge-plaintext و --offline. تأیید plaintext یعنی دیتابیس خروجی **رمزنگاری‌نشده** است. فایل‌های بازیابی‌شده شامل اطلاعات مالی و اشخاص هستند و باید روی فولدر محدود و دیسک امن نگهداری شوند.

## دستور CLI

نمونه فقط برای درک فرمت و با مسیرهای ساختگی:

    python -m standalone_accounting_restore --source "D:\PRIVATE_TEST_BACKUPS\standalone-manual-20261022.sqlite3" --destination "D:\EMPTY_TEST_ROOT\standalone-accounting.sqlite3" --acknowledge-plaintext --offline

API Python:

    from pathlib import Path
    from standalone_accounting_restore import restore_standalone_accounting

    result = restore_standalone_accounting(
        Path(r"D:\PRIVATE_TEST_BACKUPS\standalone-manual-20261022.sqlite3"),
        Path(r"D:\EMPTY_TEST_ROOT\standalone-accounting.sqlite3"),
        plaintext_acknowledged=True,
        offline_acknowledged=True,
    )

مسیر source باید بکاپ SQLite موجود و معتبر باشد؛ نام بکاپ می‌تواند مانند نسخه‌پشتیبان قبلی تاریخ‌دار باشد. مقصد باید **دقیقاً** standalone-accounting.sqlite3 نام داشته باشد و نباید در فایل‌سیستم موجود باشد. هر دو مسیر از نوع Path مطلق هستند. پوشهٔ والد مقصد باید قبلاً ساخته شده باشد. هیچ مسیر پیش‌فرض APPDATA یا فایل تولیدی به‌صورت ضمنی استفاده نمی‌شود.

## مسیر امنیتی بازگردانی

1. ابتدا هر دو Boolean واقعی برای اقرار plaintext و حالت آفلاین بررسی می‌شوند؛ عبارت یا عدد یا ورودی نامعتبر پذیرفته نیست.
2. فقط فایل source معمولی و موجود پذیرفته است. فایل symlink، Windows junction در مسیر یا والد، یا فایل‌هایی با sidecarهای SQLite به نام‌های -wal، -shm، -journal رد می‌شوند. این یک شرط محافظه‌کارانه برای بکاپ قابل‌حمل تک‌فایلی است.
3. پوشه مقصد باید موجود باشد؛ مقصد (حتی hard-link موجود به همان inode مبدأ)، symlink، مقصد خراب یا path دارای junction رد می‌شود. اگر مقصد فعلاً ناموجود اما sidecarهایی مانند standalone-accounting.sqlite3-wal باقی مانده باشند، عملیات ممنوع است؛ هیچ فایل قبلی پاک یا overwrite نمی‌شود.
4. قبل از ساخت فایل موقت، SQLite ورودی با اتصال mode=ro و query_only باز و در تراکنش خواندن بررسی می‌شود: user_version=1، schema دقیق و فقط جدول standalone_accounting، PRAGMA integrity_check، شماره revision و _decode_checked برای SHA-256، canonical JSON و بازپخش کامل رویدادها، از جمله معنای آنها. این قرارداد از اعتبارسنجی موجود standalone_accounting_backup.py استفاده می‌کند و الگوریتم دفتر رویداد را تکثیر نمی‌کند.
5. در همان پوشه مقصد یک فایل موقت انحصاری با tempfile.mkstemp ساخته می‌شود. با sqlite3.backup از مبدأ فقط‌خواندنی یک snapshot سازگار گرفته می‌شود. این یک raw file copy نیست.
6. فایل **موقت** بار دیگر از طریق Store.read با actor داخلی ساختگی و تستی، و سپس checkpoint و journal_mode=DELETE اعتبارسنجی می‌شود؛ تاریخچه حتی اگر digest ذخیره‌شده توسط مهاجم دوباره محاسبه شده باشد باید معنای معتبر داشته باشد. شماره revision و digest بکاپ اولیه با snapshot نهایی مقایسه می‌شوند. اگر متفاوت باشند، عملیات رد می‌شود.
7. تنها فایل موقت برای fsync با دسترسی r+b باز می‌شود؛ مبدأ همچنان فقط‌خواندنی است. انتشار با os.link در همان پوشه مقصد، به‌صورت atomic create-if-absent و بدون overwrite انجام می‌شود، سپس fsync دایرکتوری در حد پشتیبانی OS انجام می‌شود.
8. در خطا قبل از انتشار، فایل موقت و sidecarهای مختص آن پاک می‌شوند. اگر انتشار موفق شده ولی عملیات بعدی شکست بخورد، فقط فایل تازه‌ای که **هنوز همان inode موقت خود ما** است قابل جمع کردن است؛ هیچ فایل دیگری که فرایند ثالث جایگزین کرده حذف نمی‌شود.

## ممنوعیت‌های صریح

- **مقصد از قبل موجود را هرگز بازنویسی نمی‌کند.** برای recovery یک پایگاه موجود باید برنامه خاموش و فایل فعلی با فرآیند جداگانه، دارای نسخه پشتیبان و تأیید انسانی، به محل امن منتقل شود؛ این ابزار چنین تغییری را انجام نمی‌دهد.
- هیچ کاربر، مبلغ یا منبع مالی از task manager، APPDATA، unified SQLite، legacy finance یا RIAL V2 جمع‌آوری/ترکیب نمی‌شود.
- دیتابیس مبدأ نه با StandaloneAccountingStore سازنده باز می‌شود، نه migrate/init و نه با sqlite3 اتصال write. اجرای backup/restore روی داده واقعی در این tranche انجام نشده است.
- نسخه‌پشتیبان دارای اعتبار SQL، checksums و بازپخش معنایی است، ولی **امضای رمزنگاری‌شده یا اثبات اصالت خارج از دیتابیس ندارد**. مهاجمی با امکان بازنویسی تاریخچه کامل ممکن است بکاپ جعلیِ خودسازگار تولید کند.

## محدودیت‌های فنی و concurrency

OFFLINE بر عهده اپراتور است؛ هم‌زمان اجراشدن یک نویسنده روی فایل مقصد یا شروع مجدد میزبان پس از تأیید، توسط این اسکریپت قفل جهانی نمی‌شود. اختلاف (revision,digest) بین سر بکاپ هنگام بررسی و نسخه کپی‌شده رد می‌شود، ولی فایل مبدأ می‌تواند بلافاصله بعد از snapshot تغییر کند؛ بدون قفل خارجی و توقف برنامه ضمانت فراتر وجود ندارد.

hard-link به filesystem با پشتیبانی فایل‌لینک (مانند NTFS) نیاز دارد. هیچ fallback غیراتمیک با copyfile یا os.replace وجود ندارد. fsync دادهٔ موقت روی ویندوز با r+b انجام می‌شود و fsync پوشه best-effort است؛ پایداری مطلق در برابر قطع برق/خرابی سخت‌افزار تضمین نمی‌شود. کنترل symlink/junction پیش از عملیات انجام می‌شود اما جلوی همهٔ حملات TOCTOU توسط مهاجم دارای مجوز تغییر پوشه را نمی‌گیرد. روی فولدر اختصاصی و مجوز محدود کار کنید.

از بازگردانی فقط با SOURCE بکاپ معتبر مستقل TOMAN پشتیبانی می‌شود؛ این ابزار نه همگام‌سازی با تسک‌منیجر است و نه ادعای آماده‌بودن نسخه انتشار مدار.

## شواهد تست

    python -B -m unittest discover -s tests -p test_standalone_accounting_restore.py -q

آزمون‌ها کاملاً روی TemporaryDirectory اجرا شدند و شامل backup→restore→Store.read برابری دقیق، revision صفر، ادامه ثبت CAS بعد از بازیابی، عدم بازنویسی دیتابیس یا فایل موجود، same inode/hard-link، symlink مبدأ/مقصد/والد، ممنوعیت sidecarها، foreign task/unified schema، version غیرمجاز، SHA-256 خراب، تاریخچه جعلی حتی با digest بازحساب‌شده، خطای copy/validation/fsync، race انتشار، concurrent restore، تفاوت digest با revision برابر، cleanup بعد از link و عدم حذف فایل جایگزین فرایند دیگر، و CLI موفق و ردشده است.

### نتیجه واقعی روی Windows، ۲۲ اکتبر ۲۰۲۶

| فایل تست | PASS | FAIL |
|---|---:|---:|
| test_standalone_accounting_restore.py | 36 | 0 |
| test_standalone_accounting_backup.py | 28 | 0 |
| test_standalone_accounting.py | 15 | 0 |
| test_standalone_accounting_host.py | 25 | 0 |
| **جمع چهار مجموعه** | **104** | **0** |

هر چهار فرمان unittest با exit code صفر تمام شده است. پیام «Backup refused» در یکی از تست‌های بکاپ، خروجی مورد انتظار سناریوی عمدیِ عدم بازنویسی فایل موجود بود، نه شکست مجموعه آزمون.

تمام آزمون‌ها از داده‌های مصنوعی استفاده کردند. هیچ APPDATA، داده واقعی، Git یا release لمس نشده است.
