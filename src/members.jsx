import React,{useRef,useState} from 'react';
import {Check,Camera,Code2,UserRound,Palette,Wrench,BriefcaseBusiness,ChartNoAxesColumn,
 Sparkles,Folder,Star,Rocket,ClipboardCheck,LockKeyhole,Save,X,Calculator,
 Building2,Headset,Factory,ClipboardList,Handshake,ShieldCheck,Megaphone} from 'lucide-react';
import './members.css';

export const AVATARS={
 user:[UserRound,'کاربر'],briefcase:[BriefcaseBusiness,'کسب‌وکار'],code:[Code2,'توسعه‌دهنده'],
 palette:[Palette,'طراح'],wrench:[Wrench,'فنی'],chart:[ChartNoAxesColumn,'تحلیل‌گر'],
 sparkles:[Sparkles,'خلاق'],check:[ClipboardCheck,'بررسی'],rocket:[Rocket,'شروع'],
 folder:[Folder,'پروژه'],star:[Star,'ویژه'],camera:[Camera,'عکس'],
 finance:[Calculator,'مالی و حسابداری'],management:[Building2,'مدیریت'],
 support:[Headset,'پشتیبانی'],production:[Factory,'تولید'],
 operations:[ClipboardList,'عملیات'],sales:[Handshake,'فروش'],
 quality:[ShieldCheck,'کنترل کیفیت'],marketing:[Megaphone,'بازاریابی']
};

export const ROLE_LABELS={admin:'مدیر',editor:'ویرایشگر',viewer:'مشاهده‌گر'};
export const DEFAULT_AVATAR_COLOR='#5376b5';
const COLOR_FORMAT=/^#[a-fA-F0-9]{6}$/;
const avatarColor=user=>COLOR_FORMAT.test(user?.avatarColor||'')?user.avatarColor:DEFAULT_AVATAR_COLOR;

export function RoleBadge({role,compact=false}){
 const name=ROLE_LABELS[role]||ROLE_LABELS.viewer;
 return <span className={'member-role member-role-'+(ROLE_LABELS[role]?role:'viewer')+(compact?' compact':'')} title={'سطح دسترسی: '+name}>{compact?name[0]:name}</span>;
}

export function Avatar({user,size=28}){
 const Icon=AVATARS[user?.avatarIcon]?.[0]||UserRound;
 const job=AVATARS[user?.avatarIcon]?.[1]||AVATARS.user[1];
 const label=(user?.displayName||user?.username||'کاربر')+' · '+(ROLE_LABELS[user?.role]||'نقش نامشخص')+' · '+job;
 return <span className="person-avatar workplace-avatar" style={{width:size,height:size,'--avatar-color':avatarColor(user)}} title={label} aria-label={label}>
   {user?.avatarPhoto?<img src={user.avatarPhoto} alt=""/>:<Icon size={Math.max(13,Math.round(size*.52))}/>}
   {ROLE_LABELS[user?.role]&&<span className={'avatar-role-pin avatar-role-'+user.role} aria-hidden="true">{ROLE_LABELS[user.role][0]}</span>}
 </span>;
}

export function AvatarIconPicker({value='user',onChange,disabled=false}){
 return <div className="avatar-function-grid" role="group" aria-label="انتخاب حوزه فعالیت">
   {Object.entries(AVATARS).map(([key,[Icon,label]])=><button type="button" disabled={disabled}
     key={key} className={key===value?'chosen':''} aria-pressed={key===value}
     aria-label={'حوزه فعالیت: '+label} title={label} onClick={()=>onChange?.(key)}>
     <Icon size={17}/><span>{label}</span>
   </button>)}
 </div>;
}

export function AssignedMembers({assignees=[],users=[]}){
 if(!assignees.length)return null;
 return <span className="assigned-members" title="مسئولان این کار">
   {assignees.slice(0,4).map(key=><Avatar key={key} user={users.find(u=>u.username===key)||{username:key}} size={27}/>)}
   {assignees.length>4&&<small title={'تعداد مسئولان '+assignees.length}>+{assignees.length-4}</small>}
 </span>;
}

export function AssigneeSelector({value=[],users=[],projectId,onChange,disabled=false}){
 const allowed=users.filter(u=>u.role==='admin'||u.projects===null||u.projects?.includes(projectId));
 return <div className="assignee-picker">
   {allowed.map(u=><label key={u.username} title={u.displayName||u.username}>
     <input type="checkbox" disabled={disabled} checked={value.includes(u.username)}
       onChange={e=>onChange(e.target.checked?[...value,u.username]:value.filter(x=>x!==u.username))}/>
     <Avatar user={u} size={32}/><span>{u.displayName||u.username}<small>@{u.username} · {AVATARS[u.avatarIcon]?.[1]||'کاربر'}</small><RoleBadge role={u.role}/></span>
   </label>)}
   {allowed.length===0&&<small>برای انتساب مسئول، ابتدا در بخش شبکه محلی کاربر تعریف کنید.</small>}
 </div>;
}

