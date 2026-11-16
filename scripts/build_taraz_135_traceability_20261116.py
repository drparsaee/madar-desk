"""Evidence-conservative traceability for all 135 ecosystem brainstorming ideas.

Source inventory, test existence and historical frozen acceptance are separate
facts. No field is allowed to imply production v1.0.6 acceptance.
The proposed C-ID mapping is analytical, NOT the user's approved mapping.
Only records explicitly in AUDITED may claim any implementation evidence.
"""
from __future__ import annotations

from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re

MADAR = Path(__file__).resolve().parents[1]
TARAZ = Path('D:/CoS-Test/000- Taraz/taraz-mtr-e2-isolated-20261109')
DOC = MADAR / 'docs' / 'modernization'
CATALOG = DOC / 'MADAR_TARAZ_RADAR_IDEAS_CATALOG_20261108.html'
NOTE_14 = DOC / 'MADAR_TARAZ_RADAR_IDEATION_ATOMIC_NOTE_20261107_V1_4.md'
NOTE_128 = DOC / 'MADAR_TARAZ_RADAR_IDEATION_ATOMIC_NOTE_20261107_V1_28.md'
OUTPUT = DOC / 'MADAR_TARAZ_RADAR_135_IDEA_TRACEABILITY_20261116.md'
CSV = DOC / 'MADAR_TARAZ_RADAR_135_IDEA_TRACEABILITY_20261116.csv'
PACKAGES = DOC / 'MADAR_TARAZ_RADAR_C01_C18_IMPLEMENTATION_AUDIT_20261116.md'

ALLOWED = ('VERIFIED_IMPLEMENTED','PARTIAL_IMPLEMENTATION','SOURCE_ONLY',
           'PLANNED','BLOCKED','NOT_VERIFIED')

