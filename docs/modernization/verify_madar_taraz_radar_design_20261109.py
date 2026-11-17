"""Read-only content and sidecar checks for design notes. Creates a QA report only on PASS.

Does not connect to, modify, or test the actual Madar/Taraz applications.
"""

from pathlib import Path
import hashlib
import json
import os
import re
import sqlite3


ROOT = Path(__file__).resolve().parent
NOTE = ROOT / "MADAR_TARAZ_RADAR_IDEATION_ATOMIC_NOTE_20261107_V1_28.md"
OLD = ROOT / "MADAR_TARAZ_RADAR_IDEATION_ATOMIC_NOTE_20261107_V1_27.md"
DESIGN = ROOT / "MADAR_TARAZ_RADAR_INTEGRATED_DESIGN_AND_ACCEPTANCE_20261109.md"
REPORT = ROOT / "MADAR_TARAZ_RADAR_DESIGN_VALIDATION_20261109.md"

EXPECTED_NEW = "7b92ca42fce0e12444ccb4b11d9a2107718bcaf1e2c985633b83b916425122d7"
EXPECTED_OLD = "815a6a06dba1527ce2ecaa9ad9187b4dba31636dcd7b2a030e7ca3b4f549b691"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(condition, description):
    if not condition:
        raise AssertionError(description)


