'use strict';
/**
 * Reproducible UX-01..10 audit of the real Vite accounting UI, in headless
 * Chromium with axe-core 4.14.0 and an in-memory synthetic RIAL ledger.
 * This runner deliberately exits non-zero for unmet acceptance criteria.
 * It never sends a successful accounting mutation to the synthetic bridge.
 */
const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');
const {spawnSync}=require('node:child_process');
const {observation,assessAxe,assessContrast,assessTouch,summarize}=
  require('./madar_ux_acceptance_rules_20261103.cjs');

const root=path.resolve(__dirname,'..');
const outDir=path.join(root,'.qa-uxqa-20261103');
const packagedAxe=path.join(root,'node_modules','axe-core','axe.min.js');
const legacyAxe=path.join(root,'.qa-uxqa-tools','node_modules','axe-core','axe.min.js');
const axePath=process.env.MADAR_UXQA_AXE_PATH||
  (fs.existsSync(packagedAxe)?packagedAxe:legacyAxe);
const widths=process.env.MADAR_UXQA_WIDTHS?
  process.env.MADAR_UXQA_WIDTHS.split(',').map(Number):[390,560,768,1440];
if(!widths.length||widths.some(width=>![390,560,768,1440].includes(width))||
    new Set(widths).size!==widths.length)
  throw Error('MADAR_UXQA_WIDTHS must contain distinct supported widths: 390,560,768,1440');
const themes=process.env.MADAR_UXQA_THEMES?
  process.env.MADAR_UXQA_THEMES.split(','):['dark','light'];
if(!themes.length||themes.some(theme=>!['dark','light'].includes(theme))||
    new Set(themes).size!==themes.length)
  throw Error('MADAR_UXQA_THEMES must contain distinct dark,light values');
const report={format:3,baseline:'25a99ae9b32229968255f5187d1639586a48ea03',
  runUTC:new Date().toISOString(),scope:'Synthetic accounting UI, Chromium + axe 4.14.0',
  matrix:[],checks:[],errors:[],limitations:[],toolchain:{}};
const save=()=>{
  fs.mkdirSync(outDir,{recursive:true});
  report.summary=summarize(report.checks);
  fs.writeFileSync(path.join(outDir,'acceptance.json'),JSON.stringify(report,null,2)+'\n');
  console.log('UXQA_REPORT '+path.join(outDir,'acceptance.json'));
  console.log('UXQA_SUMMARY '+JSON.stringify(report.summary));
};
const add=(id,status,evidence,context={})=>report.checks.push(observation(id,status,evidence,context));
const errorText=error=>String(error?.message||error).slice(0,650);

function playwrightModule(){
  const tries=[process.env.MADAR_UXQA_PLAYWRIGHT,
    path.join(process.env.APPDATA||'', 'npm','node_modules','playwright'),
    path.join(process.env.USERPROFILE||'','AppData','Roaming','npm',
      'node_modules','playwright'),
    'playwright'];
  for(const location of tries){if(!location)continue;try{return require(location);}catch{}}
  throw Error('Playwright missing; supply MADAR_UXQA_PLAYWRIGHT or install globally');
}
function fixture(){
  const run=spawnSync('python',['-B','scripts/madar_ux_fixture_20261103.py'],{
    cwd:root,encoding:'utf8',env:{...process.env,PYTHONIOENCODING:'utf-8'},
    maxBuffer:8*1024*1024});
  if(run.status!==0)throw Error('Synthetic in-memory ledger failed: '+run.stderr);
  const payload=JSON.parse(run.stdout);
  if(payload?.view?.currency!=='RIAL'||Object.keys(payload.view.invoices||{}).length!==2)
    throw Error('Synthetic fixture invariant failed (RIAL / issued+draft)');
  return payload;
}
function freePort(){return new Promise((resolve,reject)=>{
  const socket=net.createServer();socket.once('error',reject);
  socket.listen(0,'127.0.0.1',()=>{
    const port=socket.address().port;socket.close(err=>err?reject(err):resolve(port));
  });
});}

