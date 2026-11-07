"""Real Windows WebView2 P0 smoke in a disposable, synthetic AppData profile.

Run: py -3.12 -B scripts/qa_p0_v123_webview2.py
Never starts with the Windows user's AppData, does not install or publish.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / ".qa-p0-v123-webview2"
REPORT = QA / "native-ui-acceptance.json"
MARKER = QA / ".synthetic-owner.json"


def _check_isolation():
    marker = json.loads(MARKER.read_text(encoding="utf8"))
    if marker != {"owner": "madar-p0-v123-webview2", "synthetic": True}:
        raise PermissionError("Synthetic QA ownership is absent")
    expected = (QA / "AppData" / "Roaming").resolve()
    if Path(os.environ["APPDATA"]).resolve() != expected:
        raise PermissionError("APPDATA is not the owned synthetic QA profile")
    for key in ("LOCALAPPDATA", "WEBVIEW2_USER_DATA_FOLDER"):
        if not Path(os.environ[key]).resolve().is_relative_to(QA.resolve()):
            raise PermissionError(key + " escapes the owned synthetic profile")
    if any(directory.is_symlink() or
           (hasattr(directory, "is_junction") and directory.is_junction())
           for directory in (QA, *QA.parents)):
        raise PermissionError("QA path contains a link/junction")


def _child():
    _check_isolation()
    sys.path.insert(0, str(ROOT))
    import native_app

    bridge = native_app.Bridge()
    if bridge.connection.get("mode") != "solo":
        raise PermissionError("QA may not connect to the user's LAN host")
    bridge.saveState(native_app.initial_state())
    state = bridge.getState()
    if len(state["tasks"]) < 2 or not state["boards"]:
        raise RuntimeError("Synthetic sample project did not initialize")
    if not bridge.path.resolve().is_relative_to(Path(os.environ["APPDATA"]).resolve()):
        raise PermissionError("Task database path is not synthetic")

    orig_create = native_app.webview.create_window
    started = threading.Event()
    completed = threading.Event()
    result = {"schema": 1, "mode": "real-WebView2", "synthetic": True,
              "version": "1.0.23", "checks": {}, "metrics": {}}
    checks = result["checks"]
    metrics = result["metrics"]

    def create_window(*args, **kwargs):
        window = orig_create(*args, **kwargs)

        def drive():
            if started.is_set():
                return
            started.set()
            def evaluate(js):
                return window.evaluate_js("(()=>" + js + ")()")
            def wait(js, timeout=10):
                deadline = time.monotonic() + timeout
                last = None
                while time.monotonic() < deadline:
                    try:
                        last = evaluate(js)
                        if last:
                            return last
                    except Exception as exc:
                        last = type(exc).__name__
                    time.sleep(0.2)
                return last
            def check(label, js, timeout=0):
                try:
                    value = wait(js, timeout) if timeout else evaluate(js)
                    checks[label] = bool(value is True)
                    if not checks[label]:
                        metrics[label + "_actual"] = value
                except Exception as exc:
                    checks[label] = False
                    metrics[label + "_exception"] = type(exc).__name__ + ": " + str(exc)[:200]
            def click(selector):
                return evaluate("(()=>{const e=document.querySelector(" +
                                json.dumps(selector) + ");if(!e)return false;" +
                                "e.click();return true})()")
            try:
                check("actual_webview2_mount",
                      "!!document.querySelector('.app-shell')&&typeof window.madar==='object'",
                      18)
                check("rtl_layout", "getComputedStyle(document.body).direction==='rtl'")
                evaluate("(()=>{window.__madarP0Errors=[];"
                         "addEventListener('error',e=>window.__madarP0Errors.push(String(e.message)));"
                         "addEventListener('unhandledrejection',e=>window.__madarP0Errors.push(String(e.reason)));"
                         "return true})()")

                # Open a synthetic project and real task board, without posting data.
                check("select_synthetic_project",
                      "(()=>{const p=[...document.querySelectorAll('.projects-nav .project-entry button')]" +
                      ".find(x=>x.textContent.includes('پروژه نمونه'));if(!p)return false;p.click();return true})()", 5)
                check("board_has_synthetic_cards", "document.querySelectorAll('.task-card').length>0", 8)
                check("gantt_button_visible", """!!document.querySelector('button[aria-label="گانت"]')""", 4)
                if checks.get("gantt_button_visible"):
                    click('button[aria-label="گانت"]')
                    check("gantt_mount", "!!document.querySelector('.gantt-root')", 6)
                    check("gantt_scale_day_week_month",
                          """(()=>{const s=document.querySelector('select[aria-label="مقیاس گانت"]');""" +
                          "return !!s&&['day','week','month'].every(x=>[...s.options].some(o=>o.value===x))})()")
                    metrics["ganttRows"] = evaluate("document.querySelectorAll('.gantt-row').length")
                    metrics["ganttColumns"] = evaluate("document.querySelectorAll('.gantt-axis-cell').length")
                    # Return to board without mutating a task.
                    click('button[aria-label="برد کارها"]')
                    check("board_restored", "!!document.querySelector('.kanban')", 6)

                check("project_chat_action", "!![...document.querySelectorAll('button')]" +
                      ".find(x=>x.textContent.includes('گفت‌وگوی پروژه'))")
                if checks.get("project_chat_action"):
                    evaluate("(()=>{[...document.querySelectorAll('button')]" +
                             ".find(x=>x.textContent.includes('گفت‌وگوی پروژه')).click();return true})()")
                    check("project_chat_dialog",
                          """!!document.querySelector('[role="dialog"]')&&""" +
                          """document.querySelector('[role="dialog"]').textContent.includes('گفت‌وگو')""", 6)
                    evaluate("""(()=>{document.querySelector('[role="dialog"] button[aria-label="بستن"]')?.click();return true})()""")
                    time.sleep(0.35)

                check("open_real_task", "(()=>{const c=document.querySelector('.task-card');" +
                      "if(!c)return false;c.click();return true})()")
                check("card_drawer", "!!document.querySelector('.drawer')", 6)
                check("card_comment_control", "!!document.querySelector('.drawer')&&" +
                      "document.querySelector('.drawer').textContent.includes('گفتگو')", 4)
                if checks.get("card_drawer"):
                    evaluate("""(()=>{document.querySelector('.drawer button[aria-label="بستن"]')?.click();return true})()""")
                    time.sleep(0.3)

                check("settings_navigation", "(()=>{const b=[...document.querySelectorAll('.sidebar-settings')]" +
                      ".find(x=>x.textContent.trim()==='تنظیمات');if(!b)return false;b.click();return true})()")
                check("settings_real_dialog", "!!document.querySelector('.settings-modal')", 6)
                check("general_settings_rows", "document.querySelectorAll('.settings-modal .settings-general-row').length>=5")
                check("taraz_separate_settings", "!![...document.querySelectorAll('.settings-page-nav button')]" +
                      ".find(x=>x.textContent.includes('اتصال تراز'))")
                check("subscription_disabled", "(()=>{const b=[...document.querySelectorAll('.settings-page-nav button')]" +
                      ".find(x=>x.textContent.includes('خرید اشتراک'));if(!b)return false;b.click();" +
                      "return !!document.querySelector('.settings-modal .settings-subscription-state')&&" +
                      "!!document.querySelector('.settings-modal .settings-subscription-state + .settings-general-row button[disabled]')})()")
                evaluate("(()=>{[...document.querySelectorAll('.settings-page-nav button')]" +
                         ".find(x=>x.textContent.trim()==='عمومی')?.click();return true})()")
                metrics["themeBefore"] = evaluate("document.documentElement.dataset.theme||''")
                for label, word in (("light_theme", "روشن"), ("dark_theme", "تاریک")):
                    check(label, """(()=>{const b=[...document.querySelectorAll('[aria-label="حالت تم"] button')]""" +
                          ".find(x=>x.textContent.includes(" + json.dumps(word, ensure_ascii=False) +
                          "));if(!b||b.disabled)return false;b.click();return true})()")
                    time.sleep(0.35)
                    metrics[label + "Computed"] = evaluate(
                        "(()=>{const css=getComputedStyle(document.body);return " +
                        "{color:css.color,background:css.backgroundColor,theme:document.documentElement.dataset.theme}})()")
                check("dark_theme_readable", "(()=>{const d=getComputedStyle(document.body);" +
                      "return d.color!==d.backgroundColor&&!!document.querySelector('.settings-general-page')})()")
                # The UI's persisted theme is returned to its system setting.
                evaluate("""(()=>{[...document.querySelectorAll('[aria-label="حالت تم"] button')]""" +
                         ".find(x=>x.textContent.includes('سیستم'))?.click();return true})()")
                click('.settings-modal button[aria-label="بستن"]')

                check("label_manager_opens", "(()=>{const b=[...document.querySelectorAll('.sidebar-settings')]" +
                      ".find(x=>x.textContent.includes('مدیریت برچسب'));if(!b)return false;b.click();return true})()")
                check("label_manager_dialog",
                      """!!document.querySelector('[role="dialog"]')&&""" +
                      """document.querySelector('[role="dialog"]').textContent.includes('برچسب')""", 5)
                # Delete placement is separately protected by component tests.
                metrics["uncaughtErrors"] = evaluate("window.__madarP0Errors||[]")
                checks["no_uncaught_browser_errors"] = not metrics["uncaughtErrors"]
            except Exception as exc:
                metrics["harness_error"] = type(exc).__name__ + ": " + str(exc)[:250]
            finally:
                REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8")
                completed.set()
                try:
                    window.destroy()
                except Exception as exc:
                    metrics["close_error"] = type(exc).__name__

        window.events.loaded += lambda: threading.Thread(target=drive, daemon=True).start()
        return window

    native_app.webview.create_window = create_window
    native_app.main()
    if not completed.is_set():
        raise RuntimeError("WebView2 GUI QA completed without a report")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        _child()
        return
    if QA.exists():
        raise FileExistsError("Refusing to reuse or overwrite an existing QA profile: " + str(QA))
    for folder in (QA, *QA.parents):
        if folder.is_symlink() or (hasattr(folder, "is_junction") and folder.is_junction()):
            raise PermissionError("QA root cannot be nested in a link/junction")
    QA.mkdir(parents=True)
    MARKER.write_text(json.dumps({"owner": "madar-p0-v123-webview2", "synthetic": True}), encoding="utf8")
    env = os.environ.copy()
    env["APPDATA"] = str(QA / "AppData" / "Roaming")
    env["LOCALAPPDATA"] = str(QA / "AppData" / "Local")
    env["WEBVIEW2_USER_DATA_FOLDER"] = str(QA / "WebView2")
    env["PYTHONIOENCODING"] = "utf-8"
    for key in ("MADAR_QA_REPORT", "MADAR_QA_VIEW", "MADAR_RELEASE_QA",
                "MADAR_QA_INTERACTION", "MADAR_QA_MUTATE_ISOLATED"):
        env.pop(key, None)
    for key in ("APPDATA", "LOCALAPPDATA", "WEBVIEW2_USER_DATA_FOLDER"):
        Path(env[key]).mkdir(parents=True, exist_ok=True)
    try:
        run = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "--child"],
                             cwd=ROOT, env=env, capture_output=True, text=True, timeout=110)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Isolated WebView2 smoke exceeded the 110s bound") from exc
    if not REPORT.is_file():
        raise RuntimeError("Real GUI produced no acceptance report; exit=" + str(run.returncode)
                           + " stderr=" + run.stderr[-1500:])
    report = json.loads(REPORT.read_text(encoding="utf8"))
    failures = [name for name, ok in report["checks"].items() if ok is not True]
    print(json.dumps({"exit": run.returncode, "checks": report["checks"],
                      "failures": failures, "metrics": report["metrics"],
                      "report": str(REPORT)}, ensure_ascii=False, indent=2))
    if run.returncode or failures:
        raise RuntimeError("Isolated real-WebView2 acceptance failed; see report")


if __name__ == "__main__":
    main()
