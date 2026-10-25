# وضعیت اجرای بسته‌های رقابتی مدار

**تاریخ ارزیابی:** 2026-10-21  
**مبنای خواسته:** `COMPETITOR_WEAKNESSES_TO_MADAR_STRENGTHS_2026-10-21.md`  
**نسخه:** source working tree، بدون Git و بدون انتشار production  
**تعریف وضعیت:** «اتصال کد» به معنی پذیرش روی دستگاه واقعی، تکمیل معیار Done، یا هم‌ارزی ۱۰۰٪ Trello نیست.

| بسته | شواهد اجرایی موجود در پروژه | وضعیت ادغام و پذیرش |
|---|---|---|
| M-01 Data Trust | `app_storage.py`, `full_recovery.py`, `maintenance_recovery.py`، آزمون‌های atomic revision/WAL/restore | پایه اجرایی؛ قبول recovery با داده مرجع واقعی و بازگردانی تمام پیوست/مجوزها هنوز باز |
| M-02 Offline Sync Trust | `offline_exchange.py`, `cloud_continuity.py`, `src/sync_health.js` و `tests/test_m02_reconnect_25_edits.py` | ۲۵ ویرایش غیرهمپوشان دو کلاینت در پوشه موقت ادغام شد؛ تداخل یک کارت صریح باقی ماند؛ **۲/۲ تست مصنوعی PASS**؛ آزمون LAN واقعی و conflict UI باز |
| M-03 Large Board Performance | `src/board_performance.js` به فیلتر/گروه‌بندی App متصل، `src/progressive_lane.jsx` حداکثر ۲۴۰ عنصر React در هر ستون، benchmark مصنوعی در `scripts/benchmark_large_board.cjs` | پیاده‌سازی و تست محدود؛ FPS/رندر حقیقی روی Windows هدف، scroll/focus GUI و ۱k/۵k acceptance باز |
| M-04 Simple Mode | `src/interface_mode.js/.jsx` و tiered UI در `src/App.jsx`؛ تنظیم محلی براساس هویت حساب، ACL مستقل | اتصال UI، تست static و SSR؛ آزمون ۵ کاربر/زمان و کلیدهای UX در محیط نصب‌شده باز |
| M-05 Project Finance Safety | `finance_visibility.py` و `lan.py` redaction + guard editor؛ UI ارقام admin و حالت مالی؛ `finance.py` و حسابداری پایه | آزمون واحد/LAN موقت؛ invoice lifecycle/approval کامل و GUI واقعی نیازمند تأیید مستقل |
| M-06 Dependency & Planner | `src/card_dependencies.js`, `card_dependency_validation.py` در `native_app.is_valid`, `src/card_dependency_panel.jsx` در TaskEditor | گراف DAG و UI اولیه؛ هشدار تغییر موعد، Today/Waiting و تقویم هنوز متصل نیستند |
| M-07 Rule Engine Safe | `automation_v1.py`, `rule_safety.py`, `m07_host_guard.py`؛ guard پیش از enqueue و run در SQLite opt-in | **RC8 QA کامل و smoke موفق**، ۹ آزمون host و ۳ آزمون orchestration؛ causal provenance پایدار، audit معتبر و LAN واقعی هنوز باز |
| M-08 Independent Accounting GL | `accounting_core.py`, `accounting_service.py` پایه؛ `accounting_gl.py` kernel ایزوله با تست double entry، trial balance، reverse | دو طرح موجود؛ **هیچ dual posting مجاز نیست**. هم‌مخزن‌سازی kernel جدید با host/finance و crash acceptance باز |
| M-09 Migration Freedom | `src/trello_import.js`, `src/migration_export.js`، `src/portable_export_panel.jsx` در UI با افشای omissions و consent؛ JSON/CSV فقط عملیاتی | export متصل به UI؛ manifest پیوست از host، import roundtrip از UI و بدون‌اتلاف واقعی مالی/باینری باز |
| M-10 AI With Provenance | NEW `ai_change_review.py` و `tests/test_ai_change_review.py`، پیش‌نمایش محدود سه فیلد وظیفه، approval intent، budget/provenance/undo plan؛ MCP اصلی read-only | **18/18 تست ایزوله موفق**؛ مدل واقعی متصل نیست و هیچ host write/approval durable یا AI mutation فعال نشده |

## شواهد متمرکز در این نوبت

