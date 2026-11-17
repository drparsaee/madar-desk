# راهنمای زمینه‌ای مدار ۱.۰.۲۶ | قرارداد ادغام

**وضعیت:** ماژول مستقل در سورس است؛ هنوز به `App.jsx` متصل نشده و نمایش در نسخه نصب‌شده تأیید نشده است.

## فایل‌های ایجادشده

- `src/mtr_context_help_data.js`: راهنمای کوتاه فارسی برای **۴۱ موضوع مشاهده‌شده** در `App.jsx`، هر موضوع ۱ تا ۳ گام، دسته‌ها، جست‌وجو، نام‌های جایگزین.
- `src/mtr_context_help.jsx`: named export `MadarContextHelp` با دکمه کوچک «؟» و پنل بسته به‌صورت پیش‌فرض؛ نام‌گذاری دسترس‌پذیر، فوکوس روی جست‌وجو هنگام باز شدن، بستن با Escape یا ×، بازگشت فوکوس به دکمه.
- `src/mtr_context_help.css`: RTL و توکن‌های مشترک روشن/تاریک، عرض محدود و نمایش مناسب موبایل.
- `tests/mtr_context_help.test.cjs`: تست داده‌ها، تطابق شناسه‌ها با خود `App.jsx`، جست‌وجو، محدودیت موضوعات مجاز، SSR واقعی React و عناصر دسترس‌پذیری.

## اتصال برای ایجنت مالک `App.jsx`

ماژول نباید برنامه را پیمایش کند، مجوز صادر کند یا داده‌ای را تغییر دهد. ایجنت ادغام باید context واقعی صفحه را از state موجود `App.jsx` تعیین کند و فقط در جایگاه بصری مناسب آن را mount کند:

```jsx
import {MadarContextHelp} from './mtr_context_help.jsx';

// نمونهٔ ترتیب، برای تطبیق با state واقعی App:
const helpSection =
  settingsOpen ? 'settings' :
  lanOpen ? 'lan' :
  notificationsOpen ? 'notifications' :
  rulesOpen ? 'automation' :
  plannerOpen ? 'planner' :
  reportingOpen ? 'reporting' :
  cloudOpen ? 'backup' :
  webSyncOpen ? 'web-sync' :
  !!activeTask ? 'cards' :
  mode; // board, list, table, time, gantt

<MadarContextHelp
  currentSection={helpSection}
  availableSections={visibleHelpIds}
/>
```

`availableSections` اختیاری است. **برای جلوگیری از نمایش راهنمای قابلیت‌های پنهان‌شده به‌خاطر ACL یا پلتفرم**، ایجنت ادغام فهرست شناسه‌های قابل‌مشاهده را از همان `show('...')`، `canManage`، `isWebApp` و وضعیت واقعی دریافت کند. دادن آرایه خالی، هیچ موضوعی را در فهرست نشان نمی‌دهد. با حذف این پراپرتی، همه ۴۱ موضوع برای مرور عمومی نمایش داده می‌شوند؛ این به معنی فعال بودن قابلیت نیست و متن هر راهنما شرایط را بیان می‌کند.

شناسه‌های کلیدی: `overview`, `board`, `list`, `table`, `time`, `gantt`, `cards`, `card-checklist`, `card-files`, `card-reports`, `projects`, `project-settings`, `workspace`, `search`, `filters`, `labels`, `planner`, `reporting`, `activity`, `automation`, `automation-buttons`, `notifications`, `project-chat`, `lan`, `lan-users`, `sync`, `web-sync`, `taraz-exchange`, `backup`, `settings`, `profile`, `theme`, `archive`, `trash`, `import`, `export`, `calendar`, `api-keys`, `updates`.

## مرزهای ادعا

«ارسال به تراز» در راهنما **فقط پیشنهاد دستی کارت** است؛ مشاهدهٔ صندوق یا فایل‌های محلی اثبات رسید رسمی یا ثبت مالی نیست. ارتباط LAN، همگام‌سازی وب، نقش‌ها و مجوزها و تکمیل بازیابی به شرایط اجرای واقعی وابسته‌اند. هیچ قابلیت موجودی توسط راهنما فعال نمی‌شود.

آزمون اجراشده:

```
node --test tests/mtr_context_help.test.cjs
```

نتیجهٔ آزمون مستقل سورس: **۹ PASS، ۰ FAIL**. پوشش این مرحله شامل اجرای داخل `App.jsx`، بازکردن واقعی در EXE، تست دستی صفحه‌کلید در WebView2 یا بررسی بصری روی میزبان ویندوز نیست؛ این موارد به ایجنت ادغام تعلق دارند.
