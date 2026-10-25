# M-04 | حالت ساده، تیمی و مالی مدار

وضعیت در بازبینی کد ۲۱ اکتبر ۲۰۲۶: **اتصال M-04 در `App.jsx` توسط عامل اصلی انجام شده و قرارداد ایستای رابط در دامنه آزمون‌های زیر PASS است.** ماژول شامل `src/interface_mode.js`، `src/interface_mode.jsx`، `src/interface_mode.css` و آزمون‌های `tests/interface_mode.test.cjs` و `tests/interface_mode_ui_contract.test.cjs` است. این بررسی به معنی آزمون تعاملی EXE یا کامل‌شدن پذیرش تجاری نیست.

## رفتار

سه سطح `basic` (ساده)، `operations` (تیم و عملیات)، `finance` (مالی و هوش مصنوعی) روی یک مدل داده کار می‌کنند. Basic: برد/کارت، ساخت کار با مجوز ویرایش، مسئول، موعد، یادآور، جست‌وجو و فیلتر سبک. Operations: علاوه بر آن گزارش، تقویم/زمان‌بندی، برنامه‌ریز، تاریخچه، فیلتر پیشرفته، اتوماسیون و ابزارهای مدیر در صورت داشتن مجوز. Finance: علاوه بر آن پیش‌فاکتور، مدیریت مالی، سود و هزینه برای مدیر. قابلیت AI در نسخه فعلی بر اساس این ماژول ساخته یا فعال نمی‌شود؛ قابلیت نمایش ورودی احتمالی آن علاوه بر حالت finance به `canManage` و `aiAvailable:true` نیاز دارد. اجرای AI مستقل از این gate باید دارای کنترل دسترسی و تأیید انسانی باشد.

قابلیت‌های اساسی نگهداری و بازیابی (sync/شبکه، backup/restore، تنظیمات، اعلان‌ها و پروفایل) در هر سه حالت نمایان می‌مانند. تغییر حالت فقط ترجیح نمایش همان حساب است. هیچ تسک، فاکتور، قیمت یا مجوزی با تغییر حالت ایجاد، تغییر یا حذف نمی‌شود. این ماژول جای کنترل دسترسی میزبان، API یا شرط‌های `canManage`/`canEdit` نیست.

ترجیح کاربر در `localStorage` با پیشوند `madar:interface-mode:v1:` و شناسه حساب حاصل از `plannerIdentity(lanStatus)` ذخیره می‌شود. کلید client شامل URL/گواهی/نام کاربر همان logic قبلی است؛ اطلاعات ناقص remote کلید نمی‌گیرد. Solo بدون نام، `local` همان میزبان است؛ کاربرهای نام‌دار از هم جدا هستند. رکورد معتبر دقیقاً `{ "version": 1, "mode": "basic|operations|finance" }` است. مقدار نامعتبر، نسخه ناشناس، خطای ذخیره‌سازی یا نبود حساب، به Basic برمی‌گردد. تغییر حالت قابل ذخیره‌نشدن می‌تواند در حافظه جلسه اعمال شود و `persisted=false` به رابط برگردد؛ این به معنی موفقیت ذخیره دائمی نیست.

## API مصرفی Prime

```jsx
import {InterfaceModeSelector, useInterfaceModePreference} from './interface_mode.jsx';
import {isInterfaceFeatureVisible} from './interface_mode.js';

// داخل App، نزدیک سایر hookها، مستقل از mode='board' فعلی:
const {mode:interfaceMode, setMode:setInterfaceMode,
       persisted:modePersisted, accountReady:modeAccountReady} =
  useInterfaceModePreference(lanStatus);

// پس از محاسبه canManage و canEdit فعلی:
const show = feature => isInterfaceFeatureVisible(interfaceMode, feature, {canManage,canEdit});

// در بخش همیشه دردسترس sidebar، یا کنار نام پروفایل:
<InterfaceModeSelector mode={interfaceMode} onChange={setInterfaceMode}
                       disabled={!modeAccountReady} compact />
{!modePersisted && <span role="status">حالت در این دستگاه ذخیره نشد.</span>}
```

فقط نمایش کنترل‌ها و همچنین mounted modalهای مربوطه باید با `show(feature)` شرطی شود. جدول زیر کلیدهای مهم و جایگاه فعلی آنها را نشان می‌دهد:

| رابط فعلی در App.jsx | کلید | حداقل سطح و شرط |
|---|---|---|
| برد، فهرست، جست‌وجو، کارت، کارهای مهم، زباله‌دان | `boardView`, `listView`, `search`, `cards`, `quickFilters`, `taskTrash` | Basic |
| ساخت کار / پروژه / برد | `createTask`, `createProject`, `createBoard` | Basic با `canEdit`/`canManage` |
| پنل فضاهای کاری | `workspaceManagement` | Operations؛ ویرایش همچنان `canManage` |
| گزارش، برنامه شخصی، تاریخچه، داشبورد زمان | `reporting`, `planner`, `activity`, `timeDashboard` | Operations |
| زمان‌بندی نمای برد و فیلتر کامل | `timelineView`, `advancedFilters` | Operations |
| مدیریت قوانین / ورود Trello / تبادل تقویم / کلید امن | `automationRules`, `trelloImport`, `calendarInterop`, `secureApiKeys` | Operations + `canManage` |
| دکمه مالی و قراردادها/فاکتورها | `financeHub`, `projectFinance` | Finance + `canManage` |
| نمایش سود و هزینه کارت، هزینه چک‌لیست، قیمت پروژه | `profitPeek`, `taskCostControls`, `checklistCostControls`, `projectPricing` | Finance + `canManage` |
| بخش آینده عامل AI | `aiAgent` | Finance + `canManage` + `aiAvailable === true` |
| تنظیمات، پشتیبان، وضعیت شبکه، اعلان، پروفایل | `settings`, `backupRestore`, `networkStatus`, `notifications`, `profile` | همه حالت‌ها |

**نکات ضروری یکپارچه‌سازی:**

1. `App.jsx` یک `mode` برای برد/فهرست/زمان دارد. نام متغیر حالت جدید باید `interfaceMode` باشد تا با آن تداخل نکند. در بازگشت به Basic اگر نمای `time` فعال بود، `setMode('board')` ضروری است؛ صرف مخفی‌کردن تب زمان‌بندی کافی نیست.
2. علاوه بر دکمه‌های نوار کناری، شرط `show()` به render بخش‌های داخلی و modals مرتبط (`reportingOpen`, `rulesOpen`, `financeOpen`, `financeHubOpen`, `profitVisible` و سایر overlayها) هم اعمال شود. هنگام کاهش سطح، modal فعال بسته شود؛ در بازگشت به سطح بالاتر نباید پنل قبلی ناگهان مجدد باز شود.
3. **مسیر مالی مشاهده‌شده:** `TaskEditor` ورودی `showCosts={show('taskCostControls')}` گرفته و مقدار `priceEnabled` را با `canManage && showCosts` می‌سازد؛ `TaskCard` نیز `showCosts={show('profitPeek')}` می‌گیرد و نمایش `card-cost` شرط `canManage` دارد. هزینه مراحل چک‌لیست از `priceEnabled` تبعیت می‌کند. `projectSettings` با `canManage && show('projectAdministration')` mount می‌شود و فیلدهای قیمت شرط `show('projectPricing')` دارند. پنل‌های `ProfitPeek`, `FinancePanel`, `FinanceOverview` به‌ترتیب با `show('profitPeek')`, `show('projectFinance')`, `show('financeHub')` شرطی شده‌اند. این فقط شاهد کد UI است؛ احراز مجوز و redaction سمت API/host جداگانه باید آزموده شود.
4. تغییر حالت تنها UI را مخفی می‌کند، حق ویرایش/خواندن داده را تعیین نمی‌کند؛ کنترل API و redaction خروجی‌های LAN باید مستقل حفظ و آزمون شوند. در مسیرهایی که هنوز host مجوز مالی ندارد، داده مالی اصلاً به کاربر غیرمجاز ارسال نشود.
5. هیچ تغییر به `data`, `setData`, `change` یا `api.saveState` برای نگهداری mode لازم نیست؛ ترجیح محیطی مستقل است. Backup عمومی داده برنامه شامل این ترجیح محلی نیست.

## شواهد پذیرش و محدودیت

`node --test tests/interface_mode.test.cjs tests/interface_mode_ui_contract.test.cjs tests/planner_identity.test.cjs` در ۲۱ اکتبر ۲۰۲۶ روی کد مشترک همان لحظه: **۲۲ PASS، ۰ FAIL، ۰ SKIP**. موارد شامل اعتبارسنجی سختگیرانه، جداسازی حساب/میزبان، خطای storage، SSR انتخاب‌گر و تحلیل ایستای JSX با `@babel/parser` برای نگهداشت شرط‌های دسترسی و نمایش در ناوبری، صفحه و پنل‌های mountشده است. آزمون قرارداد به وضعیت فعلی `App.jsx` حساس است و هنگام حذف یا تغییر این شرط‌ها باید شکست بخورد. این‌ها شواهد unit/SSR/static AST هستند؛ آزمون عملی EXE، تغییر نقش در زمان بازبودن پنل، تعویض حساب در مرورگر، واقعی‌بودن ACL شبکه/host و معیار پذیرش تجاری M-04 یعنی **۵ سناریوی رایج با ۵ کاربر و مقایسه زمان قبل/بعد** هنوز تأیید نشده‌اند.