- Python `tests.test_finance_visibility` و `tests.test_lan_finance_projection`: **16/16 PASS** در پوشه disposable.
- Python `tests.test_card_dependency_validation` + `tests.test_finance_visibility`: **21/21 PASS**.
- Node `tests/board_progressive`, `board_performance`, `interface_mode_ui_contract`, `interface_mode`, `migration_export`: **63/63 PASS**.
- Node `tests/card_dependencies` و `tests/listarchive_ui_contract`: **25/25 PASS** پس از بروزرسانی assertion قدیمی مبتنی بر inline filtering.
- Vite `npm run build`: PASS (آخرین ساخت پس از اتصال M06 UI، ۱۶۳۸ ماژول؛ هشدار chunk بزرگ غیرمسدودکننده).
- M-07 `tests.test_rule_safety`, `tests.test_automation_v1`, `tests.test_collab`: **68/68 PASS** (گزارش همان worker، نه تکرار مستقل توسط Prime).
- M-07 host path after RC7 build: `tests.test_m07_guard_unit` **3/3 PASS**, `tests.test_m07_host_preflight` **9/9 PASS** با SQLite disposable، `tests.test_release_automation_host` در مجموعه ۵۰تایی اتوماسیون PASS؛ `test_app_storage.py` جداگانه 30/30 PASS. این مسیر در RC8 بسته‌بندی شد، نه RC7.
- M-10 `py -3.12 -m unittest tests.test_ai_change_review -q`: **18/18 PASS** در اجرای مستقل Prime؛ ماژول صرفاً پیش‌بررسی/طرح تغییر است و هیچ side effect خارجی ندارد.
- M-02 `py -3.12 -m unittest tests.test_m02_reconnect_25_edits -v`: **2/2 PASS**، اجرای جدید پس از QA جامع، در دو مسیر داده موقت؛ جدا از شمار آزمون‌های جامع بالا.
- **آزمون کامل انتشار:** `py -3.12 scripts/release_qa.py --full` پس از اصلاح قراردادهای قدیمی: **632 Python + 265 JavaScript PASS، خروج 0**. اولین اجرای QA با خطاهای تست static قدیمی متوقف شد؛ آن آزمون‌ها با مسیرهای جدید تطبیق و مجدداً اجرا شدند.
- **کاندیدای جدید:** RC7 با نام مستقل و بدون بازنویسی RC5/RC6 ساخته شد؛ **۹/۹ smoke PASS** روی loopback/DOM/Bridge/font/board/PNG و دیگر شاخص‌های smoke. `native_done=false` برای callback تصویر، ولی PNG با CRC و zlib معتبر است؛ GUI click acceptance هنوز باز.
- **SHA256 RC7:** `E655D2824A8F9B7DEA8D7FE072DB54025306234FE5392B985ADA241B1118A1D9`، اندازه 13,840,449 بایت. جزئیات در `RC7_COMPETITIVE_CANDIDATE_VERIFICATION_2026-10-21.md`.
- **QA جامع جدید پس از M07:** `py -3.12 scripts/release_qa.py --full` exit 0؛ **۱۹ release regressions + ۶۶۶ Python + ۲۶۵ JavaScript = ۹۵۰ pass**.
- **نامزد RC8:** `release/Madar-Desk-v1.0-rc8-rule-safety-candidate.exe`، build exit 0، EXE smoke **۹/۹ PASS**. حجم **13,854,878 بایت**؛ SHA-256 `9D063DF504BBC422F9CD8B6F6D07DA125B9228CA98B14DD9C47FCF39E79A62A0`. گزارش کامل: `RC8_RULE_SAFETY_CANDIDATE_VERIFICATION_2026-10-21.md`. هیچ گیت دستی با این نتیجه خودکار بسته نشده است.

## دروازه‌های پذیرش باز

1. آزمون واقعی دو دستگاه Windows با LAN قطع/وصل و ۲۵ تغییر مصنوعی، CAS، نمایش conflict و zero silent loss.
2. Restore مرجع شامل کل وظایف، accounts، finance، attachments و audit پس از crash با چک‌سام صفر اختلاف.
3. کاربرهای واقعی: ۵ نفر، سناریوهای درخواست تا تسویه، و ثبت زمان/خطا برای ایجاد برد/تسک/مسئول/موعد.
4. benchmark واقعی برد ۱۰۰۰ و ۵۰۰۰ کارت و FPS قابل بازتولید روی سخت‌افزار مقصد؛ bench Node مصنوعی جایگزین آن نیست.
5. آزمون click/keyboard/drag و feature regressions در EXE جدید، جدا از smoke باز شدن برنامه.
6. تطبیق ۲۲۰ معیار Trello؛ snapshot static تاریخی 39 covered/112 partial/69 missing، نه درصد parity پذیرفته‌شده.

**قید محیط:** هیچ تغییر مجاز به نصب production، APPDATA/LOCALAPPDATA واقعی، Google Drive واقعی، SQLite مالی واقعی، یا RCهای سابق نیست. پروژه فاقد `.git` است.

## نامزد تست کاربر RC9 (افزوده‌شده پس از RC8)

- فایل مستقل: `release/Madar-Desk-v1.0-rc9-user-testing-candidate.exe` با SHA256 `9D70EAC7D9F8D8E0BD313EFFC7C8BA3659F59A76843BCF467D57414940E4BBC1`؛ RC8 یا نامزدهای پیشین بازنویسی نشده‌اند.
- گزارش آزمون: `RC9_USER_TEST_CANDIDATE_VERIFICATION_2026-10-21.md`. QA کامل با **19 release + 684 Python + 276 JavaScript = 979 PASS**؛ GUI واقعی روی EXE با **23/23 PASS** از جمله بازکردن حسابداری و ذخیره کارت در میزبان ایزوله.
- اصلاحات افزوده‌شده: `finance_reference_guard.py` جهت جلوگیری از جداشدن task و سند حسابداری، جلوگیری از حذف پروژه دارای کارت، اصلاحات ورودی/پرداخت در `src/accounting_panel.jsx`، صفحه‌بندی فهرست طولانی، کنترل focus در modal و نسخه قابل‌شناسایی در footer.
- بسته ارسال به کاربر آزمایشی: `release/Madar-Desk-v1.0-rc9-user-testing-package.zip` همراه راهنما و سناریوها، SHA256 `47de63e0f1666c5ec2832e3ee5159fdf2fe701cf2c06d91ae525697a6a41c832`؛ ZIP با CRC و هش محتوا بررسی شد.
- همچنان **نامزد تست کنترل‌شده با داده ساختگی**؛ دفترکل مستقل M08، M10 اعمال AI، LAN واقعی دو دستگاه، بازیابی کامل پیوست/حساب و FPS فیزیکی ۱۰۰۰/۵۰۰۰ کارت معیارهای بسته‌نشده هستند. صدور قانونی مالیاتی تأیید نشده است.
