// Keep this allowlist aligned with collab.TRIGGERS and _validate_rule in collab.py.
// The host remains the authority for ACL and schema validation.
export const TRIGGER_GROUPS = [
  {id:'move',label:'جابه‌جایی کارت',hint:'انتقال کارت میان فهرست‌ها',triggers:['card_moved']},
  {id:'changes',label:'تغییرات کارت',hint:'ساخت کارت یا تغییر برچسب',triggers:['card_created','label_changed']},
  {id:'dates',label:'تاریخ‌ها',hint:'نزدیک‌شدن موعد کارت',triggers:['due_soon']},
  {id:'checklists',label:'چک‌لیست‌ها',hint:'تکمیل همه موارد چک‌لیست',triggers:['checklist_completed']},
  {id:'content',label:'محتوای کارت',hint:'تغییر عنوان یا توضیحات هنوز پشتیبانی نمی‌شود',triggers:[]},
  {id:'fields',label:'فیلدها',hint:'تغییر فیلد سفارشی',triggers:['custom_field_changed']},
];

export const TRIGGER_INFO = {
  card_moved:{label:'انتقال کارت به فهرست',description:'با جابه‌جایی کارت بین ستون‌ها یا تغییر مرحله'},
  card_created:{label:'ساخته‌شدن کارت',description:'پس از ایجاد یک کارت جدید در پروژه'},
  label_changed:{label:'تغییر برچسب کارت',description:'پس از اضافه‌شدن یا برداشته‌شدن برچسب'},
  due_soon:{label:'نزدیک‌شدن به موعد',description:'در بررسی موعدها، از روز موعد تا ۷ روز پیش از آن'},
  checklist_completed:{label:'تکمیل چک‌لیست',description:'وقتی همه موارد یک چک‌لیست کامل شوند'},
  custom_field_changed:{label:'تغییر فیلد سفارشی',description:'پس از تغییر مقدار یک فیلد سفارشی'},
};

export const ACTION_INFO = {
  notify:{label:'ارسال اعلان به عضو',description:'اعلان در بخش پیام‌های عضو انتخاب‌شده ثبت می‌شود'},
  comment:{label:'ثبت نظر خودکار',description:'نظر با متن انتخاب‌شده روی همان کارت ثبت می‌شود'},
};

const IDENTIFIER=/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$/;
const USERNAME=/^[A-Za-z0-9][A-Za-z0-9._-]{2,39}$/;

export function buildAutomationRule({id,projectId,trigger,actionType,recipient,message,limitToList=false,listId='',dueDay='',dueListId='',duePriority=''}) {
  if(!IDENTIFIER.test(id||'')||!IDENTIFIER.test(projectId||''))throw Error('شناسه قانون یا پروژه معتبر نیست.');
  if(!Object.hasOwn(TRIGGER_INFO,trigger))throw Error('رویداد انتخاب‌شده پشتیبانی نمی‌شود.');
  if(!Object.hasOwn(ACTION_INFO,actionType))throw Error('عمل انتخاب‌شده پشتیبانی نمی‌شود.');
  if(typeof message!=='string'||!message.trim()||message.includes('\0'))throw Error('متن عمل را وارد کنید.');
  const text=message.trim();
  const maximum=actionType==='notify'?240:4000;
  if(text.length>maximum)throw Error('متن از محدودیت مجاز بیشتر است.');
  if(actionType==='notify'&&!USERNAME.test(recipient||''))throw Error('یک عضو معتبر برای اعلان انتخاب کنید.');
  const conditions=[];
  if(limitToList){
    if(!['card_moved','card_created'].includes(trigger)||typeof listId!=='string'||!listId||listId.length>100){
      throw Error('فیلتر فهرست برای این رویداد معتبر نیست.');
    }
    conditions.push({field:'toColumnId',equals:listId});
  }
  if(dueDay!==''&&dueDay!==null&&dueDay!==undefined){
    const day=Number(dueDay);
    if(trigger!=='due_soon'||!Number.isInteger(day)||day<0||day>7||String(dueDay).trim()===''){
      throw Error('روز موعد باید عددی بین صفر تا هفت باشد.');
    }
    conditions.push({field:'dueWithinDays',equals:day});
  }
  // The due scheduler publishes these two scalar values from the card itself.
  // Other host-allowlisted conditions are not necessarily present in due events.
  for(const [value,field,label] of [[dueListId,'toColumnId','فهرست'],[duePriority,'priority','اولویت']]){
    if(value===''||value===null||value===undefined)continue;
    if(trigger!=='due_soon'||typeof value!=='string'||!value.trim()||value.length>100){
      throw Error('فیلتر '+label+' برای رویداد موعد معتبر نیست.');
    }
    conditions.push({field,equals:value});
  }
  return {
    id,projectId,trigger,conditions,
    actions:[actionType==='notify'?{type:'notify',users:[recipient],message:text}:{type:'comment',text}],
    enabled:true,
  };
}

export function describeRule(rule){
  const action=Array.isArray(rule.actions)?rule.actions[0]:null;
  return {
    trigger:TRIGGER_INFO[rule.trigger]?.label||rule.trigger,
    action:ACTION_INFO[action?.type]?.label||action?.type||'عمل ناشناخته',
    message:action?.message||action?.text||'',
    recipient:action?.type==='notify'?(action.users||[]).join('، '):'',
    destination:rule.conditions?.find(c=>c.field==='toColumnId')?.equals||'',
    dueDay:rule.conditions?.find(c=>c.field==='dueWithinDays')?.equals,
    duePriority:rule.trigger==='due_soon'?rule.conditions?.find(c=>c.field==='priority')?.equals:undefined,
  };
}