function pageMetrics(){
  const visible=el=>{
    const r=el.getBoundingClientRect();
    // A zero/1px clipped floating-label placeholder is not rendered content.
    // Likewise children of a closed <details> are not visible, even when
    // getBoundingClientRect() reports an old positive geometry in Chromium.
    if(r.width<4||r.height<4)return false;
    for(let ancestor=el;ancestor;ancestor=ancestor.parentElement){
      const s=getComputedStyle(ancestor);
      if(ancestor.hidden||s.display==='none'||s.visibility==='hidden'||
          s.visibility==='collapse'||s.contentVisibility==='hidden')return false;
      if(ancestor.tagName==='DETAILS'&&!ancestor.open&&
          !ancestor.querySelector(':scope > summary')?.contains(el))return false;
    }
    return true;
  };
  const color=text=>{
    const values=String(text).match(/\d+(?:\.\d+)?/g);
    return values&&values.length>=3?values.slice(0,3).map(Number):null;
  };
  const light=rgb=>{
    const linear=rgb.map(value=>{
      const v=value/255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;
    });
    return .2126*linear[0]+.7152*linear[1]+.0722*linear[2];
  };
  const contrast=el=>{
    const textStyle=getComputedStyle(el);
    const fg=color(textStyle.color);
    let ancestor=el,bg=null,unresolved=false;
    if(textStyle.color.startsWith('rgba(')||
      textStyle.webkitTextFillColor!==textStyle.color||
      textStyle.backgroundClip==='text')unresolved=true;
    while(ancestor&&ancestor.nodeType===1){
      const style=getComputedStyle(ancestor);
      if(style.backgroundImage!=='none')unresolved=true;
      if(Number(style.opacity)<1||style.mixBlendMode!=='normal'||
        style.filter!=='none'||style.backdropFilter!=='none')unresolved=true;
      const alpha=(style.backgroundColor.match(/[\d.]+/g)||[])[3];
      if(alpha!==undefined&&Number(alpha)<1)unresolved=true;
      if(style.backgroundColor!=='transparent'&&alpha!=='0'&&alpha!==0&&
          !style.backgroundColor.endsWith(', 0)')&&!style.backgroundColor.endsWith(',0)')){
        bg=color(style.backgroundColor);break;
      }
      ancestor=ancestor.parentElement;
    }
    if(unresolved||!fg||!bg)return null;
    const a=light(fg),b=light(bg);
    return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
  };
  const candidates=[...document.querySelectorAll(
    '.sac-invoice-editor label.sac-field>span,.sac-invoice-editor .sac-field>span,'+
    '.sac-invoice-editor .sac-panel-title p,.sac-vtr-due-title h3,'+
    '.sac-vtr-due-item strong,.sac-vtr-due-item small,'+
    '.sac-ah-card>span,.sac-ah-card>small,.sac-ah-action small,'+
    '.sac-wizard-step-hint,.sac-wizard-heading-top span,'+
    '.sac-wizard-section-title,.sac-wizard-impact-warning,'+
    '.sac-invoice-summary-note,.sac-wizard-sticky-amount>span,'+
    '.sac-wizard-sticky-amount>small')].filter(visible);
  const directText=el=>[...el.childNodes].some(node=>
    node.nodeType===Node.TEXT_NODE&&node.textContent.trim());
  // A wrapping span may contain an inline <small> with a distinct ink color
  // (the Jalali hint does). Measure the actual text-bearing child, not a
  // misleading inherited foreground from its parent wrapper.
  const labels=[...new Set(candidates.flatMap(el=>directText(el)?[el]:
    [...el.querySelectorAll('*')].filter(child=>visible(child)&&directText(child))))];
  const samples=labels.map(el=>{
    window.__uxqaContrastIdCounter=(window.__uxqaContrastIdCounter||0)+1;
    const uid='r'+window.__uxqaContrastIdCounter;
    el.setAttribute('data-uxqa-contrast-id',uid);
    return {uid,text:(el.textContent||'').trim().slice(0,55),ratio:contrast(el)};
  });
  const targets=[...document.querySelectorAll(
    '.sac-ribbon-quick button,.sac-vtr-cta,.sac-vtr-due-actions button,'+
    '.sac-invoice-commandbar-actions button,.sac-workflow-actions button,'+
    '.sac-ribbon-tabs button,.sac-ribbon-tools button,'+
    '.sac-simple-nav button,.sac-nav-quick-actions button,.sac-nav-mode button,'+
    '.sac-ah-actions button,.sac-ah-card button,'+
    '.sac-wizard-sticky-footer button,.sac-wizard-step-nav button')].filter(el=>visible(el)&&!el.disabled)
    .map(el=>({text:(el.getAttribute('aria-label')||el.textContent||'').trim().slice(0,44),
      width:Math.round(el.getBoundingClientRect().width),
      height:Math.round(el.getBoundingClientRect().height)}));
  const scrollables=[...document.querySelectorAll('.sac-vtr-table-scroll,.sac-ribbon-tabs,.sac-ribbon-tools')]
    .filter(visible).map(el=>({name:el.getAttribute('aria-label')||el.className,
      overflow:el.scrollWidth>el.clientWidth+1,tabIndex:el.tabIndex,
      scrollWidth:el.scrollWidth,clientWidth:el.clientWidth,
      hasName:!!(el.getAttribute('aria-label')||el.getAttribute('aria-labelledby'))}));
  const composer=document.querySelector('.sac-invoice-editor');
  const activeActions=[...document.querySelectorAll(
    '.sac-invoice-commandbar-actions button,.sac-wizard-sticky-footer button,'+
    '.sac-invoice-summary button.sac-summary-save,.sac-invoice-editor .sac-form-actions button')]
    .filter(el=>visible(el)&&!el.disabled&&
      /ذخیره|پیش‌نویس|ادامه|بعد|مرور|ثبت اصلاح/.test(el.textContent||el.getAttribute('aria-label')||''));
  const activeRects=activeActions.map(el=>el.getBoundingClientRect());
  const heading=(document.querySelector('.sac-header h1')?.textContent||'').trim();
  const actionText=document.querySelector('.sac-ah-card.primary')?.textContent||'';
  const openAR=document.querySelector('.sac-ah-card.primary strong')?.textContent?.trim()||'';
  return {heading,theme:document.documentElement.dataset.theme,
    viewport:innerWidth,pageScrollWidth:document.documentElement.scrollWidth,
    horizontalOverflow:document.documentElement.scrollWidth>innerWidth+1,
    labels:samples,targets,scrollables,invoiceForm:!!composer,
    actionableOverview:/دریافتنی|مطالبات/.test(actionText)&&
      !!openAR&&!/نامشخص|—|^۰$|^0$/.test(openAR),
    dueSectionText:actionText.slice(0,250),
    saveVisibleInViewport:activeRects.some(rect=>rect.top>=0&&rect.bottom<=innerHeight),
    guidedWizard:!!document.querySelector('.sac-invoice-wizard-guided'),
    wizardStep:document.querySelector('.sac-wizard-step-nav [aria-current="step"]')?.textContent?.trim()||'',
    composerActionCount:activeActions.length,
    activeActionNames:activeActions.map(el=>el.textContent?.trim()?.slice(0,45)),
    hasInvoiceSummary:!!document.querySelector('.sac-invoice-summary,.sac-invoice-totals,'+
      '[aria-label="خلاصه فاکتور"],.sac-wizard-sticky-footer'),
    routeIds:[...document.querySelectorAll('.sac-simple-nav button[data-accounting-tab],'+
      '.sac-nav-more-menu button[data-accounting-tab],'+
      '.sac-ribbon-tools button[data-accounting-tab]')]
      .filter(visible).map(b=>({id:b.getAttribute('data-route-id')||
        b.getAttribute('data-ux-route')||b.getAttribute('data-accounting-tab')||
        b.getAttribute('data-tab-id')||b.getAttribute('aria-controls')||'',
        label:b.textContent?.trim()?.slice(0,50)})),
    searchTrigger:!!document.querySelector('[data-accounting-action="search"]'),
    simpleNav:!!document.querySelector('.sac-ux-simple .sac-simple-nav')};
}

/**
 * Evaluate real rendered text-background pixels, including nested alpha layers
 * and gradients. A first image shows text; in the second only glyph paint is
 * transparent (backgrounds, filters and layout remain intact); the third
 * verifies restoration and raster stability. The CSS foreground is compared
 * with EVERY background pixel where the glyph actually painted, never just the
 * midpoint of a gradient. Unknown geometry, color, coverage or repaint blocks.
 *
 * Use this only against the synthetic Chromium UI, never operational records.
 */