# An ID in this table has been matched to a *narrower* real implementation.
# Nothing in the table represents completion of the complete brainstorming idea.
# Evidence paths use M: (Madar) or T: (Taraz), relative to their Git worktree.
# Tests not run in this review are marked NOT_RUN, even when they exist.
AUDITED = {
    'B01-01': ('SOURCE_ONLY','M:madar_ai_draft.py','M:tests/test_madar_ai_draft.py [NOT_RUN]','', 'AI task draft is not a proven full customer-message-to-order workflow'),
    'B01-02': ('SOURCE_ONLY','T:src/accounting_invoice_wizard.jsx','T:tests/taraz_clarify_invoice_flow_20261111.test.cjs [NOT_RUN]','', 'Invoice input modes do not prove Madar order-mode switching'),
    'B01-07': ('PARTIAL_IMPLEMENTATION','M:src/taskops.js;T:taraz_order_store.py','T:tests/test_taraz_order_store_20261111.py [NOT_RUN]','', 'Task/order components exist; complete multi-department split is unverified'),
    'B01-09': ('PARTIAL_IMPLEMENTATION','M:src/gantt_model.js','M:tests/gantt_model.test.cjs [PASS_20261116]','', 'Gantt shift impact preview exists; complete order-route simulation unverified'),
    'B02-02': ('SOURCE_ONLY','T:taraz_aaas_agent.py','T:tests/test_taraz_ai_chat_vertical_20261114.py [PRIOR_RUN]','', 'Taraz agent memory is not the full searchable Madar company knowledge base'),
    'B02-09': ('PARTIAL_IMPLEMENTATION','M:src/gantt_model.js','M:tests/gantt_model.test.cjs [PASS_20261116]','', 'Bounded date-shift preview only, not all proposed AI actions'),
    'B02-15': ('SOURCE_ONLY','T:taraz_aaas_agent.py','T:tests/test_taraz_ai_chat_vertical_20261114.py [PRIOR_RUN]','', 'Bounded review flow present; general delegated multi-agent authority unverified'),
    'B03-01': ('PARTIAL_IMPLEMENTATION','M:radar_crm_store.py','M:tests/test_radar_crm_store.py [PASS_20261116]','', 'Contacts, notes, followups; complete 360-degree financial/call history missing'),
    'B03-05': ('SOURCE_ONLY','M:radar_crm_store.py','M:tests/test_radar_host_adapter.py [PASS_20261116]','', 'Manual followup scheduling is not an intelligent next-best-action engine'),
    'B03-13': ('PARTIAL_IMPLEMENTATION','M:radar_crm_store.py','M:tests/test_radar_crm_store.py [PASS_20261116]','', 'Contact note and audit history only; complete collaboration history unverified'),
    'B05-01': ('PARTIAL_IMPLEMENTATION','M:mtr_e2_send_journal.py;M:mtr_deficiency_workflow.py','M:tests/test_mtr_deficiency_workflow.py [PASS_20261116]','', 'Manual financial request pieces; production cross-app queue not accepted'),
    'B05-02': ('SOURCE_ONLY','M:radar_party_match_preview.py','M:tests/test_radar_party_match_preview.py [NOT_RUN]','', 'Read-only party match proposal does not register official Taraz customer'),
    'B05-03': ('SOURCE_ONLY','T:taraz_madar_data_reader.py','T:tests/test_taraz_madar_data_reader_20261110.py [NOT_RUN]','', 'Read-only integration evidence, not bidirectional party synchronization'),
    'B05-05': ('PARTIAL_IMPLEMENTATION','M:src/order_finance_fields.jsx;T:taraz_order_store.py','M:tests/order_finance_ui.test.cjs [PASS_20261116]','', 'Some financial order fields supported; fully adaptive finance form unverified'),
    'B05-06': ('SOURCE_ONLY','M:mtr_deficiency_workflow.py','M:tests/test_mtr_deficiency_workflow.py [PASS_20261116]','', 'Deficiency workflow is not AI field completion'),
    'B05-07': ('PARTIAL_IMPLEMENTATION','M:mtr_deficiency_workflow.py','M:tests/test_mtr_deficiency_workflow.py [PASS_20261116]','', 'Safe human referral contract tested; installed cross-app orchestration not verified'),
    'B05-08': ('PARTIAL_IMPLEMENTATION','M:mtr_finance_workflow_contract.py','M:tests/test_mtr_finance_workflow_contract.py [PASS_20261116]','', 'Conflict decision contract only; integrated accounting reconciliation unverified'),
    'B05-09': ('SOURCE_ONLY','T:src/taraz_madar_dashboard.jsx','T:tests/taraz_v106_madar_project_contract_20261112.test.cjs [NOT_RUN]','', 'Taraz display does not establish Madar-side invoice preview'),
    'B05-10': ('SOURCE_ONLY','T:taraz_madar_order_sync.py','T:tests/test_taraz_madar_order_sync_20261112.py [NOT_RUN]','', 'Sync contract exists; real two-app installed lifecycle not verified'),
    'B05-11': ('PARTIAL_IMPLEMENTATION','T:taraz_madar_order_link.py','T:tests/test_taraz_madar_order_link_20261112.py [NOT_RUN]','', 'Order/project link store only; official joint order-and-journal identifier unverified'),
    'B05-12': ('SOURCE_ONLY','M:mtr_finance_workflow_contract.py','M:tests/test_mtr_finance_workflow_contract.py [PASS_20261116]','', 'Amendment/audit contract does not prove comprehensive financial change history'),
    'B05-14': ('SOURCE_ONLY','T:taraz_madar_order_sync.py','T:tests/test_taraz_madar_order_sync_20261112.py [NOT_RUN]','', 'Reconciliation controls do not prove full offline bidirectional conflict handling'),
    'B05-15': ('SOURCE_ONLY','T:src/taraz_madar_dashboard.jsx','T:tests/test_taraz_madar_data_reader_20261110.py [NOT_RUN]','', 'Partial dashboard code; no installed operational KPI validation'),
    'B06-01': ('SOURCE_ONLY','T:src/taraz_order_workspace.jsx','T:tests/taraz_order_workspace.test.cjs [NOT_RUN]','', 'Order documents visible in one module, not complete cross-product document center'),
    'B06-02': ('PARTIAL_IMPLEMENTATION','T:src/standalone_accounting_workspace.jsx','T:scripts/qa_taraz_fresh_windows_frozen_20261115.py [PRIOR_FROZEN_PASS]','T:build-5eaec2d34649 PDF Preview PASS [20261115]','Standalone PDF preview works; Madar-side live invoice preview not verified'),
    'B07-01': ('BLOCKED','T:scripts/qa_taraz_fresh_reset_rollback_20261115.py','T:docs/TARAZ_FRESH_START_EXECUTION_EVIDENCE_20261115_FA.md [PRIOR_CLONE]','', 'Actual production installer remains intentionally locked; no multi-stage installed acceptance'),
    'B07-09': ('PARTIAL_IMPLEMENTATION','T:taraz_three_root_backup_20261114.py','T:docs/TARAZ_FRESH_START_FINAL_BACKUP_20261116_FA.md [VERIFIED_SAME_PRINCIPAL]','', '67 SQLite restored; no atomic cross-root VSS or cross-device DPAPI'),
    'B07-11': ('BLOCKED','T:scripts/build_taraz_v106_aaas_20261111.py','T:docs/TARAZ_FRESH_START_FINAL_BACKUP_20261116_FA.md [BACKUP_ONLY]','', 'Updater Production Apply disabled; no field-deployment acceptance'),
    'B07-12': ('PARTIAL_IMPLEMENTATION','T:scripts/qa_taraz_fresh_reset_rollback_20261115.py','T:docs/TARAZ_FRESH_START_EXECUTION_EVIDENCE_20261115_FA.md [PRIOR_CLONE_PASS]','', 'Clone rollback PASS only; production in-place rollback not proven'),
    'B07-15': ('PARTIAL_IMPLEMENTATION','T:taraz_three_root_backup_20261114.py','T:docs/TARAZ_FRESH_START_FINAL_BACKUP_20261116_FA.md [VERIFIED_SAME_PRINCIPAL]','', 'Same-principal recovery successful; device-loss/disaster restore unverified'),
    'B08-01': ('SOURCE_ONLY','M:role_profiles.py','M:tests/test_radar_host_adapter.py [PASS_20261116]','', 'Role primitives are not an end-user role designer'),
    'B08-02': ('PARTIAL_IMPLEMENTATION','M:radar_crm_store.py','M:tests/test_radar_host_adapter.py [PASS_20261116]','', 'Scoped backend CRM permissions; field-level combined policy unverified'),
    'B08-03': ('PARTIAL_IMPLEMENTATION','M:radar_crm_store.py','M:tests/test_radar_crm_store.py [PASS_20261116]','', 'CRM project isolation tested; organization-wide cross-module ACL not established'),
    'B08-05': ('PARTIAL_IMPLEMENTATION','M:mtr_finance_workflow_contract.py','M:tests/test_mtr_finance_workflow_contract.py [PASS_20261116]','', 'Explicit human financial approval gates; full enterprise separation of duties unverified'),
    'B08-08': ('PARTIAL_IMPLEMENTATION','M:radar_crm_store.py','M:tests/test_radar_crm_store.py [PASS_20261116]','', 'CRM event log exists; enterprise-wide immutable audit is not proven'),
    'B08-10': ('SOURCE_ONLY','T:standalone_accounting_identity.py','T:tests/test_taraz_fresh_windows_workspace_20261115.py [PRIOR_RUN]','', 'Windows-bound local identity is not fleet-wide session/device management'),
    'B08-13': ('PARTIAL_IMPLEMENTATION','M:radar_crm_store.py','M:tests/test_radar_host_adapter.py [PASS_20261116]','', 'CRM cross-tenant test coverage; all Madar/Taraz interfaces not audited'),
    'B08-15': ('SOURCE_ONLY','T:taraz_ai_chat_store.py','T:tests/test_taraz_ai_chat_vertical_20261114.py [PRIOR_RUN]','', 'Bounded financial suggestion authorizations; generalized agent-grant manager absent'),
    'B09-01': ('SOURCE_ONLY','T:src/taraz_madar_dashboard.jsx','T:tests/test_taraz_madar_data_reader_20261110.py [NOT_RUN]','', 'Dashboard prototype does not prove CEO real-time KPI quality'),
    'B09-02': ('SOURCE_ONLY','T:taraz_order_store.py','T:tests/test_taraz_order_finance_20261112.py [NOT_RUN]','', 'Order finance computations are not realized-profit accounting'),
    'B09-03': ('SOURCE_ONLY','M:src/host_backup_health.js','M:tests/backup_status_next.test.cjs [NOT_RUN]','', 'Backup health fragment, not organization health score'),
    'B09-06': ('SOURCE_ONLY','M:src/gantt_model.js','M:tests/gantt_model.test.cjs [PASS_20261116]','', 'Gantt capacity dependencies do not prove manufacturing utilization analytics'),
    'B09-09': ('SOURCE_ONLY','M:radar_crm_store.py','M:tests/test_radar_crm_store.py [PASS_20261116]','', 'CRM contact store does not prove sales funnel conversion analytics'),
}

