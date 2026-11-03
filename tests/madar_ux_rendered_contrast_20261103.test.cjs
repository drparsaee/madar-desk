'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const {measureRenderedContrast,resolveRenderedContrast,pageMetrics}=
  require('../scripts/madar_ux_completion_audit_20261103.cjs');

const playwright=process.env.MADAR_UXQA_PLAYWRIGHT||
  path.join(process.env.APPDATA||'','npm','node_modules','playwright');

test('actual Chromium glyph-background raster: gradients, overlays, alpha, scrolling and fail-closed cases',
  {timeout:90000},async t=>{
    const {chromium}=require(playwright);
    const browser=await chromium.launch({channel:'msedge',headless:true});
    try{
      const page=await browser.newPage({viewport:{width:390,height:600},
        reducedMotion:'reduce',deviceScaleFactor:1});
      const setup=async (css,text='رابط حسابداری آزمایشی ۱۲۳۴۵۶ lorem ipsum test')=>{
        await page.setContent(`<html><head><style>
          *{box-sizing:border-box}html,body{margin:0;}
          body{font-family:Arial,sans-serif;min-height:100%;background:white}
          #target{display:block;padding:12px;font-size:18px;font-weight:700;
            width:340px;line-height:1.4;margin:45px 20px;${css}}
          </style></head><body><div id="target"
          data-uxqa-contrast-id="r1">${text}</div></body></html>`);
        await page.evaluate(()=>document.fonts.ready);
      };
      await setup('color:white;background:linear-gradient(90deg,#161616,#303030)');
      const darkGradient=await measureRenderedContrast(page,'r1');
      assert.ok(darkGradient.ratio>=4.5,JSON.stringify(darkGradient));
      assert.ok(darkGradient.glyphPixels>=8);
      assert.ok(darkGradient.backgroundLuminanceRange[1]>
        darkGradient.backgroundLuminanceRange[0],
      'Gradient must actually vary beneath painted glyphs');

      await setup('color:white;background:linear-gradient(90deg,#111 0%,#fff 100%)');
      const brokenGradient=await measureRenderedContrast(page,'r1');
      assert.ok(Number.isFinite(brokenGradient.ratio),JSON.stringify(brokenGradient));
      assert.ok(brokenGradient.ratio<4.5,
        'Worst-case gradient must fail even when its dark half passes');

      await page.setContent(`<style>
        body{margin:0;font:700 18px Arial;background:linear-gradient(90deg,#222,#444)}
        #overlay{background:rgba(255,255,255,.85);padding:20px;margin:45px 20px;width:340px}
        #target{color:#050505}</style>
        <section id="overlay"><span id="target" data-uxqa-contrast-id="r1">Overlay text contrast</span></section>`);
      const overlay=await measureRenderedContrast(page,'r1');
      assert.ok(overlay.ratio>=4.5,JSON.stringify(overlay));

      await setup('color:rgba(0,0,0,.20);background:#fff');
      const translucentInk=await measureRenderedContrast(page,'r1');
      assert.ok(Number.isFinite(translucentInk.ratio),JSON.stringify(translucentInk));
      assert.ok(translucentInk.ratio<4.5,
        'A low-alpha foreground on white must fail after compositing');

      await page.setContent(`<style>
        body{margin:0;background:#fff;font:16px Arial}
        .scroller{height:120px;overflow:auto}
        #target{background:#fff;color:#000;padding:12px}
        </style><div class="scroller"><div style="height:900px"></div><p id="target"
        data-uxqa-contrast-id="r1">Far down inside a nested scroll container</p></div>`);
      const scrolled=await measureRenderedContrast(page,'r1');
      assert.ok(scrolled.ratio>=4.5,JSON.stringify(scrolled));
      assert.ok(await page.locator('.scroller').evaluate(el=>el.scrollTop)>0,
        'The helper must scroll hidden-offscreen text into view');

      // At the exact 768px breakpoint, re-centring an already visible sticky
      // caption shifts its scroll container and can change its pixels between
      // the before and restored shots. This was the stage-5 r68 regression.
      await page.setViewportSize({width:768,height:850});
      await page.setContent(`<style>
        body{margin:0;background:#fff;font:16px Arial}
        .scrollport{height:720px;overflow:auto;background:#fff}
        .sticky{position:sticky;bottom:0;display:block;width:300px;
          background:#1d2532;color:#e1edf8;padding:10px}
        </style><div class="scrollport"><div style="height:590px"></div>
        <small class="sticky" data-uxqa-contrast-id="r1">
          پیش‌نویس ذخیره‌نشده · مرحله ۵/۵</small>
        <div style="height:500px"></div></div>`);
      const stickyBefore=await page.locator('.scrollport').evaluate(el=>el.scrollTop);
      const stickyRendered=await measureRenderedContrast(page,'r1');
      assert.ok(stickyRendered.ratio>=4.5,JSON.stringify(stickyRendered));
      assert.equal(await page.locator('.scrollport').evaluate(el=>el.scrollTop),stickyBefore,
        'Already visible, unobstructed sticky footer must not be force-scrolled');

      // An element may fit inside the viewport yet be covered by a sticky
      // overlay. In that case scrolling is still required; no fake PASS.
      await page.setContent(`<style>
        body{margin:0;background:white;font:16px Arial}
        .scrollport{height:520px;overflow:auto;background:white}
        #target{display:block;margin-top:290px;padding:10px;color:black;background:white}
        .overlay{position:fixed;top:290px;left:0;width:768px;height:55px;
          background:#888;z-index:10}
        </style><div class="scrollport"><div id="target"
          data-uxqa-contrast-id="r1">Covered but scrollable label</div>
          <div style="height:720px"></div></div><div class="overlay"></div>`);
      const occludedRendered=await measureRenderedContrast(page,'r1');
      assert.ok(occludedRendered.ratio>=4.5,JSON.stringify(occludedRendered));
      assert.ok(await page.locator('.scrollport').evaluate(el=>el.scrollTop)>0,
        'Visible but occluded text must scroll out from under the overlay');
      await page.setViewportSize({width:390,height:600});

      await setup('color:#111;background:#fff;display:none');
      const hidden=await measureRenderedContrast(page,'r1');
      assert.equal(hidden.ratio,null,'Invisible text cannot silently pass');

      await setup('width:700px;color:#000;background:#fff');
      const oversize=await measureRenderedContrast(page,'r1');
      assert.equal(oversize.ratio,null,'Text extending past viewport must block');

      await setup('color:#000;background:rgba(255,255,255,.5);opacity:.7');
      const grouped=await measureRenderedContrast(page,'r1');
      assert.equal(grouped.ratio,null,'Group opacity needs distinct paint math and must block');

      await setup('color:#fff;background:#111');
      let shot=0;
      const originalScreenshot=page.screenshot.bind(page);
      page.screenshot=async args=>{
        shot++;
        if(shot===2)throw Error('synthetic screenshot failure');
        return originalScreenshot(args);
      };
      const failedCapture=await measureRenderedContrast(page,'r1');
      assert.equal(failedCapture.ratio,null,'Screenshot failure must never count as pass');
      assert.match(failedCapture.reason,/synthetic screenshot failure/);
      assert.equal(await page.locator('#uxqa-text-only-mask').count(),0,
        'Paint mask must be removed when second screenshot fails');
      page.screenshot=originalScreenshot;

      await page.setContent(`<style>
        body{margin:0;background:#111;color:#fff;font:700 18px Arial}
        #target{margin:45px 20px;padding:10px}
        </style><div id="target" data-uxqa-contrast-id="r1">Unstable painted backdrop</div>`);
      shot=0;
      page.screenshot=async args=>{
        if(++shot===3)await page.evaluate(()=>{document.body.style.background='#fff';});
        return originalScreenshot(args);
      };
      const movedBackground=await measureRenderedContrast(page,'r1');
      assert.equal(movedBackground.ratio,null,
        'Background changes between capture and paint restoration must block');
      assert.match(movedBackground.reason,/changed after removing text mask/);
      page.screenshot=originalScreenshot;

      await page.setContent(`<style>body{background:white}
        .sac-invoice-editor .sac-field span{color:#333}</style>
        <div class="sac-invoice-editor">
        <label class="sac-field"><span>Visible label</span></label>
        <details><summary>Closed</summary><label class="sac-field">
          <span>Invisible detail label</span></label></details>
        <label class="sac-field"><span style="width:1px;height:1px;display:block">Clipped label</span></label>
        <label class="sac-field"><span class="madar-jalali-field"><input/>
          <small style="color:#333">Jalali hint with distinct ink</small></span></label>
        </div>`);
      const measuredLabels=await page.evaluate(pageMetrics);
      assert.ok(measuredLabels.labels.some(x=>x.text==='Visible label'));
      assert.ok(measuredLabels.labels.some(x=>x.text.includes('Jalali hint')),
        'The actual child foreground of a Jalali hint must be measured');
      assert.ok(!measuredLabels.labels.some(x=>x.text.includes('Invisible detail')),
        'Closed details must not pretend to be rendered text');
      assert.ok(!measuredLabels.labels.some(x=>x.text.includes('Clipped label')),
        'One-pixel placeholders must not count as visible content');

      const absent=await measureRenderedContrast(page,'does-not-exist');
      assert.equal(absent.ratio,null);
      assert.equal(await page.locator('#uxqa-text-only-mask').count(),0,
        'Temporary paint mask must always be restored');

      const resolved=await resolveRenderedContrast(page,[
        {uid:'no-such-id',ratio:null,text:'must block'},
        {uid:'r1',ratio:7.2,text:'opaque known CSS'}]);
      assert.equal(resolved[0].ratio,null);
      assert.equal(resolved[1].ratio,7.2);
      assert.equal(resolved[1].method,'opaque-css-background');
      await page.close();
      t.diagnostic('Raster tests exercised real Chromium screenshot/background pixels; no fictitious pass for unmeasurable samples.');
    }finally{await browser.close();}
  });
