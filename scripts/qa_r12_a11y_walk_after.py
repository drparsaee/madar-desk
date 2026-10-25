"""Read-only keyboard/accessibility UX survey of all standalone workspace tabs.

Collects *observed* missing accessible names or form-label associations. No
accounting command is sent; all sources and profiles are temporary.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import time
from threading import Thread

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from standalone_accounting_desktop import AccountingDesktopAPI,serve_accounting_page


def run():
    with tempfile.TemporaryDirectory(prefix='madar-r12-a11y-') as root:
        scratch=Path(root)
        for key in ('APPDATA','LOCALAPPDATA','WEBVIEW2_USER_DATA_FOLDER','TEMP','TMP'):
            folder=scratch/key.lower();folder.mkdir(exist_ok=True)
            os.environ[key]=str(folder)
        api=AccountingDesktopAPI(scratch/'accounting',company_name='شرکت آزمون کاربر')
        api.standaloneAccountingRead()
        server=serve_accounting_page(ROOT/'dist')
        runner=Thread(target=server.serve_forever,daemon=True);runner.start()
        outputs={'tabs':[],'violations':[],'countControls':0,'loaded':False,
                 'ledgerRevisionBefore':api.standaloneAccountingRead()['revision']}
        import webview
        window=webview.create_window('مدار | ممیزی رابط و فرم‌ها',
            f'http://127.0.0.1:{server.server_port}/accounting.html',
            width=1440,height=900,js_api=api)

        def eval_js(source):return window.evaluate_js('(()=>{'+source+'})()')

        def survey():
            try:
                for _ in range(70):
                    if eval_js('return !!document.querySelector(".sac-ribbon-shell") && !!document.querySelector(".sac-sidebar nav")'):
                        outputs['loaded']=True
                        break
                    time.sleep(.12)
                available=eval_js('return [...document.querySelectorAll(".sac-sidebar nav button")].map(b=>b.textContent.trim())')
                if not available:
                    outputs['violations'].append({'location':'global','issue':'no navigation available'})
                for name in available:
                    js_name=json.dumps(name,ensure_ascii=False)
                    eval_js('const button=[...document.querySelectorAll(".sac-sidebar nav button")].find(x=>x.textContent.trim()==='+js_name+');if(button)button.click();return true;')
                    time.sleep(.09)
                    response=eval_js('''
                      const visible=e=>{
                        const s=getComputedStyle(e),r=e.getBoundingClientRect();
                        return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0;
                      };
                      const container=document.querySelector('.sac-body')||document;
                      const controls=[...container.querySelectorAll('button,input,select,textarea,a[href]')]
                        .filter(visible);
                      const issues=[];
                      for(const el of controls){
                        const tag=el.tagName.toLowerCase();
                        const type=el.getAttribute('type')||'';
                        const closestLabel=el.closest('label');
                        const labelledBy=el.getAttribute('aria-labelledby')?.split(/\\s+/)
                          .map(id=>document.getElementById(id)?.textContent||'').join(' ');
                        const labelFromFor=el.id?document.querySelector('label[for="'+CSS.escape(el.id)+'"]')?.textContent:'';
                        const accessible=(el.getAttribute('aria-label')||labelledBy||
                          labelFromFor||closestLabel?.textContent||el.getAttribute('title')||
                          (tag==='button'||tag==='a'?el.textContent:'')||'').trim();
                        if(!accessible&&type!=='hidden')issues.push({type:'no_accessible_name',
                          tag,typeAttr:type,html:el.outerHTML.slice(0,180)});
                        if(tag==='button'&&!el.hasAttribute('type'))
                          issues.push({type:'button_without_explicit_type',html:el.outerHTML.slice(0,180)});
                        if(el.hasAttribute('autofocus')&&tag!=='input')
                          issues.push({type:'unusual_autofocus',html:el.outerHTML.slice(0,180)});
                      }
                      const ids=[...document.querySelectorAll('[id]')].map(x=>x.id);
                      const dup=[...new Set(ids.filter((id,i)=>ids.indexOf(id)!==i))];
                      dup.forEach(id=>issues.push({type:'duplicate_id',id}));
                      return {controls:controls.length,issues,sections:document.querySelectorAll('section.sac-panel').length};
                    ''')
                    response=response or {}
                    outputs['tabs'].append({'tab':name,'controls':response.get('controls',0),
                                            'panels':response.get('sections',0),
                                            'violationCount':len(response.get('issues',[]))})
                    for issue in response.get('issues',[]):
                        outputs['violations'].append({'location':name,**issue})
                    outputs['countControls']+=response.get('controls',0)
            except Exception as exc:
                outputs['error']=repr(exc)
            finally:
                window.destroy()

        window.events.loaded+=survey
        try:webview.start()
        finally:
            server.shutdown();server.server_close();runner.join(timeout=5)
        outputs['ledgerRevisionAfter']=api.standaloneAccountingRead()['revision']
        report_path=ROOT/'.qa-r12-a11y-observations-after.json'
        if report_path.exists():
            raise RuntimeError('Refusing to overwrite an existing accessibility report')
        report_path.write_text(json.dumps(outputs,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'loaded':outputs['loaded'],'tabs':len(outputs['tabs']),
             'countControls':outputs['countControls'],
             'violations':len(outputs['violations']),
             'ledgerUnchanged':outputs['ledgerRevisionBefore']==outputs['ledgerRevisionAfter'],
             'error':outputs.get('error'),'report':str(report_path)},ensure_ascii=True))
        return 0 if outputs['loaded'] and not outputs.get('error') else 1


if __name__=='__main__':raise SystemExit(run())
