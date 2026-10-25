"""Exactly 100 independent malicious/invalid company-name cases.

These are 100 adversarial TEST CASES, not 100 discovered defects.
Always confined to a temporary registry, never an installed company hub.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from standalone_accounting_company_registry import (
    CompanyRegistryError, StandaloneCompanyRegistry,
)


def cases():
    values=[]
    values.extend(('control', 'A'+chr(i)+'B') for i in (*range(32),127))
    hidden=[0x00AD,0x061C,0x200B,0x200E,0x200F,
            0x202A,0x202B,0x202C,0x202D,0x202E,
            0x2066,0x2067,0x2068,0x2069]
    values.extend(('bidi-or-invisible', 'حساب'+chr(i)+'کتاب') for i in hidden)
    values.extend(('too-long', 'س' * n) for n in range(121,141))
    base='AlphaAlpha'
    for mask in range(1,21):
        chars=[char.upper() if mask & (1 << i) else char.lower()
               for i,char in enumerate(base)]
        values.append(('duplicate-visual-label',''.join(chars)))
    values.extend(('bad-type',value) for value in (None,{},[],1,3.14,b'Alpha',True))
    values.extend(('empty-or-spaces',value) for value in ('',' ','\t','\n','    ','\u2003'))
    assert len(values)==100,len(values)
    return values


def main():
    checks=[]
    with TemporaryDirectory(prefix='madar-r12-security-100-') as temp:
        registry=StandaloneCompanyRegistry(Path(temp))
        registry.create_company('AlphaAlpha')
        registry.create_company('شرکت کاویان')
        for position,(category,value) in enumerate(cases(),1):
            try:
                registry.create_company(value)
            except CompanyRegistryError:
                passed=True
            except Exception as exc:
                passed=False
            else:
                passed=False
            checks.append({'case':position,'category':category,'passed':passed,
                           'input':repr(value)[:100]})
        # A valid Persian company with ZWNJ must still work as normal.
        accepted=registry.create_company('بسته\u200cبندی آزمایشی')
        good=accepted['name']=='بسته\u200cبندی آزمایشی'
    report={'total':len(checks),'passed':sum(r['passed'] for r in checks),
            'failed':[r for r in checks if not r['passed']],
            'persian_zwnj_valid':good,'cases':checks}
    output=Path(__file__).resolve().parents[1]/'.qa-r12-company-security-100.json'
    if output.exists():raise RuntimeError('Refusing to overwrite security report')
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'total':report['total'],'passed':report['passed'],
      'failed':len(report['failed']),'persian_zwnj_valid':good,
      'report':str(output)},ensure_ascii=True))
    return 0 if report['passed']==100 and good else 1


if __name__=='__main__':raise SystemExit(main())
