# پشتیبان‌گیری دستی و مستقل حسابداری مدار

## وضعیت واقعی

فایل standalone_accounting_backup.py ابزاری **دستی، اختیاری و بدون رمزنگاری** برای تهیه یک کپی منسجم از پایگاه داده جدید standalone-accounting.sqlite3 است. این ماژول تنها برای حسابداری مستقل TOMAN است و به task manager، finance.json، madar-unified.sqlite3، RIAL V2، انبار، backupهای قدیمی یا میزبان LAN وصل نیست.

ابزار نه backup خودکار دارد، نه restore/import/migration، نه آپلود، نه وابستگی به APPDATA و نه خروجی EXE. فایل خروجی SQLite plaintext است؛ هر فردی با دسترسی به فایل می‌تواند اطلاعات مالی آن را بخواند. مقصد را روی دیسک رمزگذاری‌شده با دسترسی محدود نگه دارید.

## نحوه اجرا

CLI با دو مسیر کامل و صریح:

    python -m standalone_accounting_backup --source "C:\my-private-data\MadarDesk\standalone-accounting.sqlite3" --destination "D:\my-private-backups\accounting-snapshot-20261022.sqlite3" --acknowledge-plaintext

مسیرهای بالا نمونه‌اند؛ ابزار خودش APPDATA را پیدا نمی‌کند، پوشه نمی‌سازد، دیتابیس مفقود را مقداردهی نمی‌کند و مقصد را حدس نمی‌زند. آرگومان --acknowledge-plaintext به معنای پذیرش نبود رمزنگاری است؛ نبود این تأیید عملیات را متوقف می‌کند.

استفاده از API:

    from pathlib import Path
    from standalone_accounting_backup import backup_standalone_accounting
    result_path = backup_standalone_accounting(
        Path(r"C:\my-private-data\MadarDesk\standalone-accounting.sqlite3"),
        Path(r"D:\my-private-backups\manual.sqlite3"),
        plaintext_acknowledged=True,
    )

مبدأ باید فایل عادی موجود با نام دقیق standalone-accounting.sqlite3 باشد؛ نام‌های unified/task/finance/backup مجاز نیستند و schema مستقل هم باید تأیید شود. فولدر مقصد باید از قبل وجود داشته باشد. وجود فایل مقصد (حتی hard-link، symlink یا symlink خراب) باعث رد عملیات می‌شود؛ هر بار نام مقصد تازه انتخاب کنید.

## مراحل عملیاتی و اعتبارسنجی

1. تأیید مقدار Boolean واقعی plaintext_acknowledged=True؛ بررسی مسیرهای absolute، وجود مبدأ و رد source/destination/ancestor symlink.
2. ایجاد فایل موقت انحصاری با tempfile.mkstemp در همان پوشه مقصد؛ هیچ خروجی روی مسیر نهایی در این مرحله ایجاد نمی‌شود.
3. اتصال به مبدأ با URI SQLite در حالت mode=ro و PRAGMA query_only=ON؛ استفاده از sqlite3.Connection.backup برای گرفتن snapshot منسجم حتی در حضور writerهای هم‌زمان. بر خلاف کپی بایتی، commitهای موجود در WAL در snapshot حفظ می‌شوند.
4. بررسی PRAGMA integrity_check، user_version=1، schema دقیق جدول standalone_accounting، revision و SHA-256. تابع standalone_accounting._decode_checked برای تاریخچه غیرخالی JSON canonical، hash chain و بازپخش معنایی accounting_core.validate_accounting_state را بررسی می‌کند. سپس StandaloneAccountingStore(temp).read با actor داخلی ساختگی و admin، بدون حساب کاربر واقعی، برای کنترل مجدد view/revision اجرا می‌شود. دیتابیس معتبر خالی با revision صفر پذیرفته است.
5. فایل موقت پس از تأیید، از WAL به journal_mode=DELETE برمی‌گردد تا کپی مستقل یک‌فایلی باشد؛ بررسی مجدد integrity/replay انجام می‌شود.
6. با os.fsync روی **کپی موقت و descriptor قابل نوشتن r+b** داده به storage flush می‌شود. این اصلاح روی ویندوز لازم است چون fsync روی handle فقط خواندنی ممکن است Bad file descriptor بدهد.
7. انتشار با os.link(temp,destination) انجام می‌شود: hard-link همان‌دایرکتوری ایجاد فایل را **اتمیک و بدون overwrite** می‌کند. os.replace استفاده نشده است. sync دایرکتوری در صورت پشتیبانی best-effort است و نام موقت پاک می‌شود.

