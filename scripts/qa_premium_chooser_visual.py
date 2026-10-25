"""Window-screenshot and user-like synthetic selection, never real company hub."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from PIL import ImageGrab
import ctypes

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from standalone_accounting_company_registry import StandaloneCompanyRegistry
from standalone_accounting_premium_chooser import PremiumCompanyChooser


class Rect(ctypes.Structure):
    _fields_=[('left',ctypes.c_long),('top',ctypes.c_long),
              ('right',ctypes.c_long),('bottom',ctypes.c_long)]


def main():
    destination=ROOT/'.qa-premium-chooser-r12-preview.png'
    if destination.exists():
        raise RuntimeError('Refusing to replace an existing screenshot')
    with TemporaryDirectory(prefix='madar-r12-chooser-') as directory:
        registry=StandaloneCompanyRegistry(directory)
        registry.create_company('مجتمع آموزشی بین‌المللی نمونه')
        registry.create_company('شرکت توسعه بسته‌بندی آزمایشی')
        registry.create_company('آژانس طراحی و چاپ نمونه')
        chooser=PremiumCompanyChooser(registry)
        checks={}
        def test_ui():
            chooser.root.update_idletasks()
            checks['registry_three_companies']=len(chooser.visible)==3
            checks['has_enter_button']=chooser.enter_btn.winfo_exists()==1
            checks['selection_initial']=bool(chooser.selected)
            hwnd=ctypes.windll.user32.GetParent(chooser.root.winfo_id())
            rect=Rect()
            success=ctypes.windll.user32.GetWindowRect(hwnd,ctypes.byref(rect))
            if not success or rect.right<=rect.left or rect.bottom<=rect.top:
                checks['screenshot']=False
            else:
                ImageGrab.grab(bbox=(rect.left,rect.top,rect.right,rect.bottom),
                               all_screens=True).save(destination)
                checks['screenshot']=True
            chooser.query.set('بسته‌بندی')
            checks['search_filter']=len(chooser.visible)==1
            chooser._select(chooser.visible[0]['id'])
            checks['filtered_selection']=chooser.visible[0]['id']==chooser.selected
            chooser.query.set('')
            chooser._toggle_create(True)
            chooser.company_name.set('دفتر تازه آزمایشی')
            chooser._create()
            checks['created_by_ui']=len(registry.list_companies())==4
            checks['no_financial_ledger_created']=not list(Path(directory).rglob('standalone-accounting.sqlite3'))
            chooser._confirm()
        chooser.root.after(900,test_ui)
        selected=chooser.run()
        checks['selected_new_company']=selected is not None and selected['name']=='دفتر تازه آزمایشی'
        print(json.dumps({'checks':checks,'screenshot':str(destination)},ensure_ascii=False))
        return 0 if checks and all(checks.values()) else 1


if __name__=='__main__':raise SystemExit(main())
