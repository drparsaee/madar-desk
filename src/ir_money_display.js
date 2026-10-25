// UI compatibility boundary only. The current host ledger accepts INTEGER TOMAN.
// Rial is a selectable entry/view unit, never a declaration of rial-native storage.
export const MAX_LEGACY_TOMAN=1000000000000000n;
export const MONEY_UNITS=Object.freeze({TOMAN:'تومان',RIAL:'ریال'});

const normalizeDigits=value=>value.replace(/[۰-۹]/g,c=>String(c.charCodeAt(0)-1776))
  .replace(/[٠-٩]/g,c=>String(c.charCodeAt(0)-1632)).replace(/٬/g,',');

const parseDigits=value=>{
  if(typeof value!=='string')return null;
  const normalized=normalizeDigits(value.trim());
  if(!/^(?:0|[1-9][0-9]*|[1-9][0-9]{0,2}(?:,[0-9]{3})+)$/.test(normalized))return null;
  return BigInt(normalized.replace(/,/g,''));
};

export function parseMoneyInput(input,unit='TOMAN',{allowZero=false}={}){
  if(!Object.hasOwn(MONEY_UNITS,unit))return {amount:null,error:'واحد پولی نامعتبر است.'};
  const parsed=parseDigits(input);
  if(parsed===null)return {amount:null,error:'مبلغ را به‌صورت عدد صحیح، با جداکننده هزارگان معتبر وارد کنید.'};
  if(!allowZero&&parsed===0n)return {amount:null,error:'مبلغ باید بزرگ‌تر از صفر باشد.'};
  if(unit==='RIAL'&&parsed%10n!==0n)
    return {amount:null,error:'مبلغ ریالی باید مضرب ۱۰ ریال باشد؛ موتور فعلی مبلغ را به تومان ذخیره می‌کند و گرد کردن مجاز نیست.'};
  const toman=unit==='RIAL'?parsed/10n:parsed;
  if(toman>MAX_LEGACY_TOMAN)return {amount:null,error:'مبلغ از سقف مجاز موتور حسابداری فعلی بیشتر است.'};
  return {amount:Number(toman),error:''}; // Bounded below Number.MAX_SAFE_INTEGER.
}

const persianDigits=value=>value.replace(/[0-9]/g,n=>'۰۱۲۳۴۵۶۷۸۹'[Number(n)]);

export function formatLegacyMoney(amount,unit='TOMAN',{fallback='ثبت نشده'}={}){
  if(!Object.hasOwn(MONEY_UNITS,unit))return fallback;
  if(typeof amount==='number'&&!Number.isSafeInteger(amount))return fallback;
  if(typeof amount!=='number'&&typeof amount!=='bigint')return fallback;
  const value=BigInt(amount)*(unit==='RIAL'?10n:1n);
  const digits=(value<0n?-value:value).toString().replace(/\B(?=(\d{3})+(?!\d))/g,',');
  return (value<0n?'−':'')+persianDigits(digits)+' '+MONEY_UNITS[unit];
}

export function formatLegacyEntry(amount,unit='TOMAN'){
  if(!Object.hasOwn(MONEY_UNITS,unit)||typeof amount!=='number'||!Number.isSafeInteger(amount)||amount<0)return '';
  return (BigInt(amount)*(unit==='RIAL'?10n:1n)).toString();
}

// Changing the selector converts every recognizable typed amount exactly.
// Invalid or incomplete input is cleared, never silently reinterpreted.
export function convertTypedMoney(value,fromUnit,toUnit){
  if(value==='')return {value:'',cleared:false};
  if(fromUnit===toUnit)return {value,cleared:false};
  const parsed=parseMoneyInput(value,fromUnit,{allowZero:true});
  if(parsed.error||!Object.hasOwn(MONEY_UNITS,toUnit))return {value:'',cleared:true};
  return {value:(BigInt(parsed.amount)*(toUnit==='RIAL'?10n:1n)).toString(),cleared:false};
}
