// Render the approved Madar SVG through Chromium so its Illustrator SVG filters
// remain consistent in the Windows icon and PNG derivatives.
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const globalPlaywright = path.join(process.env.APPDATA || '', 'npm', 'node_modules', 'playwright');
let chromium;
try {
  ({chromium} = require('playwright'));
} catch (_) {
  ({chromium} = require(globalPlaywright));
}

(async () => {
  const svg = fs.readFileSync(path.join(root, 'assets', 'madar-final.svg'), 'utf8');
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1024,height:1024},deviceScaleFactor:1});
    await page.setContent('<!doctype html><html><style>*{margin:0;padding:0}body{background:transparent}svg{display:block;width:1024px;height:1024px}</style><body>' + svg + '</body></html>');
    await page.locator('svg').screenshot({path:path.join(root,'public','madar-icon-1024.png'),omitBackground:true});
    await page.close();
  } finally {
    await browser.close();
  }
})().catch((error) => {console.error(error);process.exitCode=1;});