async function measureRenderedContrast(page,uid){
  const selector='[data-uxqa-contrast-id="'+uid+'"]';
  let maskApplied=false;
  try{
    const meta=await page.evaluate(async name=>{
      const el=document.querySelector('[data-uxqa-contrast-id="'+name+'"]');
      if(!el)return {error:'target disappeared before raster audit'};
      if(!el.textContent?.trim())return {error:'no text to measure'};
      // A sticky footer can already be visible at the 768px breakpoint.
      // Forcing it to the centre of a nested scrollport changes the sticky
      // constraint while the three screenshots are being captured. Do not
      // move an element that is already fully inside the viewport.
      const initialRect=el.getBoundingClientRect();
      const fullyInViewport=initialRect.width>=4&&initialRect.height>=4&&
        initialRect.left>=0&&initialRect.top>=0&&
        initialRect.right<=innerWidth&&initialRect.bottom<=innerHeight;
      const initialHit=fullyInViewport?document.elementFromPoint(
        (initialRect.left+initialRect.right)/2,
        (initialRect.top+initialRect.bottom)/2):null;
      const initiallyUnoccluded=initialHit&&(initialHit===el||el.contains(initialHit));
      if(!fullyInViewport||!initiallyUnoccluded)
        el.scrollIntoView({block:'center',inline:'nearest',behavior:'instant'});
      await document.fonts.ready;
      const rect=el.getBoundingClientRect();
      const styles=getComputedStyle(el);
      for(let ancestor=el;ancestor;ancestor=ancestor.parentElement){
        const paint=getComputedStyle(ancestor);
        if(Number(paint.opacity)<1||paint.mixBlendMode!=='normal'||
            paint.filter!=='none'||paint.backdropFilter!=='none')
          return {error:'group opacity/filter/blend changes text ink; unsupported exact compositing'};
      }
      if(styles.visibility==='hidden'||styles.display==='none'||
          rect.width<4||rect.height<4||
          rect.left<-0.5||rect.top<-0.5||
          rect.right>innerWidth+0.5||rect.bottom>innerHeight+0.5)
        return {error:'text bounding rectangle is not fully visible after scrolling',
          rect:{x:rect.x,y:rect.y,width:rect.width,height:rect.height},
          viewport:{width:innerWidth,height:innerHeight}};
      const midpoint=document.elementFromPoint((rect.left+rect.right)/2,
        (rect.top+rect.bottom)/2);
      if(!midpoint||(midpoint!==el&&!el.contains(midpoint)))
        return {error:'text centre is occluded by another element'};
      if(styles.backgroundClip==='text'&&styles.backgroundImage!=='none')
        return {error:'foreground is an image clipped to text, not a solid CSS color'};
      const rgbOf=style=>{
        const canvas=document.createElement('canvas');
        canvas.width=canvas.height=1;
        const ctx=canvas.getContext('2d',{willReadFrequently:true});
        if(!ctx)return null;
        try{ctx.clearRect(0,0,1,1);ctx.fillStyle=style;ctx.fillRect(0,0,1,1);
          return [...ctx.getImageData(0,0,1,1).data];}
        catch{return null;}
      };
      const fill=styles.webkitTextFillColor&&styles.webkitTextFillColor!=='currentcolor'?
        styles.webkitTextFillColor:styles.color;
      const foreground=rgbOf(fill);
      if(!foreground||foreground[3]===0)return {error:'unsupported or transparent CSS foreground',fill};
      const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);
      let current,textNodes=0;
      while((current=walker.nextNode())){
        if(!current.textContent.trim())continue;
        textNodes++;
        const parentStyle=getComputedStyle(current.parentElement);
        const childFill=parentStyle.webkitTextFillColor&&
          parentStyle.webkitTextFillColor!=='currentcolor'?
          parentStyle.webkitTextFillColor:parentStyle.color;
        const childForeground=rgbOf(childFill);
        if(!childForeground||childForeground.some((value,index)=>
          Math.abs(value-foreground[index])>1))
          return {error:'mixed foreground colors inside text target',fill,childFill};
      }
      if(!textNodes)return {error:'target has no visible text nodes'};
      return {rect:{left:rect.left,top:rect.top,right:rect.right,bottom:rect.bottom},
        viewport:{width:innerWidth,height:innerHeight},foreground,fill,textNodes};
    },uid);
    if(meta.error)return {ratio:null,method:'rendered-glyph-pixels',reason:meta.error,meta};
    // Let synchronous nested scrolling and font rasterisation settle before
    // comparing the three screenshots. Instability still blocks after this.
    await page.evaluate(()=>new Promise(resolve=>
      requestAnimationFrame(()=>requestAnimationFrame(resolve))));
    const screenshotOptions={animations:'disabled',caret:'hide',scale:'css'};
    const before=await page.screenshot(screenshotOptions);
    await page.evaluate(name=>{
      if(document.getElementById('uxqa-text-only-mask'))
        throw Error('An earlier raster mask is still present');
      const style=document.createElement('style');
      style.id='uxqa-text-only-mask';
      const target='[data-uxqa-contrast-id="'+name+'"]';
      style.textContent=target+','+target+' *,'+target+'::before,'+
        target+'::after,'+target+' *::before,'+target+' *::after{'+
        '-webkit-text-fill-color:transparent!important;text-shadow:none!important}';
      document.head.appendChild(style);
    },uid);
    maskApplied=true;
    const background=await page.screenshot(screenshotOptions);
    await page.evaluate(()=>document.getElementById('uxqa-text-only-mask')?.remove());
    maskApplied=false;
    const restored=await page.screenshot(screenshotOptions);
    const measured=await page.evaluate(async ({before,background,restored,meta})=>{
      const decode=async b64=>{
        const image=new Image();
        image.src='data:image/png;base64,'+b64;
        await image.decode();
        const canvas=document.createElement('canvas');
        canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;
        const ctx=canvas.getContext('2d',{willReadFrequently:true});
        if(!ctx)throw Error('No canvas pixel context');
        ctx.drawImage(image,0,0);
        return {width:canvas.width,height:canvas.height,
          pixels:ctx.getImageData(0,0,canvas.width,canvas.height).data};
      };
      const original=await decode(before),masked=await decode(background),
        again=await decode(restored);
      if([masked,again].some(item=>item.width!==original.width||
          item.height!==original.height)||
          original.width!==meta.viewport.width||original.height!==meta.viewport.height)
        return {ratio:null,reason:'screenshots do not match CSS viewport geometry'};
      const {rect,foreground}=meta;
      const l=Math.max(0,Math.floor(rect.left)),t=Math.max(0,Math.floor(rect.top));
      const r=Math.min(original.width,Math.ceil(rect.right));
      const b=Math.min(original.height,Math.ceil(rect.bottom));
      if(l>=r||t>=b)return {ratio:null,reason:'empty raster text rectangle'};
      const luminance=rgb=>{
        const linear=rgb.map(channel=>{
          const x=channel/255;
          return x<=.04045?x/12.92:((x+.055)/1.055)**2.4;
        });
        return .2126*linear[0]+.7152*linear[1]+.0722*linear[2];
      };
      let glyphPixels=0,unstablePixels=0,alphaPixels=0,minRatio=Infinity;
      let minPixel=null,gradientMin=Infinity,gradientMax=-Infinity;
      const fgAlpha=foreground[3]/255;
      for(let y=t;y<b;y++)for(let x=l;x<r;x++){
        const index=(y*original.width+x)*4;
        const originalPixel=original.pixels,backgroundPixel=masked.pixels,
          restoredPixel=again.pixels;
        const instability=Math.max(...[0,1,2].map(channel=>
          Math.abs(originalPixel[index+channel]-restoredPixel[index+channel])));
        if(instability>5)unstablePixels++;
        const glyphDelta=Math.max(...[0,1,2].map(channel=>
          Math.abs(originalPixel[index+channel]-backgroundPixel[index+channel])));
        if(glyphDelta<10)continue;
        glyphPixels++;
        if(originalPixel[index+3]<254||backgroundPixel[index+3]<254||
          restoredPixel[index+3]<254){alphaPixels++;continue;}
        const backdrop=[...backgroundPixel.slice(index,index+3)];
        const composite=backdrop.map((value,channel)=>
          foreground[channel]*fgAlpha+value*(1-fgAlpha));
        const bgL=luminance(backdrop),fgL=luminance(composite);
        const ratio=(Math.max(bgL,fgL)+.05)/(Math.min(bgL,fgL)+.05);
        if(ratio<minRatio){minRatio=ratio;minPixel={x,y,background:backdrop};}
        gradientMin=Math.min(gradientMin,bgL);
        gradientMax=Math.max(gradientMax,bgL);
      }
      if(unstablePixels>2)return {ratio:null,reason:'screenshot changed after removing text mask',
        glyphPixels,unstablePixels};
      if(alphaPixels)return {ratio:null,reason:'transparent screenshot pixels prevent reliable compositing',
        glyphPixels,alphaPixels};
      if(glyphPixels<8||!Number.isFinite(minRatio))return {ratio:null,
        reason:'too few changed glyph pixels to support contrast measurement',glyphPixels};
      return {ratio:minRatio,method:'rendered-glyph-pixels',glyphPixels,
        minPixel,backgroundLuminanceRange:[gradientMin,gradientMax],
        screenshotRestored:true,foreground};
    },{before:before.toString('base64'),background:background.toString('base64'),
      restored:restored.toString('base64'),meta});
    return measured;
  }catch(error){
    return {ratio:null,method:'rendered-glyph-pixels',reason:String(error.message||error).slice(0,220)};
  }finally{
    if(maskApplied)await page.evaluate(()=>
      document.getElementById('uxqa-text-only-mask')?.remove()).catch(()=>{});
  }
}