def main():
    check(digest(NOTE) == EXPECTED_NEW, "note v1.28 SHA")
    check(digest(OLD) == EXPECTED_OLD, "historical note v1.27 SHA")
    check(DESIGN.is_file(), "integrated design file")
    nt = NOTE.read_text(encoding="utf-8")
    dt = DESIGN.read_text(encoding="utf-8")
    check("## ??. " not in nt, "corrupt 6.24 section marker remains")
    check("\ufffd" not in nt and "\ufffd" not in dt, "Unicode replacement character")
    check("## ۴۳." in nt and "## ۴۹." in nt, "repaired and batch headings")
    check(len(dt) > 15000 and dt.startswith("# سند یکپارچه طراحی"), "design length/title")

    decisions = {
        2: "B", 3: "B", 4: "B", 5: "A", 6: "B", 7: "C", 8: "A",
        9: "B", 10: "C", 11: "B", 12: "B", 13: "A", 14: "A",
        15: "B", 16: "B", 17: "B", 18: "A", 19: "B", 20: "B",
        21: "B", 22: "B", 23: "B", 24: "B", 25: "B", 26: "B",
        27: "B", 28: "B", 29: "B",
    }
    found = [
        (int(number), choice)
        for number, choice in re.findall(
            r"^\| 6\.(\d+) \| ([ABC]) \|", dt, flags=re.MULTILINE
        )
    ]
    check(len(found) == 28 and dict(found) == decisions, "matrix decision choices")
    check(len({number for number, choice in found}) == 28, "no duplicated decisions")
    for number in range(2, 30):
        check(re.search(r"Refine 6\." + str(number) + r"(?:\D|$)", nt) is not None,
              f"note lacks Refine 6.{number}")
    for number in range(25, 30):
        check(re.search(r"^## [^\n]+Refine 6\." + str(number) + r"\b", nt,
                        flags=re.MULTILINE) is not None,
              f"note lacks decision section 6.{number}")

    ac = [int(n) for n in re.findall(r"^\| \*\*AC-(\d\d)\*\* \|", dt,
                                      flags=re.MULTILINE)]
    gates = [int(n) for n in re.findall(r"^\| \*\*G-(\d\d)\*\* \|", dt,
                                         flags=re.MULTILINE)]
    check(ac == list(range(1, 33)), "AC-01..AC-32 coverage/order")
    check(gates == list(range(1, 9)), "G-01..G-08 coverage/order")
    for label in ("[مصوب]", "[پیشنهاد فنی]", "[باز]", "کنترل نسخه",
                  "شناسه اختصاصی", "انجام‌نشده/اثبات‌نشده"):
        check(label in dt, "design missing label: " + label.encode("unicode_escape").decode("ascii"))

    paths = [
        (Path(os.environ["APPDATA"]) / "MadarDesk" / "atomic-notes.sqlite3", "madar"),
        (Path(os.environ["APPDATA"]) / "Taraz" / "atomic-notes.sqlite3", "taraz"),
        (
            Path(r"D:\CoS-Test\youtube-creator-intelligence-wt\creator-intelligence\local-data\atomic-notes.sqlite3"),
            "jaryan",
        ),
    ]
    baseline = None
    checks = []
    for db_path, product in paths:
        db = sqlite3.connect("file:" + db_path.as_posix() + "?mode=ro", uri=True)
        try:
            integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
            rows = db.execute(
                "SELECT note_version, content_sha256 FROM atomic_notes ORDER BY note_version"
            ).fetchall()
            current = db.execute(
                "SELECT note_id, product_key, content_markdown, content_sha256 "
                "FROM atomic_notes WHERE note_version='1.28'"
            ).fetchone()
            check(integrity == "ok", f"SQLite integrity: {product}")
            check(len(rows) == 29 and len({v for v, h in rows}) == 29,
                  f"version count: {product}")
            check({v for v, h in rows} == {"1." + str(i) for i in range(29)},
                  f"historical versions: {product}")
            check(next(h for v, h in rows if v == "1.27") == EXPECTED_OLD,
                  f"historical v1.27: {product}")
            check(next(h for v, h in rows if v == "1.28") == EXPECTED_NEW,
                  f"new v1.28: {product}")
            check(current is not None, f"missing v1.28 row: {product}")
            check(current[0] == "IDEATION-MADAR-TARAZ-RADAR-20261107-V1.28"
                  and current[1] == product and current[3] == EXPECTED_NEW,
                  f"v1.28 metadata: {product}")
            check(hashlib.sha256(current[2].encode("utf-8")).hexdigest() == EXPECTED_NEW,
                  f"v1.28 content SHA: {product}")
            if baseline is None:
                baseline = rows
            else:
                check(baseline == rows, f"version/hash cross-sidecar mismatch: {product}")
            checks.append({"product": product, "integrity": integrity, "versions": len(rows)})
        finally:
            db.close()

    design_sha = digest(DESIGN)
    report = f"""# گزارش راستی‌آزمایی بسته طراحی مدار، تراز و رادار

> تاریخ: ۲۰۲۶-۱۱-۰۹  
> دامنه: نوت اتمی، سند یکپارچه طراحی و سه پایگاهچه جانبی. **نه نرم‌افزار عملیاتی**.

## آزمون‌هایی که واقعاً انجام شدند

| کنترل | نتیجه |
|---|---|
| فایل نسخه ۱.۲۸ و SHA-256 | PASS |
| حفظ هش فایل تاریخی نسخه ۱.۲۷ | PASS |
| ثبت ۲۸ تصمیم Refine 6.2 تا 6.29 با گزینه‌های A/B/C صحیح | PASS |
| وجود بخش‌های Refine 6.25 تا 6.29 | PASS |
| اصلاح آسیب‌دیدگی کدگذاری متن 6.24 در نسخه جدید | PASS |
| وجود ۳۲ سناریوی AC-01 تا AC-32 و ترتیب صحیح | PASS |
| وجود ۸ گیت G-01 تا G-08 و ترتیب صحیح | PASS |
| تفکیک مصوب، پیشنهاد فنی و مسائل باز | PASS |
| SQLite integrity_check در مدار، تراز و جریان | OK |
| شمار نسخه‌های هر سه sidecar | ۲۹ |
| تطابق هش کامل رکورد ۱.۲۸ در هر سه پایگاهچه | PASS |
| یکسان بودن زوج‌های نسخه/هش در سه پایگاهچه | PASS |

## مشخصات فایل‌های بررسی‌شده

- نوت جدید ۱.۲۸: SHA-256 = {EXPECTED_NEW}
- نوت تاریخی ۱.۲۷ (دست‌نخورده): SHA-256 = {EXPECTED_OLD}
- سند یکپارچه: SHA-256 = {design_sha}

## محدودیت‌های صریح

- این کنترل‌ها **صحت ساختاری ثبت تصمیم‌ها و انطباق نسخه‌های طراحی** را بررسی می‌کنند.
- هیچ API، رابط کاربری عملیاتی، داده حسابداری واقعی، شبکه، کد برنامه، نصب، استقرار، انتشار، گیت مالی یا تست امنیت عملیاتی بررسی نشده است.
- متن 6.24 در نسخه تاریخی ۱.۲۷ به علامت سؤال تبدیل شده بود؛ بر اساس متن مستقیم انتخاب کاربر در نسخه جدید بازسازی شد، نه اینکه از فایل خراب به‌صورت واژه‌به‌واژه استخراج شده باشد.
- سناریوهای AC و G صرفاً **معیار پیشنهادی برای آزمون آینده** هستند و هنوز اجرا نشده‌اند.
- وجود نوت طراحی در sidecar جریان، اتصال اجرایی جریان به مدار/تراز را اثبات نمی‌کند.
"""
    if REPORT.exists():
        check(REPORT.read_text(encoding="utf-8") == report,
              "existing report differs; will not overwrite")
    else:
        with REPORT.open("x", encoding="utf-8", newline="\n") as out:
            out.write(report)
    check(digest(REPORT) == hashlib.sha256(report.encode("utf-8")).hexdigest(),
          "QA report hash")
    print(json.dumps({
        "result": "PASS",
        "note": {"path": str(NOTE), "sha256": EXPECTED_NEW, "bytes": NOTE.stat().st_size},
        "design": {"path": str(DESIGN), "sha256": design_sha,
                   "bytes": DESIGN.stat().st_size, "lines": len(dt.splitlines()),
                   "refine_decisions": len(found), "acceptance_scenarios": len(ac),
                   "cross_cutting_gates": len(gates)},
        "validation": {"path": str(REPORT), "sha256": digest(REPORT)},
        "sidecars": checks,
    }, ensure_ascii=True))


if __name__ == "__main__":
    main()
