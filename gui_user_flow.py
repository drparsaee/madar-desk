"""QA-only deterministic desktop interactions in an isolated Madar EXE.

Never import/run for a normal user's desktop. Caller requires BOTH
MADAR_RELEASE_QA=1 and MADAR_QA_INTERACTION=1 in an isolated subprocess.
The fixture title is deliberately unique and never applied to a real profile.
"""
from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import time


TASK_TITLE = 'آزمون رابط تست کاربر مدار QA'


def _require_isolated_qa(bridge):
    """Reject accidental execution in a user's running/connected desktop."""
    env = os.environ
    if any(env.get(flag) != '1' for flag in ('MADAR_RELEASE_QA', 'MADAR_QA_INTERACTION')):
        raise RuntimeError('interactive GUI QA must be explicitly enabled')
    if env.get('MADAR_QA_VIEW') != 'sample-project':
        raise RuntimeError('interactive GUI QA requires synthetic sample-project')
    report = env.get('MADAR_QA_REPORT')
    if not report:
        raise RuntimeError('isolated QA report path missing')
    root = Path(report).resolve().parent
    if not root.name.startswith('.qa-v1-gui-isolated-'):
        raise RuntimeError('QA report must be inside runner-owned scratch')
    for key, parts in {
        'APPDATA': ('AppData', 'Roaming'),
        'LOCALAPPDATA': ('AppData', 'Local'),
        'WEBVIEW2_USER_DATA_FOLDER': ('WebView2',),
    }.items():
        if not env.get(key) or Path(env[key]).resolve() != root.joinpath(*parts):
            raise RuntimeError(f'{key} is not inside the runner-owned scratch')
    if not isinstance(getattr(bridge, 'connection', None), dict) or (
            bridge.connection.get('mode') != 'solo'):
        raise RuntimeError('interactive QA requires a standalone synthetic host')
    host_file = getattr(bridge, 'path', None)
    if host_file is None or not Path(host_file).resolve().is_relative_to(
            Path(env['APPDATA']).resolve()):
        raise RuntimeError('host task store must belong to isolated QA APPDATA')