async function resolveRenderedContrast(page,samples){
  if(!Array.isArray(samples))return [];
  const results=[];
  for(const sample of samples){
    if(Number.isFinite(sample.ratio)){
      results.push({...sample,method:'opaque-css-background'});
      continue;
    }
    const measured=await measureRenderedContrast(page,sample.uid);
    results.push({...sample,...measured});
  }
  return results;
}

async function axeScan(page){
  await page.addScriptTag({path:axePath});
  return page.evaluate(async()=>{
    if(!window.axe)throw Error('axe injection failed');
    const result=await window.axe.run(document);
    return {version:window.axe.version,
      violations:result.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.length,
        targets:v.nodes.slice(0,3).map(node=>node.target)})),
      incomplete:result.incomplete.map(v=>({id:v.id,nodes:v.nodes.length})),
      passes:result.passes.length};
  });
}

async function main(){
  fs.mkdirSync(outDir,{recursive:true});
  if(!fs.existsSync(axePath))throw Error('axe-core 4.14.0 not installed at '+axePath);
  const axePkg=JSON.parse(fs.readFileSync(path.join(path.dirname(axePath),'package.json'),'utf8'));
  if(axePkg.version!=='4.14.0')throw Error('Expected axe-core 4.14.0, got '+axePkg.version);
  const sha=spawnSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'});
  report.sourceSHA=sha.stdout.trim();
  const playwright=playwrightModule();
  const payload=fixture();
  report.toolchain={axe:axePkg.version,chromium:await playwright.chromium.executablePath(),
    node:process.version,python:'3.12+',fixture:'RIAL, one issued unpaid invoice and one unposted draft'};
  const {build,preview}=await import('vite');
  await build({root,logLevel:'error'});
  const port=await freePort();
  const server=await preview({root,logLevel:'error',preview:{host:'127.0.0.1',port,strictPort:true}});
  let browser;
  const origin=server.resolvedUrls.local[0];
  const start=async(width,theme,role='admin')=>{
    const context=await browser.newContext({viewport:{width,height:850},locale:'fa-IR',
      timezoneId:'Asia/Tehran',reducedMotion:'reduce',colorScheme:theme});
    const cap=role==='admin'?{canManage:true,canDraft:true,canAdmin:true}:
      role==='editor'?{canManage:false,canDraft:true,canAdmin:false}:
      {canManage:false,canDraft:false,canAdmin:false};
    await context.addInitScript(({payload,cap,theme,role})=>{
      window.localStorage.setItem('madar-ui-theme',theme);
      window.__uxqaCalls=[];
      window.madar={
        standaloneAccountingRead:async()=>structuredClone({...payload,capabilities:cap,
          currentUser:{username:'uxqa-'+role,role,jobTitle:'آزمون رابط'}}),
        standaloneAccountingCommand:async request=>{
          window.__uxqaCalls.push(request);
          throw Error('UX QA fixture blocks all persisted accounting mutations');
        }
      };
    },{payload,cap,theme,role});
    const page=await context.newPage();
    const errors=[];
    page.on('pageerror',error=>errors.push(errorText(error)));
    const http=await page.goto(new URL('accounting.html',origin).href,
      {waitUntil:'domcontentloaded',timeout:30000});
    if(http.status()!==200)throw Error('Vite accounting page HTTP '+http.status());
    await page.locator('.sac-root').waitFor({state:'visible',timeout:20000});
    await page.locator('.sac-simple-nav button[data-accounting-tab]').first().waitFor({state:'visible',timeout:9000});
    await page.waitForFunction(()=>!document.querySelector('.sac-alert')?.textContent?.includes('دریافت داده دفترکل'),null,{timeout:9000}).catch(()=>{});
    return {context,page,errors};
  };
  const nav=async(page,key)=>{
    await page.keyboard.press('Control+k');
    const dialog=page.getByRole('dialog',{name:'جست‌وجوی حسابداری'});
    await dialog.waitFor({state:'visible',timeout:3500});
    const input=dialog.getByRole('combobox',{name:/جست‌وجوی بخش/});
    if(!await input.evaluate(el=>el===document.activeElement))
      throw Error('Ctrl+K failed to focus search combobox');
    await input.fill(key);
    const options=dialog.getByRole('option');
    const count=await options.count();
    if(!count)throw Error('No authorized search result for '+key);
    const exact=options.filter({hasText:key});
    if(await exact.count())await exact.first().click();
    else await page.keyboard.press('Enter');
    await dialog.waitFor({state:'hidden',timeout:3500});
    return (await page.locator('.sac-header h1').textContent()).trim();
  };
  const tabNav=async(page,key)=>{
    const target=page.locator('.sac-simple-nav [data-accounting-tab="'+key+'"]');
    if(await target.isVisible().catch(()=>false)){await target.click();return 1;}
    const more=page.locator('.sac-simple-nav [data-accounting-action="more"]');
    await more.click();
    const item=page.locator('.sac-nav-more-menu [data-accounting-tab="'+key+'"]');
    await item.click({timeout:3500});return 2;
  };
  const openInvoice=async page=>{
    // 390/560 mobile intentionally hides the quick-action row; the actionable
    // home card is the primary one-tap route. The desktop quick button remains.
    const quick=page.locator('.sac-nav-quick-actions [data-accounting-action="invoice"]');
    if(await quick.isVisible().catch(()=>false))await quick.click();
    else if(await page.locator('.sac-ah-action.sac-ah-sale').isVisible().catch(()=>false))
      await page.locator('.sac-ah-action.sac-ah-sale').click();
    else{
      await tabNav(page,'invoice');
      await page.locator('.sac-workflow-actions button.sac-primary').click({timeout:4000});
    }
    await page.locator('.sac-invoice-editor').waitFor({state:'visible',timeout:4500});
  };
  const homeActionPaths=[
    {id:'sale',tab:'invoice',expect:'فاکتورهای فروش',composer:true},
    {id:'purchase',tab:'bill',expect:'صورتحساب‌های خرید'},
    {id:'receipt',tab:'settlements',expect:'دریافت، پرداخت و اقساط'},
    {id:'payment',tab:'settlements',expect:'دریافت، پرداخت و اقساط'},
    {id:'reconcile',tab:'cash',expect:'صندوق، بانک و مغایرت'},
    {id:'reports',tab:'reports',expect:'گزارش‌های مالی'}
  ];
  const verifyHomePaths=async(page,scope)=>{
    for(const route of homeActionPaths){
      try{
        await page.locator('.sac-ah-action.sac-ah-'+route.id).click({timeout:3500});
        const heading=(await page.locator('.sac-header h1').textContent()).trim();
        const composer=await page.locator('.sac-invoice-editor').isVisible();
        add('UX-03',heading===route.expect&&(!route.composer||composer)?'PASS':'FAIL',
          'Quick action home workflow uses one visible click',
          {scope,action:route.id,actions:1,heading,composer});
      }catch(error){
        add('UX-03','FAIL','Quick action home workflow cannot reach destination',
          {scope,action:route.id,error:errorText(error)});
      }finally{
        try{await tabNav(page,'overview');}catch(error){
          add('UX-03','BLOCKED','Cannot return to synthetic action home',
            {scope,action:route.id,error:errorText(error)});
        }
      }
    }
  };
  const verifyWizard=async(page,scope)=>{
    const wizard=page.locator('.sac-wizard-step-nav');
    if(!await wizard.isVisible())return {status:'MISSING',reason:'Guided five-stage invoice navigation not rendered'};
    const steps=await wizard.locator('button').count();
    if(steps!==5)return {status:'FAIL',reason:'Wizard does not expose exactly five stages',steps};
    const auditStage=async(stage)=>{
      const stageScope=scope+'/wizard/'+stage;
      const metrics=await page.evaluate(pageMetrics);
      const scan=await axeScan(page);
      const axeResult=assessAxe(scan);
      add('UX-02',axeResult.status,axeResult.reason,{scope:stageScope,
        severe:axeResult.severe,incomplete:axeResult.incomplete});
      const colorViolations=scan.violations.filter(v=>v.id==='color-contrast');
      const renderedLabels=await resolveRenderedContrast(page,metrics.labels);
      const contrast=assessContrast(renderedLabels);
      add('UX-01',colorViolations.length?'FAIL':contrast.status,
        colorViolations.length?'axe-core found text color contrast violations':contrast.reason,
        {scope:stageScope,colorViolations,measuredSamples:renderedLabels.length,
          rasterSamples:renderedLabels.filter(item=>item.method==='rendered-glyph-pixels').length,
          unresolved:contrast.unresolved,failures:contrast.failures,
          rendered:renderedLabels});
      const touch=assessTouch(metrics.targets);
      add('UX-06',touch.status,touch.reason,{scope:stageScope,count:touch.measured,
        failures:touch.failures?.slice(0,12)});
      add('UX-07',metrics.horizontalOverflow?'FAIL':'PASS',
        metrics.horizontalOverflow?'Wizard stage causes page overflow':
          'Wizard stage fits viewport width',{scope:stageScope,
          scrollWidth:metrics.pageScrollWidth,viewport:metrics.viewport});
      add('UX-05',metrics.saveVisibleInViewport?'PASS':'FAIL',
        'Active guided wizard step action must remain visible in viewport',
        {scope:stageScope,activeActionNames:metrics.activeActionNames,
          wizardStep:metrics.wizardStep});
    };
    const id=page.locator('#sac-wizard-panel-document input[dir="ltr"]').first();
    await id.fill('UX-DRAFT-UNSAVED');
    const customer=page.locator('#sac-wizard-panel-document select').first();
    await customer.selectOption({index:1});
    const actions=page.locator('.sac-wizard-sticky-actions');
    const next=async()=>{
      await actions.locator('button.sac-primary').click();
      await page.waitForTimeout(50);
    };
    await next();
    const active=()=>wizard.locator('[aria-current="step"]').textContent();
    if(!String(await active()).includes('اقلام'))return {status:'FAIL',reason:'Did not advance to line items after valid document'};
    await auditStage('lines');
    await page.locator('#sac-wizard-panel-lines [data-invoice-col="0"]').first().fill('UX QATEST SERVICE');
    await page.locator('#sac-wizard-panel-lines [data-invoice-col="2"]').first().fill('97500');
    await next();
    if(!String(await active()).includes('مالیات'))return {status:'FAIL',reason:'Did not advance to tax step after valid line'};
    await auditStage('tax');
    await next();
    if(!String(await active()).includes('پرداخت'))return {status:'FAIL',reason:'Did not advance to due/payment step'};
    await auditStage('due');
    await next();
    if(!String(await active()).includes('مرور'))return {status:'FAIL',reason:'Did not reach review/save step'};
    await auditStage('review');
    const warning=await page.locator('.sac-wizard-impact-warning').isVisible();
    const reviewSave=await page.locator('.sac-wizard-sticky-actions button[type=submit]').isVisible();
    // Returning across steps must leave the exact line and header untouched.
    await wizard.locator('button').nth(1).click();
    const line=await page.locator('#sac-wizard-panel-lines [data-invoice-col="0"]').first().inputValue();
    await wizard.locator('button').first().click();
    const preserved=await id.inputValue();
    const selected=await customer.inputValue();
    const noCalls=await page.evaluate(()=>window.__uxqaCalls.length===0);
    return {status:warning&&reviewSave&&line==='UX QATEST SERVICE'&&
      preserved==='UX-DRAFT-UNSAVED'&&!!selected&&noCalls?'PASS':'FAIL',
    reason:'Five-stage guided invoice; financial warning, review save and persistence across steps',
    steps,warning,reviewSave,line,preserved,selected,noCalls};
  };
  const keyboardOperate=async(page,selector,{activate=false}={})=>{
    // Close the modal first; its focus trap deliberately prevents Tab from
    // reaching application controls. Then navigate with keyboard Tab.
    const dialog=page.getByRole('dialog',{name:'جست‌وجوی حسابداری'});
    if(await dialog.count())await page.keyboard.press('Escape');
    await page.locator('[data-accounting-action="search"]').first().focus();
    let found=false,tabs=0;
    for(let index=0;index<100;index++){
      await page.keyboard.press('Tab');
      tabs=index+1;
      found=await page.evaluate(css=>{
        const el=document.activeElement;
        return !!el?.matches(css)&&!!el.getClientRects().length&&!el.disabled;
      },selector);
      if(found)break;
    }
    if(!found)return {success:false,tabs,reason:'Tab focus never reached workflow control'};
    const before=await page.evaluate(()=>({tag:document.activeElement.tagName,
      value:document.activeElement.value||'',type:document.activeElement.type||''}));
    if(activate){
      await page.keyboard.press('Enter');
      return {success:await page.locator('.sac-invoice-editor').isVisible().catch(()=>false),
        tabs,before,action:'Enter opens invoice editor'};
    }
    if(before.tag==='INPUT'&&!['date','number','checkbox','radio'].includes(before.type)){
      await page.keyboard.type('UX');
      const after=await page.evaluate(()=>document.activeElement.value);
      return {success:after.includes('UX'),tabs,before,after,action:'typed into focused field'};
    }
    if(before.tag==='SELECT'){
      await page.keyboard.press('ArrowDown');
      const after=await page.evaluate(()=>document.activeElement.value);
      return {success:true,tabs,before,after,action:'keyboard operated focused select'};
    }
    return {success:false,tabs,before,reason:'Focused control has no safe keyboard edit action'};
  };
  try{
    browser=await playwright.chromium.launch({channel:'msedge',headless:true});
    report.toolchain.browser=browser.version();
    for(const theme of themes)for(const width of widths){
      const scope=theme+'/'+width;
      let session;
      try{
        session=await start(width,theme);
        const {page,errors}=session;
        const overview=await page.evaluate(pageMetrics);
        const overviewAxe=await axeScan(page);
        const overviewContrast=await resolveRenderedContrast(page,overview.labels);
        // Advanced Ribbon remains available on desktop; compact mobile
        // deliberately retains More instead of rendering a second wide row.
        await page.locator('.sac-nav-mode').getByRole('button',{name:'پیشرفته'}).click();
        const advancedRibbon=await page.locator('.sac-advanced-ribbon .sac-ribbon-tabs').isVisible();
        const mobileMore=await page.locator('.sac-simple-nav [data-accounting-action="more"]').isVisible();
        add('UX-07',(width>=768?advancedRibbon:mobileMore)?'PASS':'FAIL',
          'Advanced navigation is usable on desktop and compact More remains on mobile',
          {scope,advancedRibbon,mobileMore});
        await page.locator('.sac-nav-mode').getByRole('button',{name:'ساده'}).click();
        await verifyHomePaths(page,scope);
        await openInvoice(page);
        const composer=await page.evaluate(pageMetrics);
        const composerAxe=await axeScan(page);
        const composerContrast=await resolveRenderedContrast(page,composer.labels);
        const scrollInfo=await page.evaluate(()=>{
          const body=document.querySelector('.sac-body');
          const before=body?.scrollTop||0;
          const middle=body?Math.max(0,(body.scrollHeight-body.clientHeight)/2):0;
          if(body)body.scrollTop=middle;
          return {before,middle,afterMiddle:body?.scrollTop||0,
            scrollHeight:body?.scrollHeight||0,clientHeight:body?.clientHeight||0};
        });
        await page.waitForTimeout(80);
        const composerMidScroll=await page.evaluate(pageMetrics);
        await page.evaluate(()=>{
          const body=document.querySelector('.sac-body');
          if(body)body.scrollTop=body.scrollHeight;
          window.scrollTo(0,document.documentElement.scrollHeight);
        });
        await page.waitForTimeout(80);
        const composerAfterScroll=await page.evaluate(pageMetrics);
        const entry={scope,overview,composer,composerMidScroll,composerAfterScroll,scrollInfo,
          contrast:{overview:overviewContrast,composer:composerContrast},
          axe:{overview:overviewAxe,composer:composerAxe},errors};
        report.matrix.push(entry);
        for(const [screen,measured,scan] of [['overview',overview,overviewAxe],['composer',composer,composerAxe]]){
          const sample=scope+'/'+screen;
          const axeResult=assessAxe(scan);
          add('UX-02',axeResult.status,axeResult.reason,{scope:sample,
            severe:axeResult.severe,incomplete:axeResult.incomplete});
          const colorViolations=scan.violations.filter(v=>v.id==='color-contrast');
          if(colorViolations.length)add('UX-01','FAIL',
            'axe-core 4.14.0 found actual text contrast violations',
            {scope:sample,colorViolations});
          if(measured.horizontalOverflow)add('UX-07','FAIL','Page-level horizontal overflow',{scope:sample,
            pageScrollWidth:measured.pageScrollWidth,viewport:width});
          else add('UX-07','PASS','No page-level horizontal overflow',{scope:sample});
          const touch=assessTouch(measured.targets);
          add('UX-06',touch.status,touch.reason,{scope:sample,
            count:touch.measured,failures:touch.failures?.slice(0,16)});
        }
        const contrast=assessContrast([...overviewContrast,...composerContrast]);
        add('UX-01',contrast.status,contrast.reason,{scope,samples:contrast.sampleCount,
          rendered:overviewContrast.concat(composerContrast),
          failures:contrast.failures,unresolved:contrast.unresolved});
        if(composer.invoiceForm&&composer.saveVisibleInViewport&&
          composerMidScroll.saveVisibleInViewport&&composerAfterScroll.saveVisibleInViewport&&
          composer.composerActionCount>=1)
          add('UX-05','PASS','Active invoice step action visible at start, middle and end of scroll',{scope,
            actions:composer.activeActionNames,scrollInfo});
        else add('UX-05','FAIL','Invoice form action or save bar not visible without scrolling',{
          scope,invoiceForm:composer.invoiceForm,
          initialVisible:composer.saveVisibleInViewport,
          middleVisible:composerMidScroll.saveVisibleInViewport,
          afterScrollVisible:composerAfterScroll.saveVisibleInViewport,
          actions:composer.activeActionNames,scrollInfo});
        if(overview.actionableOverview)add('UX-04','PASS','Outstanding receivable has visible action context',{scope});
        else add('UX-04','FAIL','Outstanding synthetic issued receivable is not surfaced as receivable',{scope,
          excerpt:overview.dueSectionText});
        const simple=await page.locator('.sac-ux-simple .sac-simple-nav').isVisible();
        const more=page.locator('.sac-simple-nav [data-accounting-action="more"]');
        const moreVisible=await more.isVisible();
        add('UX-07',simple&&moreVisible?'PASS':'FAIL',
          'Mobile simple navigation requires a visible More control and no horizontal page overflow',
          {scope,simple,moreVisible,scrolls:overview.scrollables.filter(s=>s.overflow)});
        if(width===390||width===1440){
          const name='invoice-'+theme+'-'+width+'.png';
          await page.screenshot({path:path.join(outDir,name),animations:'disabled'});
          entry.screenshot=name;
        }
        try{
          const outcome=await verifyWizard(page,scope);
          add('UX-05',outcome.status,outcome.reason,{scope:scope+'/wizard',...outcome});
          add('UX-09',outcome.status,outcome.reason,{scope:scope+'/wizard',...outcome});
        }catch(error){
          add('UX-05','FAIL','Guided wizard navigation or state preservation failed',
            {scope:scope+'/wizard',error:errorText(error)});
          add('UX-09','FAIL','Guided wizard navigation or review warning failed',
            {scope:scope+'/wizard',error:errorText(error)});
          add('UX-01','BLOCKED','Guided invoice stages not completely contrast-audited',
            {scope:scope+'/wizard',error:errorText(error)});
          add('UX-02','BLOCKED','Guided wizard step scans stopped before all four stages',
            {scope:scope+'/wizard',error:errorText(error)});
        }
        if(errors.length)add('UX-10','FAIL','Uncaught JS exceptions while rendering',{scope,errors});
      }catch(error){
        const reason=errorText(error);
        report.errors.push({scope,error:reason});
        for(const id of ['UX-01','UX-02','UX-04','UX-05','UX-06','UX-07'])
          add(id,'BLOCKED','Browser checkpoint did not complete: '+reason,{scope});
      }finally{if(session)await session.context.close();}
    }
    const session=await start(1440,'dark','admin');
    try{
      const {page}=session;
      const goals=[
        {name:'invoice',query:'فاکتورهای فروش',expect:'فاکتورهای فروش'},
        {name:'purchase',query:'صورتحساب‌های خرید',expect:'صورتحساب‌های خرید'},
        {name:'receipts',query:'دریافت، پرداخت',expect:'دریافت، پرداخت و اقساط'},
        {name:'ledger',query:'حساب‌ها و دفترکل',expect:'حساب‌ها و دفترکل'},
        {name:'reports',query:'گزارش‌های مالی',expect:'گزارش‌های مالی'}
      ];
      for(const goal of goals){
        try{
          const label=await nav(page,goal.query);
          add('UX-03',label===goal.expect?'PASS':'FAIL',
            label===goal.expect?'Keyboard route within two navigation actions':
              'Unexpected route after keyboard search',{goal:goal.name,result:label,actions:2});
          add('UX-08',label===goal.expect?'PASS':'FAIL',
            label===goal.expect?'Global section keyboard route reached intended page':
              'Global section shortcut did not reach page',{goal:goal.name,result:label});
        }catch(error){
          add('UX-03','FAIL','Cannot reach novice target through keyboard route',{goal:goal.name,error:errorText(error)});
          add('UX-08','FAIL','Keyboard workflow failed',{goal:goal.name,error:errorText(error)});
        }
      }
      // Five actual keyboard interaction checkpoints, following keyboard
      // navigation. These do not assert persistence or ledger acceptance.
      for(const goal of [
        {name:'invoice-draft',query:'فاکتورهای فروش',selector:
          '.sac-nav-quick-actions [data-accounting-action="invoice"]',activate:true},
        {name:'purchase-draft',query:'صورتحساب‌های خرید',selector:
          '.sac-invoice-editor input[dir="ltr"]:not([readonly])'},
        {name:'receipt-entry',query:'دریافت، پرداخت',selector:
          '.sac-body form input:not([readonly]):not([disabled]):not([type="hidden"])'},
        {name:'ledger-filter',query:'حساب‌ها و دفترکل',selector:
          '.sac-body input:not([readonly]):not([disabled]):not([type="hidden"])'},
        {name:'report-filter',query:'گزارش‌های مالی',selector:
          '.sac-body input:not([readonly]):not([disabled]):not([type="hidden"]),.sac-body select:not([disabled])'}
      ]){
        if(goal.name==='report-filter'&&!payload.view.financialReports){
          add('UX-08','BLOCKED',
            'Synthetic accounting_core view has no financialReports payload; report input controls are intentionally not rendered',
            {goal:goal.name,fixtureMissing:'view.financialReports'});
          continue;
        }
        try{
          await nav(page,goal.query);
          const result=await keyboardOperate(page,goal.selector,{activate:goal.activate});
          add('UX-08',result.success?'PASS':'FAIL',
            result.success?'Tab and keyboard operated a real workflow control':
              'Workflow control inaccessible or inoperable via keyboard',
            {goal:goal.name,...result});
          if(goal.activate&&result.success){
            // Cancel without editing; subsequent tasks start from clean UI.
            await nav(page,'داشبورد');
          }
        }catch(error){
          add('UX-08','FAIL','Keyboard workflow action failed',
            {goal:goal.name,error:errorText(error)});
        }
      }
      // Measured novice click paths: visible simple nav and expandable More.
      const novice=[
        {name:'invoice',id:'invoice',label:'فاکتورهای فروش'},
        {name:'purchase',id:'bill',label:'صورتحساب‌های خرید'},
        {name:'receipts',id:'settlements',label:'دریافت، پرداخت و اقساط'},
        {name:'reconciliation',id:'cash',label:'صندوق، بانک و مغایرت'},
        {name:'reports',id:'reports',label:'گزارش‌های مالی'}
      ];
      for(const route of novice){
        try{
          const actions=await tabNav(page,route.id);
          const actual=(await page.locator('.sac-header h1').textContent()).trim();
          add('UX-03',actual===route.label&&actions<=2?'PASS':'FAIL',
            'Novice route via one or two visible menu actions',{goal:route.name,
              actions,result:actual});
        }catch(error){
          add('UX-03','FAIL','Novice navigation target not reachable in two actions',
            {goal:route.name,error:errorText(error)});
        }
      }
      await page.keyboard.press('Control+k');
      const guide=await page.locator('.sac-global-search-footer').filter({hasText:'Esc'}).count();
      await page.keyboard.press('Escape');
      add('UX-08',guide?'PASS':'MISSING',guide?'Keyboard guidance accessible':
        'Keyboard shortcut/help guide control not found');
      await page.keyboard.press('Control+k');
      const searchDialog=page.getByRole('dialog',{name:'جست‌وجوی حسابداری'});
      const searchInput=searchDialog.getByRole('combobox');
      await searchInput.fill('UX-ISSUED-001');
      const invoiceMatches=await searchDialog.getByRole('option').allTextContents();
      await searchInput.fill('CUSTOMER-UX');
      const partyMatches=await searchDialog.getByRole('option').allTextContents();
      await page.keyboard.press('Escape');
      const recordSearch=invoiceMatches.some(x=>x.includes('UX-ISSUED-001'))&&
        partyMatches.some(x=>x.includes('CUSTOMER-UX')||x.includes('مشتری آزمایشی'));
      add('UX-08',recordSearch?'PASS':'MISSING',recordSearch?
        'Global search retrieved synthetic invoice and customer by ID':
        'Global search did not retrieve both authorized invoice ID and customer ID',
        {invoiceMatches,partyMatches});
      await page.locator('.sac-simple-nav [data-accounting-action="more"]').click();
      const routeIds=await page.locator('.sac-simple-nav button[data-accounting-tab],'+
        '.sac-nav-more-menu button[data-accounting-tab]')
        .evaluateAll(buttons=>buttons.map(el=>({
        id:el.getAttribute('data-route-id')||el.getAttribute('data-ux-route')||
          el.getAttribute('data-accounting-tab')||el.getAttribute('data-tab-id')||
          el.getAttribute('aria-controls'),
        text:(el.textContent||'').trim().slice(0,35)})));
      const unique=routeIds.length===18&&routeIds.every(item=>item.id)&&
        new Set(routeIds.map(item=>item.id)).size===routeIds.length;
      add('UX-10',unique?'PASS':'MISSING',unique?'Navigation uses unique stable route identifiers':
        'Navigation lacks stable route identifiers; tests would rely on display strings',
        {total:routeIds.length,withoutId:routeIds.filter(item=>!item.id).slice(0,8)});
      await page.locator('.sac-simple-nav [data-accounting-action="more"]').click();
      try{
        await nav(page,'فاکتورهای فروش');
        const statuses=[];
        for(const item of [{id:'UX-DRAFT-002',kind:'draft'},
          {id:'UX-ISSUED-001',kind:'issued'}]){
          const row=page.locator('tr').filter({hasText:item.id}).first();
          await row.waitFor({state:'visible',timeout:3500});
          const text=(await row.innerText()).trim();
          const actions=await row.locator('button').allTextContents();
          const actionText=actions.join(' ');
          const valid=item.kind==='draft'?
            /تأیید/.test(actionText)&&/ویرایش/.test(actionText)&&!/تسویه|صدور سند/.test(actionText):
            /تسویه/.test(actionText)&&!/تأیید|ویرایش پیش‌نویس|صدور سند/.test(actionText);
          statuses.push({id:item.id,kind:item.kind,text:text.slice(0,160),actions,valid});
        }
        add('UX-09',statuses.every(x=>x.valid)?'PASS':'FAIL',
          'Document actions must match draft versus issued status without implicit posting',
          {statuses});
      }catch(error){
        add('UX-09','BLOCKED','Status-dependent actions not verified: '+errorText(error));
      }
      // Actual novice use: one quick action opens an editable invoice, then
      // changed data must remain if an attempted navigation is cancelled.
      await openInvoice(page);
      await page.locator('.sac-invoice-editor').waitFor();
      const rowInput=page.locator('.sac-invoice-editor input').filter({visible:true});
      const draftInput=page.locator('.sac-invoice-editor input[dir=ltr]').first();
      await draftInput.fill('UX-DRAFT-UNSAVED');
      const details=page.locator('.sac-invoice-editor details.sac-disclosure').first();
      if(await details.isVisible())await details.locator('summary').click();
      const stillEdited=await draftInput.inputValue().catch(()=>null);
      add('UX-05',stillEdited==='UX-DRAFT-UNSAVED'?'PASS':'FAIL',
        'Expanding optional invoice details must not reset unsaved form values',
        {preserved:stillEdited});
      let dialogs=0;
      page.on('dialog',async dialog=>{dialogs++;await dialog.dismiss();});
      await nav(page,'گزارش‌های مالی');
      const preserved=await page.locator('.sac-invoice-editor input[dir=ltr]').first()
        .inputValue({timeout:900}).catch(()=>null);
      add('UX-09',dialogs>0&&preserved==='UX-DRAFT-UNSAVED'?'PASS':'FAIL',
        dialogs>0?'Unsaved form retains values when user rejects navigation':
          'No user-facing unsaved draft confirmation before leaving',
        {dialogs,preserved});
      add('UX-05',dialogs>0&&preserved==='UX-DRAFT-UNSAVED'?'PASS':'FAIL',
        'Unsaved invoice data must survive cancelled navigation',{dialogs,preserved});
      const noMutation=await page.evaluate(()=>window.__uxqaCalls.length===0);
      add('UX-09',noMutation?'PASS':'FAIL',
        noMutation?'Unsaved draft navigation did not invoke accounting mutations':
          'Unexpected accounting mutation attempt',{count:await page.evaluate(()=>window.__uxqaCalls.length)});
    }catch(error){
      report.errors.push({scope:'desktop/admin-workflows',error:errorText(error)});
      for(const id of ['UX-03','UX-08','UX-09','UX-10'])
        add(id,'BLOCKED','Keyboard/guide/draft scenario did not complete: '+errorText(error));
    }finally{await session.context.close();}
    for(const role of ['viewer','editor']){
      const restricted=await start(1440,'dark',role);
      try{
        const {page}=restricted;
        const newInvoice=await page.locator('.sac-nav-quick-actions [data-accounting-action="invoice"]').count();
        add('UX-08',(role==='viewer'?newInvoice===0:newInvoice>0)?'PASS':'FAIL',
          'Quick-create permission matches synthetic UI capability',{role,newInvoice});
        await nav(page,'فاکتورهای فروش');
        const issue=await page.getByRole('button',{name:/^صدور فاکتور$|^تأیید فاکتور$/}).count();
        add('UX-08',issue===0?'PASS':'FAIL','Viewer/editor cannot issue or approve without management grant',
          {role,issueCount:issue});
        await page.keyboard.press('Control+k');
        const searchDialog=page.getByRole('dialog',{name:'جست‌وجوی حسابداری'});
        const searchInput=searchDialog.getByRole('combobox');
        const guide=await searchDialog.locator('.sac-global-search-footer').filter({hasText:'Esc'}).count();
        await searchInput.fill('مهاجرت');
        const privateOptions=await searchDialog.getByRole('option').allTextContents();
        add('UX-08',privateOptions.length===0?'PASS':'FAIL',
          'Non-admin search does not reveal admin-only migration navigation',
          {role,privateOptions});
        await page.keyboard.press('Escape');
        add('UX-08',guide?'PASS':'FAIL',guide?
          'Keyboard search help visible for restricted role':
          'Keyboard search help missing for restricted role',{role});
        if(role==='editor'){
          await tabNav(page,'overview');
          await openInvoice(page);
          const wizard=await page.locator('.sac-wizard-step-nav button').count();
          add('UX-09',wizard===5?'PASS':'MISSING',
            wizard===5?'Editor has five-stage novice draft guide':'Editor draft guide unavailable',
            {role,steps:wizard});
        }else add('UX-09',newInvoice===0?'PASS':'FAIL',
          'Read-only viewer is not offered draft creation',{role});
      }catch(error){
        add('UX-08','BLOCKED','Restricted role search/navigation scenario failed: '+errorText(error),{role});
      }finally{await restricted.context.close();}
    }
    // Subset runs are useful for diagnosis, never evidence of full 8-scope
    // acceptance. Explicitly report every missing viewport/theme as blocked.
    const seen=new Set(report.matrix.map(entry=>entry.scope));
    for(const theme of ['dark','light'])for(const width of [390,560,768,1440]){
      const scope=theme+'/'+width;
      if(seen.has(scope))continue;
      for(const id of ['UX-01','UX-02','UX-06'])
        add(id,'BLOCKED','Viewport/theme intentionally not measured in this run',
          {scope,requestedWidths:widths,requestedThemes:themes});
    }
    report.limitations.push('Synthetic JS capability flags test UI only; server ACL, host persistence, and real user-role data filtering were not exercised.');
    report.limitations.push('axe incomplete and calculated foreground/background ambiguity require human review; no claim of full WCAG compliance.');
  }finally{
    if(browser)await browser.close();
    await new Promise(resolve=>server.httpServer.close(resolve));
  }
}

if(require.main===module)(async()=>{
  try{await main();}
  catch(error){report.errors.push({scope:'harness',error:errorText(error)});
    for(const id of ['UX-01','UX-02','UX-03','UX-04','UX-05','UX-06','UX-07','UX-08','UX-09','UX-10'])
      add(id,'BLOCKED','Harness could not fully execute: '+errorText(error));}
  finally{save();if(report.summary.overall!=='PASS')process.exitCode=1;}
})();

module.exports={measureRenderedContrast,resolveRenderedContrast,pageMetrics};
