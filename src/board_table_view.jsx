import React,{useEffect,useMemo,useRef,useState} from 'react';
import {ChevronLeft,ChevronRight,RotateCcw,Settings2} from 'lucide-react';
import {displayDate} from './productivity.jsx';
import {boardTableColumns,readBoardViewPreferences,saveBoardViewPreferences,safeNumericAggregate,
  MIN_TABLE_WIDTH,MAX_TABLE_WIDTH} from './board_table_preferences.js';
import './board_table_view.css';

const fa=value=>value.toLocaleString('fa-IR');

function cellText(task,column,{stages,projects,users,priorities,calendar}){
  const field=column.field;
  if(field){
    const value=task.customFieldValues?.[field.id];
    if(value===null||value===undefined||value==='')return '—';
    if(field.type==='checkbox')return value===true?'بله':'خیر';
    if(field.type==='select')return field.options?.find(option=>option.id===value)?.label||'—';
    if(field.type==='date')return typeof value==='string'?displayDate(value,calendar,true):'—';
    if(field.type==='number')return typeof value==='number'&&Number.isFinite(value)?fa(value):'—';
    return String(value);
  }
  switch(column.id){
    case 'title':return task.title||'بدون عنوان';
    case 'stage':return stages.find(stage=>stage.id===(task.listId||task.status))?.label||'—';
    case 'priority':return priorities.find(item=>item.id===task.priority)?.label||'—';
    case 'due':return task.dueDate?displayDate(task.dueDate,calendar,true):'—';
    case 'project':return projects.find(project=>project.id===task.projectId)?.name||'—';
    case 'completed':return task.completed===true?'انجام‌شده':'باز';
    default:return '—';
  }
}