export function ProfilePanel({user,api,onClose,onUpdated}){
 const [name,setName]=useState(user?.displayName||'');
 const [icon,setIcon]=useState(user?.avatarIcon||'user');
 const [photo,setPhoto]=useState(user?.avatarPhoto||'');
 const [color,setColor]=useState(avatarColor(user));
 const [oldPass,setOldPass]=useState('');
 const [newPass,setNewPass]=useState('');
 const [notice,setNotice]=useState('');
 const [error,setError]=useState('');
 const [busy,setBusy]=useState(false);
 const fileRef=useRef(null);
 const upload=async e=>{
   const file=e.target.files?.[0];if(!file)return;
   if(!['image/png','image/jpeg','image/webp'].includes(file.type)||file.size>5_000_000){
     setError('فقط عکس PNG/JPEG/WebP با حجم کمتر از ۵ مگابایت انتخاب کنید.');return;
   }
   const objectUrl=URL.createObjectURL(file);
   try{
     const img=new Image();
     await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=reject;img.src=objectUrl;});
     const canvas=document.createElement('canvas');canvas.width=96;canvas.height=96;
     const ctx=canvas.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,96,96);
     const scale=Math.max(96/img.width,96/img.height),w=img.width*scale,h=img.height*scale;
     ctx.drawImage(img,(96-w)/2,(96-h)/2,w,h);
     const result=canvas.toDataURL('image/jpeg',.76);
     if(result.length>120000)throw Error('حجم عکس پردازش‌شده بیشتر از حد مجاز است.');
     setPhoto(result);setError('');
   }catch(e){setError('تبدیل عکس ناموفق بود: '+e.message);}
   finally{URL.revokeObjectURL(objectUrl);e.target.value='';}
 };
 const run=async action=>{setBusy(true);setError('');setNotice('');try{await action();}catch(e){setError(e.message||String(e));}finally{setBusy(false);}};
 return <div className="overlay" onMouseDown={onClose}><section className="dialog member-modal" onMouseDown={e=>e.stopPropagation()} role="dialog" aria-modal="true">
   <div className="dialog-head"><h2><UserRound size={19}/> پروفایل من</h2><button className="icon-btn" onClick={onClose}><X size={20}/></button></div>
   <div className="dialog-body member-content">
     <div className="profile-hero"><Avatar user={{...user,avatarPhoto:photo,avatarIcon:icon,avatarColor:color,displayName:name}} size={66}/><div><strong>{user?.username||'local'}</strong><RoleBadge role={user?.role}/><small>حوزه فعالیت و رنگ آواتار را خودت انتخاب می‌کنی؛ این‌ها برداشت سیستم از شخصیت تو نیستند.</small></div></div>
     <label className="member-field">نام نمایشی<input maxLength={80} value={name} onChange={e=>setName(e.target.value)}/></label>
     <h3>حوزه فعالیت یا نماد دلخواه</h3><AvatarIconPicker value={icon} onChange={value=>{setIcon(value);setPhoto('');}}/>
     <label className="member-color-field">رنگ آواتار<input type="color" value={color} aria-label="رنگ آواتار من" onChange={e=>setColor(e.target.value)}/></label>
     <div className="profile-photo-actions"><input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={upload}/><button className="btn secondary" onClick={()=>fileRef.current?.click()}><Camera size={16}/> بارگذاری تصویر شخصی</button>{photo&&<button className="btn secondary" onClick={()=>setPhoto('')}>حذف عکس</button>}</div>
     <button className="btn primary" disabled={busy} onClick={()=>run(async()=>{const updated=await api.lanMyProfile({displayName:name,avatarIcon:icon,avatarPhoto:photo,avatarColor:color});onUpdated?.(updated);setNotice('پروفایل ذخیره شد.');})}><Save size={16}/> ذخیره پروفایل</button>
     {user?.username!=='local'&&<div className="member-password"><h3><LockKeyhole size={17}/> تغییر رمز ورود</h3><label className="member-field">رمز فعلی<input type="password" autoComplete="current-password" value={oldPass} onChange={e=>setOldPass(e.target.value)}/></label><label className="member-field">رمز جدید (حداقل ۱۰ نویسه)<input type="password" autoComplete="new-password" value={newPass} onChange={e=>setNewPass(e.target.value)}/></label><button className="btn secondary" disabled={busy||newPass.length<10||!oldPass} onClick={()=>run(async()=>{await api.lanChangePassword(oldPass,newPass);setOldPass('');setNewPass('');setNotice('رمز تغییر کرد و نشست‌های قدیمی لغو شدند.');})}>تغییر رمز</button></div>}
     {notice&&<p className="inline-message">{notice}</p>}{error&&<p className="lan-error" role="alert">{error}</p>}
   </div>
 </section></div>;
}
