import React from 'react';

// Fixed, familiar sRGB choices complement (never replace) the freeform picker.
export const COMMON_COLORS=Object.freeze([
  ['#000000','مشکی'],['#FFFFFF','سفید'],['#64748B','خاکستری'],
  ['#EF4444','قرمز'],['#F97316','نارنجی'],['#F59E0B','کهربایی'],
  ['#EAB308','زرد'],['#22C55E','سبز'],['#14B8A6','فیروزه‌ای'],
  ['#06B6D4','آبی فیروزه‌ای'],['#3B82F6','آبی'],['#6366F1','نیلی'],
  ['#8B5CF6','بنفش'],['#D946EF','ارغوانی'],['#EC4899','صورتی'],
  ['#92400E','قهوه‌ای'],
]);

export function CommonColorPalette({value,onChange,disabled=false,label='رنگ'}) {
  return <div className="madar-common-colors" role="group" aria-label={'رنگ‌های مرسوم '+label}>
    {COMMON_COLORS.map(([hex,name])=><button key={hex} type="button" disabled={disabled}
      aria-label={'انتخاب '+name+' برای '+label} aria-pressed={value?.toUpperCase()===hex}
      title={name+' '+hex} className="madar-common-colors__swatch"
      style={{backgroundColor:hex}} onClick={()=>onChange(hex)}>
      {value?.toUpperCase()===hex&&<span aria-hidden="true" className="madar-common-colors__mark">✓</span>}
    </button>)}
  </div>;
}

export function CommonColorOptions(props) {
  return <details className="madar-common-colors__details">
    <summary>رنگ‌های آماده</summary>
    <CommonColorPalette {...props}/>
  </details>;
}