/** Read-only table of the exact already filtered and ACL-redacted board cards. */
export function BoardTableView({
  board,scopeId,identity,storage,tasks=[],stages=[],projects=[],users=[],
  priorities=[],calendar='jalali',onOpen,onContextRequest,
}){
  const columns=useMemo(()=>boardTableColumns(board),[board?.customFields,board?.id]);
  const [prefs,setPrefs]=useState(()=>readBoardViewPreferences(storage,identity,scopeId,columns));
  const [configOpen,setConfigOpen]=useState(false);
  const [draftWidths,setDraftWidths]=useState({});
  const [visibleCount,setVisibleCount]=useState(200);
  const settingsButton=useRef(null);
  useEffect(()=>{setPrefs(readBoardViewPreferences(storage,identity,scopeId,columns));},
    [storage,identity,scopeId,columns]);
  useEffect(()=>{setVisibleCount(200);},[scopeId,identity,tasks.length]);
  const byId=new Map(columns.map(column=>[column.id,column]));
  const ordered=prefs.columns.map(item=>({...byId.get(item.id),...item}))
    .filter(item=>item.id&&byId.has(item.id));
  const shown=ordered.filter(column=>column.visible);
  const rows=tasks.slice(0,visibleCount);
  const totals=useMemo(()=>new Map(columns.filter(column=>column.numeric)
    .map(column=>[column.id,safeNumericAggregate(tasks,column.field.id)])),[columns,tasks]);
  const changeColumn=(id,patch)=>{
    const updated=prefs.columns.map(column=>column.id===id?{...column,...patch}:column);
    setPrefs(saveBoardViewPreferences(storage,identity,scopeId,{columns:updated},columns));
  };
  const move=(id,delta)=>{
    const updated=prefs.columns.map(column=>({...column}));
    const index=updated.findIndex(column=>column.id===id),target=index+delta;
    if(index<0||target<0||target>=updated.length)return;
    [updated[index],updated[target]]=[updated[target],updated[index]];
    setPrefs(saveBoardViewPreferences(storage,identity,scopeId,{columns:updated},columns));
  };
  const commitWidth=(column)=>{
    const raw=draftWidths[column.id];
    if(raw===undefined)return;
    const width=Number(raw);
    if(Number.isInteger(width)&&width>=MIN_TABLE_WIDTH&&width<=MAX_TABLE_WIDTH)
      changeColumn(column.id,{width});
    setDraftWidths(current=>{const next={...current};delete next[column.id];return next;});
  };
  const reset=()=>setPrefs(saveBoardViewPreferences(storage,identity,scopeId,
    {columns:columns.map(({id,width})=>({id,width,visible:true}))},columns));
  const context={stages,projects,users,priorities,calendar};
  return <section className="madar-board-table" aria-label="نمای جدول کارها" dir="rtl">
    <div className="madar-board-table__tools">
      <span>{fa(tasks.length)} کارت در نمای جاری</span>
      <button ref={settingsButton} type="button" className="madar-board-table__configure"
        onClick={()=>setConfigOpen(open=>!open)} aria-expanded={configOpen}
        aria-controls="madar-board-table-config"><Settings2 size={16}/> تنظیم ستون‌ها</button>
    </div>
    {configOpen&&<div className="madar-board-table__config" id="madar-board-table-config"
      role="region" aria-label="چینش و نمایش ستون‌های جدول">
      <div className="madar-board-table__config-heading"><strong>ستون‌های این برد</strong>
        <button type="button" onClick={reset}><RotateCcw size={15}/> بازنشانی</button>
        <button type="button" onClick={()=>{setConfigOpen(false);settingsButton.current?.focus();}}>بستن</button>
      </div>
      <div className="madar-board-table__config-grid">
        {ordered.map((column,index)=><div className="madar-board-table__config-item" key={column.id}>
          <label><input type="checkbox" checked={column.visible} disabled={column.id==='title'}
            onChange={event=>changeColumn(column.id,{visible:event.target.checked})}/>
            <span title={column.label}>{column.label}</span></label>
          <label className="madar-board-table__width">عرض
            <input type="number" aria-label={'عرض ستون '+column.label} min={MIN_TABLE_WIDTH}
              max={MAX_TABLE_WIDTH} step="1" value={draftWidths[column.id]??column.width}
              onChange={event=>setDraftWidths(current=>({...current,[column.id]:event.target.value}))}
              onBlur={()=>commitWidth(column)}
              onKeyDown={event=>{if(event.key==='Enter')event.currentTarget.blur();}}/> px</label>
          <button type="button" aria-label={'انتقال '+column.label+' به راست'} title="یک ستون به راست"
            disabled={index===0} onClick={()=>move(column.id,-1)}><ChevronRight size={15}/></button>
          <button type="button" aria-label={'انتقال '+column.label+' به چپ'} title="یک ستون به چپ"
            disabled={index===ordered.length-1} onClick={()=>move(column.id,1)}><ChevronLeft size={15}/></button>
        </div>)}
      </div>
      <small>ستون عنوان برای باز کردن کارت‌ها همیشه نمایش داده می‌شود. جمع عددی فقط برای فیلدهای عددی سفارشی با دقت قابل محاسبه نمایش داده می‌شود.</small>
    </div>}
    <div className="madar-board-table__scroller" tabIndex={0} aria-label="جدول با امکان پیمایش افقی">
      <table style={{width:Math.max(640,shown.reduce((sum,column)=>sum+column.width,0))}}>
        <colgroup>{shown.map(column=><col key={column.id} style={{width:column.width}}/>)}</colgroup>
        <thead><tr>{shown.map(column=><th key={column.id} scope="col">{column.label}</th>)}</tr></thead>
        <tbody>{rows.map(task=><tr key={task.id} onContextMenu={event=>{
          if(!onContextRequest)return;event.preventDefault();onContextRequest(task,event);
        }}>{shown.map(column=><td key={column.id} title={cellText(task,column,context)}>
          {column.id==='title'
            ?<button className="madar-board-table__open" type="button"
              aria-label={'جزئیات '+(task.title||'کارت')} onClick={()=>onOpen?.(task.id)}>
              {cellText(task,column,context)}</button>
            :cellText(task,column,context)}
        </td>)}</tr>)}</tbody>
        {shown.some(column=>column.numeric)&&<tfoot><tr>{shown.map(column=><td key={column.id}>
          {column.numeric?(()=>{
            const total=totals.get(column.id);
            return total?.status==='ok'?<span title={'جمع '+fa(total.count)+' مقدار عددی'}>جمع: {total.value}</span>
              :total?.status==='unsafe'?<span title="مقادیر عددی برای جمع دقیق ایمن نیستند">جمع نامطمئن</span>:'';
          })():column.id==='title'?'جمع فیلدهای عددی':''}
        </td>)}</tr></tfoot>}
      </table>
      {!tasks.length&&<p className="madar-board-table__empty">کارتی با فیلترهای فعلی پیدا نشد.</p>}
    </div>
    {rows.length<tasks.length&&<div className="madar-board-table__more">
      <span>{fa(rows.length)} از {fa(tasks.length)} کارت نمایش داده شد</span>
      <button type="button" onClick={()=>setVisibleCount(current=>Math.min(current+200,tasks.length))}>
        نمایش ۲۰۰ کارت بعدی</button>
    </div>}
  </section>;
}