# C-ID is a tentative semantic grouping of ideas. The source notes DO NOT
# explicitly provide a 135-row approved C-ID mapping.
C_MAP = {
    'B01': ('C02','C01','C02','C02','C02','C02','C01','C01','C04','C02','C01','C01'),
    'B02': ('C03','C03','C03','C02','C05','C04','C05','C05','C04','C03','C03','C03','C05','C04','C05','C04','C04','C04'),
    'B03': ('C06',) + ('C07',)*11 + ('C06','C07','C07'),
    'B04': ('C08',)*9 + ('C09',)*6,
    'B05': ('C11','C10','C10','C10','C11','C11','C11','C11','C12','C10','C10','C11','C12','C15','C17'),
    'B06': ('C12','C12') + ('C13',)*13,
    'B07': ('C14','C14','C14','C14','C14','C15','C15','C15','C15','C16','C14','C15','C15','C15','C15'),
    'B08': ('C16',)*15,
    'B09': ('C17','C18','C17','C18','C17','C17','C18','C17','C17','C18','C17','C18','C17','C17','C17'),
}

PROPOSED_ONLY = {
    'B04-10','B04-11','B04-12','B04-13','B04-14','B04-15',
    'B09-04','B09-07','B09-10','B09-12',
}

PHASE = {'C01':'P2 / Madar','C02':'P3','C03':'P3','C04':'P3',
         'C05':'P3','C06':'P4 / Radar','C07':'P4 / Radar',
         'C08':'P4 / Radar','C09':'P4 / Radar','C10':'P4',
         'C11':'P4','C12':'P1','C13':'P4','C14':'P7',
         'C15':'P5','C16':'P5','C17':'D1','C18':'D1 / P3'}