def run_ui_flow(window, bridge):
    _require_isolated_qa(bridge)
    results = {}

    def eval_js(code):
        return window.evaluate_js('(function(){' + code + '})()')

    def check(name, code, *, wait=0.22):
        try:
            value = eval_js(code)
            results[name] = {'pass': value is True, 'observed': value}
        except Exception as exc:
            results[name] = {'pass': False, 'error': type(exc).__name__ + ': ' + str(exc)[:180]}
        if wait:
            time.sleep(wait)

    check('initial_rtl_and_board', """
      return !!document.querySelector('.app-shell .sidebar-nav') &&
        (document.documentElement.dir==='rtl' ||
        document.querySelector('.app-shell')?.getAttribute('dir')==='rtl' ||
        getComputedStyle(document.body).direction==='rtl');
    """)
    # Accounting navigation is an independent, admin-gated route, NOT a modal.
    # This test must not submit any accounting forms or click finance actions.
    check('accounting_nav_visible', """
      return [...document.querySelectorAll('.sidebar-nav button')].some(
        b=>b.textContent.includes('ورود به محیط حسابداری'));
    """, wait=0.25)
    # Capture an authoritative host snapshot, not merely DOM text.
    try:
        finance_before = deepcopy(bridge._load_finance())
        results['finance_snapshot_captured'] = {'pass': True, 'observed': True}
    except Exception as exc:
        finance_before = None
        results['finance_snapshot_captured'] = {
            'pass': False, 'error': type(exc).__name__ + ': ' + str(exc)[:180]}

    check('accounting_workspace_opens', """
      const btn=[...document.querySelectorAll('.sidebar-nav button')].find(
        b=>b.textContent.includes('ورود به محیط حسابداری'));
      if(!btn||btn.disabled)return false;btn.click();return true;
    """, wait=0.65)
    check('accounting_workspace_fullscreen', """
      const root=document.querySelector('.accw-root[dir=rtl]');
      return !!root && !!root.querySelector('.accw-side nav') &&
        !!root.querySelector('.accw-main') &&
        !document.querySelector('.app-shell') &&
        !root.closest('[role=dialog]') &&
        !document.querySelector('.accounting-panel[role=dialog]');
    """)
    check('accounting_overview_selected', """
      const root=document.querySelector('.accw-root');
      const current=root?.querySelector('.accw-side nav button[aria-current=page]');
      return !!current && current.textContent.includes('داشبورد') &&
        root.querySelector('.accw-top h1')?.textContent.includes('داشبورد');
    """)
    check('accounting_navigation_payments', """
      const nav=document.querySelector('.accw-root .accw-side nav');
      const button=[...nav?.querySelectorAll('button')||[]].find(
        b=>b.textContent.includes('دریافت و پرداخت'));
      if(!button||button.disabled)return false;button.click();return true;
    """, wait=0.3)
    check('accounting_payments_visible', """
      const root=document.querySelector('.accw-root');
      return !!root?.querySelector('.accw-payment-card') &&
        root.querySelector('.accw-side nav button[aria-current=page]')
            ?.textContent.includes('دریافت و پرداخت');
    """)
    check('accounting_navigation_reports', """
      const nav=document.querySelector('.accw-root .accw-side nav');
      const button=[...nav?.querySelectorAll('button')||[]].find(
        b=>b.textContent.includes('گزارش‌ها'));
      if(!button||button.disabled)return false;button.click();return true;
    """, wait=0.3)
    check('accounting_reports_visible', """
      const root=document.querySelector('.accw-root');
      return !!root?.querySelector('.accw-pane') &&
        root.querySelector('.accw-side nav button[aria-current=page]')
            ?.textContent.includes('گزارش‌ها') &&
        root.querySelector('.accw-top h1')?.textContent.includes('گزارش‌ها');
    """)
    check('accounting_currency_default_toman', """
      const root=document.querySelector('.accw-root');
      const choice=root?.querySelector('select[aria-label="واحد پولی حسابداری"]');
      const values=[...choice?.options||[]].map(x=>x.value);
      return !!choice && choice.value==='TOMAN' &&
        values.includes('TOMAN')&&values.includes('RIAL') &&
        root.querySelector('.accw-money-disclosure[role=note]')?.textContent.includes('تومان');
    """)
    check('accounting_currency_choose_rial', """
      const choice=document.querySelector('.accw-root select[aria-label="واحد پولی حسابداری"]');
      if(!choice||choice.disabled)return false;
      const setter=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value')?.set;
      if(!setter)return false;
      setter.call(choice,'RIAL');choice.dispatchEvent(new Event('change',{bubbles:true}));
      return true;
    """, wait=0.32)
    check('accounting_currency_rial_display', """
      const root=document.querySelector('.accw-root');
      return root?.querySelector('select[aria-label="واحد پولی حسابداری"]')?.value==='RIAL' &&
        root.querySelector('.accw-sidefoot')?.textContent.includes('ریال') &&
        root.querySelector('.accw-money-disclosure[role=note]')?.textContent.includes('ریال') &&
        root.querySelector('.accw-money-disclosure')?.textContent.includes('تومان صحیح');
    """)
    check('accounting_currency_choose_toman', """
      const choice=document.querySelector('.accw-root select[aria-label="واحد پولی حسابداری"]');
      if(!choice||choice.disabled)return false;
      const setter=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value')?.set;
      if(!setter)return false;
      setter.call(choice,'TOMAN');choice.dispatchEvent(new Event('change',{bubbles:true}));
      return true;
    """, wait=0.32)
    check('accounting_currency_toman_restored', """
      const root=document.querySelector('.accw-root');
      return root?.querySelector('select[aria-label="واحد پولی حسابداری"]')?.value==='TOMAN' &&
        root.querySelector('.accw-sidefoot')?.textContent.includes('تومان');
    """)
    check('close_accounting_workspace', """
      const btn=document.querySelector('.accw-root .accw-exit');
      if(!btn||!btn.textContent.includes('بازگشت به تسک‌منیجر'))return false;
      btn.click();return true;
    """, wait=0.55)
    check('accounting_workspace_closed', """
      return !document.querySelector('.accw-root') &&
        !!document.querySelector('.app-shell .sidebar-nav') &&
        !!document.querySelector('.kanban');
    """, wait=0.35)
    try:
        if finance_before is None:
            raise RuntimeError('pre-navigation finance snapshot unavailable')
        unchanged = bridge._load_finance() == finance_before
        results['finance_unchanged'] = {'pass': unchanged, 'observed': unchanged}
    except Exception as exc:
        results['finance_unchanged'] = {
            'pass': False, 'error': type(exc).__name__ + ': ' + str(exc)[:180]}

    # A fresh task is safe only after the finance workspace really closed,
    # the board returned, and its authoritative finance snapshot is unchanged.
    # On any failed prerequisite, stop clicking. The smoke validator will
    # report missing task checks as FAIL rather than forging a green result.
    prerequisite_names = (
        'initial_rtl_and_board', 'accounting_nav_visible',
        'finance_snapshot_captured', 'accounting_workspace_opens',
        'accounting_workspace_fullscreen', 'accounting_overview_selected',
        'accounting_navigation_payments', 'accounting_payments_visible',
        'accounting_navigation_reports', 'accounting_reports_visible',
        'accounting_currency_default_toman',
        'accounting_currency_choose_rial', 'accounting_currency_rial_display',
        'accounting_currency_choose_toman', 'accounting_currency_toman_restored',
        'close_accounting_workspace', 'accounting_workspace_closed',
        'finance_unchanged',
    )
    if any(results[name]['pass'] is not True for name in prerequisite_names):
        return results

    check('create_task_opens', """
      const btn=document.querySelector('.create-primary');
      if(!btn || btn.disabled)return false;btn.click();return true;
    """,wait=0.35)
    check('create_task_dialog', "return !!document.querySelector('.dialog[role=dialog] form.task-create');")
    # React tracks native input setters: using the prototype setter prevents
    # bypassing its controlled value mechanism while dispatching input.
    check('fill_task_title', """
      const i=document.querySelector('.task-create input[required]');
      if(!i)return false;
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(i,'آزمون رابط تست کاربر مدار QA');
      i.dispatchEvent(new Event('input',{bubbles:true}));return true;
    """)
    check('create_task_submit', """
      const submit=document.querySelector('.task-create button[type=submit]');
      if(!submit||submit.disabled)return false;submit.click();return true;
    """,wait=0.75)
    check('new_task_drawer', """
      const drawer=document.querySelector('.drawer[role=dialog]');
      return !!drawer && drawer.querySelector('.task-edit-title')?.value==='آزمون رابط تست کاربر مدار QA';
    """,wait=0.75)
    try:
        # The bridge reads the actual disposable host state; DOM appearance
        # alone is insufficient evidence that an edit survived persistence.
        stored = bridge.getState()
        matched = [task for task in stored.get('tasks', []) if task.get('title') == TASK_TITLE]
        results['task_saved_to_host'] = {'pass': len(matched) == 1,
                                         'observed': len(matched)}
    except Exception as exc:
        results['task_saved_to_host'] = {'pass': False,
                                         'error': type(exc).__name__ + ': ' + str(exc)[:180]}
    try:
        if finance_before is None:
            raise RuntimeError('pre-navigation finance snapshot unavailable')
        unchanged = bridge._load_finance() == finance_before
        results['finance_unchanged_after_task'] = {'pass': unchanged, 'observed': unchanged}
    except Exception as exc:
        results['finance_unchanged_after_task'] = {
            'pass': False, 'error': type(exc).__name__ + ': ' + str(exc)[:180]}
    return results