در خطای SQLite، checksum، replay، fsync یا no-clobber، نام موقت و sidecarهای مربوط به **همان نام موقت** حذف می‌شوند، درحالی‌که فایل مبدأ دست‌نخورده می‌ماند. در race ساخت مقصد نیز فایل برنامه دیگر حفظ می‌شود.

## محدودیت‌ها

- هیچ روش restore امنی در این tranche تعریف نشده است. فایل را روی دیتابیس در حال اجرا کپی/overwrite نکنید. Restore آفلاین باید جداگانه طراحی و تست شود.
- خود plaintext backup رمزنگاری ندارد؛ SHA-256 داخلی یک امضای مستقل نیست و مهاجم با دسترسی نوشتن می‌تواند آن را محاسبه کند.
- snapshot یک نقطه از زمان است؛ تراکنش‌هایی که **بعد از** snapshot commit شده‌اند ممکن است داخل نسخه موجود نباشند. پایین‌تر بودن revision پشتیبان نسبت به head فعلی لزوماً خطا نیست.
- مسیرهای symlink موجود رد می‌شوند، اما این ابزار یک sandbox در برابر حمله خصمانه به filesystem یا تعویض junction/ancestor هم‌زمان نیست؛ فقط روی فولدرهای محدود و معتبر اجرا کنید.
- انتشار hard-link فقط روی filesystemهایی مثل NTFS که hard-link را پشتیبانی می‌کنند انجام می‌شود. ابزار برای filesystemهای فاقد hard-link fallback غیراتمیک نمی‌سازد. sync دایرکتوری در ویندوز best-effort است؛ تضمین قطع برق/خرابی سخت‌افزار مطلق نیست.
- اتصال SQLite مبدأ ro است، ولی بسته به وضعیت WAL ممکن است sidecarهای مشترک -shm استفاده شوند. سازنده StandaloneAccountingStore روی **مبدأ** هرگز اجرا نمی‌شود.
- خروجی فقط اطلاعات حسابداری مستقل legacy TOMAN است؛ شامل RIAL V2، موجودی، تسک‌منیجر یا سایر صورت‌حساب‌ها نیست. این قابلیت به معنی آمادگی انتشار EXE نیست.

## آزمون‌های مستقل

    python -B -m unittest discover -s tests -p test_standalone_accounting_backup.py -q

سناریوهای synthetic: پایگاه اولیه خالی و تاریخچه چندرویدادی، writer concurrent و snapshot منسجم، backupهای هم‌زمان یک مقصد، same path و hard-link alias، symlink مبدأ/مقصد/والد (اگر Windows privilege بدهد)، مقصد موجود و race انتشار، مبدأ ناموجود، نام اشتباه و دیتابیس foreign، schema version نامعتبر، checksum خراب، replay معنایی خراب **حتی با digest بازحساب‌شده**، عدم تأیید plaintext، مسیر نسبی، خرابی mid-copy/replay/fsync و cleanup، CLI موفق و رد بدون تأیید. همه تست‌ها روی TemporaryDirectory و داده ساختگی‌اند. APPDATA، SQL واقعی، Git یا release لمس نشده‌اند.

### نتیجه نهایی اجرا روی ویندوز

| مجموعه unittest | PASS | FAIL |
|---|---:|---:|
| test_standalone_accounting_backup.py | 28 | 0 |
| test_standalone_accounting.py (worker-10) | 15 | 0 |
| test_standalone_accounting_host.py (worker-11) | 25 | 0 |
| **مجموع** | **68** | **0** |

تمام فرمان‌ها exit code صفر داشتند. متن Backup refused برای آزمون عمدی عدم overwrite موجود در stderr انتظار می‌رفت و به معنی شکست suite نیست.
