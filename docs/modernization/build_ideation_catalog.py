"""Build a read-only, standalone RTL idea catalog from the versioned source note.

No application database is opened or mutated. The output is a single offline HTML file.
Usage: py -3.12 docs/modernization/build_ideation_catalog.py
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "MADAR_TARAZ_RADAR_IDEATION_ATOMIC_NOTE_20261107_V1_4.md"
OUTPUT = ROOT / "MADAR_TARAZ_RADAR_IDEAS_CATALOG_20261108.html"
SOURCE_SHA = "e14886d763ba8481ee4659fe0417b742b528714b32298117f81cb90bc96cff12"

CATEGORIES = {
    "B01": "ثبت و مدیریت سفارش",
    "B02": "هوش مصنوعی مستقل و ایجنت‌ها",
    "B03": "CRM رادار و مدیریت مشتری",
    "B04": "شبکه تأمین‌کنندگان و درآمدزایی",
    "B05": "اتصال مدار و تراز و یکپارچگی مالی",
    "B06": "فاکتور، اسناد و ارتباط با مشتری",
    "B07": "نصب، شبکه و همگام‌سازی",
    "B08": "کاربران، نقش‌ها و امنیت",
    "B09": "داده، گزارش و تحلیل کسب‌وکار",
}

# Only the user's explicitly identified ideas are labeled user-originated.
# The other brainstorm titles do NOT imply attribution to the assistant.
STAGES = {
    "C01": ("نسخه ۱", "هسته ضروری"),
    "C02": ("نسخه ۱.۱", "دستیار ثبت سفارش"),
    "C03": ("نسخه ۲", "AI آفلاین"),
    "C04": ("نسخه ۲", "هوش سازمانی"),
    "C05": ("نسخه ۲", "ایجنت‌های عملیاتی"),
    "C06": ("نسخه ۱", "محدود: مشتری موقت و تاریخچه"),
    "C07": ("نسخه ۲", "پیگیری هوشمند CRM"),
    "C08": ("نسخه ۲", "کشف تأمین‌کننده"),
    "C09": ("نسخه ۳", "بازار فرصت‌های تجاری"),
    "C10": ("نسخه ۱", "هسته ضروری"),
    "C11": ("نسخه ۱", "هسته ضروری"),
    "C12": ("نسخه ۱", "هسته ضروری"),
    "C13": ("نسخه ۱", "محدود: ارسال دستی سند"),
    "C14": ("نسخه ۱", "محدود: نصب محلی و LAN"),
    "C15": ("نسخه ۱", "محدود: بکاپ و صف مقاوم"),
    "C16": ("نسخه ۱", "هسته ضروری"),
    "C17": ("نسخه ۱.۱", "داشبورد اولیه"),
    "C18": ("نسخه ۳", "هوش مالی پیشرفته"),
}


def extract(markdown: str) -> dict:
    brainstorm = markdown.split("## 3. فاز سوم: Brainstorm", 1)[1].split(
        "## 4. فاز چهارم:", 1
    )[0]
    items = []
    for match in re.finditer(
        r"(?m)^\| (B\d{2}-\d{2}) \| ([^|\n]+) \| ([^|\n]+) \|\s*$",
        brainstorm,
    ):
        identifier, name, description = [part.strip() for part in match.groups()]
        cat = identifier[:3]
        assert cat in CATEGORIES
        user_origin = "ایده کاربر" in name
        name = name.replace(" — ایده کاربر", "")
        items.append(
            {
                "id": identifier,
                "title": name,
                "description": description,
                "category": cat,
                "categoryName": CATEGORIES[cat],
                "origin": "ایده صریح کاربر" if user_origin else "منشأ فردی نامشخص",
            }
        )
    assert len(items) == 135, f"Expected 135, got {len(items)}"
    assert len({x["id"] for x in items}) == 135
    expected = {"B01": 12, "B02": 18, **{f"B{i:02d}": 15 for i in range(3, 10)}}
    assert dict(Counter(x["category"] for x in items)) == expected
    for item in items:
        assert item["title"] and item["description"] and "?" * 3 not in item["description"]

    candidates_section = markdown.split("### ۱۸ نامزد تجمیع‌شده", 1)[1].split(
        "### وضعیت ارزیابی", 1
    )[0]
    candidates = {}
    for match in re.finditer(
        r"(?m)^\| (C\d{2}) \| ([^|\n]+) \| ([^|\n]+) \|\s*$",
        candidates_section,
    ):
        code, title, scope = [p.strip() for p in match.groups()]
        assert code not in candidates
        candidates[code] = {
            "id": code,
            "title": title,
            "description": scope,
            "stage": STAGES[code][0],
            "scope": STAGES[code][1],
        }
    assert len(candidates) == 18 and set(candidates) == set(STAGES)

    scores_section = markdown.split("## ۱۰.", 1)[1].split("## ۱۱.", 1)[0]
    score_rows = re.findall(
        r"(?m)^\| (C\d{2}) \| ([1-5](?:/[1-5]){8}) \| (\d+\.\d+) \|",
        scores_section,
    )
    assert len(score_rows) == 18
    weights = [15, 14, 14, 12, 12, 10, 8, 8, 7]
    for code, ratings, score in score_rows:
        assert code in candidates
        computed = round(
            sum(w * int(r) for w, r in zip(weights, ratings.split("/"))) / 5, 1
        )
        assert computed == float(score), (code, computed, score)
        candidates[code]["score"] = float(score)

    dependencies = markdown.split("## ۱۲.", 1)[1].split("## ۱۳.", 1)[0]
    for match in re.finditer(
        r"(?m)^\| (C\d{2}) \| ([^|\n]+) \| ([^|\n]+) \| ([^|\n]+) \|",
        dependencies,
    ):
        code, required, optional, overlap = [p.strip() for p in match.groups()]
        candidates[code].update(
            {"required": required, "optional": optional, "overlap": overlap}
        )

    risk_block = markdown.split("## ۱۳.", 1)[1].split("## ۱۴.", 1)[0]
    for match in re.finditer(
        r"(?m)^\| (C\d{2}) \| ([^|\n]+) \| ([^|\n]+) \| ([^|\n]+) \| ([^|\n]+) \|",
        risk_block,
    ):
        code, cost, difficulty, risk, gate = [p.strip() for p in match.groups()]
        candidates[code].update(
            {"cost": cost, "difficulty": difficulty, "risk": risk, "gate": gate}
        )
    assert all(len(x) == 13 for x in candidates.values()), [
        (c, x.keys()) for c, x in candidates.items() if len(x) != 13
    ]
    return {
        "sourceVersion": "۱.۴",
        "sourceHash": SOURCE_SHA,
        "summary": {"ideas": len(items), "categories": len(CATEGORIES), "candidates": len(candidates)},
        "categories": [{"id": code, "title": title, "count": expected[code]} for code, title in CATEGORIES.items()],
        "ideas": items,
        "candidates": list(candidates.values()),
    }


TEMPLATE = r'''<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light">
<title>اطلس ایده‌ها | مدار، تراز و رادار</title>
<style>
:root{font-family:Tahoma,"Segoe UI",Arial,sans-serif;color:#18243b;background:#f4f7fb;scroll-behavior:smooth;--blue:#205daa;--navy:#132945;--line:#dfe7f1;--muted:#566780}
*{box-sizing:border-box}body{margin:0;line-height:1.8}button,input,select{font:inherit}button{cursor:pointer}button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #72a7ff;outline-offset:2px}
.shell{max-width:1340px;margin:0 auto;padding:0 24px}.hero{background:linear-gradient(120deg,#0f223e,#185c77);color:#fff;padding:33px 0 30px}.eyebrow{font-size:12px;font-weight:bold;letter-spacing:1px;color:#bbe8f4}.hero h1{font-size:clamp(25px,3vw,39px);margin:7px 0 9px}.hero p{color:#d6e9f6;margin:0;max-width:860px;font-size:14px}.hero em{font-style:normal;color:#ffdd95}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:22px 0}.stat{padding:16px 20px;background:#fff;border:1px solid var(--line);border-radius:14px;box-shadow:0 3px 12px #26406808}.stat strong{display:block;font-size:27px;line-height:1.3;color:#173858}.stat span{font-size:12px;color:var(--muted)}
.nav{display:flex;gap:8px;flex-wrap:wrap;border-bottom:1px solid var(--line);padding-bottom:13px}.tab{background:#fff;color:#324967;border:1px solid var(--line);padding:9px 15px;border-radius:10px}.tab[aria-selected=true]{background:var(--navy);color:#fff;border-color:var(--navy);font-weight:bold}
.toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:18px 0 8px}.search{flex:2;min-width:240px}.field{min-height:44px;border:1px solid #cbd7e5;border-radius:10px;background:white;padding:9px 12px;color:#1b2c44}.select{min-width:200px;flex:1}.subtle{font-size:12px;color:var(--muted)}.spacer{flex:1}
.action{border:1px solid #c9d6e5;background:#fff;color:#1f436b;border-radius:9px;padding:8px 12px;font-size:12px}.action:hover,.tab:hover{border-color:#538abb}
.results-bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:11px 0 16px}.results-bar b{color:#285882}.notice{background:#ecf7f5;border:1px solid #c6e4db;color:#185149;padding:11px 14px;border-radius:11px;font-size:12px}.warning{background:#fff7e7;border-color:#f1d9a9;color:#6a4a16}
.category{margin:12px 0;border:1px solid var(--line);border-radius:15px;background:white;overflow:hidden;box-shadow:0 2px 8px #2345680a}.category>summary{padding:14px 18px;cursor:pointer;font-weight:bold;display:flex;gap:12px;align-items:center;list-style:none}.category>summary::-webkit-details-marker{display:none}.category>summary:after{content:"⌄";margin-right:auto;color:#66809e;font-size:19px}.category[open]>summary:after{content:"⌃"}.category>summary:hover{background:#f7fbff}
.token{font:600 11px/1.3 Consolas,monospace;direction:ltr;background:#edf3fb;color:#27619d;border-radius:6px;padding:5px 8px;display:inline-block;white-space:nowrap}.count{font-size:12px;background:#eef3f8;color:#355474;padding:2px 9px;border-radius:30px}
.items{border-top:1px solid var(--line);padding:9px 13px 13px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.item{border:1px solid #e3eaf2;border-radius:10px;padding:12px 14px;background:#fcfdff}.item-head{display:flex;align-items:center;gap:8px;margin-bottom:5px;flex-wrap:wrap}.item h3{font-size:14px;line-height:1.65;margin:0;color:#1b3653}.item p{font-size:12.5px;color:#536275;margin:0}.origin{font-size:10px;border:1px solid #d0e6b8;background:#f0f8df;color:#3b691e;border-radius:7px;padding:1px 7px}
.candidates{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:16px 0 22px}.candidate{background:white;border:1px solid var(--line);border-radius:14px;padding:17px;box-shadow:0 3px 12px #2b47660a}.candidate h3{font-size:15px;margin:9px 0 5px}.candidate p{font-size:12px;color:#536275;margin:0 0 11px}.pill{display:inline-flex;align-items:center;gap:4px;border-radius:100px;font-size:10px;padding:2px 9px;background:#eff5ff;color:#225a91;margin-left:4px}.score{font-size:12px;font-weight:bold;color:#1f685a}.mini{font-size:12px;padding:8px 0;border-top:1px solid #edf1f5;color:#516079}.mini strong{color:#283e59}.candidate details{font-size:12px;color:#455770}.candidate details summary{cursor:pointer;color:#235c96;font-weight:bold;padding:7px 0}
.phase{background:white;border:1px solid var(--line);border-radius:14px;padding:16px;margin:12px 0}.phase h2{margin:0 0 5px;font-size:18px}.phase .candidate-tags{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}.chip{background:#f0f5fc;border:1px solid #d6e4f1;border-radius:8px;padding:7px 10px;cursor:pointer;font-size:12px}.chip:hover{background:#dcebf9}
.decision{background:#fff;border:1px solid var(--line);padding:16px;margin:12px 0;border-radius:14px}.decision h3{margin:0 0 7px;font-size:15px}.decision p{margin:0;color:#52637b;font-size:13px}
footer{border-top:1px solid var(--line);padding:24px 0;margin-top:32px;color:#728096;font-size:11px}.footerline{direction:ltr;overflow-wrap:anywhere;font-family:Consolas,monospace;font-size:10px}
@media(max-width:800px){.stats{grid-template-columns:repeat(2,1fr)}.items,.candidates{grid-template-columns:1fr}.shell{padding:0 13px}.hero{padding:23px 0}.candidate{padding:12px}.select{min-width:170px}}
@media print{.nav,.toolbar,.controls,.results-bar button{display:none!important}.hero{background:white!important;color:black!important;border-bottom:2px solid #333}.hero p,.eyebrow{color:#444!important}.category{break-inside:avoid}.category:not([open])>.items{display:grid}.items,.candidates{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>
<header class="hero"><div class="shell">
<div class="eyebrow">MADAR · TARAZ · RADAR CRM</div>
<h1>اطلس ایده‌ها و امکانات اکوسیستم</h1>
<p>یک نمای یکپارچه از تمام ایده‌های ثبت‌شده، قابلیت‌های تجمیعی، وابستگی‌ها و پیشنهاد تقسیم نسخه‌ها. <em>بانک ایده‌ها تأیید شده، ولی برنامه اجرای قابلیت‌ها هنوز مصوب نیست.</em></p>
</div></header>
<main class="shell">
  <section class="stats" aria-label="آمار"><div class="stat"><strong>۱۳۵</strong><span>ایده با شرح کامل</span></div><div class="stat"><strong>۹</strong><span>دسته اصلی</span></div><div class="stat"><strong>۱۸</strong><span>قابلیت تجمیع‌شده</span></div><div class="stat"><strong>۶.۰</strong><span>فاز فعلی: Refine</span></div></section>
  <div class="nav" role="tablist" aria-label="بخش‌های فهرست">
    <button class="tab" id="ideasTab" data-tab="ideas" role="tab" aria-selected="true">همه ۱۳۵ ایده</button>
    <button class="tab" id="candidatesTab" data-tab="candidates" role="tab" aria-selected="false">۱۸ قابلیت اصلی</button>
    <button class="tab" id="versionsTab" data-tab="versions" role="tab" aria-selected="false">پیشنهاد نسخه‌بندی</button>
    <button class="tab" id="statusTab" data-tab="status" role="tab" aria-selected="false">تصمیم‌ها و وضعیت</button>
  </div>
  <div class="toolbar controls">
    <input id="search" class="field search" type="search" placeholder="جست‌وجوی عنوان، توضیح یا شناسه مثل B05-07 یا C11…" aria-label="جست‌وجوی ایده‌ها و قابلیت‌ها">
    <select id="category" class="field select" aria-label="فیلتر دسته"><option value="all">همه دسته‌ها</option></select>
    <select id="stage" class="field select" aria-label="فیلتر نسخه پیشنهادی" style="display:none"><option value="all">همه نسخه‌ها</option><option>نسخه ۱</option><option>نسخه ۱.۱</option><option>نسخه ۲</option><option>نسخه ۳</option></select>
    <button id="clear" class="action">پاک‌کردن فیلتر</button>
    <button id="export" class="action">خروجی CSV</button>
  </div>
  <div class="results-bar"><span id="resultCount" class="subtle" aria-live="polite"></span><span class="spacer"></span><span class="subtle">کاملاً آفلاین، بدون API یا اتصال اینترنتی</span></div>
  <section id="content" aria-live="polite"></section>
</main>
<footer class="shell">
  <div>منبع: نوت اتمی v1.4 در docs/modernization و ارزیابی 5.3. وضعیت فعلی: مرحله ۵ بسته شده و مرحله ۶ صرفاً در سطح طراحی آغاز شده است.</div>
  <div>برچسب نسخه‌ها فقط پیشنهاد دستیار در Refine 6.1 است، نه اولویت یا تصمیم اجرایی تأییدشده.</div>
  <div class="footerline" id="sourceHash"></div>
</footer>
<script type="application/json" id="catalog-data">__PAYLOAD__</script>
<script>
"use strict";
const data=JSON.parse(document.getElementById('catalog-data').textContent);
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const norm=s=>String(s||'').toLocaleLowerCase('fa').replace(/ي/g,'ی').replace(/ك/g,'ک').replace(/\s+/g,' ').trim();
let tab='ideas';
let lastVisible=[];
$('sourceHash').textContent='SHA-256 منبع: '+data.sourceHash;
for(const cat of data.categories){const o=document.createElement('option');o.value=cat.id;o.textContent=cat.id+' · '+cat.title+' ('+cat.count+')';$('category').append(o)}
function cardIdea(x){
 return '<article class="item"><div class="item-head"><span class="token" dir="ltr">'+esc(x.id)+'</span><h3>'+esc(x.title)+'</h3>'+(x.origin==='ایده صریح کاربر'?'<span class="origin">ایده مستقیم کاربر</span>':'')+'</div><p>'+esc(x.description)+'</p></article>';
}
function cardCandidate(x){
 return '<article class="candidate"><div><span class="token">'+esc(x.id)+'</span><span class="pill">'+esc(x.stage)+' · پیشنهادی</span> <span class="score">'+x.score.toFixed(1)+' / ۱۰۰ (فرضی)</span></div>'
  +'<h3>'+esc(x.title)+'</h3><p>'+esc(x.description)+'</p>'
  +'<div class="mini"><strong>دامنه پیشنهاد‌شده: </strong>'+esc(x.scope)+'</div>'
  +'<div class="mini"><strong>هزینه نسبی: </strong>'+esc(x.cost)+' | <strong>دشواری: </strong>'+esc(x.difficulty)+' | <strong>ریسک: </strong>'+esc(x.risk)+'</div>'
  +'<details><summary>وابستگی‌ها و گیت ارزیابی</summary><div class="mini"><strong>پیش‌نیاز: </strong>'+esc(x.required)+'</div><div class="mini"><strong>تکمیلی: </strong>'+esc(x.optional)+'</div><div class="mini"><strong>هم‌پوشانی: </strong>'+esc(x.overlap)+'</div><div class="mini"><strong>گیت آزمون: </strong>'+esc(x.gate)+'</div></details></article>';
}
function searchItems(arr){const q=norm($('search').value);return arr.filter(item=>!q || norm(Object.values(item).join(' ')).includes(q))}
function ideasView(){
 $('category').style.display='';$('stage').style.display='none';
 const items=searchItems(data.ideas).filter(x=>$('category').value==='all'||x.category===$('category').value);
 lastVisible=items;$('resultCount').textContent=items.length+' ایده از ۱۳۵ · '+new Set(items.map(x=>x.category)).size+' دسته';
 const groups=data.categories.map(cat=>{
   const found=items.filter(x=>x.category===cat.id);
   if(!found.length)return '';
   return '<details class="category" '+(!!norm($('search').value)||$('category').value!=='all'||cat.id==='B01'?'open':'')+'><summary><span class="token">'+cat.id+'</span>'+esc(cat.title)+'<span class="count">'+found.length+' ایده</span></summary><div class="items">'+found.map(cardIdea).join('')+'</div></details>';
 }).join('');
 $('content').innerHTML='<div class="notice">تمام ۱۳۵ ایده با عنوان و شرح از متن مرجع بازیابی شده‌اند. فقط مواردی که در یادداشت صریحاً «ایده کاربر» داشته‌اند با این برچسب مشخص‌اند؛ منشأ بقیه جداگانه قابل اثبات نیست.</div><div class="controls" style="display:flex;gap:8px;margin:12px 0"><button id="openAll" class="action">بازکردن همه دسته‌ها</button><button id="closeAll" class="action">بستن همه دسته‌ها</button></div>'+(groups||'<div class="notice warning">موردی با این فیلتر پیدا نشد.</div>');
 $('openAll').addEventListener('click',()=>document.querySelectorAll('.category').forEach(x=>x.open=true));
 $('closeAll').addEventListener('click',()=>document.querySelectorAll('.category').forEach(x=>x.open=false));
}
function candidatesView(){
 $('category').style.display='none';$('stage').style.display='';
 const found=searchItems(data.candidates).filter(x=>$('stage').value==='all'||x.stage===$('stage').value);
 lastVisible=found;$('resultCount').textContent=found.length+' قابلیت از ۱۸';
 $('content').innerHTML='<div class="notice warning">امتیازهای مقایسه‌ای و وابستگی‌ها در مرحله ۵ تأیید شده‌اند، اما فرضی هستند. تقسیم نسخه‌های ۱ تا ۳ پیشنهاد مرحله Refine است و هنوز تصویب نشده است.</div><div class="candidates">'+found.map(cardCandidate).join('')+'</div>'+(found.length?'':'<div class="notice">موردی پیدا نشد.</div>');
}
function versionsView(){
 $('category').style.display='none';$('stage').style.display='none';lastVisible=data.candidates;
 $('resultCount').textContent='۴ سبد نسخه‌بندی پیشنهادی؛ بدون انتخاب یا حذف نامزد';
 const stages=[['نسخه ۱','چرخه اصلی سفارش تا سند و زیرساخت ضروری'],['نسخه ۱.۱','دستیار ثبت سفارش و داشبورد اولیه'],['نسخه ۲','هوشمندسازی سازمان و رادار'],['نسخه ۳','شبکه فرصت‌های تجاری و مدل‌های مالی پیشرفته']];
 $('content').innerHTML='<div class="notice warning">این توالی پاسخ پیشنهادی دستیار به سؤال «نظر خودت چیه؟» است؛ کاربر هنوز تعیین نکرده چه قابلیت‌هایی در نسخه اول بمانند.</div>'+stages.map(([name,desc])=>{
   const xs=data.candidates.filter(x=>x.stage===name);
   return '<section class="phase"><h2>'+esc(name)+' <span class="count">'+xs.length+' قابلیت</span></h2><p class="subtle">'+esc(desc)+'</p><div class="candidate-tags">'+xs.map(x=>'<button class="chip" data-go="'+x.id+'"><b>'+x.id+'</b> · '+esc(x.title)+(x.scope.startsWith('محدود')?' (محدود)':'')+'</button>').join('')+'</div></section>';
 }).join('');
 document.querySelectorAll('[data-go]').forEach(el=>el.onclick=()=>{tab='candidates';$('search').value=el.dataset.go;selectTab()});
}
function statusView(){
 $('category').style.display='none';$('stage').style.display='none';lastVisible=[];
 $('resultCount').textContent='مرز تصمیم‌های موجود و موارد باز';
 const entries=[
 ['تأییدشده','تعریف مسئله Clarify 1.17؛ نقشه ذهنی ۲.۲ با ۹ شاخه؛ بانک Brainstorm 3.9 با ۱۳۵ ایده؛ ۹ وزن معیار؛ فهرست ۱۸ نامزد و ارزیابی فرضی مرحله ۵.'],
 ['شروع شده، نه نهایی','مرحله ۶ (Refine) برای تعیین بخش‌های مطلوب، قابل تغییر، قابل حذف از محدوده نسخه اول و موانع پذیرش آغاز شده است.'],
 ['پیشنهادی، نه مصوب','تقسیم ۱۸ قابلیت میان نسخه‌های ۱، ۱.۱، ۲ و ۳ و برآورد سطح قابلیت‌های محدود نسخه اول.'],
 ['قید قطعی مالی','مدار درخواست و پیش‌نویس ایجاد می‌کند؛ تراز بعد از تأیید مدیر یا مدیر مالی مرجع ثبت رسمی سند است.'],
 ['حدود AI و ارتباط','AI آفلاین هدف طراحی است، نه قابلیت تأییدشده فعلی؛ دسترسی پیام‌رسان، فروش لید و ارتباط خودکار نیازمند مجوز و شواهد واقعی‌اند.'],
 ['محصولات مستقل','رادار نام CRM است؛ جریان نام اپلیکیشن تحقیق و پایش یوتیوب است و وارد این فهرست ۱۸ قابلیت سازمانی نمی‌شود.'],
 ['حفظ داده','این اطلس فقط فایل آفلاین خواندنی ساخته‌شده از نوت مرجع است؛ هیچ اتصال یا انتشار عملیاتی را اجرا نمی‌کند.']
 ];
 $('content').innerHTML=entries.map(([h,t])=>'<article class="decision"><h3>'+esc(h)+'</h3><p>'+esc(t)+'</p></article>').join('');
}
function selectTab(){
 document.querySelectorAll('.tab').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.tab===tab)));
 $('search').style.display=(tab==='ideas'||tab==='candidates')?'':'none';
 if(tab==='ideas')ideasView();
 else if(tab==='candidates')candidatesView();
 else if(tab==='versions')versionsView();
 else statusView();
}
for(const button of document.querySelectorAll('.tab'))button.addEventListener('click',()=>{tab=button.dataset.tab;$('search').value='';selectTab()});
for(const id of ['search','category','stage'])$(id).addEventListener(id==='search'?'input':'change',selectTab);
$('clear').addEventListener('click',()=>{$('search').value='';$('category').value='all';$('stage').value='all';selectTab()});
$('export').addEventListener('click',()=>{
 const rows=tab==='ideas'?[['شناسه','دسته','عنوان','شرح','منشأ'],...lastVisible.map(x=>[x.id,x.categoryName,x.title,x.description,x.origin])]:
 [['شناسه','عنوان','شرح','نسخه پیشنهادی','دامنه','امتیاز فرضی','هزینه نسبی','دشواری','ریسک'],...lastVisible.map(x=>[x.id,x.title,x.description,x.stage,x.scope,x.score,x.cost,x.difficulty,x.risk])];
 const csv='\uFEFF'+rows.map(r=>r.map(x=>'"'+String(x??'').replace(/"/g,'""')+'"').join(',')).join('\r\n');
 const blob=new Blob([csv],{type:'text/csv;charset=utf-8'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='madar-taraz-radar-'+tab+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);
});
selectTab();
</script>
</body></html>'''


def main() -> None:
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == SOURCE_SHA, (
        "The authoritative note changed: inspect it before regenerating."
    )
    data = extract(SOURCE.read_text(encoding="utf-8"))
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )
    output = TEMPLATE.replace("__PAYLOAD__", payload)
    assert "__PAYLOAD__" not in output
    assert output.count('id="catalog-data"') == 1
    assert all(item["id"] in output for item in data["ideas"])
    OUTPUT.write_text(output, encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "created",
                "output": str(OUTPUT),
                "bytes": OUTPUT.stat().st_size,
                "html_sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
                "ideas": len(data["ideas"]),
                "categories": len(data["categories"]),
                "candidates": len(data["candidates"]),
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
