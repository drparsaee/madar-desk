const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../src/accounting_invoice_quick_filter.js'),'utf8')
  .replace(/export /g, '');
const { filterInvoiceRows, invoiceStatusCounts } = new Function(source + 
  '\nreturn {filterInvoiceRows,invoiceStatusCounts};')();

const records = {
  'INV-1': { id:'INV-1', status:'draft', documentDate:'2026-10-01',partyId:'a' },
  'INV-2': { id:'INV-2', status:'issued', documentDate:'2026-10-02',partyId:'b',number:'55' },
  'INV-3': { id:'INV-3', status:'approved', documentDate:'2026-10-03',partyId:'a' },
};
const people = { a:{ name:'شرکت کیان' }, b:{ name:'چاپ پارس' } };

test('status and order are presentation-only', () => {
  assert.deepEqual(filterInvoiceRows(records,people,'','draft').map(x=>x.id),['INV-1']);
  assert.deepEqual(filterInvoiceRows(records,people).map(x=>x.id),['INV-3','INV-2','INV-1']);
  assert.equal(records['INV-1'].status,'draft');
});
test('search by invoice number, customer and Arabic/Persian variants', () => {
  assert.deepEqual(filterInvoiceRows(records,people,'55').map(x=>x.id),['INV-2']);
  assert.deepEqual(filterInvoiceRows(records,people,'كيان').map(x=>x.id),['INV-3','INV-1']);
  assert.deepEqual(filterInvoiceRows(records,people,'not-found'),[]);
});
test('counts never invent a financial status',()=>{
  assert.deepEqual(invoiceStatusCounts(records),{all:3,draft:1,approved:1,issued:1});
  assert.deepEqual(invoiceStatusCounts({}),{all:0,draft:0,approved:0,issued:0});
});