def note_rows(path):
    rows = {}
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        match = re.match(r'^\|\s*(B\d\d-\d\d)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|$', line)
        if match:
            assert match[1] not in rows, ('duplicate',match[1])
            rows[match[1]] = (match[2].strip(), match[3].strip(), number)
    return rows


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sanitize(text):
    return str(text).replace('|','\\|').replace('\n',' ').strip()


def audit():
    html = CATALOG.read_text(encoding='utf-8')
    found = re.search(r'<script[^>]*id="catalog-data"[^>]*>(.*?)</script>', html, re.S)
    assert found, 'Embedded original catalog JSON missing'
    atlas = json.loads(found[1])
    a, b = note_rows(NOTE_14), note_rows(NOTE_128)
    ideas = atlas['ideas']
    expected = {item['id'] for item in ideas}
    assert len(ideas)==len(expected)==135
    assert len(atlas['candidates'])==18 and len(atlas['categories'])==9
    assert expected==set(a)==set(b)
    assert all(a[k][:2]==b[k][:2] for k in expected), 'Historical brainstorm text changed'
    assert atlas['sourceHash']==sha(NOTE_14), 'HTML not pinned to original v1.4'
    assert all(item['description']==b[item['id']][1] for item in ideas)
    assert all(item['title']==b[item['id']][0].split(' — ایده کاربر')[0] for item in ideas)
    assert set(C_MAP)=={x['id'] for x in atlas['categories']}
    assert set(AUDITED)<=expected and PROPOSED_ONLY<=expected
    assert all(len(C_MAP[k])==sum(item['category']==k for item in ideas) for k in C_MAP)
    assert set(PHASE)=={c['id'] for c in atlas['candidates']}

    rows = []
    per_category = Counter()
    for item in ideas:
        idea_id = item['id']
        cat, index = idea_id.split('-')
        candidate = C_MAP[cat][int(index)-1]
        if idea_id in AUDITED:
            status, source, test, frozen, blocker = AUDITED[idea_id]
        elif idea_id in PROPOSED_ONLY:
            status, source, test, frozen, blocker = ('PLANNED','','','','Candidate stage only, no authorized implementation evidence')
        else:
            status, source, test, frozen, blocker = ('NOT_VERIFIED','','','','No item-specific validated source-to-test-to-runtime chain established')
        assert status in ALLOWED
        for field in (source, test):
            if not field:
                continue
            for member in field.split(';'):
                tag = member.strip().split(' [',1)[0]
                prefix, rel = tag.split(':',1)
                assert prefix in ('M','T'),tag
                target = (MADAR if prefix=='M' else TARAZ)/rel
                assert target.is_file(), ('Missing evidence file',idea_id,str(target))
        row = {
            'Idea ID':idea_id, 'Title':b[idea_id][0],
            'Product':{'B01':'Madar','B02':'Madar / Taraz',
                       'B03':'Radar (inside Madar)','B04':'Radar (inside Madar)',
                       'B05':'Madar / Taraz','B06':'Taraz / Madar',
                       'B07':'Madar / Taraz','B08':'Madar / Taraz','B09':'Madar / Taraz'}[cat],
            'Candidate C-ID':candidate, 'Phase':PHASE[candidate],
            'Source Evidence':source or 'NOT_ESTABLISHED',
            'Test Evidence':test or 'NOT_ESTABLISHED',
            'Frozen EXE':frozen or 'NOT_VERIFIED_FOR_FULL_IDEA',
            'Installed App':'Taraz 1.0.4 only; 1.0.6 NOT_INSTALLED / capability NOT_VERIFIED',
            'Status':status,
            'Blocker':blocker,
        }
        rows.append(row)
        per_category[cat] += 1
    return atlas,rows,per_category,a,b


def write():
    atlas,rows,counts,old,new = audit()
    statuses = Counter(row['Status'] for row in rows)
    fields = ('Idea ID','Title','Product','Candidate C-ID','Phase',
              'Source Evidence','Test Evidence','Frozen EXE','Installed App','Status','Blocker')
    with CSV.open('w',newline='',encoding='utf-8-sig') as file:
        writer = csv.DictWriter(file,fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    intro = [
      '# ماتریس شواهد ۱۳۵ ایدهٔ مدار، تراز و رادار',
      '',
      '**ماهیت:** ارزیابی محدود شواهد، نه اعلام تکمیل قابلیت و نه مجوز انتشار.',
      '',
      f'- منبع HTML: `{CATALOG.name}`، SHA-256: `{sha(CATALOG)}`',
      f'- نوت ۱.۴: `{NOTE_14.name}`، SHA-256: `{sha(NOTE_14)}`',
      f'- نوت ۱.۲۸: `{NOTE_128.name}`، SHA-256: `{sha(NOTE_128)}`',
      '- سه منبع ۱۳۵ شناسه و شرح یکسان دارند؛ اطلس HTML به هش نسخهٔ ۱.۴ ارجاع می‌دهد؛ نسخهٔ ۱.۲۸ تصمیم‌های Refine جدیدتر دارد.',
      '- سه عنوان B02-16 تا B02-18 در نوت دارای پسوند «ایده کاربر» هستند؛ HTML فقط این پسوند را از عنوان حذف کرده است.',
      '- انتساب C-ID **تحلیل معنایی و پیشنهادی** است؛ مرجع نسخه‌دار، انتساب فردبه‌فردِ تأییدشده ارائه نمی‌کند.',
      '- در ستون Test، `PASS_20261116` یعنی آزمون‌های هدفمند در این مرور اجرا و عبور کرده‌اند؛ `NOT_RUN` یعنی فقط فایل آزمون موجود است؛ `PRIOR_RUN` یعنی شواهد اجرای قبلی، نه بازآزمایی فعلی.',
      '- در Frozen EXE تنها قابلیت جزئی آزموده‌شده ذکر می‌شود؛ هیچ ردیف، پذیرش تمام ایده در نسخهٔ نصب‌شده را ادعا نمی‌کند.',
      '- `NOT_VERIFIED` به معنی عدم اجرای ممیزی هدفمند برای آن ردیف است، نه نبود قطعی پیاده‌سازی.',
      '- `PLANNED` در این سند به معنی پیشنهاد اطلس، **نه مجوز اجرایی قطعی کاربر** است.',
      '',
      '## شمارش وضعیت‌ها',
      '',
      '| Status | Count |',
      '|---|---:|',
    ]
    for key in ALLOWED:
        intro.append(f'| {key} | {statuses[key]} |')
    intro += ['',f'**جمع: {sum(statuses.values())} ایده؛ {len(counts)} دسته، ۱۸ بستهٔ کاندید.**','','## ماتریس','','| '+' | '.join(fields)+' |','|'+'|'.join('---' for _ in fields)+'|']
    for row in rows:
        intro.append('| '+' | '.join(sanitize(row[field]) for field in fields)+' |')
    OUTPUT.write_text('\n'.join(intro)+'\n',encoding='utf-8')
    package_lines = [
      '# ممیزی ۱۸ بستهٔ C01–C18',
      '',
      'بسته‌ها کاندید طراحی‌اند، نه قابلیت تمام‌شده. شمارش ردیف‌ها بر اساس نگاشت معنایی غیررسمی است.',
      'هر status در این جدول **وضعیت بسته** است، نه ادعای اجرای تمامی ایده‌های داخل آن.',
      '',
      '| C-ID | Title | Proposed Version | Phase | Ideas mapped | Verified | Partial | Source only | Planned | Blocked | Not verified | Package Status | Evidence / Next gate |',
      '|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|',
    ]
    for item in atlas['candidates']:
        cid=item['id']
        members=[r for r in rows if r['Candidate C-ID']==cid]
        c=Counter(r['Status'] for r in members)
        if c['BLOCKED']:
            status='BLOCKED'
        elif c['PARTIAL_IMPLEMENTATION']:
            status='PARTIAL_IMPLEMENTATION'
        elif c['SOURCE_ONLY']:
            status='SOURCE_ONLY'
        elif c['PLANNED'] and c['PLANNED']==len(members):
            status='PLANNED'
        else:
            status='NOT_VERIFIED'
        sources = list(dict.fromkeys(
            r['Source Evidence'].split(';')[0] for r in members
            if r['Source Evidence']!='NOT_ESTABLISHED'))[:2]
        proof=' / '.join(sources) if sources else 'No item-specific implementation evidence'
        gate=item['gate']
        package_lines.append('| '+' | '.join(map(sanitize,[
          cid,item['title'],item['stage'],PHASE[cid],len(members),
          c['VERIFIED_IMPLEMENTED'],c['PARTIAL_IMPLEMENTATION'],c['SOURCE_ONLY'],
          c['PLANNED'],c['BLOCKED'],c['NOT_VERIFIED'],status,
          proof+'; NEXT: '+gate,
        ]))+' |')
    package_lines += [
      '',
      '## مرحلهٔ بعد و وابستگی',
      '',
      '- P0: مرجع سورس و نوت‌های نسخه‌دار حفظ شدند؛ هیچ پیاده‌سازی از ثبت ایده استنتاج نمی‌شود.',
      '- P1/P2: پذیرش Frozen فاکتور، PDF و سفارش از شواهد قبلی تراز؛ نصب عملیاتی ۱.۰.۶ هنوز انجام نشده است.',
      '- D1: مدل مشترک داده و KPI باید روی دادهٔ مرجع واقعی و با ACL ممیزی شود.',
      '- P3: Provider واقعی فعلاً غیرفعال است؛ تاریخچهٔ Chat به معنی اجرای مدل نیست.',
      '- P4: یکپارچگی دو برنامه و Radar مستلزم قرارداد واقعی دوطرفه، نقش و رسید مالی است.',
      '- P5/P6: Recovery، Writer quiescence و آزمون ایزوله/نصب مستقل ضروری‌اند.',
      '- P7: Release Gate و Rollback Production تا عبور همهٔ پیش‌شرط‌ها باید Fail-closed بمانند.',
      '',
      '**درصد پیشرفت ارائه نشده است:** تعریف وزن و معیار پذیرش ۱۳۵ مورد و ۱۸ بسته هنوز تصویب نشده است.',
    ]
    PACKAGES.write_text('\n'.join(package_lines)+'\n',encoding='utf-8')
    return {'ideas':len(rows),'packages':len(atlas['candidates']),'statuses':dict(statuses),
            'categoryCounts':dict(counts),'paths':[str(OUTPUT),str(CSV),str(PACKAGES)]}


if __name__=='__main__':
    print(json.dumps(write(),ensure_ascii=True))
