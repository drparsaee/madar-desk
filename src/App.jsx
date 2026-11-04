import React, {useEffect, useMemo, useRef, useState} from 'react';
import packageInfo from '../package.json';
import {
  Activity, Archive, ArrowDownToLine, ArrowLeft, ArrowUpLeft, Bell, CalendarDays,
  Check, CheckCheck, CheckCircle2, ChevronDown, ChevronLeft, Circle,
  ClipboardCheck, Cloud, CloudDownload, CloudUpload, Command, Copy, Download,
  Ellipsis, FileText, Flag, FolderClosed, HardDriveDownload, Inbox,
  LayoutDashboard, LayoutGrid, ListChecks, LoaderCircle, Menu, MessageCircle,
  MoreHorizontal, Plus, Search, Settings2, ShieldCheck, Tag,
  Trash2, Users, X, Zap, Clock3, FolderOpen, BarChart3, RefreshCw,
  Eye, EyeOff, Wallet, GripVertical, FileInput, Sun, Moon, Palette, Table2, Undo2, Redo2
} from 'lucide-react';
import {DEFAULT_STAGES,SettingsPanel,LanPanel,MoneyField,money,cardCostEnabled} from './features.jsx';
import {CalendarField,SharedLinks,TimeDashboard,displayDate,similarTasks,searchText,durationText} from './productivity.jsx';
import {Avatar,AssignedMembers,AssigneeSelector,ProfilePanel} from './members.jsx';
import {LabelChip,InlineChecklist,AdvancedFilters,matchAdvanced,RichDescription} from './boardplus.jsx';
import {CardComments,NotificationsDialog,ActivityDialog} from './teamplus.jsx';
import {FinancePanel} from './financepanel.jsx';
import {RulesPanel} from './rulespanel.jsx';
import {AutomationButtonsPanel,AutomationButtonsLauncher,AutomationButtonStrip} from './automation_buttons.jsx';
import {duplicateCard} from './taskops.js';
import {CardAttachments} from './attachments.jsx';
import {archiveBoardState,restoreBoardState,renameBoardState,moveCardToBoard,boardStageUpdate,legacyStatusForStage} from './boardops.js';
import {boardForColumn,propagateAddedWorkspaceStages} from './board_stage_sync.js';
import {ProfitPeek} from './financeoverview.jsx';
import {AccountingPanel} from './accounting_panel.jsx';
import {AccountingWorkspace} from './accounting_workspace.jsx';
import {RialJournalPanel} from './rial_journal_panel.jsx';
import {filterTasks} from './searchplus.js';
import {SearchPlus} from './searchplus.jsx';
import {searchTaskLocations} from './task_search_results.js';
import {SearchResultsPanel} from './task_search_results.jsx';
import {LabelEditor} from './labels.jsx';
import {priorityDefs,priorityById,reorderStageArray} from './priorities.js';
import {ReportingPanel} from './reporting.jsx';
import {TrelloImportPanel} from './trello_import.jsx';
import {CardCover,CardChecklists,CardCustomFields,BoardFieldEditor,coverTextColor} from './cardextras.jsx';
import {PlannerPanel} from './planner.jsx';
import {removeUnpaidLegacyStep} from './checklistguard.js';
import {plannerIdentity} from './planner_identity.js';
import {EMPTY_ADVANCED_FILTER,readScopedAdvancedFilter,updateScopedAdvancedFilter} from './advanced_filter_scope.js';
import {importCalendarEvents} from './calendar_import_state.js';
import {getOrderedLaneCards,moveCardInState} from './cardorder.js';
import {sortLaneState,moveAllLaneCardsState} from './lane_operations.js';
import {WorkspaceManager} from './workspaces_panel.jsx';
import {archiveListState,restoreListState,activeBoardLists} from './listarchive.js';
import {softDeleteCardState,restoreDeletedCardState} from './cardtrash.js';
import {archiveCardState,restoreArchivedCardState} from './cardarchive.js';
import {CardContextMenu} from './card_context_menu.jsx';
import {themeScope,readTheme,writeTheme} from './theme_preference.js';
import {hostBackupHealth} from './host_backup_health.js';
import {readCardSectionPreferences,saveCardSectionPreferences,CARD_SECTIONS} from './card_section_preferences.js';
import {syncHealth} from './sync_health.js';
import {createBoardPerformanceIndex} from './board_performance.js';
import {PortableExportPanel} from './portable_export_panel.jsx';
import {ProgressiveLane} from './progressive_lane.jsx';
import {CardDependencyPanel} from './card_dependency_panel.jsx';
import {resolvedDisplayScope,isManagedFeatureVisible} from './managed_display.js';
import {ClockWidget} from './clock_widget.jsx';
import {LaneActionsMenu} from './board_lane_actions.jsx';
import {BoardTableView} from './board_table_view.jsx';
import {boardTableColumns,readBoardViewPreferences,saveBoardViewPreferences} from './board_table_preferences.js';
import {VitreaOverview} from './vitrea_overview.jsx';
import {DEFAULT_WIDGET_SETTINGS,normalizeWidgetSettings} from './widget_preferences.js';
import {OrderSaleFields,StageExpenseFields} from './order_finance_fields.jsx';
import {prepareStandaloneFromTask} from './standalone_order_adapter.js';
import {emptyCardHistory,isUndoableCardPatch,recordCardEdit,cardHistoryAvailability,applyCardHistory} from './card_undo.js';
import './interface_mode.css';
import './boardplus.css';
import './task_editor_compact.css';
import './kanban_compact.css';
import './vitrea_shell.css';
import './vitrea_navigation.css';
import './vitrea_design_tokens.css';
import './workspace_empty.css';
import './trello_quick_add.css';
import './sidebar_compact.css';
import './backup_easy.css';

const uid=()=>Math.random().toString(36).slice(2)+Date.now().toString(36);
const now=()=>new Date().toISOString();
const todayISO=()=>{const value=new Date();return `${value.getFullYear()}-${String(value.getMonth()+1).padStart(2,'0')}-${String(value.getDate()).padStart(2,'0')}`;};
const makeBoard=(project,workspace,stages)=>({
 id:uid(),workspaceId:workspace,projectId:project.id,name:project.name,
 color:project.color,archived:false,stages:JSON.parse(JSON.stringify(stages)),
 labelDefinitions:[],customFields:[]
});
const seed=()=>({
  version:1,
  workspaces:[{id:'workspace-legacy',name:'فضای کاری من',archived:false}],
  boards:[],projects:[],tasks:[],
  stages:DEFAULT_STAGES,settings:{theme:'dark',themeForAllUsers:false,googleClientId:'',costDefault:false}
});
const normalize=s=>({...s,stages:s.stages?.length?s.stages:DEFAULT_STAGES,boards:s.boards||[],workspaces:s.workspaces?.length?s.workspaces:[{id:'workspace-legacy',name:'فضای کاری من',archived:false}],projects:s.projects.map(p=>({costEnabled:false,price:0,fileLinks:[],...p})),tasks:s.tasks.map(t=>({...t,cost:t.cost||0,costEnabled:t.costEnabled??null,assignees:t.assignees||[],fileLinks:t.fileLinks||[],estimatedMinutes:t.estimatedMinutes||0,actualMinutes:t.actualMinutes||0,checklist:t.checklist.map(c=>({cost:0,...c}))})),settings:{theme:'dark',themeForAllUsers:false,costDefault:false,...s.settings}});
const mockBridge={
  getState:async()=>JSON.parse(localStorage.getItem('madar-preview')||'null')||seed(),
  saveState:async s=>{localStorage.setItem('madar-preview',JSON.stringify(s));return true;},
  exportBackup:async()=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(JSON.parse(localStorage.getItem('madar-preview')||'{}'),null,2)],{type:'application/json'}));a.download='madar-backup.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),500);return {path:'madar-backup.json'};},
  importBackup:async()=>{throw new Error('ورود فایل در نسخه پیش‌نمایش وب فعال نیست؛ برنامه ویندوز این قابلیت را دارد.');},
  driveStatus:async()=>({connected:false,clientId:''}),
  driveConnect:async()=>{throw new Error('اتصال Google Drive در نسخه EXE در دسترس است.');},
  driveUpload:async()=>{throw new Error('این قابلیت فقط در برنامه ویندوز فعال است.');},
  driveList:async()=>[],
  driveRestore:async()=>{throw new Error('این قابلیت فقط در برنامه ویندوز فعال است.');},
  driveDisconnect:async()=>({connected:false}),
  lanStatus:async()=>({mode:'solo',user:{username:'local',role:'admin',projects:null}}),
  lanDiscover:async()=>[],
  hostServiceStatus:async()=>({supported:false,installed:false,running:false}),
  lanHost:async()=>{throw Error('امکان شبکه در نسخه EXE فعال است.');},
  lanJoin:async()=>{throw Error('امکان شبکه در نسخه EXE فعال است.');},
  lanLeave:async()=>({mode:'solo'}),
  lanUsers:async()=>[],
  lanDisplayRoles:async()=>[],
  lanSaveDisplayRole:async()=>{throw Error('مدیریت نقش‌های کاربران به میزبان شبکه نیاز دارد.');},
  lanDeleteDisplayRole:async()=>{throw Error('مدیریت نقش‌های کاربران به میزبان شبکه نیاز دارد.');},
  lanSaveUser:async()=>{throw Error('شبکه فعال نیست.');},
  lanDeleteUser:async()=>{throw Error('شبکه فعال نیست.');},
  lanProfiles:async()=>[{username:'local',displayName:'من',avatarIcon:'user',avatarPhoto:'',role:'admin',projects:null}],
  lanMyProfile:async()=>{throw Error('شخصی‌سازی کاربران شبکه در برنامه ویندوز فعال است.');},
  lanChangePassword:async()=>{throw Error('حساب شبکه فعال نیست.');},
  lanResetPassword:async()=>{throw Error('حساب شبکه فعال نیست.');},
  integrationIssueKey:async()=>{throw Error('کلید API فقط روی میزبان HTTPS ویندوز فعال است.');},
  integrationRevokeKey:async()=>{throw Error('کلید API فقط روی میزبان HTTPS ویندوز فعال است.');},
  calendarExportIcs:async()=>{throw Error('خروجی ICS فقط از برنامه ویندوز قابل دریافت است.');},
  calendarImportPreview:async()=>{throw Error('ورود ICS فقط در برنامه ویندوز فعال است.');},
  automationEngineStatus:async()=>({mode:'legacy',ready:false,pending:0,dead:0}),
  enableAutomationEngine:async()=>{throw Error('موتور اتوماسیون فقط در میزبان ویندوز با SQLite فعال می‌شود.');},
  syncStatus:async()=>({mode:'solo',connected:true,pending:false,lastSync:null,drive:false,folder:{configured:false}}),
  chooseDriveFolder:async()=>{throw Error('انتخاب پوشه Google Drive در EXE فعال است.');},
  driveFolderStatus:async()=>({configured:false,folder:'',pending:false}),
  driveFolderList:async()=>[],
  driveFolderRestore:async()=>{throw Error('بازیابی پوشه در نسخه ویندوز فعال است.');},
  driveFolderBackup:async()=>{throw Error('پشتیبان پوشه فقط در EXE ویندوز فعال است.');},
  cloudPeerStatus:async()=>({paired:false,enabled:false,cloudVerified:false}),
  cloudPeerConfigure:async()=>{throw Error('اشتراک پوشه میان کلاینت‌ها فقط در برنامه ویندوز فعال است.');},
  cloudPeerGenerate:async()=>{throw Error('این قابلیت فقط در برنامه ویندوز فعال است.');},
  cloudPeerForget:async()=>({paired:false,enabled:false,cloudVerified:false}),
  financeRead:async()=>[],
  financeStatus:async()=>({pending:0,warning:''}),
  financeCommand:async()=>{throw Error('ثبت مالی در نسخه ویندوز فعال است.');},
  accountingRead:async()=>{throw Error('حسابداری دوبل فقط در نسخه ویندوز فعال است.');},
  accountingCommand:async()=>{throw Error('ثبت حسابداری دوبل فقط در نسخه ویندوز فعال است.');},
  standaloneAccountingRead:async()=>{throw Error('حسابداری مستقل فقط در میزبان ویندوز فعال است.');},
  standaloneAccountingCommand:async()=>{throw Error('ثبت حسابداری مستقل فقط در میزبان ویندوز فعال است.');},
  standaloneAccountingPrepare:async()=>{throw Error('آماده‌سازی سفارش صرفاً توسط میزبان معتبر امکان‌پذیر است.');},
  standaloneAccountingQuote:async()=>{throw Error('محاسبه سفارش فقط در میزبان حسابداری فعال است.');},
  getPreferences:async()=>JSON.parse(localStorage.getItem('madar-preferences')||'{"calendar":"jalali"}'),
  setPreferences:async p=>{const old=JSON.parse(localStorage.getItem('madar-preferences')||'{"calendar":"jalali"}');const widgetSettings=normalizeWidgetSettings(p.widgetSettings||old.widgetSettings||p.clockWidget||old.clockWidget);const next={...old,...p,widgetSettings,clockWidget:widgetSettings.mode};localStorage.setItem('madar-preferences',JSON.stringify(next));return next;},
  openSharedFile:async()=>{throw Error('بازکردن فایل از File Explorer فقط در EXE ویندوز فعال است.');},
  downloadSharedFile:async()=>{throw Error('دانلود فایل اشتراکی فقط در EXE ویندوز فعال است.');},
  chooseSharedFile:async()=>{throw Error('انتخاب مسیر SMB فقط در EXE ویندوز فعال است.');},
  attachmentSave:async()=>{throw Error('ذخیره پیوست فقط در EXE ویندوز فعال است.');},
  releaseCheck:async()=>({available:false,current:packageInfo.version}),
  releaseDownload:async()=>{throw Error('آپدیت اینترنتی فقط در EXE ویندوز فعال است.');},
  releaseInstall:async()=>{throw Error('نصب اینترنتی فقط در EXE ویندوز فعال است.');},
  createLocalBackup:async()=>{throw Error('نسخه پشتیبان داخلی فقط در EXE فعال است.');},
  listLocalBackups:async()=>[],
  automaticBackupStatus:async()=>({running:false,intervalSeconds:30,complete:false,scope:null}),
  restoreLocalBackup:async()=>{throw Error('بازیابی داخلی فقط در EXE فعال است.');}
  ,collabRead:async()=>[],
  collabCommand:async()=>{throw Error('گفتگو در نسخه نمایشی وب غیرفعال است.');}
  ,runDueScheduler:async()=>({events:0,new:0})
  ,attachmentList:async()=>[]
  ,attachmentPreview:async()=>({available:false,kind:'none'})
  ,attachmentRead:async()=>{throw Error('دریافت فایل فقط در نسخه ویندوز فعال است.');}
  ,attachmentUpload:async()=>{throw Error('بارگذاری فایل فقط در نسخه ویندوز فعال است.');}
  ,attachmentDelete:async()=>{throw Error('حذف فایل فقط در نسخه ویندوز فعال است.');}
  ,attachmentBackup:async()=>{throw Error('بکاپ فایل فقط روی میزبان ویندوز فعال است.');}
  ,createUnifiedSqliteBackup:async()=>{throw Error('خروجی SQLite فقط روی میزبان ویندوز فعال است.');}
};
const api=window.madar||mockBridge;
const isDesktop=!!window.madar;
const shortDate=v=>{if(!v)return '';try{return new Date(v).toLocaleDateString('fa-IR',{month:'short',day:'numeric'});}catch{return v;}};

function Empty({title,description,onAdd}){
  return <div className="lane-empty"><span className="lane-empty-icon"><Plus size={18}/></span><strong>{title}</strong><small>{description}</small>{onAdd&&<button onClick={onAdd}>افزودن کار <Plus size={14}/></button>}</div>;
}

function TaskCard({task,project,users,onOpen,onContextRequest,onDrag,onToggleStep,onToggleComplete,onCardDrop,onKeyboardReorder,calendar,priorities,canEdit=true,canManage=false,showCosts=true}){
  const [collapsed,setCollapsed]=useState(true);
  const done=task.checklist.filter(i=>i.done).length;
  const percent=task.checklist.length?Math.round(done/task.checklist.length*100):0;
  const report=task.reports[task.reports.length-1];
  const priority=priorityById(priorities,task.priority);
  const cover=task.cover?.type==='color'&&/^#[0-9a-f]{6}$/i.test(task.cover.color)?task.cover:null;
  const coverFull=cover?.size==='full';
  return <div role="button" tabIndex={0} className={'task-card priority-effect-'+priority.effect+(task.completed===true?' task-card--completed':'')+(coverFull?' task-card--cover-full':cover?' task-card--cover-strip':'')} style={{'--priority-color':priority.color,...(cover?{'--card-cover-color':cover.color,'--card-cover-contrast':coverTextColor(cover.color)}:{})}} draggable={canEdit} onContextMenu={e=>{e.preventDefault();e.stopPropagation();onContextRequest?.(task,e);}} onDragStart={e=>{e.dataTransfer.setData('text/plain',task.id);e.dataTransfer.setData('application/x-madar-card',task.id);e.dataTransfer.effectAllowed='move';onDrag?.(task.id);}} onDragOver={e=>{if(canEdit&&onCardDrop&&Array.from(e.dataTransfer.types||[]).includes('application/x-madar-card')){e.preventDefault();e.stopPropagation();e.dataTransfer.dropEffect='move';}}} onDrop={e=>{if(!canEdit||!onCardDrop)return;const id=e.dataTransfer.getData('application/x-madar-card');if(!id)return;e.preventDefault();e.stopPropagation();const bounds=e.currentTarget.getBoundingClientRect();onCardDrop(id,task.id,e.clientY<bounds.top+bounds.height/2?'before':'after');}} onClick={()=>onOpen(task.id)} onKeyDown={e=>{if(e.target!==e.currentTarget)return;if(e.key==='ContextMenu'||(e.shiftKey&&e.key==='F10')){e.preventDefault();const rect=e.currentTarget.getBoundingClientRect();onContextRequest?.(task,{clientX:rect.left+20,clientY:rect.top+20});}else if(canEdit&&onKeyboardReorder&&e.altKey&&(e.key==='ArrowUp'||e.key==='ArrowDown')){e.preventDefault();onKeyboardReorder(task.id,e.key==='ArrowUp'?-1:1);}else if(e.key==='Enter'||e.key===' '){e.preventDefault();onOpen(task.id);}}} aria-keyshortcuts={onKeyboardReorder?'Alt+ArrowUp Alt+ArrowDown Shift+F10':'Shift+F10'} aria-label={'جزئیات '+task.title}>
    <div className="task-card-head" aria-label={cover&&!coverFull?'کاور رنگی بالای کارت':undefined}>
      <div className="task-card-top"><button type="button" disabled={!canEdit} className="task-complete-toggle" aria-label={(task.completed===true?'برگرداندن از تکمیل ':'تکمیل کارت ')+task.title} title={task.completed===true?'برگرداندن از تکمیل':'تکمیل کارت'} aria-pressed={task.completed===true} onClick={e=>{e.preventDefault();e.stopPropagation();onToggleComplete?.(task.id);}} onKeyDown={e=>e.stopPropagation()}><Check size={15}/></button></div>
      <div className="task-title">{task.title}</div>
    </div>
    {task.description&&<div className="task-description">{task.description}</div>}
    {!!task.labels?.length&&<div className="tags">{task.labels.map((l,i)=><LabelChip key={i} label={task.labelColors?.[l]?{name:l,color:task.labelColors[l]}:l}/>)}</div>}
    {task.checklist.length>0&&<div className="progress-block"><div className="progress-caption"><span><ListChecks size={13}/> {done} از {task.checklist.length} مرحله</span><b>{percent}٪</b></div><div className="progress-track"><i style={{width:percent+'%'}}/></div></div>}
    <InlineChecklist items={task.checklist} taskId={task.id} canEdit={canEdit} collapsed={collapsed} onCollapse={()=>setCollapsed(x=>!x)} onToggle={onToggleStep}/>
    {canManage&&showCosts&&cardCostEnabled(task,project)&&<div className="card-cost"><WalletIcon/>{money((task.cost||0)+task.checklist.reduce((x,c)=>x+(c.cost||0),0))} تومان</div>}
    {report&&<div className="agent-line"><span className="agent-avatar"><Zap size={12}/></span><span><b>{report.agent}:</b> {report.summary}</span></div>}
    <div className="task-footer">
      <span className="priority priority-label"><Flag size={13}/>{priority.label}</span>
      <span className="footer-icons"><AssignedMembers users={users} assignees={task.assignees||[]}/>{!!task.reports.length&&<span><MessageCircle size={13}/>{task.reports.length}</span>}<span title="تاریخ ایجاد"><CalendarDays size={13}/>{displayDate(task.createdAt,calendar)}</span>{!!task.dueDate&&<span title="موعد انجام"><CalendarDays size={13}/>{displayDate(task.dueDate,calendar)}</span>}{!!task.estimatedMinutes&&<span title="برآورد زمان"><Clock3 size={13}/>{durationText(task.estimatedMinutes)}</span>}</span>
    </div>
  </div>;
}
function WalletIcon(){return <span className="money-coin">ت</span>;}

function Modal({title,children,onClose,width=470}){
  const root=useRef(null),closeRef=useRef(onClose);
  closeRef.current=onClose;
  useEffect(()=>{
    const previous=document.activeElement;
    const focusable=()=>Array.from(root.current?.querySelectorAll('button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])')||[])
      .filter(el=>el.getClientRects().length>0);
    const initial=root.current?.querySelector('[autofocus]')||focusable()[0];
    initial?.focus();
    const fn=e=>{
      if(e.key==='Escape'){e.stopPropagation();closeRef.current();return;}
      if(e.key!=='Tab')return;
      const elements=focusable();
      if(!elements.length){e.preventDefault();root.current?.focus();return;}
      const first=elements[0],last=elements[elements.length-1];
      if(e.shiftKey&&(document.activeElement===first||!root.current?.contains(document.activeElement))){e.preventDefault();last.focus();}
      else if(!e.shiftKey&&(document.activeElement===last||!root.current?.contains(document.activeElement))){e.preventDefault();first.focus();}
    };
    window.addEventListener('keydown',fn);
    return()=>{window.removeEventListener('keydown',fn);if(previous?.isConnected)previous.focus();};
  },[]);
  return <div className="overlay" onMouseDown={()=>closeRef.current()}><div ref={root} tabIndex={-1} className="dialog" style={{maxWidth:width}} onMouseDown={e=>e.stopPropagation()} role="dialog" aria-modal="true" aria-label={title}><div className="dialog-head"><h2>{title}</h2><button className="icon-btn" aria-label="بستن" onClick={()=>closeRef.current()}><X size={19}/></button></div>{children}</div></div>;
}

function SyncIndicator({status,lastSync,showDetails,conflict=false,saving=false,compact=false}){
  const health=syncHealth(status,{conflict,saving});
  const label=health.label;
  const shortLabel=compact?({offline:'آفلاین',conflict:'تعارض',pending:'در صف',saving:'ذخیره'}[health.kind]||'محلی'):label;
  return <button type="button" aria-live="polite" aria-label={'وضعیت اتصال: '+label} className={'sync-indicator '+(['pending','saving','conflict'].includes(health.kind)?'sync-pending':['offline'].includes(health.kind)?'sync-offline':'sync-online')+(compact?' sync-indicator--dock':'')} onClick={showDetails} title={label+(lastSync?' | آخرین دریافت: '+new Date(lastSync).toLocaleString('fa-IR'):'')}><span className="sync-led"/><span className="sync-indicator__label">{shortLabel}</span></button>;
}

function TaskEditor({task,projects,boards,stages,allTasks,allTemplates=[],users,username,calendar,api,priorities,onUpdate,onBoardChange,onClose,onDelete,onArchive,onDuplicate,onOpenSale,onOpenPurchase,onUndo,onRedo,canUndo=false,canRedo=false,initialSection=null,canEdit=true,canManage=false,showCosts=true,showOperations=true}){
  const [newStep,setNewStep]=useState('');
  const [customFieldsOpen,setCustomFieldsOpen]=useState(()=>Boolean(boards.find(board=>board.id===task.boardId)?.customFields?.length));
  const [automationButtonsOpen,setAutomationButtonsOpen]=useState(false);
  const [automationButtonView,setAutomationButtonView]=useState('card');
  const drawerRef=useRef(null);
  const onCloseRef=useRef(onClose);
  onCloseRef.current=onClose;
  useEffect(()=>{
    const before=document.activeElement;
    const drawer=drawerRef.current;
    if(!drawer)return;
    drawer.querySelector('.task-edit-title:not(:disabled),.task-quick-actions button')?.focus();
    const handleKey=event=>{
      if(event.key==='Escape'){
        event.stopPropagation();
        onCloseRef.current();
        return;
      }
      if(event.key!=='Tab')return;
      const controls=Array.from(drawer.querySelectorAll('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href],[tabindex]:not([tabindex="-1"])'))
        .filter(item=>item.getClientRects().length>0&&getComputedStyle(item).visibility!=='hidden');
      if(!controls.length){event.preventDefault();drawer.focus();return;}
      const first=controls[0],last=controls[controls.length-1];
      if(event.shiftKey&&(document.activeElement===first||!drawer.contains(document.activeElement))){
        event.preventDefault();last.focus();
      }else if(!event.shiftKey&&(document.activeElement===last||!drawer.contains(document.activeElement))){
        event.preventDefault();first.focus();
      }
    };
    document.addEventListener('keydown',handleKey);
    return()=>{document.removeEventListener('keydown',handleKey);if(before?.isConnected)before.focus();};
  },[]);
  const [accountView,setAccountView]=useState(null);
  useEffect(()=>{
    if(!canManage)return;
    let live=true;
    api.standaloneAccountingRead().then(r=>{if(live)setAccountView(r.view);}).catch(()=>{});
    return()=>{live=false;};
  },[api,canManage]);
  const [agent,setAgent]=useState('');
  const [summary,setSummary]=useState('');
  const [reportComposerOpen,setReportComposerOpen]=useState(false);
  const [confirmDelete,setConfirmDelete]=useState(false);
  const [confirmArchive,setConfirmArchive]=useState(false);
  const [sectionOpen,setSectionOpen]=useState(()=>readCardSectionPreferences(localStorage,username));
  useEffect(()=>setSectionOpen(readCardSectionPreferences(localStorage,username)),[username]);
  const onSectionToggle=(section,event)=>{
    if(event.target!==event.currentTarget)return;
    const open=event.currentTarget.open;
    setSectionOpen(previous=>{
      if(previous[section]===open)return previous;
      return saveCardSectionPreferences(localStorage,username,{...previous,[section]:open});
    });
  };
  const update=changes=>{if(canEdit)onUpdate(task.id,changes);};
  const addStep=()=>{if(!newStep.trim())return;update({checklist:[...task.checklist,{id:uid(),text:newStep.trim(),done:false}]});setNewStep('');};
  const addReport=()=>{if(!summary.trim())return;update({reports:[...task.reports,{id:uid(),agent:agent.trim()||'من',summary:summary.trim(),createdAt:now()}]});setSummary('');setReportComposerOpen(false);};
  const total=task.checklist.length,done=task.checklist.filter(i=>i.done).length;
  const priceEnabled=canManage&&showCosts&&cardCostEnabled(task,projects.find(p=>p.id===task.projectId));
  const taskBoard=boards.find(b=>b.id===task.boardId);
  const suggestedTasks=useMemo(()=>similarTasks(task.title,allTasks,task.id),[task.title,task.id,allTasks]);
  const jumpToSection=section=>{
    if(CARD_SECTIONS.includes(section))setSectionOpen(previous=>{
      if(previous[section])return previous;
      return saveCardSectionPreferences(localStorage,username,{...previous,[section]:true});
    });
    const target=document.getElementById('task-section-'+section);
    if(!target)return;
    if(target.tagName==='DETAILS')target.open=true;
    // A disclosure opened by the toolbar becomes scrollable after the render.
    requestAnimationFrame(()=>{
      target.scrollIntoView({behavior:window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches?'instant':'smooth',block:'start'});
      target.focus({preventScroll:true});
    });
  };
  useEffect(()=>{
    if(!initialSection)return;
    const frame=requestAnimationFrame(()=>jumpToSection(initialSection));
    return()=>cancelAnimationFrame(frame);
  },[initialSection,task.id]);
  return <div className="drawer-overlay" onMouseDown={onClose}><aside ref={drawerRef} tabIndex={-1} className="drawer" onMouseDown={e=>e.stopPropagation()} role="dialog" aria-modal="true" aria-label="جزئیات کار">
    <div className="drawer-top"><span className="small-overline"><ClipboardCheck size={17}/> جزئیات کار</span><div style={{display:'flex',alignItems:'center',gap:4,marginInlineStart:'auto'}}>
      {onUndo&&<button type="button" onClick={onUndo} className="icon-btn" disabled={!canUndo} title="بازگرداندن ویرایش کارت" aria-label="بازگرداندن ویرایش کارت"><Undo2 size={19}/></button>}
      {onRedo&&<button type="button" onClick={onRedo} className="icon-btn" disabled={!canRedo} title="انجام دوباره ویرایش کارت" aria-label="انجام دوباره ویرایش کارت"><Redo2 size={19}/></button>}
      <button onClick={onClose} className="icon-btn" aria-label="بستن"><X size={21}/></button></div></div>
    <div className="drawer-scroll">
      <input className="task-edit-title" aria-label="عنوان کار" value={task.title} disabled={!canEdit} onChange={e=>update({title:e.target.value})}/>
      <nav className="task-quick-actions" aria-label="دسترسی سریع به بخش‌های کارت">
        <button type="button" onClick={()=>jumpToSection('metadata')} aria-controls="task-section-metadata"><CalendarDays size={15}/> مشخصات</button>
        <button type="button" onClick={()=>jumpToSection('description')} aria-controls="task-section-description"><FileText size={15}/> توضیحات</button>
        <button type="button" onClick={()=>jumpToSection('assignees')} aria-controls="task-section-assignees"><Users size={15}/> مسئولان</button>
        <button type="button" onClick={()=>jumpToSection('attachments')} aria-controls="task-section-attachments"><FolderOpen size={15}/> پیوست‌ها</button>
        <button type="button" onClick={()=>jumpToSection('checklist')} aria-controls="task-section-checklist"><ListChecks size={15}/> چک‌لیست <span className="task-quick-count">{done}/{total}</span></button>
        <button type="button" onClick={()=>jumpToSection('tags')} aria-controls="task-section-tags"><Tag size={15}/> برچسب‌ها</button>
        <button type="button" onClick={()=>jumpToSection('cover')} aria-controls="task-section-cover"><Palette size={15}/> کاور</button>
        {showOperations&&<button type="button" onClick={()=>jumpToSection('time')} aria-controls="task-section-time"><Clock3 size={15}/> زمان</button>}
        {showOperations&&<button type="button" onClick={()=>jumpToSection('dependencies')} aria-controls="task-section-dependencies"><ShieldCheck size={15}/> پیش‌نیازها</button>}
        <button type="button" onClick={()=>{setReportComposerOpen(true);jumpToSection('reports');}} aria-controls="task-section-reports"><MessageCircle size={15}/> گزارش</button>
      </nav>
      <details className="task-optional-block task-shared-disclosure" id="task-section-metadata" tabIndex={-1}
        open={sectionOpen.metadata} onToggle={event=>onSectionToggle('metadata',event)}>
        <summary><CalendarDays size={16}/> مشخصات</summary>
      <div className="edit-grid">
        <label>پروژه<select disabled={!canEdit} value={task.projectId} onChange={e=>update({projectId:e.target.value})}>{projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        {boards.filter(b=>b.projectId===task.projectId&&!b.archived).length>1&&
          <label>برد<select disabled={!canEdit} value={task.boardId||''} onChange={e=>update({boardId:e.target.value})}>
            {boards.filter(b=>b.projectId===task.projectId&&!b.archived).map(b=><option key={b.id} value={b.id}>{b.name}</option>)}
          </select></label>}
        <label>مرحله<select disabled={!canEdit} value={task.listId||task.status} onChange={e=>update({listId:e.target.value})}>{stages.map(s=><option key={s.id} value={s.id} disabled={s.archived===true&&s.id!==(task.listId||task.status)}>{s.label}{s.archived===true?' (بایگانی‌شده)':''}</option>)}</select></label>
        <label>اولویت<select disabled={!canEdit} value={task.priority} onChange={e=>update({priority:e.target.value})}>{priorities.map(p=><option key={p.id} value={p.id}>{p.label}</option>)}</select></label>
        <CalendarField value={task.dueDate||''} calendar={calendar} disabled={!canEdit} label="موعد انجام"
          popupOnClick onChange={dueDate=>update({dueDate})}/>
      </div>
      <div className="task-created-date"><CalendarDays size={15}/> تاریخ ثبت: {displayDate(task.createdAt,calendar,true)}</div>
      {!!task.orderCustomerName&&<div className="task-created-date">سفارش‌دهنده: {task.orderCustomerName}</div>}
      </details>
      <details className="task-optional-block task-shared-disclosure" id="task-section-description" tabIndex={-1}
        open={sectionOpen.description} onToggle={event=>onSectionToggle('description',event)}>
        <summary><FileText size={16}/> توضیحات</summary>
      <div className="edit-section"><h3><FileText size={17}/> توضیحات و جهت متن</h3><RichDescription disabled={!canEdit} value={task.description||''} direction={task.textDirection||'auto'} onChange={description=>update({description})} onDirection={textDirection=>update({textDirection})}/></div>
      </details>
      <details className="task-optional-block task-shared-disclosure" id="task-section-assignees" tabIndex={-1}
        open={sectionOpen.assignees} onToggle={event=>onSectionToggle('assignees',event)}>
        <summary><Users size={16}/> مسئولان کار <small>{(task.assignees||[]).length.toLocaleString('fa-IR')} نفر</small></summary>
        <div className="edit-section"><AssigneeSelector users={users} projectId={task.projectId} value={task.assignees||[]} disabled={!canEdit} onChange={assignees=>update({assignees})}/></div>
      </details>
      <details className="task-optional-block task-shared-disclosure" id="task-section-attachments" tabIndex={-1}
        open={sectionOpen.attachments} onToggle={event=>onSectionToggle('attachments',event)}>
        <summary><FolderOpen size={16}/> پیوست‌ها</summary>
      <div className="edit-section"><CardAttachments cardId={task.id} api={api} canEdit={canEdit}/></div>
      {showOperations&&<div className="edit-section"><CardComments cardId={task.id} api={api} canEdit={canEdit} username={username}/></div>}
      <details className="task-optional-block" defaultOpen={!!task.fileLinks?.length}>
        <summary><span>لینک فایل‌های اشتراکی</span>{!!task.fileLinks?.length&&<small>{task.fileLinks.length} لینک</small>}</summary>
        <div className="edit-section"><SharedLinks links={task.fileLinks||[]} canEdit={canEdit} api={api} onChange={fileLinks=>update({fileLinks})}/></div>
      </details>
      </details>
      <details className="task-optional-block task-shared-disclosure" id="task-section-checklist" tabIndex={-1}
        open={sectionOpen.checklist} onToggle={event=>onSectionToggle('checklist',event)}>
        <summary><ListChecks size={16}/> چک‌لیست <small>{done}/{total}</small></summary>
      <div className="edit-section"><div className="section-header"><h3><ListChecks size={17}/> مراحل انجام</h3><span>{done} / {total}</span></div>
        <div className="step-list">{task.checklist.map(c=><div className="task-compact-step" key={c.id}>
          <div className="step-row">
            <button type="button" disabled={!canEdit} className={'step-check '+(c.done?'checked':'')}
              aria-label={'تغییر وضعیت '+c.text} aria-pressed={Boolean(c.done)}
              onClick={()=>update({checklist:task.checklist.map(i=>i.id===c.id?{...i,done:!i.done}:i)})}>
              {c.done&&<Check size={14}/>}
            </button>
            <span className={c.done?'completed':''}>{c.text}</span>
            <button disabled={!canEdit||!canManage||Number(c.cost??0)!==0||!!c.expenseItems?.length} className="tiny-icon" title={Number(c.cost??0)!==0?'برای حذف مرحله ابتدا هزینه ثبت‌شده را بررسی کنید.':'حذف مرحله'} aria-label="حذف مرحله" onClick={()=>{const changes=removeUnpaidLegacyStep(task,c.id);if(changes)update(changes);}}><X size={14}/></button>
          </div>
          {priceEnabled&&<details className="task-step-cost-disclosure">
            <summary>هزینه مرحله{Number(c.cost||0)>0?' · '+money(c.cost)+' تومان':''}{!c.cost&&(c.costCategory||c.costDate)?' · دارای جزئیات':''}</summary>
            <div className="step-cost-fields">
              <label className="task-step-money-label">مبلغ<MoneyField disabled={!canEdit} value={c.cost||0} label={'هزینه مرحله '+c.text} onChange={cost=>update({checklist:task.checklist.map(i=>i.id===c.id?{...i,cost,costDate:i.costDate||(cost?todayISO():'')}:i)})}/></label>
              <label>دسته هزینه<input aria-label={'دسته هزینه مرحله '+c.text} maxLength={80} value={c.costCategory||''} disabled={!canEdit} placeholder="مثلاً پیک" onChange={e=>update({checklist:task.checklist.map(i=>i.id===c.id?{...i,costCategory:e.target.value}:i)})}/></label>
              <CalendarField label={'تاریخ هزینه مرحله '+c.text} calendar={calendar} value={c.costDate||''} disabled={!canEdit} onChange={costDate=>update({checklist:task.checklist.map(i=>i.id===c.id?{...i,costDate}:i)})}/>
            </div>
          </details>}
        </div>)}</div>
        {canManage&&task.checklist.map(step=><details key={step.id} className="task-optional-block task-step-expenses" defaultOpen={!!step.expenseItems?.length}>
          <summary>هزینه‌های مستقل مرحله: {step.text}{!!step.expenseItems?.length&&<small>{step.expenseItems.length} مورد</small>}</summary>
          <StageExpenseFields task={task} step={step}
            parties={Object.values(accountView?.parties||{})}
            existingJobs={accountView?.contractorJobs||{}}
            accountReady={Boolean(accountView)}
            canEdit={canEdit} onUpdate={update} onPrepare={onOpenPurchase}/>
        </details>)}
        {priceEnabled&&<div className="step-total">جمع هزینه‌های قدیمی این کار: <strong>{money((task.cost||0)+task.checklist.reduce((sum,c)=>sum+(c.cost||0),0))} تومان</strong></div>}
        {canEdit&&<div className="inline-create"><input value={newStep} onChange={e=>setNewStep(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();addStep();}}} placeholder="مرحله بعدی را بنویس..."/><button aria-label="افزودن مرحله" onClick={addStep}><Plus size={17}/></button></div>}
      </div>
      <details className="task-optional-block" defaultOpen={Boolean(task.checklistGroups?.length||task.checklists?.length)}>
        <summary>چک‌لیست‌های بیشتر</summary>
        <div className="edit-section"><CardChecklists task={task} hideLegacy disabled={!canEdit} onChange={update}/></div>
      </details>
      </details>
      <details className="task-optional-block task-shared-disclosure" id="task-section-tags" tabIndex={-1}
        open={sectionOpen.tags} onToggle={event=>onSectionToggle('tags',event)}>
        <summary><Tag size={16}/> برچسب‌ها</summary>
      <div className="edit-section"><h3><Tag size={17}/> برچسب</h3><LabelEditor labels={task.labels||[]} colors={task.labelColors||{}} onChange={({labels,labelColors})=>update({labels,labelColors})} disabled={!canEdit}/></div>
      </details>
      <details className="task-optional-block task-shared-disclosure" id="task-section-cover" tabIndex={-1} open={sectionOpen.cover} onToggle={event=>onSectionToggle('cover',event)}>
        <summary><span>کاور کارت</span>{task.cover&&<small>فعال</small>}</summary>
        <div className="edit-section"><CardCover task={task} disabled={!canEdit} onChange={update}/></div>
      </details>
      {showOperations&&<details className="task-optional-block task-shared-disclosure" id="task-section-time" tabIndex={-1}
        open={sectionOpen.time} onToggle={event=>onSectionToggle('time',event)}>
        <summary><Clock3 size={16}/> مدیریت زمان</summary>
        <div className="edit-section"><div className="time-inputs"><label>زمان برآوردی (دقیقه)<input type="number" min="0" max="5256000" value={task.estimatedMinutes||0} disabled={!canEdit} onChange={e=>update({estimatedMinutes:Math.min(5256000,Math.max(0,Number(e.target.value)||0))})}/></label><label>زمان واقعی ثبت‌شده (دقیقه)<input type="number" min="0" max="5256000" value={task.actualMinutes||0} disabled={!canEdit} onChange={e=>update({actualMinutes:Math.min(5256000,Math.max(0,Number(e.target.value)||0))})}/></label></div><small>زمان‌ها جدا از هزینه ثبت می‌شوند و در داشبورد پروژه محاسبه خواهند شد.</small></div>
      </details>}
      {showOperations&&<details className="task-optional-block task-shared-disclosure" id="task-section-dependencies" tabIndex={-1}
        open={sectionOpen.dependencies} onToggle={event=>onSectionToggle('dependencies',event)}>
        <summary><ShieldCheck size={16}/> پیش‌نیازها و موانع انجام <small>{(task.dependencies||[]).length.toLocaleString('fa-IR')} مورد</small></summary>
        <CardDependencyPanel task={task} allTasks={allTasks} canEdit={canEdit} onChange={dependencies=>update({dependencies})}/>
      </details>}
      <details className="task-optional-block task-shared-disclosure" id="task-section-reports" tabIndex={-1}
        open={sectionOpen.reports} onToggle={event=>onSectionToggle('reports',event)}>
        <summary><MessageCircle size={16}/> گزارش پیشرفت <small>{task.reports.length.toLocaleString('fa-IR')} گزارش</small></summary>
        <div className="edit-section">
        <div className="section-header task-section-heading"><h3><MessageCircle size={17}/> گزارش پیشرفت</h3>
          {canEdit&&<button className="task-inline-action" type="button" aria-expanded={reportComposerOpen} onClick={()=>setReportComposerOpen(previous=>!previous)}><Plus size={15}/>{reportComposerOpen?'بستن فرم':'افزودن گزارش'}</button>}
        </div>
        <div className="report-list">{task.reports.length?task.reports.slice().reverse().map(r=><div className="report-entry" key={r.id}><div className="report-entry-top"><span className="agent-avatar"><Zap size={12}/></span><strong>{r.agent}</strong><small>{shortDate(r.createdAt)}</small></div><p>{r.summary}</p></div>):<div className="empty-reports">هنوز گزارشی ثبت نشده است.</div>}</div>
        {canEdit&&reportComposerOpen&&<div className="report-composer"><input value={agent} onChange={e=>setAgent(e.target.value)} placeholder="نام ایجنت یا مسئول (اختیاری)" aria-label="نام مسئول"/><textarea rows={2} value={summary} onChange={e=>setSummary(e.target.value)} placeholder="یک خط درباره آخرین نتیجه کار..." aria-label="گزارش یک‌خطی"/><button className="btn primary" onClick={addReport} disabled={!summary.trim()}><Plus size={16}/> ثبت گزارش</button></div>}
        </div>
      </details>
      <details className="task-optional-block task-shared-disclosure" id="task-section-accounting" tabIndex={-1}
        open={sectionOpen.accounting} onToggle={event=>onSectionToggle('accounting',event)}>
        <summary><Wallet size={16}/> ثبت در حسابداری</summary>
      <OrderSaleFields task={task} api={api} onUpdate={update}
        onPrepare={onOpenSale} canEdit={canEdit} canManage={canManage}/>
      </details>
      <details className="task-optional-block task-shared-disclosure" id="task-section-settings" tabIndex={-1}
        open={sectionOpen.settings} onToggle={event=>onSectionToggle('settings',event)}>
        <summary><Settings2 size={16}/> تنظیمات کارت و برد</summary>
        <div className="edit-section task-card-settings">
          <div className="task-card-settings__launchers">
            <AutomationButtonsLauncher scope="card" onClick={()=>{
              setAutomationButtonsOpen(open=>automationButtonView==='card'?!open:true);
              setAutomationButtonView('card');
            }} disabled={!task.boardId}/>
            <AutomationButtonsLauncher scope="board" onClick={()=>{
              setAutomationButtonsOpen(open=>automationButtonView==='board'?!open:true);
              setAutomationButtonView('board');
            }} disabled={!task.boardId}/>
          </div>
          {task.boardId&&typeof api?.automationButtonsList==='function'&&
            <AutomationButtonStrip api={api} projectId={task.projectId} boardId={task.boardId}
              scope="card" cardId={task.id} canRun={canEdit} onCloseCard={onClose}/>}
          {automationButtonsOpen&&<AutomationButtonsPanel key={automationButtonView} api={api} project={projects.find(p=>p.id===task.projectId)}
            boardId={task.boardId||''} users={users} cardId={task.id}
            initialScope={automationButtonView} canManage={canManage} canRun={canEdit}
            onCloseCard={onClose}/>}
        </div>
      {canManage&&showCosts&&<div className="edit-section"><h3>تنظیمات هزینه همین کارت</h3><label className="setting-toggle"><input type="checkbox" disabled={!canEdit} checked={priceEnabled} onChange={e=>update({costEnabled:e.target.checked})}/><span><strong>فعال‌کردن فیلد هزینه</strong><small>فقط همین کارت؛ تنظیم کلی پروژه را تغییر نمی‌دهد.</small></span></label>{task.costEnabled!==null&&task.costEnabled!==undefined&&canEdit&&<button className="subtle-action" onClick={()=>update({costEnabled:null})}>بازگشت به تنظیم پیش‌فرض پروژه</button>}</div>}
      {showOperations&&taskBoard&&<details className="task-optional-block task-card-custom-fields" open={customFieldsOpen} onToggle={event=>setCustomFieldsOpen(event.currentTarget.open)}>
        <summary><span>فیلدهای سفارشی</span>{!!taskBoard.customFields?.length&&<small>{taskBoard.customFields.length} فیلد</small>}</summary>
        <div className="edit-section"><CardCustomFields task={task} board={taskBoard} calendar={calendar} disabled={!canEdit} onChange={update}/>
          {canManage&&<details className="task-board-field-settings">
            <summary>مدیریت فیلدهای این برد</summary>
            <BoardFieldEditor board={taskBoard} tasks={allTasks} templates={allTemplates} disabled={!canManage} onChange={onBoardChange}/>
          </details>}
        </div>
      </details>}
      {priceEnabled&&<div className="edit-section task-direct-cost-fields"><h3>هزینه مستقیم کار</h3><MoneyField disabled={!canEdit} value={task.cost||0} label="هزینه مستقیم این کار" onChange={cost=>update({cost,costDate:task.costDate||(cost?todayISO():'')})}/><label className="expense-category-field">دسته هزینه<input maxLength={80} value={task.costCategory||''} disabled={!canEdit} placeholder="مثلاً پیک، چاپ، حمل‌ونقل" onChange={e=>update({costCategory:e.target.value})}/></label><CalendarField label="تاریخ هزینه مستقیم" calendar={calendar} value={task.costDate||''} disabled={!canEdit} onChange={costDate=>update({costDate})}/><p className="money-help">تاریخ واردشده برای گزارش هزینه در بازه زمانی استفاده می‌شود. هزینه‌های قدیمی بدون تاریخ اختصاصی با تاریخ آخرین ویرایش کارت گزارش می‌شوند.</p></div>}
      {!!suggestedTasks.length&&<div className="edit-section"><h3><Copy size={17}/> پیشنهاد کارهای مشابه</h3>{suggestedTasks.map(({task:t,score})=><div className="similar-row" key={t.id}><span>{t.title}<small>{Math.round(score*100)}٪ شباهت</small></span><button disabled={!canEdit} onClick={()=>onDuplicate(t)}>ساخت مشابه</button></div>)}</div>}
      </details>
      {canEdit&&<div className="drawer-danger">
        {confirmArchive?<div className="delete-confirm"><span>کارت بایگانی شود؟ اطلاعات و فایل‌ها محفوظ می‌مانند و بعداً قابل بازیابی هستند.</span>
          <button onClick={onArchive}>تأیید آرشیو</button><button onClick={()=>setConfirmArchive(false)}>انصراف</button></div>
          :<button className="danger-link task-archive-link" onClick={()=>{setConfirmArchive(true);setConfirmDelete(false);}}><Archive size={16}/> آرشیو</button>}
        {confirmDelete?<div className="delete-confirm"><span>کارت به زباله‌دان منتقل شود؟ تمام هزینه‌ها، فایل‌ها و گزارش‌ها حفظ می‌شوند.</span><button onClick={onDelete}>تأیید حذف</button><button onClick={()=>setConfirmDelete(false)}>انصراف</button></div>:<button className="danger-link" onClick={()=>{setConfirmDelete(true);setConfirmArchive(false);}}><Trash2 size={16}/> حذف</button>}
      </div>}
    </div>
  </aside></div>;
}

function DrivePanel({data,onClose,onRestore,onRestoreStart,onRestoreFinished,isClient=false}){
  const [id,setId]=useState(data.settings.googleClientId||'');
  const [connected,setConnected]=useState(false);
  const [backups,setBackups]=useState([]);
  const [busy,setBusy]=useState('');
  const [message,setMessage]=useState('');
  const [restoreId,setRestoreId]=useState('');
  const [localBackups,setLocalBackups]=useState([]);
  const [folder,setFolder]=useState({configured:false,folder:'',available:false});
  const [folderFiles,setFolderFiles]=useState([]);
  const [peerStatus,setPeerStatus]=useState({paired:false,enabled:false});
  const [peerCode,setPeerCode]=useState('');
  const [showPeerCode,setShowPeerCode]=useState(false);
  const [storageStatus,setStorageStatus]=useState(null);
  const [automationStatus,setAutomationStatus]=useState(null);
  const [automaticBackup,setAutomaticBackup]=useState(null);
  useEffect(()=>{api.driveStatus().then(s=>{setConnected(s.connected);if(s.clientId)setId(s.clientId);}).catch(e=>setMessage(e.message));},[]);
  useEffect(()=>{api.listLocalBackups().then(setLocalBackups).catch(()=>{});},[]);
  useEffect(()=>{api.driveFolderStatus().then(setFolder).catch(e=>setMessage(e.message));api.driveFolderList().then(setFolderFiles).catch(()=>{});},[]);
  useEffect(()=>{api.cloudPeerStatus().then(setPeerStatus).catch(()=>{});},[]);
  useEffect(()=>{if(typeof api.storageStatus==='function')api.storageStatus().then(setStorageStatus).catch(e=>setMessage(e.message));},[]);
  useEffect(()=>{if(typeof api.automationEngineStatus==='function')api.automationEngineStatus().then(setAutomationStatus).catch(e=>setMessage(e.message));},[]);
  useEffect(()=>{
    if(typeof api.automaticBackupStatus!=='function')return;
    let mounted=true;
    const readBackupHealth=()=>api.automaticBackupStatus()
      .then(status=>{if(mounted)setAutomaticBackup(status);})
      .catch(error=>{if(mounted)setAutomaticBackup({running:false,lastError:String(error.message||error)});});
    readBackupHealth();
    const timer=setInterval(readBackupHealth,30000);
    return()=>{mounted=false;clearInterval(timer);};
  },[]);
  const operation=async(name,fn)=>{setBusy(name);setMessage('');try{await fn();}catch(e){setMessage(e.message||String(e));}finally{setBusy('');}};
  const guardedRestore=async load=>{
    // Acquire the restore barrier before any host call; release it only after
    // the restored state was accepted or the outcome was marked uncertain.
    onRestoreStart?.();
    let outcome='failed';
    try{
      const state=await load();
      if(state==null){outcome='cancel';return;}
      // A native backup restore returns the raw stored document, which does
      // not contain the host-issued __localRevision required by saveState CAS.
      // Read back from the authoritative host AFTER restoration, still under
      // the exclusive restore barrier. Never allow the next edit to save with
      // a missing/stale token or assume a successful host mutation on read fail.
      const authoritative=await (typeof api.getStateForUi==='function'?
        api.getStateForUi():api.getState());
      if(!authoritative||typeof authoritative!=='object')
        throw Error('بازخوانی نسخه بازیابی‌شده از میزبان معتبر نیست.');
      onRestore(authoritative);
      outcome='applied';
    }finally{onRestoreFinished?.(outcome);}
  };
  const fetchBackups=async()=>{const items=await api.driveList();setBackups(items);};
  const connect=()=>operation('connect',async()=>{await api.driveConnect(id.trim());setConnected(true);setMessage('حساب Google Drive متصل شد.');await fetchBackups();});
  const upload=()=>operation('upload',async()=>{await api.driveUpload();await fetchBackups();setMessage('نسخه پشتیبان با موفقیت در Google Drive ذخیره شد.');});
  const restore=()=>operation('restore',async()=>guardedRestore(()=>api.driveRestore(restoreId)));
  const selectFolder=()=>operation('folder',async()=>{
    const result=await api.chooseDriveFolder();
    if(!result.canceled){setFolder(await api.driveFolderStatus());setFolderFiles(await api.driveFolderList());setMessage('پوشه ذخیره‌سازی انتخاب شد. همگام‌سازی اینترنتی این پوشه را برنامه Google Drive for desktop انجام می‌دهد.');}
  });
  const folderBackup=()=>operation('folder-backup',async()=>{
    const result=await api.driveFolderBackup();
    if(result?.name){setFolderFiles(await api.driveFolderList());setMessage('نسخه اطلاعات داخل پوشه همگام‌شده ثبت شد: '+result.name);}
    else setMessage('ابتدا پوشه Google Drive for desktop را انتخاب و در ویندوز قابل‌دسترسی کنید.');
  });
  return <Modal title="پشتیبان‌گیری" onClose={onClose} width={610}>
    <div className="dialog-body cloud-panel">
      <div className="cloud-hero"><div className="cloud-hero-icon"><HardDriveDownload size={27}/></div><div><strong>پشتیبان‌گیری، بدون تنظیمات فنی</strong><p>یک نسخه از اطلاعات اصلی برنامه نگه دارید. برای نگهداری نسخه در فضای ابری، کافی است پوشه همگام‌شده را انتخاب کنید؛ نیازی به گرفتن API یا شناسه گوگل نیست.</p></div></div>
      <section className="backup-easy-quick" aria-label="پشتیبان‌گیری سریع">
        {automaticBackup&&<p className={'backup-easy-limitation'+(hostBackupHealth(automaticBackup,isClient).kind==='error'?' backup-easy-limitation--error':'')} role="status">
          {hostBackupHealth(automaticBackup,isClient).description}
          {!isClient&&automaticBackup.lastSuccess&&<> آخرین موفقیت: {new Date(automaticBackup.lastSuccess).toLocaleString('fa-IR')}.</>}
          {' '}این نسخه‌ها کامل نیستند و پیوست‌ها و حساب‌های شبکه را شامل نمی‌شوند.
        </p>}
        <div className="backup-easy-quick__item"><div><strong>۱. ذخیره روی این رایانه</strong><small>{isClient?'ایجاد پشتیبان به رایانه میزبان محدود است.':'نسخه‌ای از اطلاعات اصلی ذخیره می‌شود. پیوست‌ها و حساب‌های شبکه جداگانه‌اند.'}</small></div>
          <button className="btn primary" disabled={!!busy||isClient} onClick={()=>operation('local',async()=>{
            const result=await api.createLocalBackup();
            setLocalBackups(await api.listLocalBackups());
            setMessage('نسخه پشتیبان محلی ایجاد شد: '+result.name+' (شامل همه فایل‌های پیوست یا حساب‌های LAN نیست).');
          })}><HardDriveDownload size={17}/> ایجاد پشتیبان</button>
        </div>
        <div className="backup-easy-quick__item"><div><strong>۲. نگهداری در پوشه همگام‌شده (اختیاری)</strong><small>برنامه Google Drive for desktop همگام‌سازی پوشه را انجام می‌دهد؛ این کار به OAuth یا Google Cloud Console نیاز ندارد.</small></div>
          <div className="backup-easy-quick__buttons">
            <button className="btn secondary" disabled={!!busy} onClick={selectFolder}><FolderOpen size={16}/> انتخاب پوشه</button>
            {folder.configured&&<button className="btn secondary" disabled={!!busy||!folder.available} onClick={folderBackup}><CloudUpload size={16}/> ذخیره در پوشه</button>}
          </div>
        </div>
        {folder.configured&&<p className="backup-easy-quick__path" role="status">پوشه انتخاب‌شده: <span dir="ltr">{folder.folder}</span> · {folder.available?'در دسترس':'در دسترس نیست'}</p>}
        {!!localBackups.length&&<div className="backup-easy-recent"><strong>آخرین نسخه‌های محلی</strong>{localBackups.slice(0,3).map(item=><div key={item.name}><small dir="ltr">{item.name}</small><button disabled={!!busy} onClick={()=>operation('restore-local',async()=>{
          if(!window.confirm('این نسخه اطلاعات فعلی را جایگزین می‌کند. پیش از بازیابی، از اطلاعات فعلی نسخه ایمنی گرفته می‌شود. ادامه می‌دهید؟'))return;
          await guardedRestore(()=>api.restoreLocalBackup(item.name));
        })}>بازیابی</button></div>)}</div>}
        <p className="backup-easy-limitation">این‌ها پشتیبان کامل همه اجزای مدار نیستند؛ به‌ویژه فایل‌های پیوست، حساب‌های LAN و اطلاعات شخصی برنامه‌ریز پوشش جداگانه دارند.</p>
      </section>
      {message&&<div className="inline-message" role="status">{message}</div>}
      <details className="backup-easy-more"><summary><Settings2 size={17}/> روش‌های بیشتر، بازیابی و تنظیمات پیشرفته <ChevronDown size={16}/></summary><div className="backup-easy-more__content">
      <div className="cloud-state"><span className={'connection-dot '+(connected?'online':'')}/><span>{connected?'حساب Google Drive متصل است':'هنوز به حساب Google متصل نشده‌ای'}</span><small>{isDesktop?'برنامه ویندوز':'حالت پیش‌نمایش'}</small></div>
      <div className="drive-simple"><strong><Cloud size={18}/> اتصال ساده با Google Drive for desktop</strong><p>۱. برنامه رسمی Google Drive for desktop را روی هر سیستم نصب و با حساب Google یکسان وارد شو. ۲. یک پوشه همگام‌شده برای مدار انتخاب کن. ۳. نسخه‌های بازیابی بدون تنظیم OAuth Client ID داخل همان پوشه نگهداری می‌شوند.</p><div className="drive-simple-actions"><button disabled={!!busy} className="btn primary" onClick={selectFolder}><FolderOpen size={17}/> انتخاب پوشه همگام‌شده</button>{folder.configured&&<button disabled={!!busy||!folder.available} className="btn secondary" onClick={folderBackup}><CloudUpload size={17}/> ذخیره نسخه حالا</button>}{folder.configured&&<button disabled={!!busy} className="btn secondary" onClick={()=>operation('list-folder',async()=>setFolderFiles(await api.driveFolderList()))}><RefreshCw size={15}/> فهرست نسخه‌ها</button>}</div>{folder.configured&&<div className="drive-path"><span className={folder.available?'positive':'warning'}>{folder.available?'پوشه در دسترس است':'پوشه در دسترس نیست'}</span><code dir="ltr">{folder.folder}</code></div>}{folderFiles.length>0&&<div className="drive-folder-files"><strong>نسخه‌های موجود در پوشه</strong>{folderFiles.slice(0,12).map(file=><div key={file.name}><small dir="ltr" title={file.name}>{file.name}</small><button disabled={!!busy} onClick={()=>operation('restore-folder',async()=>{if(!window.confirm('این نسخه جایگزین اطلاعات محلی می‌شود و از نسخه فعلی بکاپ ایمن گرفته خواهد شد. ادامه می‌دهید؟'))return;await guardedRestore(()=>api.driveFolderRestore(file.name));})}>بازیابی</button></div>)}</div>}<small>Google Drive for desktop باید فایل‌ها را واقعاً با اینترنت همگام کند. این روش جایگزین سرور مشترک چندکاربره نیست؛ هنگامی که سرور قطع باشد، ویرایش‌ها در کلاینت صف می‌شوند و پس از اتصال دوباره با بررسی تعارض اعمال خواهند شد. فایل‌های SMB منتقل نمی‌شوند.</small></div>
      <div className="drive-peer">
        <strong><Users size={17}/> تبادل آزمایشی تغییرات هنگام قطع میزبان</strong>
        <p>دو رایانه با همان حساب LAN، پوشه Drive همگام‌شده یکسان و کد جفت‌سازی مشترک می‌توانند تغییرات کارت‌های متفاوت را در زمان قطعی مبادله کنند. تعارض یک کارت متوقف و گزارش می‌شود. رمز جفت‌سازی در پوشه Drive ذخیره نمی‌شود.</p>
        <small>{peerStatus.enabled?'تبادل پوشه‌ای روی این کلاینت فعال است':peerStatus.paired?'کد ذخیره شده است؛ پوشه یا اتصال کلاینت بررسی شود':'هنوز کد جفت‌سازی ثبت نشده است'}</small>
        <div className="drive-simple-actions">
          <button className="btn secondary" disabled={!!busy} onClick={()=>operation('peer-generate',async()=>{const result=await api.cloudPeerGenerate();setPeerCode(result.code);setShowPeerCode(true);setPeerStatus(result.status);setMessage('کد جدید ایجاد شد. آن را فقط با رایانه مورد اعتماد همان حساب LAN به اشتراک بگذار.');})}>ایجاد کد مشترک</button>
          {peerStatus.paired&&<button className="btn secondary" disabled={!!busy} onClick={()=>operation('peer-forget',async()=>{setPeerStatus(await api.cloudPeerForget());setPeerCode('');setShowPeerCode(false);})}>غیرفعال‌کردن</button>}
        </div>
        <label>کد مشترک رایانه اول را اینجا وارد کن</label>
        <div className="drive-simple-actions"><input dir="ltr" type="text" autoComplete="off" aria-label="کد جفت‌سازی" value={peerCode} onChange={e=>setPeerCode(e.target.value.trim())} placeholder="کد جفت‌سازی حداقل ۲۴ کاراکتری"/><button className="btn primary" disabled={!!busy||peerCode.length<24} onClick={()=>operation('peer-pair',async()=>{setPeerStatus(await api.cloudPeerConfigure(peerCode));setPeerCode('');setShowPeerCode(false);setMessage('کد جفت‌سازی روی این دستگاه ذخیره شد.');})}>ثبت کد</button></div>
        {showPeerCode&&<small>کد بالا را پیش از بستن این پنجره روی رایانه دوم وارد کن. با ساخت کد جدید، رویدادهای امضاشده با کد قبلی دیگر قابل خواندن نیستند.</small>}
        <small>محدودیت: فایل‌ها تا تأیید Google Drive for desktop روی دستگاه مقابل دیده نمی‌شوند؛ پوشه Drive خودبه‌خود مجوز LAN نمی‌دهد؛ حساب‌های مختلف، تغییر ساختار برد و فایل‌های SMB از این مسیر پشتیبانی نمی‌شوند. داده این مسیر رمزگذاری سرتاسری نشده و آزمایش دو سیستم واقعی هنوز انجام نشده است.</small>
      </div>
      {!connected&&<details className="drive-advanced"><summary>روش پیشرفته اتصال مستقیم Google API (اختیاری)</summary><div className="settings-field"><label>Google OAuth Desktop Client ID</label><input dir="ltr" placeholder="12345-....apps.googleusercontent.com" value={id} onChange={e=>setId(e.target.value)}/><p>فقط برای ساخت پشتیبان از Google API. یک‌بار باید از Google Cloud Console شناسه Desktop Client خودتان را تعریف کنید. واردکردن همان ایمیل بدون مجوز اپلیکیشن کافی نیست.</p><button className="btn secondary" disabled={!!busy||!id.trim()} onClick={connect}>{busy==='connect'?<LoaderCircle className="spin" size={16}/>:<Cloud size={16}/>} اتصال API Google</button></div></details>}
      {connected&&<><div className="cloud-actions"><button className="btn primary" disabled={!!busy} onClick={upload}><CloudUpload size={17}/> ذخیره پشتیبان جدید</button><button className="btn secondary" disabled={!!busy} onClick={()=>operation('list',fetchBackups)}><CloudDownload size={17}/> نمایش نسخه‌ها</button></div><div className="backup-list"><h4>نسخه‌های موجود در Drive</h4>{backups.length?backups.map(b=><div className="backup-row" key={b.id}><div><FileText size={17}/><div><strong>{shortDate(b.createdAt)} · {new Date(b.createdAt).toLocaleTimeString('fa-IR',{hour:'2-digit',minute:'2-digit'})}</strong><small>{b.name}</small></div></div><button onClick={()=>setRestoreId(b.id)}>بازیابی</button></div>):<p>نسخه‌ای یافت نشد. برای شروع یک پشتیبان جدید بساز.</p>}</div><button className="subtle-action" onClick={()=>operation('disconnect',async()=>{await api.driveDisconnect();setConnected(false);setBackups([]);})}>قطع اتصال Google</button></>}
      {!!restoreId&&<div className="warning-strip"><strong>جایگزینی اطلاعات محلی</strong><p>اطلاعات فعلی با نسخه انتخاب‌شده جایگزین می‌شود. ابتدا یک کپی محلی از اطلاعات فعلی ذخیره خواهد شد.</p><div><button onClick={()=>setRestoreId('')} className="btn secondary">انصراف</button><button disabled={!!busy} className="btn primary" onClick={restore}>تأیید بازیابی</button></div></div>}
      <div className="local-backups"><button className="btn secondary" onClick={()=>operation('export',async()=>{const result=await api.exportBackup();if(!result.canceled)setMessage('فایل پشتیبان ذخیره شد.');})}><Download size={16}/> خروجی JSON</button><button className="btn secondary" onClick={()=>operation('import',async()=>{if(!window.confirm('اطلاعات فعلی جایگزین شوند؟ یک کپی خودکار از داده‌های قبلی نگهداری می‌شود.'))return;await guardedRestore(async()=>{const result=await api.importBackup();return result?.state??null;});})}><ArrowDownToLine size={16}/> ورود JSON</button></div>
      <div className="local-backup-section"><h3><HardDriveDownload size={17}/> نسخه‌های پشتیبان روی این کامپیوتر</h3><div className="local-backups"><button className="btn primary" disabled={!!busy||isClient} onClick={()=>operation('local',async()=>{const result=await api.createLocalBackup();setLocalBackups(await api.listLocalBackups());setMessage('پشتیبان ناقص اما اعتبارسنجی‌شده ایجاد شد: '+result.name);})}>ایجاد پشتیبان محلی</button><button className="btn secondary" disabled={!!busy||isClient} onClick={()=>operation('load-local',async()=>setLocalBackups(await api.listLocalBackups()))}>تازه‌سازی فهرست</button><button className="btn secondary" disabled={!!busy||isClient} onClick={()=>operation('attachments-backup',async()=>{const result=await api.attachmentBackup();setMessage('پشتیبان مجزای '+result.blobs+' فایل پیوست روی میزبان ایجاد شد: '+result.path);})}>بکاپ جداگانه پیوست‌ها</button><button className="btn secondary" disabled={!!busy||isClient} onClick={()=>operation('sqlite-export',async()=>{const result=await api.createUnifiedSqliteBackup();setMessage('خروجی آزمایشی SQLite یکپارچه ایجاد شد: '+result.path);})}>خروجی SQLite یکپارچه</button></div>{localBackups.map(item=><div className="backup-row" key={item.name}><div><FileText size={16}/><small dir="ltr">{item.name}</small></div><button disabled={!!busy||isClient} onClick={()=>operation('restore-local',async()=>{if(!window.confirm('این نسخه بازیابی و داده فعلی جایگزین شود؟ از داده فعلی نسخه ایمنی ساخته می‌شود.'))return;await guardedRestore(()=>api.restoreLocalBackup(item.name));})}>بازیابی</button></div>)}</div>
      <aside role="note" className="warning-strip"><strong>محدوده واقعی پشتیبان‌ها</strong><p>خروجی JSON و Google Drive فقط اطلاعات اصلی کارها و بردها را منتقل می‌کنند. فایل SQLite محلی دامنه‌های ثبت‌شده در پایگاه داده را دارد، اما فایل‌های پیوست و حساب‌های LAN را شامل نمی‌شود. برنامه‌ریزی شخصی در حافظه همین دستگاه ذخیره می‌شود و در هیچ‌یک از این خروجی‌ها نیست. برای بازیابی گسترده همراه با پیوست‌ها از ابزار مستقل maintenance_recovery.py فقط پس از توقف کامل برنامه و نویسنده‌های شبکه استفاده کنید؛ آرشیو آن رمزنگاری نشده است.</p></aside>
      {storageStatus&&<section className="unified-storage-panel"><h3><HardDriveDownload size={17}/> ذخیره‌سازی یکپارچه SQLite</h3>
        <p className={storageStatus.mode==='sqlite'?'positive':'warning'}>وضعیت میزبان: {storageStatus.mode==='sqlite'?'SQLite فعال':'ذخیره‌سازی فایل‌های JSON'}{storageStatus.revision!=null?' · نسخه '+storageStatus.revision:''}</p>
        {storageStatus.mode!=='sqlite'&&<><p>فعال‌سازی، اطلاعات فعلی را با پشتیبان ایمنی به پایگاه داده SQLite منتقل می‌کند. بازگشت مستقیم به ذخیره‌سازی JSON از این پنجره فراهم نیست. پیش از اقدام از داده‌ها نسخه پشتیبان مستقل نگهدارید.</p>
          <button className="btn secondary" disabled={!!busy||!storageStatus.ready||typeof api.enableUnifiedStorage!=='function'} onClick={()=>operation('enable-storage',async()=>{
            if(!window.confirm('ذخیره‌سازی SQLite برای این میزبان فعال شود؟ مهاجرت یک‌طرفه است؛ ابتدا از اطلاعات فعلی نسخه پشتیبان مستقل تهیه کنید. ادامه؟'))return;
            const result=await api.enableUnifiedStorage();setStorageStatus(result);setAutomationStatus(await api.automationEngineStatus());setMessage('SQLite فعال شد؛ داده‌ها را دوباره از میزبان دریافت کنید.');
          })}>فعال‌سازی ذخیره‌سازی یکپارچه</button>
          {!storageStatus.ready&&<small className="warning">فعال‌سازی اکنون از طرف میزبان مجاز نیست.</small>}
        </>}
      </section>}
      {automationStatus&&<section className="unified-storage-panel"><h3><Activity size={17}/> موتور صف و گزارش اجرای قوانین</h3>
        <p>وضعیت: {automationStatus.mode==='active'?'فعال':automationStatus.mode==='disabled'?'در انتظار فعال‌سازی':automationStatus.mode==='remote'?'فقط میزبان':'ذخیره‌سازی قدیمی'}؛ در صف: {automationStatus.pending||0}؛ متوقف‌شده: {automationStatus.dead||0}</p>
        {automationStatus.mode==='disabled'&&<><small className="warning">فعال‌سازی یک‌طرفه است. نسخه‌های قدیمی EXE نمی‌توانند داده جدید دارای ژورنال اتوماسیون را باز کنند؛ از پایگاه داده پیش از فعال‌سازی یک نسخه پشتیبان تهیه می‌شود.</small>
          <button className="btn secondary" disabled={!!busy||!automationStatus.ready} onClick={()=>operation('enable-automation',async()=>{
            if(!window.confirm('موتور جدید صف اتوماسیون فعال شود؟ بازگشت با EXE قبلی بدون بازیابی نسخه پیش از فعال‌سازی ممکن نیست. ادامه می‌دهید؟'))return;
            const response=await api.enableAutomationEngine();setAutomationStatus(response);setMessage('موتور رویدادها فعال شد و پشتیبان اولیه ثبت شد: '+response.preActivationBackup);
          })}>فعال‌سازی موتور اتوماسیون با پشتیبان ایمنی</button></>}
      </section>}
      <p className="cloud-note"><ShieldCheck size={15}/> روش API از پوشه خصوصی appData استفاده می‌کند؛ روش Drive for desktop از پوشه انتخابی داخل ویندوز. حساب‌های LAN و رمزها در این پشتیبان‌ها قرار نمی‌گیرند.</p>
      </div></details>
    </div>
  </Modal>;
}

function IntegrationKeyPanel({api,users,onClose}){
  const [username,setUsername]=useState(users[0]?.username||'');
  const [writeAccess,setWriteAccess]=useState(false);
  const [issued,setIssued]=useState(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const issue=async()=>{
    setBusy(true);setError('');setIssued(null);
    try{setIssued(await api.integrationIssueKey(username,writeAccess?['read','write']:['read'],3600));}
    catch(e){setError(e.message||String(e));}
    finally{setBusy(false);}
  };
  const revoke=async()=>{
    if(!issued)return;
    setBusy(true);setError('');
    try{await api.integrationRevokeKey(issued.keyId);setIssued(null);}
    catch(e){setError(e.message||String(e));}
    finally{setBusy(false);}
  };
  return <Modal title="کلید API یکپارچه‌سازی" onClose={onClose} width={580}>
    <div className="dialog-body">
      <p>این کلید فقط با شبکه HTTPS فعال معتبر است، یک ساعت عمر دارد و پس از بستن این پنجره دیگر قابل نمایش نیست. آن را فقط در برنامه مورد اعتماد نگهداری کنید.</p>
      <label>حساب هدف<select disabled={busy||!!issued} value={username} onChange={e=>setUsername(e.target.value)}>{users.map(u=><option value={u.username} key={u.username}>{u.displayName||u.username} ({u.role})</option>)}</select></label>
      <label className="setting-toggle"><input type="checkbox" disabled={busy||!!issued} checked={writeAccess} onChange={e=>setWriteAccess(e.target.checked)}/><span>اجازه ویرایش عنوان کارت‌ها (بدون دسترسی مالی)</span></label>
      {!issued&&<button className="btn primary" disabled={busy||!username} onClick={issue}>ساخت کلید یک‌ساعته</button>}
      {issued&&<div role="status" className="inline-message"><p>کلید فقط همین یک‌بار نمایش داده می‌شود:</p><textarea dir="ltr" aria-label="کلید API ساخته‌شده" readOnly value={issued.key} rows={3} onFocus={e=>e.target.select()}/><small>شناسه: {issued.keyId} | مسیر: /integrations/v1/</small><div><button className="btn secondary" disabled={busy} onClick={revoke}>ابطال کلید</button></div></div>}
      {error&&<p role="alert" className="error-toast">{error}</p>}
    </div>
  </Modal>;
}

function CalendarFilePanel({api,projects,boards,onImport,onClose}){
  const eligible=projects.filter(p=>boards.some(b=>b.projectId===p.id&&!b.archived&&b.stages?.length));
  const [project,setProject]=useState(eligible[0]?.id||'');
  const [preview,setPreview]=useState(null);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const read=async e=>{
    setPreview(null);setError('');
    const file=e.target.files?.[0];if(!file)return;
    if(file.size>2000000){setError('حجم فایل ICS بیش از حد مجاز است.');return;}
    setBusy(true);
    try{setPreview(await api.calendarImportPreview(await file.text()));}
    catch(err){setError(err.message||String(err));}
    finally{setBusy(false);}
  };
  const exportFile=async()=>{
    setError('');setBusy(true);
    try{
      const content=await api.calendarExportIcs();
      const blob=new Blob([content],{type:'text/calendar;charset=utf-8'});
      const href=URL.createObjectURL(blob);
      const a=document.createElement('a');a.href=href;a.download='madar-calendar.ics';a.click();
      setTimeout(()=>URL.revokeObjectURL(href),1000);
    }catch(err){setError(err.message||String(err));}finally{setBusy(false);}
  };
  return <Modal title="تبادل فایل تقویم ICS" onClose={onClose} width={580}>
    <div className="dialog-body">
      <p>خروجی از عنوان و موعد کارت‌های قابل‌مشاهده ساخته می‌شود. فایل‌های ICS خروجی Google Calendar و Outlook قابل بررسی و ورود هستند؛ اتصال و همگام‌سازی مستقیم انجام نمی‌شود.</p>
      <button className="btn secondary" disabled={busy} onClick={exportFile}><Download size={16}/> دریافت فایل ICS</button>
      <label>انتخاب فایل تقویم<input type="file" aria-label="فایل ICS" accept=".ics,text/calendar" disabled={busy} onChange={read}/></label>
      {preview&&<><p role="status">{preview.events.length} رویداد قابل ورود، {preview.skipped.length} مورد کنار گذاشته‌شده.</p>
        <label>پروژه مقصد<select value={project} onChange={e=>setProject(e.target.value)}>{eligible.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        <small>فقط عنوان و تاریخ روز رویداد انتقال می‌یابد. ساعت، تکرار و منطقه زمانی در کارت اعمال نمی‌شوند. موارد تکراری در مقصد دوباره ساخته نخواهند شد.</small>
        <button className="btn primary" disabled={busy||!project||!preview.events.length} onClick={()=>{
          try{onImport(project,preview.events);onClose();}
          catch(err){setError(err.message||String(err));}
        }}>افزودن به برد و صف ذخیره</button>
      </>}
      {error&&<p role="alert" className="inline-message">{error}</p>}
    </div>
  </Modal>;
}

export default function App(){
  const [data,setData]=useState(null);
  const [selected,setSelected]=useState('all');
  const [boardId,setBoardId]=useState(null);
  const [addingLane,setAddingLane]=useState(false);
  const [newLaneName,setNewLaneName]=useState('');
  const [workspaceId,setWorkspaceId]=useState(null);
  useEffect(()=>{setAddingLane(false);setNewLaneName('');},[selected,boardId,workspaceId]);
  const [workspaceOpen,setWorkspaceOpen]=useState(false);
  const [mobileNavOpen,setMobileNavOpen]=useState(false);
  const [desktopNavOpen,setDesktopNavOpen]=useState(false);
  const quickDockTrigger=useRef(null);
  useEffect(()=>{
    const onResize=()=>{if(window.innerWidth>860)setMobileNavOpen(false);else setDesktopNavOpen(false);};
    window.addEventListener('resize',onResize);
    return()=>window.removeEventListener('resize',onResize);
  },[]);
  useEffect(()=>{
    if(!desktopNavOpen)return;
    const sidebar=document.getElementById('madar-sidebar');
    sidebar?.querySelector('.mobile-nav-close')?.focus();
    const onKey=event=>{
      if(event.key==='Escape'){
        event.preventDefault();setDesktopNavOpen(false);quickDockTrigger.current?.focus();
        return;
      }
      if(event.key!=='Tab'||!sidebar)return;
      const items=Array.from(sidebar.querySelectorAll('button:not(:disabled),select:not(:disabled),a[href],input:not(:disabled)'))
        .filter(node=>node.getClientRects().length&&getComputedStyle(node).visibility!=='hidden');
      if(!items.length)return;
      const first=items[0],last=items[items.length-1];
      if(event.shiftKey&&(document.activeElement===first||!sidebar.contains(document.activeElement))){event.preventDefault();last.focus();}
      else if(!event.shiftKey&&(document.activeElement===last||!sidebar.contains(document.activeElement))){event.preventDefault();first.focus();}
    };
    document.addEventListener('keydown',onKey,true);
    return()=>document.removeEventListener('keydown',onKey,true);
  },[desktopNavOpen]);
  useEffect(()=>{
    if(!mobileNavOpen)return;
    const sidebar=document.getElementById('madar-sidebar');
    const trigger=document.querySelector('.mobile-nav-toggle');
    sidebar?.querySelector('.mobile-nav-close')?.focus();
    const onKey=event=>{
      if(event.key==='Escape'){
        event.preventDefault();setMobileNavOpen(false);return;
      }
      if(event.key!=='Tab'||!sidebar)return;
      const items=Array.from(sidebar.querySelectorAll('button:not(:disabled),select:not(:disabled),a[href],input:not(:disabled)'))
        .filter(node=>node.getClientRects().length&&getComputedStyle(node).visibility!=='hidden');
      if(!items.length)return;
      const first=items[0],last=items[items.length-1];
      if(event.shiftKey&&(document.activeElement===first||!sidebar.contains(document.activeElement))){event.preventDefault();last.focus();}
      else if(!event.shiftKey&&(document.activeElement===last||!sidebar.contains(document.activeElement))){event.preventDefault();first.focus();}
    };
    document.addEventListener('keydown',onKey);
    return()=>{
      document.removeEventListener('keydown',onKey);
      if(sidebar?.contains(document.activeElement)&&trigger?.isConnected)trigger.focus();
    };
  },[mobileNavOpen]);
  const [trashOpen,setTrashOpen]=useState(false);
  const [boardModal,setBoardModal]=useState(false);
  const [boardName,setBoardName]=useState('');
  const [renameBoardId,setRenameBoardId]=useState(null);
  const [draftBoardId,setDraftBoardId]=useState('');
  const [mode,setMode]=useState('board');
  const [search,setSearch]=useState('');
  const [filter,setFilter]=useState('all');
  const [advancedState,setAdvancedState]=useState({scope:'',value:EMPTY_ADVANCED_FILTER});
  const [editorId,setEditorId]=useState(null);
  const [editorInitialSection,setEditorInitialSection]=useState(null);
  const [cardContext,setCardContext]=useState(null);
  const [cardArchiveOpen,setCardArchiveOpen]=useState(false);
  const [adding,setAdding]=useState(null);
  const [pendingQuickCardId,setPendingQuickCardId]=useState(null);
  const [collapsedLists,setCollapsedLists]=useState({});
  const [laneContextRequest,setLaneContextRequest]=useState(null);
  const laneContextSequence=useRef(0);
  const [projectModal,setProjectModal]=useState(false);
  const [workspaceProjectToAttach,setWorkspaceProjectToAttach]=useState('');
  const [projectSettings,setProjectSettings]=useState(null);
  const [projectName,setProjectName]=useState('');
  const [cloudOpen,setCloudOpen]=useState(false);
  const [settingsOpen,setSettingsOpen]=useState(false);
  const [lanOpen,setLanOpen]=useState(false);
  const [lanInitialView,setLanInitialView]=useState('connection');
  const [notificationsOpen,setNotificationsOpen]=useState(false);
  const [activityOpen,setActivityOpen]=useState(false);
  const [financeOpen,setFinanceOpen]=useState(false);
  const [accountingOpen,setAccountingOpen]=useState(false);
  const [rialJournalOpen,setRialJournalOpen]=useState(false);
  const [rialCompanyId,setRialCompanyId]=useState('');
  const [rialFiscalPeriodId,setRialFiscalPeriodId]=useState('');
  const [rialFiscalStart,setRialFiscalStart]=useState('');
  const [rialFiscalEnd,setRialFiscalEnd]=useState('');
  const [rialActivationNotice,setRialActivationNotice]=useState('');
  const [rialRefresh,setRialRefresh]=useState(0);
  const [accountingSource,setAccountingSource]=useState(null);
  const [profitVisible,setProfitVisible]=useState(false);
  const [rulesOpen,setRulesOpen]=useState(false);
  const [automationListId,setAutomationListId]=useState(null);
  const [automationButtonsScope,setAutomationButtonsScope]=useState(null);
  const [reportingOpen,setReportingOpen]=useState(false);
  const [trelloImportOpen,setTrelloImportOpen]=useState(false);
  const [portableExportOpen,setPortableExportOpen]=useState(false);
  const [plannerOpen,setPlannerOpen]=useState(false);
  const [integrationOpen,setIntegrationOpen]=useState(false);
  const [calendarInteropOpen,setCalendarInteropOpen]=useState(false);
  const [lanStatus,setLanStatus]=useState({mode:'solo',user:{role:'admin'}});
  const [themeChoice,setThemeChoice]=useState(null);
  const displayScope=resolvedDisplayScope(lanStatus);
  const interfaceMode=displayScope.mode;
  const [users,setUsers]=useState([]);
  const [profileOpen,setProfileOpen]=useState(false);
  const [syncing,setSyncing]=useState(false);
  const [lastSync,setLastSync]=useState(null);
  const [syncInfo,setSyncInfo]=useState({mode:'solo',connected:true,pending:false,folder:{configured:false}});
  const [calendar,setCalendar]=useState('jalali');
  const [widgetSettings,setWidgetSettings]=useState(DEFAULT_WIDGET_SETTINGS);
  const [toast,setToast]=useState('');
  const [updateInfo,setUpdateInfo]=useState(null);
  const [updateBusy,setUpdateBusy]=useState(false);
  const [updateDownloaded,setUpdateDownloaded]=useState(false);
  useEffect(()=>{
    if(!isDesktop)return;
    let mounted=true;
    const check=()=>api.releaseCheck().then(info=>{if(mounted){setUpdateInfo(info?.available?info:null);setUpdateDownloaded(false);}}).catch(()=>{});
    check();
    const timer=setInterval(check,6*60*60*1000);
    return()=>{mounted=false;clearInterval(timer);};
  },[]);
  const actOnUpdate=async()=>{
    if(updateBusy)return;
    setUpdateBusy(true);
    try{
      if(!updateDownloaded){await api.releaseDownload();setUpdateDownloaded(true);setToast('نسخه جدید با بررسی SHA-256 دانلود شد.');}
      else {await api.releaseInstall();setToast('آپدیت پس از خروج کامل از مدار نصب می‌شود. برنامه را ببندید.');}
    }catch(error){setToast('خطای آپدیت: '+(error?.message||String(error)));}
    finally{setUpdateBusy(false);}
  };
  const [savingError,setSavingError]=useState('');
  const [pendingRecovery,setPendingRecovery]=useState(false);
  const [draftTitle,setDraftTitle]=useState('');
  const [draftPriority,setDraftPriority]=useState('medium');
  const [draftProject,setDraftProject]=useState('');
  const [draftStatus,setDraftStatus]=useState('inbox');
  const ready=useRef(false);
  // Choose an existing real board for the first view, without writing a
  // preference or touching stored tasks. Empty workspaces retain their setup.
  const initialBoardChosen=useRef(false);
  const dirty=useRef(false);
  const blocked=useRef(false);
  // Forced authoritative reload must exclude local edits for its whole await.
  const recoveryReload=useRef(false);
  const backupRestorePreviouslyBlocked=useRef(false);
  const saving=useRef(false);
  const lastSaved=useRef('');
  const dataMutationEpoch=useRef(0);
  const quickCardAttempt=useRef(null);
  const latestData=useRef(null);
  const latestUnsavedRecovery=useRef(null);
  useEffect(()=>{latestData.current=data;},[data]);
  const cardUndo=useRef(emptyCardHistory(null));
  const clearCardUndo=()=>{cardUndo.current=emptyCardHistory(null);};
  const refresh=async(force=false)=>{
    if((dirty.current||saving.current||blocked.current)&&!force)return;
    const startEpoch=dataMutationEpoch.current;
    const fresh=normalize(await (api.getStateForUi?api.getStateForUi():api.getState()));
    // Forced reload is authorized only against the state at the moment of
    // confirmation. A new edit while the host read is pending must not be
    // overwritten by the older, asynchronously returned server snapshot.
    if(force&&dataMutationEpoch.current!==startEpoch)
      throw new Error('هنگام بازخوانی، تغییر جدیدی ثبت شد. برای جلوگیری از حذف آن، جایگزینی سرور متوقف شد.');
    // A refresh issued before an edit must not publish a stale snapshot after
    // that edit, even if the save debounce has already cleared dirty.current.
    if(!force&&((dirty.current||saving.current||blocked.current)||
                dataMutationEpoch.current!==startEpoch))return;
    setData(previous=>{
      if(previous&&JSON.stringify(previous)===JSON.stringify(fresh))return previous;
      clearCardUndo();
      return fresh;
    });
    lastSaved.current=JSON.stringify(fresh);
    setLastSync(new Date());
    setSavingError('');
  };
  const refreshLan=async()=>{
    const status=await api.lanStatus(true);
    setLanStatus(previous=>{
      if(previous?.mode!==status?.mode||previous?.user?.username!==status?.user?.username||
         previous?.user?.role!==status?.user?.role)clearCardUndo();
      return status;
    });
  };
  const refreshSyncStatus=async()=>setSyncInfo(await api.syncStatus());
  const refreshUsers=async()=>setUsers(await api.lanProfiles());
  useEffect(()=>{Promise.all([api.getStateForUi?api.getStateForUi():api.getState(),api.lanStatus(),api.getPreferences(),api.lanProfiles(),api.syncStatus()]).then(([s,lan,prefs,members,sync])=>{
    const normalized=normalize(s);setData(normalized);lastSaved.current=JSON.stringify(normalized);setLanStatus(lan);setUsers(members);setCalendar(prefs.calendar||'jalali');setWidgetSettings(normalizeWidgetSettings(prefs.widgetSettings||prefs.clockWidget));setLastSync(new Date());ready.current=true;
    setSyncInfo(sync);
  }).catch(e=>setSavingError('خطا در خواندن اطلاعات: '+e.message));},[]);
  useEffect(()=>{
    if(!ready.current||!data||!dirty.current||blocked.current)return;
    const t=setTimeout(async()=>{
      if(saving.current||!dirty.current)return;
      saving.current=true;
      const snapshot=data;
      dirty.current=false;
      try{
        const result=await api.saveState(snapshot);
        lastSaved.current=JSON.stringify(snapshot);
        const quick=quickCardAttempt.current;
        if(quick&&snapshot.tasks.some(task=>task.id===quick.id)){
          // The LAN client can accept a durable *local queue* without the
          // server acknowledging it. Never mislabel queued data as synced.
          quickCardAttempt.current=null;
          setPendingQuickCardId(null);
          setAdding(null);
          setDraftTitle('');
          setToast(result?.offline===true
            ?'کارت در صف آفلاین ثبت شد؛ تأیید میزبان هنوز دریافت نشده است.'
            :'کارت ذخیره شد؛ برای تکمیل جزئیات روی آن کلیک کنید.');
        }
        if(result?.revision||result?.localRevision){
          setData(current=>({...current,...(result.revision?{__remoteRevision:result.revision}:{}),...(result.localRevision?{__localRevision:result.localRevision}:{})}));
          if(dirty.current)setData(current=>({...current}));
        }else if(dirty.current){
          // Edits made during the previous request still need their own save.
          setData(current=>({...current}));
        }
        setLastSync(new Date());
        refreshSyncStatus().catch(()=>{});
        setSavingError('');
      }
      catch(e){
        clearCardUndo();
        dirty.current=false;
        blocked.current=true;
        setPendingRecovery(true);
        setSavingError('ذخیره ناموفق بود: '+e.message+' | قبل از ادامه تغییرات، اتصال و داده‌ها را بررسی کن.');
        const quick=quickCardAttempt.current;
        if(quick){
          setToast('ذخیره کارت موفق نبود؛ عنوان را حفظ کرده‌ایم.');
          // The global blocked/recovery latch intentionally forbids another
          // write. Do not also leave the composer stuck in a fake "saving"
          // state: the user must be able to copy or explicitly close it.
          quickCardAttempt.current=null;
          setPendingQuickCardId(null);
        }
        // A quick card can be staged while an older save is in-flight. The
        // rejected snapshot might predate it. Preserve the latest React state
        // and the pending card, never silently recover only the older snapshot.
        const recent=latestData.current?.tasks?latestData.current:snapshot;
        const recovery=quick?.card&&!recent.tasks.some(t=>t.id===quick.card.id)
          ?{...recent,tasks:[quick.card,...recent.tasks]}:recent;
        // Keep a current exportable snapshot even when localStorage is full
        // or unavailable. A stale key from another failed save is not safe.
        latestUnsavedRecovery.current=recovery;
        let recoveryStored=false;
        try{localStorage.setItem('madar-unsaved-recovery',JSON.stringify(recovery));recoveryStored=true;}
        catch{}
        if(quick)setAdding(current=>current?{...current,error:recoveryStored
          ?'ذخیره کارت رد شد؛ عنوان برای کپی حفظ شده و نسخهٔ بازیابی ثبت شده است. ابتدا از پنل بازیابی مشکل ذخیره را رفع کنید.'
          :'ذخیره کارت رد شد و ثبت نسخهٔ بازیابی نیز ممکن نبود. عنوان در فرم باقی مانده است؛ قبل از خروج آن را کپی کنید.'}:current);
        if(!recoveryStored)setSavingError('ذخیره انجام نشد و ثبت نسخهٔ بازیابی نیز ممکن نبود؛ متن‌های ذخیره‌نشده را پیش از خروج کپی کنید.');
      }finally{saving.current=false;}
    },320);
    return()=>clearTimeout(t);
  },[data]);
  useEffect(()=>{
    const timer=setInterval(()=>{if(ready.current&&!dirty.current&&!saving.current&&!blocked.current){
      Promise.all([refresh(),refreshSyncStatus(),refreshUsers(),refreshLan()]).catch(e=>setSavingError('همگام‌سازی انجام نشد: '+e.message));
    }},15000);
    return()=>clearInterval(timer);
  },[]);
  const appearanceScope=themeScope(lanStatus);
  const sharedThemeEnabled=data?.settings?.themeForAllUsers===true;
  const uiTheme=sharedThemeEnabled?(data?.settings?.theme==='light'?'light':'dark'):
    themeChoice?.scope===appearanceScope?themeChoice.theme:
    readTheme(localStorage,appearanceScope,data?.settings?.theme);
  useEffect(()=>{document.documentElement.dataset.theme=uiTheme;},[uiTheme]);
  useEffect(()=>{
    if(!data)return;
    // The standalone finance route uses the same display preference, without
    // receiving task state or authorization through localStorage.
    try{localStorage.setItem('madar-ui-theme',uiTheme);}
    catch(_error){/* Private storage may be disabled in a hardened WebView. */}
  },[uiTheme,!!data]);
  const chooseTheme=next=>{
    if(next!=='light'&&next!=='dark')return;
    if(sharedThemeEnabled){
      if(lanStatus?.user?.role!=='admin')return;
      changeAdmin(s=>({...s,settings:{...s.settings,theme:next}}));
    }else{
      writeTheme(localStorage,appearanceScope,next);
      setThemeChoice({scope:appearanceScope,theme:next});
    }
  };
  const toggleTheme=()=>chooseTheme(uiTheme==='dark'?'light':'dark');
  useEffect(()=>{if(!toast)return;const t=setTimeout(()=>setToast(''),4000);return()=>clearTimeout(t);},[toast]);
  const tasks=data?.tasks||[];
  useEffect(()=>{
    if(!pendingQuickCardId)return;
    if(!data?.tasks?.some(task=>task.id===pendingQuickCardId)){
      // A stale board/anchor or an invalid legacy card can make the state
      // updater refuse to add. Do not leave the global dirty latch set when
      // React bailed out because it returned the identical state object.
      const attempt=quickCardAttempt.current;
      if(attempt?.id===pendingQuickCardId&&!attempt.dirtyBefore&&attempt.baseline===data&&
         attempt.epoch===dataMutationEpoch.current&&!saving.current){
        dirty.current=false;
      }
      quickCardAttempt.current=null;
      setAdding(current=>current?{...current,error:
        'کارت افزوده نشد. وضعیت برد یا اطلاعات قدیمی کارت‌ها مانع ثبت است؛ عنوان شما حفظ شد.'}:current);
      setToast('افزودن کارت انجام نشد؛ عنوان واردشده حفظ شد.');
      setPendingQuickCardId(null);
    }
  },[data,pendingQuickCardId]);
  const projects=data?.projects||[];
  const stages=data?.stages||DEFAULT_STAGES;
  const priorities=priorityDefs(data?.settings);
  const boards=data?.boards||[];
  const workspaces=data?.workspaces||[];
  useEffect(()=>{
    if(!data||initialBoardChosen.current)return;
    initialBoardChosen.current=true;
    const firstWorkspace=workspaces.find(w=>!w.archived);
    const firstBoard=boards.find(b=>!b.archived&&b.workspaceId===firstWorkspace?.id&&
      projects.some(p=>p.id===b.projectId));
    if(firstBoard){
      setSelected(firstBoard.projectId);
      setBoardId(firstBoard.id);
      setMode('board');
    }
  },[data,boards,projects,workspaces]);
  const activeWorkspace=workspaces.find(w=>w.id===workspaceId&&!w.archived)
    ||workspaces.find(w=>!w.archived)||null;
  const activeWorkspaceId=activeWorkspace?.id||null;
  const workspaceBoards=boards.filter(b=>!b.archived&&b.workspaceId===activeWorkspaceId);
  const workspaceProjectIds=new Set(workspaceBoards.map(b=>b.projectId));
  // Projects are global identities; a workspace only exposes projects linked
  // through its own boards. Do not pretend an empty workspace owns old boards.
  const visibleProjects=projects.filter(p=>workspaceProjectIds.has(p.id));
  const activeBoard=(workspaceBoards.find(b=>b.id===boardId&&b.projectId===selected)
                     ||(selected==='all'?null:workspaceBoards.find(b=>b.projectId===selected)))||null;
  const boardViewScope=activeBoard?.id||'workspace:'+(activeWorkspaceId||'legacy');
  const boardViewIdentity=lanStatus.user?.username||'local';
  const advancedScope=String(plannerIdentity(lanStatus))+'|'+boardViewScope;
  const advanced=readScopedAdvancedFilter(advancedState,advancedScope);
  const setAdvanced=update=>setAdvancedState(previous=>
    updateScopedAdvancedFilter(previous,advancedScope,update));
  const boardViewColumns=useMemo(()=>boardTableColumns(activeBoard),[activeBoard?.id,activeBoard?.customFields]);
  useEffect(()=>{
    if(!data||!activeWorkspaceId)return;
    const saved=readBoardViewPreferences(localStorage,boardViewIdentity,boardViewScope,boardViewColumns);
    setMode(previous=>previous==='time'?previous:saved.mode);
  },[activeBoard?.id,activeWorkspaceId,boardViewIdentity,!!data]);
  const switchBoardDisplay=next=>{
    setMode(next);
    saveBoardViewPreferences(localStorage,boardViewIdentity,boardViewScope,{mode:next},boardViewColumns);
  };
  const viewStages=activeBoard?activeBoardLists(activeBoard):stages;
  const canManage=lanStatus?.user?.role==='admin';
  const canViewStandalone=canManage||
    lanStatus?.user?.financeView===true||
    (lanStatus?.user?.role==='editor'&&lanStatus?.user?.financeEdit===true);
  const canEdit=lanStatus?.mode==='client'
    ?(['admin','editor'].includes(lanStatus?.user?.role))
    :lanStatus?.user?.role!=='viewer';
  // The LAN bridge saves whole snapshots, so it cannot guarantee a single-card
  // conditional undo against another member's concurrent write. Fail closed.
  const cardUndoScope=['solo',lanStatus?.user?.username||'local',activeWorkspaceId||'',
    activeBoard?.id||'overview'].join('|');
  useEffect(()=>{clearCardUndo();},[cardUndoScope]);
  const cardUndoEnabled=canEdit&&lanStatus?.mode==='solo'&&!blocked.current&&!saving.current;
  const canUndo=cardHistoryAvailability(cardUndo.current,data,'undo',cardUndoScope,cardUndoEnabled);
  const canRedo=cardHistoryAvailability(cardUndo.current,data,'redo',cardUndoScope,cardUndoEnabled);
  const show=feature=>isManagedFeatureVisible(displayScope,feature,{canManage,canEdit});
  useEffect(()=>{
    if(interfaceMode==='basic'){
      setMode(previous=>previous==='time'?'board':previous);
      setReportingOpen(false);setPlannerOpen(false);setActivityOpen(false);
      setWorkspaceOpen(false);setRulesOpen(false);setTrelloImportOpen(false);
      setCalendarInteropOpen(false);setIntegrationOpen(false);
      setPortableExportOpen(false);
    }
    if(interfaceMode!=='finance'){
      setFinanceOpen(false);setAccountingOpen(false);
      setRialJournalOpen(false);
      setProfitVisible(false);
    }
  },[interfaceMode]);
  const manualRefresh=async()=>{
    if(dirty.current||saving.current){setToast('تغییرات در حال ذخیره هستند؛ پس از ذخیره دوباره تازه‌سازی کنید.');return;}
    if(blocked.current){setToast('ابتدا خطای ذخیره و تداخل را بررسی کنید.');return;}
    setSyncing(true);
    try{await Promise.all([refresh(),refreshLan(),refreshUsers(),refreshSyncStatus()]);setToast('آخرین اطلاعات موجود بارگیری شد.');}
    catch(e){setSavingError('خطای تازه‌سازی: '+e.message);}
    finally{setSyncing(false);}
  };
  const openNetwork=()=>{setLanInitialView('connection');setLanOpen(true);};
  const openUserManagement=()=>{
    if(!canManage)return;
    // Solo is a valid entry point into setup, not a silent dead button.
    setLanInitialView(lanStatus.mode==='solo'?'connection':'users');setLanOpen(true);
  };
  useEffect(()=>{setProfitVisible(false);},[selected,boardId]);
  useEffect(()=>{
    const hide=()=>setProfitVisible(false);
    window.addEventListener('blur',hide);
    const onVisibility=()=>{if(document.hidden)hide();};
    document.addEventListener('visibilitychange',onVisibility);
    return()=>{window.removeEventListener('blur',hide);document.removeEventListener('visibilitychange',onVisibility);};
  },[]);
  // The Bridge/LAN already scopes and redacts this state; the index additionally
  // requires the explicit list of project IDs in that authenticated view.
  const boardIndex=useMemo(()=>data?createBoardPerformanceIndex(data,{
    permittedProjectIds:(data.projects||[]).map(p=>p.id)
  }):null,[data]);
  const filtered=useMemo(()=>{
    if(!boardIndex)return [];
    const candidates=boardIndex.selectActiveCards({
      workspaceId:activeWorkspaceId||'workspace-legacy',
      projectId:selected==='all'?undefined:selected,
      boardId:activeBoard?.id,
      highOnly:filter==='high',withReports:filter==='with-reports'
    });
    const found=search.trim()?new Set(filterTasks(candidates,{query:search,projects,users,stages:viewStages}).map(t=>t.id)):null;
    return candidates.filter(t=>(!found||found.has(t.id))&&matchAdvanced(t,advanced,activeBoard?.id));
  },[boardIndex,activeWorkspaceId,projects,users,viewStages,selected,activeBoard?.id,search,filter,advanced]);
  // Never infer a search grant from a task. Intersect the host's authenticated
  // profile grants with the already redacted project snapshot.
  const permittedSearchProjects=useMemo(()=>{
    const grants=lanStatus.user?.projects;
    if(lanStatus.mode==='solo'||lanStatus.user?.role==='admin'||grants===null)
      return projects.map(project=>project.id);
    if(!Array.isArray(grants))return [];
    const allow=new Set(grants);
    return projects.filter(project=>allow.has(project.id)).map(project=>project.id);
  },[lanStatus.mode,lanStatus.user?.role,lanStatus.user?.projects,projects]);
  const globalSearch=useMemo(()=>{
    if(!data||!search.trim())return {results:[],error:null};
    try{return {results:searchTaskLocations(data,{query:search,
      permittedProjectIds:permittedSearchProjects,users}),error:null};}
    catch(error){return {results:[],error:'جست‌وجوی ایمن انجام نشد: '+error.message};}
  },[data,search,permittedSearchProjects,users]);
  const boardGroups=useMemo(()=>boardIndex?boardIndex.groupActiveCards({
    workspaceId:activeWorkspaceId||'workspace-legacy',
    projectId:selected==='all'?undefined:selected,
    boardId:activeBoard?.id,
    matchIds:new Set(filtered.map(t=>t.id))
  }):new Map(),[boardIndex,activeWorkspaceId,selected,activeBoard?.id,filtered]);
  const selectedProject=projects.find(p=>p.id===selected);
  const activeTask=tasks.find(t=>t.id===editorId);
  const change=(next,preserveCardUndo=false)=>{if(!canEdit)return;
    if(recoveryReload.current){
      setToast('بازخوانی اطلاعات در جریان است؛ پس از پایان آن دوباره ویرایش کنید.');
      return;
    }
    if(!preserveCardUndo)clearCardUndo();
    dataMutationEpoch.current++;dirty.current=true;setData(current=>{
    if(recoveryReload.current)return current;
    const newState=typeof next==='function'?next(current):next;
    if(blocked.current){
      latestUnsavedRecovery.current=newState;
      try{localStorage.setItem('madar-unsaved-recovery',JSON.stringify(newState));}catch{}
    }
    return newState;
  });setProfitVisible(false);};
  const reverseCardEdit=direction=>{
    const allowed=cardUndoEnabled&&!saving.current&&!blocked.current&&lanStatus.mode==='solo'&&canEdit;
    if(!cardHistoryAvailability(cardUndo.current,data,direction,cardUndoScope,allowed)){
      clearCardUndo();setToast('بازگشت تغییر ممکن نیست؛ وضعیت کارت یا دسترسی تغییر کرده است.');return;
    }
    const timestamp=now();
    let result;
    change(current=>{
      // React can re-run functional updaters in StrictMode: commit only once.
      if(result)return result;
      const attempt=applyCardHistory(cardUndo.current,current,direction,cardUndoScope,
        allowed&&!saving.current&&!blocked.current,timestamp);
      if(!attempt.applied){clearCardUndo();return current;}
      cardUndo.current=attempt.history;
      result=attempt.state;
      return result;
    },true);
  };
  useEffect(()=>{
    const onKey=event=>{
      if(!event.ctrlKey||event.altKey||event.metaKey||event.defaultPrevented)return;
      const target=event.target;
      if(target?.closest?.('input, textarea, select, [contenteditable], [role="textbox"]'))return;
      if(target?.isContentEditable)return;
      if(target?.closest?.('[role="dialog"], [aria-modal="true"]'))return;
      const key=event.key.toLowerCase();
      const direction=key==='z'&&!event.shiftKey?'undo':
        (key==='y'&&!event.shiftKey||key==='z'&&event.shiftKey)?'redo':null;
      if(!direction)return;
      if(!cardHistoryAvailability(cardUndo.current,data,direction,cardUndoScope,cardUndoEnabled))return;
      event.preventDefault();reverseCardEdit(direction);
    };
    window.addEventListener('keydown',onKey);
    return()=>window.removeEventListener('keydown',onKey);
  },[data,cardUndoScope,cardUndoEnabled]);
  const changeAdmin=next=>{if(!canManage)return;change(next);};
  const updateBoardListArchive=(listId,restore=false)=>{
    if(!canManage||!activeBoard)return;
    const action=restore?restoreListState:archiveListState;
    const options={canManage:true};
    try{
      if(action(data,activeBoard.id,listId,options)===data)return;
      changeAdmin(s=>{try{return action(s,activeBoard.id,listId,options);}catch{return s;}});
      setToast(restore?'ستون و کارت‌های آن بازیابی شدند.':'ستون بایگانی شد؛ کارت‌ها و هزینه‌ها حفظ شدند.');
    }catch(e){setToast('عملیات ستون انجام نشد: '+e.message);}
  };
  const selectWorkspace=id=>{
    setWorkspaceId(id);setSelected('all');setBoardId(null);setFilter('all');
    setAdvanced(a=>({...a,status:'all'}));
    // The workspace selector is a <select>, not a button: sidebar click
    // delegation otherwise leaves its full-screen backdrop over the board.
    setDesktopNavOpen(false);setMobileNavOpen(false);
  };
  const openBoardView=()=>{
    // An explicit Board action must open a real board, not merely reselect an
    // already active "board" mode while the aggregate overview is shown.
    const destination=activeBoard||workspaceBoards.find(b=>b.projectId===selected)||workspaceBoards[0];
    if(destination){setSelected(destination.projectId);setBoardId(destination.id);}
    else if(selected==='all'&&visibleProjects[0])setSelected(visibleProjects[0].id);
    setMode('board');setFilter('all');
    if(destination)saveBoardViewPreferences(localStorage,boardViewIdentity,destination.id,{mode:'board'},boardTableColumns(destination));
  };
  const navigateSearchLocation=result=>{
    const board=boards.find(item=>item.id===result.boardId);
    const space=workspaces.find(item=>item.id===board?.workspaceId);
    if(!board||board.archived||space?.archived){
      setToast('محل این کارت بایگانی شده است. ابتدا برد یا فضای کاری را بازیابی کنید.');
      return;
    }
    if(board.projectId==null||!projects.some(project=>project.id===board.projectId)){
      setToast('این برد پروژه قابل انتخاب ندارد؛ موقعیت کارت در نتایج جست‌وجو نمایش داده شده است.');
      return;
    }
    if(board.stages?.some(stage=>stage.id===result.listId&&stage.archived===true)){
      setToast('فهرست این کارت بایگانی شده است؛ ابتدا فهرست را بازیابی کنید.');
      return;
    }
    setWorkspaceId(board.workspaceId);
    setSelected(board.projectId);
    setBoardId(board.id);
    setMode('board');
    setFilter('all');
    setAdvanced(a=>({...a,status:'all'}));
    setSearch('');
  };
  const reorderCard=(cardId,toListId,anchorCardId=null,placement='end')=>{
    if(!canEdit||!activeBoard)return;
    if(!activeBoardLists(activeBoard).some(s=>s.id===toListId))return;
    const card=tasks.find(t=>t.id===cardId);
    if(!card||card.boardId!==activeBoard.id)return;
    const request={cardId,toListId,toBoardId:activeBoard.id,anchorCardId,placement};
    try{
      if(moveCardInState(data,request)===data)return;
      // Keep the host's full-state CAS and recovery path authoritative.
      change(s=>{try{return moveCardInState(s,request);}catch{return s;}});
    }catch(e){setToast('جابه‌جایی کارت انجام نشد: '+e.message);}
  };
  const reorderStage=(sourceId,targetId)=>{
    if(!canManage||sourceId===targetId)return;
    changeAdmin(s=>activeBoard?
      {...s,boards:(s.boards||[]).map(b=>b.id===activeBoard.id?{...b,stages:reorderStageArray(b.stages,sourceId,targetId)}:b)}:
      {...s,stages:reorderStageArray(s.stages,sourceId,targetId)});
  };
  const updateStagePresentation=(stageId,fields)=>{
    if(!canManage||!viewStages.some(stage=>stage.id===stageId))return;
    const patch={};
    if(Object.hasOwn(fields,'label')){
      if(typeof fields.label!=='string'||!fields.label.trim()||fields.label.trim().length>100)return;
      patch.label=fields.label.trim();
    }
    if(Object.hasOwn(fields,'subtitle')){
      if(typeof fields.subtitle!=='string'||fields.subtitle.length>180)return;
      patch.subtitle=fields.subtitle.trim();
    }
    if(Object.hasOwn(fields,'color')){
      if(!/^#[0-9a-f]{6}$/i.test(fields.color))return;
      patch.color=fields.color;
    }
    if(!Object.keys(patch).length)return;
    changeAdmin(s=>activeBoard?
      {...s,boards:(s.boards||[]).map(b=>b.id===activeBoard.id?
        {...b,stages:b.stages.map(stage=>stage.id===stageId?{...stage,...patch}:stage)}:b)}:
      {...s,stages:s.stages.map(stage=>stage.id===stageId?{...stage,...patch}:stage),
        boards:(s.boards||[]).map(b=>b.archived||b.workspaceId!==activeWorkspaceId?b:
          {...b,stages:b.stages.map(stage=>stage.id===stageId?{...stage,...patch}:stage)})});
  };
  const addLane=()=>{
    const label=newLaneName.trim();
    if(!canManage||!label||label.length>100)return;
    const activeCount=activeBoard?.stages?.length||stages.length;
    if(activeCount>=40||(!activeBoard&&stages.length>=40)||
       (!activeBoard&&workspaceBoards.some(board=>board.stages.length>=40))){
      setToast('حداکثر ۴۰ ستون مجاز است؛ ستون‌های بایگانی‌شده نیز شمرده می‌شوند.');
      return;
    }
    const nextStage={id:'stage_'+uid(),label,subtitle:'',color:'#64748b'};
    changeAdmin(s=>{
      // A selected board has independent stages. In the workspace's aggregate
      // view, make the new shared column a valid destination in its active
      // boards too, or a card created under it would silently fall back to
      // the first list of the destination board.
      if(activeBoard){
        return {...s,stages:s.stages.length<40?[...s.stages,nextStage]:s.stages,
          boards:(s.boards||[]).map(board=>board.id===activeBoard.id?
            {...board,stages:[...board.stages,nextStage]}:board)};
      }
      return {...s,stages:[...s.stages,nextStage],
        boards:(s.boards||[]).map(board=>!board.archived&&board.workspaceId===activeWorkspaceId?
          {...board,stages:[...board.stages,nextStage]}:board)};
    });
    setAddingLane(false);
    setNewLaneName('');
    setToast(activeBoard?'ستون جدید به این برد اضافه شد.':'ستون جدید به بردهای فعال این فضای کاری اضافه شد.');
  };
  const copyBoardList=stageId=>{
    if(!canManage||!activeBoard)return;
    const original=activeBoard.stages.find(stage=>stage.id===stageId&&stage.archived!==true);
    if(!original)return;
    if(activeBoard.stages.length>=40){setToast('ظرفیت ۴۰ ستون این برد تکمیل است.');return;}
    // Copy the lane's presentation only, never duplicate financial/card IDs.
    // A full card-copy action would require independent invoice/attachment refs.
    const copy={...original,id:'stage_'+uid(),label:original.label.slice(0,93)+' (کپی)',archived:false};
    changeAdmin(s=>({...s,boards:s.boards.map(board=>{
      if(board.id!==activeBoard.id||board.archived||board.stages.length>=40||
         !board.stages.some(stage=>stage.id===stageId&&stage.archived!==true)||
         board.stages.some(stage=>stage.id===copy.id))return board;
      const index=board.stages.findIndex(stage=>stage.id===stageId);
      const nextStages=board.stages.slice();nextStages.splice(index+1,0,copy);
      return {...board,stages:nextStages};
    })}));
    setToast('ساختار ستون کپی شد؛ کارت‌ها و اطلاعات مالی کپی نشده‌اند.');
  };
  const sortBoardList=(stageId,sortBy)=>{
    if(!canEdit||!activeBoard)return;
    try{
      if(sortLaneState(data,activeBoard.id,stageId,sortBy)===data)return;
      change(state=>{try{return sortLaneState(state,activeBoard.id,stageId,sortBy);}catch{return state;}});
      setToast('کارت‌ها مرتب شدند؛ اطلاعات کارت‌ها و هزینه‌ها تغییر نکرد.');
    }catch(error){setToast('مرتب‌سازی انجام نشد: '+error.message);}
  };
  const moveAllBoardList=(fromId,toId)=>{
    if(!canManage||!activeBoard||fromId===toId)return;
    const source=activeBoard.stages.find(stage=>stage.id===fromId&&!stage.archived);
    const destination=activeBoard.stages.find(stage=>stage.id===toId&&!stage.archived);
    if(!source||!destination)return;
    const count=getOrderedLaneCards(tasks,activeBoard.id,fromId).filter(card=>card.deleted!==true).length;
    if(!count)return;
    if(!window.confirm(`${count.toLocaleString('fa-IR')} کارت از «${source.label}» به «${destination.label}» منتقل شوند؟ وضعیت گردش‌کار ممکن است تغییر کند؛ اطلاعات مالی کارت‌ها حفظ می‌شوند.`))return;
    try{
      if(moveAllLaneCardsState(data,activeBoard.id,fromId,toId)===data)return;
      change(state=>{try{return moveAllLaneCardsState(state,activeBoard.id,fromId,toId);}catch{return state;}});
      setToast('کارت‌ها به لیست مقصد منتقل شدند.');
    }catch(error){setToast('انتقال انجام نشد: '+error.message);}
  };
  const taskUpdate=(id,fields)=>{
    const eligible=lanStatus.mode==='solo'&&!blocked.current&&isUndoableCardPatch(fields);
    const actionId=uid();
    change(s=>{
    const original=s.tasks.find(t=>t.id===id);
    const board=s.boards?.find(b=>b.id===original?.boardId);
    const requestedList=fields.listId||(fields.status&&board?.stages.some(x=>x.id===fields.status)?fields.status:null);
    if(requestedList&&board?.stages.some(stage=>stage.id===requestedList&&stage.archived===true)&&requestedList!==original?.listId)return s;
    const movingWithinBoard=original&&board&&requestedList&&requestedList!==original.listId
      &&(!fields.boardId||fields.boardId===original.boardId)
      &&(!fields.projectId||fields.projectId===original.projectId);
    const base=movingWithinBoard?moveCardInState(s,{cardId:id,toListId:requestedList,placement:'end'}):s;
    const next={...base,tasks:base.tasks.map(t=>{
    if(t.id!==id)return t;
    let changed={...t,...fields,updatedAt:now()};
    if(fields.projectId&&fields.projectId!==t.projectId){
      const board=base.boards?.find(b=>b.projectId===fields.projectId&&!b.archived);
      if(!board)return t;
      const {cardOrder:oldOrder,...relocated}=moveCardToBoard({...changed,boardId:t.boardId,projectId:fields.projectId},board,base.stages);
      changed={...relocated,updatedAt:changed.updatedAt};
    }else if(fields.boardId&&fields.boardId!==t.boardId){
      const board=base.boards?.find(b=>b.id===fields.boardId);
      const {cardOrder:oldOrder,...relocated}=moveCardToBoard({...changed,boardId:t.boardId},board,base.stages);
      changed={...relocated,updatedAt:changed.updatedAt};
    }else if(fields.listId||fields.status){
      const stageBoard=base.boards?.find(b=>b.id===t.boardId);
      changed=stageBoard?boardStageUpdate(changed,stageBoard,base.stages,fields.listId||fields.status):{...changed,status:fields.status||fields.listId};
    }
    return changed;
    })};
    if(eligible)cardUndo.current=recordCardEdit(cardUndo.current,s,next,id,fields,cardUndoScope,actionId);
    return next;
  },eligible);
  };
  const toggleChecklistStep=(taskId,stepId)=>change(s=>({...s,tasks:s.tasks.map(t=>t.id===taskId?
    {...t,checklist:t.checklist.map(c=>c.id===stepId?{...c,done:!c.done}:c),updatedAt:now()}:t)}));
  const cardTrashOptions=()=>canManage?{canManage:true}:{canEdit:true,grantedProjectIds:projects.map(p=>p.id)};
  const deleteTask=id=>{
    if(!canEdit)return;
    try{
      const options=cardTrashOptions();
      if(softDeleteCardState(data,id,options)===data)return;
      change(s=>softDeleteCardState(s,id,options));
      setEditorId(null);
      setToast('کارت به زباله‌دان منتقل شد؛ هزینه‌ها و اطلاعات آن حفظ شدند.');
    }catch(e){setToast('انتقال به زباله‌دان انجام نشد: '+e.message);}
  };
  const archiveTask=id=>{
    if(!canEdit)return;
    try {
      const options=cardTrashOptions();
      if(archiveCardState(data,id,options)===data)return;
      change(state=>archiveCardState(state,id,options));
      setCardContext(null);
      setEditorId(null);
      setToast('کارت بایگانی شد؛ اطلاعات و مدارک آن حفظ شدند.');
    } catch(error){setToast('بایگانی کارت انجام نشد: '+error.message);}
  };
  const restoreArchivedTask=id=>{
    if(!canEdit)return;
    try {
      const options=cardTrashOptions();
      if(restoreArchivedCardState(data,id,options)===data)return;
      change(state=>restoreArchivedCardState(state,id,options));
      setToast('کارت به موقعیت قبلی خود بازیابی شد.');
    } catch(error){setToast('بازیابی کارت انجام نشد: '+error.message);}
  };
  const archivedCards=tasks.filter(t=>t.archived===true&&t.archivedByBoard!==true&&
    t.deleted!==true&&projects.some(project=>project.id===t.projectId)&&
    (!t.boardId||boards.some(board=>board.id===t.boardId&&board.workspaceId===activeWorkspaceId)));
  const requestCardMenu=(task,event)=>setCardContext({
    id:uid(),cardId:task.id,title:task.title,
    completed:task.completed===true,
    x:event.clientX,y:event.clientY,
  });
  const restoreTrashedCard=id=>{
    if(!canEdit)return;
    try{
      const options=cardTrashOptions();
      if(restoreDeletedCardState(data,id,options)===data)return;
      change(s=>restoreDeletedCardState(s,id,options));
      setToast('کارت با تمام اطلاعاتش بازیابی شد.');
    }catch(e){setToast('بازیابی کارت انجام نشد: '+e.message);}
  };
  const trashCards=tasks.filter(t=>t.deleted===true &&
    projects.some(p=>p.id===t.projectId) &&
    (!t.boardId||boards.some(b=>b.id===t.boardId&&b.workspaceId===activeWorkspaceId)));
  const toggleCardComplete=id=>{
    if(!canEdit)return;
    const task=tasks.find(t=>t.id===id&&t.deleted!==true);
    if(!task)return;
    // Completion is separate from legacy status/listId: changing status to
    // "done" would enqueue financial completion events on the native host.
    taskUpdate(id,{completed:task.completed!==true});
  };
  const createTask=()=>{
    const title=draftTitle.trim().replace(/\s+/g,' ');
    if(!title||!adding||!canEdit||blocked.current||pendingQuickCardId)return;
    if(saving.current){
      setAdding(current=>current?{...current,error:
        'ذخیره تغییر قبلی هنوز تمام نشده است. عنوان شما حفظ شد؛ پس از پایان ذخیره دوباره اقدام کنید.'}:current);
      return;
    }
    const targetBoard=workspaceBoards.find(b=>b.id===adding.boardId&&b.projectId===adding.projectId);
    if(!targetBoard||!visibleProjects.some(p=>p.id===adding.projectId)){
      setToast('برای این فضای کاری ابتدا یک پروژه و برد انتخاب یا ایجاد کنید.');
      setAdding(null);
      return;
    }
    const availableStages=activeBoardLists(targetBoard);
    const stage=availableStages.find(s=>s.id===adding.listId)?.id;
    if(!stage){
      setAdding(null);setToast('ستون مقصد دیگر فعال نیست؛ دوباره افزودن کارت را انتخاب کنید.');
      return;
    }
    const placement=['start','end','before','after'].includes(adding.placement)?adding.placement:'end';
    const anchorCardId=adding.anchorCardId||null;
    const t={id:uid(),projectId:adding.projectId,boardId:targetBoard.id,
      listId:stage,title,description:'',status:legacyStatusForStage(stage,stages)||stage,
      priority:'medium',completed:false,dueDate:'',labels:[],checklist:[],reports:[],assignees:[],
      costEnabled:null,fileLinks:[],estimatedMinutes:0,actualMinutes:0,cost:0,
      createdAt:now(),updatedAt:now()};
    const move={cardId:t.id,toBoardId:targetBoard.id,toListId:stage,
      ...(placement==='before'||placement==='after'?{anchorCardId}:{}),placement};
    // Fail before scheduling a state mutation; legacy host-valid IDs are
    // visible but can be invalid for the strict ordering writer.
    try{moveCardInState({...data,tasks:[t,...data.tasks]},move);}
    catch{
      setAdding(current=>current?{...current,error:
        'ثبت کارت با ترتیب فعلی برد ممکن نیست. عنوان شما حفظ شد؛ اطلاعات کارت‌های قدیمی را بررسی کنید.'}:current);
      setToast('کارت ثبت نشد؛ عنوان واردشده حفظ شد.');
      return;
    }
    // A different unsaved edit may already own the dirty latch. A rejected
    // no-op quick-add must never clear that edit's pending persistence.
    const dirtyBefore=dirty.current;
    change(s=>{
      // The currently selected workspace and board must still own the list.
      const board=s.boards.find(b=>b.id===targetBoard.id&&b.workspaceId===activeWorkspaceId&&!b.archived);
      if(!board||!board.stages.some(item=>item.id===stage&&!item.archived))return s;
      if((placement==='before'||placement==='after')&&
        !s.tasks.some(item=>item.id===anchorCardId&&item.boardId===board.id&&item.listId===stage&&item.deleted!==true))return s;
      const next={...s,tasks:[t,...s.tasks]};
      try{return moveCardInState(next,move);}
      catch{return s;}
    });
    // A card visible in React is NOT yet persisted. Keep its draft intact
    // until api.saveState acknowledges the snapshot, or show a save error.
    quickCardAttempt.current={id:t.id,card:t,baseline:data,
      epoch:dataMutationEpoch.current,dirtyBefore};
    setPendingQuickCardId(t.id);
  };
  const duplicateTask=template=>{
    const board=boards.find(b=>b.id===template.boardId);
    if(board?.archived){setToast('ابتدا برد بایگانی‌شده را بازیابی کنید.');return;}
    const draft=duplicateCard(template,uid(),now(),uid);
    const {cardOrder:staleOrder,...t}=draft;
    const sourceListActive=board?.stages.some(stage=>stage.id===t.listId&&stage.archived!==true);
    if(board&&!sourceListActive){
      const fallback=activeBoardLists(board)[0];
      if(!fallback){setToast('برد مقصد ستون فعال ندارد.');return;}
      t.listId=fallback.id;
      t.status=legacyStatusForStage(fallback.id,stages)||fallback.id;
    }
    change(s=>{
      const next={...s,tasks:[t,...s.tasks]};
      if(!board||!t.listId)return next;
      const placement=sourceListActive?'after':'start';
      try{return moveCardInState(next,{cardId:t.id,toListId:t.listId,
        ...(placement==='after'?{anchorCardId:template.id}:{}),placement});}
      catch{return next;}
    });
    setEditorId(t.id);setToast('تسک مشابه ساخته شد؛ هزینه‌ها و مراحل تکمیل‌شده منتقل نشدند.');
  };
  const openAdd=(status,placement='end',anchorCardId=null)=>{
    if(!canEdit)return;
    if(pendingQuickCardId){
      setToast('ابتدا نتیجهٔ ذخیره کارت قبلی مشخص شود.');
      return;
    }
    if(!workspaceBoards.length){
      setAdding(null);
      setToast('این فضای کاری هنوز برد ندارد؛ ابتدا پروژه و برد بسازید.');
      return;
    }
    const projectId=selected==='all'?
      (workspaceBoards.find(b=>activeBoardLists(b).some(s=>s.id===status))?.projectId||visibleProjects[0]?.id||''):
      selected;
    const board=boardForColumn(workspaceBoards,projectId,status,activeBoard?.id);
    if(!board||!activeBoardLists(board).some(stage=>stage.id===status)){
      setToast('برای افزودن کارت، یکی از ستون‌های برد فعال را انتخاب کنید.');
      return;
    }
    if((placement==='before'||placement==='after')&&
      !tasks.some(t=>t.id===anchorCardId&&t.boardId===board.id&&t.listId===status&&t.deleted!==true)){
      setToast('جایگاه درج کارت تغییر کرده است؛ دوباره انتخاب کنید.');return;
    }
    // The aggregate overview is never a card destination. Show the actual
    // board first, then reveal the quick composer directly in its list.
    setSelected(projectId);setBoardId(board.id);setMode('board');
    setDraftBoardId(board.id);setDraftStatus(status);setDraftProject(projectId);
    setDraftPriority('medium');setDraftTitle('');
    setAdding({boardId:board.id,projectId,listId:status,placement,anchorCardId});
  };
  const renderLaneComposer=stage=><form className="lane-quick-add" aria-label={'افزودن کارت به '+stage.label}
    onSubmit={event=>{event.preventDefault();createTask();}}>
    <textarea autoFocus rows={3} maxLength={300} required
      readOnly={!!pendingQuickCardId||blocked.current}
      aria-label="عنوان کارت جدید" placeholder="عنوان کارت را بنویسید…"
      value={draftTitle} onChange={event=>{
        setDraftTitle(event.target.value);
        setAdding(current=>current?.error?{...current,error:''}:current);
      }}
      onKeyDown={event=>{
        if(event.key==='Escape'){
          event.preventDefault();event.stopPropagation();
          if(pendingQuickCardId)return;
          setAdding(null);setDraftTitle('');
        }else if(event.key==='Enter'&&!event.shiftKey&&!event.nativeEvent.isComposing){
          event.preventDefault();if(draftTitle.trim()&&!pendingQuickCardId)createTask();
        }
      }}/>
    {adding?.error&&<p className="lane-quick-add__error" role="alert">{adding.error}</p>}
    <div className="lane-quick-add__actions">
      <button type="submit" className="lane-quick-add__save"
        disabled={!draftTitle.trim()||!!pendingQuickCardId||blocked.current}>
        <Plus size={15}/> {blocked.current?'ذخیره متوقف شد':
          pendingQuickCardId?'در حال ذخیره کارت…':'افزودن کارت'}</button>
      <button type="button" className="lane-quick-add__cancel" title="انصراف"
        aria-label="بستن افزودن کارت" disabled={!!pendingQuickCardId}
        onClick={()=>{setAdding(null);setDraftTitle('');}}><X size={19}/></button>
      <small>Enter: افزودن · Shift+Enter: خط جدید</small>
    </div>
  </form>;
  const attachExistingProject=projectId=>{
    if(!canManage||!activeWorkspaceId)return;
    const project=projects.find(p=>p.id===projectId);
    if(!project)return;
    // A new board in this workspace may reuse a project identity, but must
    // never move existing boards or cards (and their financial references).
    const board=makeBoard(project,activeWorkspaceId,stages);
    changeAdmin(s=>({...s,boards:[...(s.boards||[]),board]}));
    setSelected(project.id);setBoardId(board.id);setMode('board');
    setWorkspaceProjectToAttach('');
    setToast('برد این پروژه در فضای کاری فعلی ساخته شد؛ کارت‌ها و هزینه‌های قبلی جابه‌جا نشدند.');
  };
  const createProject=()=>{
    if(!projectName.trim())return;
    const p={id:uid(),name:projectName.trim(),color:['#5672ca','#3d977e','#b27cc2','#d39558'][projects.length%4],price:0,costEnabled:!!data.settings.costDefault,fileLinks:[]};
    const b=makeBoard(p,activeWorkspaceId||'workspace-legacy',stages);
    change(s=>({...s,projects:[...s.projects,p],boards:[...(s.boards||[]),b]}));
    setSelected(p.id);setBoardId(b.id);setProjectModal(false);setProjectName('');setToast('پروژه ساخته شد.');
  };
  const createBoard=()=>{
    if(!boardName.trim()||!selectedProject)return;
    const board=makeBoard({...selectedProject,name:boardName.trim()},
       activeWorkspaceId||'workspace-legacy',viewStages);
    changeAdmin(s=>({...s,boards:[...(s.boards||[]),board]}));
    setBoardId(board.id);setBoardName('');setBoardModal(false);setToast('برد جدید در پروژه ساخته شد.');
  };
  const renameBoard=()=>{
    if(!renameBoardId||!boardName.trim())return;
    changeAdmin(s=>renameBoardState(s,renameBoardId,boardName));
    setRenameBoardId(null);setBoardName('');setToast('نام برد تغییر کرد.');
  };
  const archiveBoard=()=>{
    if(!activeBoard||!window.confirm('برد و کارت‌های فعال آن بایگانی شوند؟ از فهرست بردهای بایگانی‌شده می‌توان آن‌ها را بازیابی کرد.'))return;
    changeAdmin(s=>archiveBoardState(s,activeBoard.id));
    setBoardId(null);setToast('برد بایگانی شد و قابل بازیابی است.');
  };
  const restoreBoard=id=>{
    changeAdmin(s=>restoreBoardState(s,id));setBoardId(id);setToast('برد و کارت‌های بایگانی‌شده همراه آن بازیابی شدند.');
  };
  const updateProject=()=>{
    if(!projectName.trim()||!projectSettings)return;
    change(s=>({...s,projects:s.projects.map(p=>p.id===projectSettings?{...p,name:projectName.trim()}:p)}));
    setProjectSettings(null);setProjectName('');setToast('نام پروژه تغییر کرد.');
  };
  const deleteProject=()=>{
    if(!projectSettings||projects.length<=1)return;
    // Do not silently re-parent tasks: their invoices, purchase sources and
    // accounting journals retain the original legal project association.
    if(tasks.some(t=>t.projectId===projectSettings)){
      setToast('حذف پروژه دارای کارت مجاز نیست؛ کارت‌ها و اسناد مالی آن باید حفظ شوند.');
      return;
    }
    const fallback=projects.find(p=>p.id!==projectSettings);
    if(!fallback)return;
    const deletedBoards=new Set(boards.filter(b=>b.projectId===projectSettings).map(b=>b.id));
    change(s=>({...s,
      projects:s.projects.filter(p=>p.id!==projectSettings),
      boards:s.boards.filter(b=>b.projectId!==projectSettings),
      templates:(s.templates||[]).filter(t=>!deletedBoards.has(t.boardId)),
    }));
    if(selected===projectSettings)setSelected('all');
    setProjectSettings(null);setProjectName('');
    setToast('پروژه خالی حذف شد؛ هیچ کارت یا سندی جابه‌جا نشد.');
  };
  const updateSettingsForBoard=fn=>{
    if(!activeBoard){
      changeAdmin(s=>propagateAddedWorkspaceStages(s,fn(s),activeWorkspaceId));
      return;
    }
    changeAdmin(s=>{
      const currentBoard=(s.boards||[]).find(board=>board.id===activeBoard.id);
      if(!currentBoard)return s;
      const localTasks=s.tasks.filter(t=>t.boardId===activeBoard.id);
      const draft={...s,stages:currentBoard.stages,tasks:localTasks};
      const edited=fn(draft);
      if(edited===draft)return s;
      const updatedStageIds=new Set(edited.stages.map(x=>x.id));
      const fallback=edited.stages.find(stage=>stage.archived!==true)?.id;
      const globalStages=[...s.stages];
      for(const stage of edited.stages){
        if(globalStages.length<40&&!globalStages.some(x=>x.id===stage.id))globalStages.push(stage);
      }
      const adapted=edited.tasks.map(t=>{
        if(updatedStageIds.has(t.listId))return t;
        const listId=updatedStageIds.has(t.status)?t.status:fallback;
        if(!listId)return t;
        return {...t,listId,status:legacyStatusForStage(listId,globalStages)||t.status};
      });
      const originalOther=s.tasks.filter(t=>t.boardId!==activeBoard.id);
      return {...s,settings:edited.settings,projects:edited.projects,
        stages:globalStages,
        boards:s.boards.map(b=>b.id===activeBoard.id?{...b,stages:edited.stages}:b),
        tasks:[...originalOther,...adapted]};
    });
  };
  const clearRecoveredFailure=()=>{
    latestUnsavedRecovery.current=null;
    try{localStorage.removeItem('madar-unsaved-recovery');}catch{}
  };
  const restoreState=s=>{
    if(!recoveryReload.current)
      throw Error('بازیابی خارج از محافظ انحصاری مجاز نیست.');
    const normalized=normalize(s);
    // Backup/Drive restore is an authoritative state replacement. Any
    // ordinary refresh started before it must not publish an older snapshot.
    dataMutationEpoch.current++;
    clearCardUndo();setData(normalized);dirty.current=false;
    lastSaved.current=JSON.stringify(normalized);
    blocked.current=false;setPendingRecovery(false);setSavingError('');
    clearRecoveredFailure();setSelected('all');setEditorId(null);
    setCloudOpen(false);setToast('اطلاعات بازیابی شد.');
    return true;
  };
  const startBackupRestore=()=>{
    if(recoveryReload.current||saving.current||dirty.current||
      pendingQuickCardId||quickCardAttempt.current){
      throw Error('ابتدا ذخیره کارت‌ها را کامل کنید. بازیابی نسخه هنگام نوشتن داده یا تغییر ذخیره‌نشده مجاز نیست.');
    }
    if(blocked.current&&!window.confirm(
      'خطای ذخیره هنوز برطرف نشده است. بازیابی نسخه، اطلاعات ذخیره‌نشده را جایگزین می‌کند. ادامه می‌دهید؟'))
      throw Error('بازیابی بدون تأیید تغییرات ذخیره‌نشده لغو شد.');
    backupRestorePreviouslyBlocked.current=blocked.current;
    recoveryReload.current=true;blocked.current=true;setSyncing(true);
  };
  const finishBackupRestore=outcome=>{
    if(outcome==='cancel')blocked.current=backupRestorePreviouslyBlocked.current;
    else if(outcome!=='applied'){
      blocked.current=true;setPendingRecovery(true);
      setSavingError('نتیجه بازیابی نسخه نامشخص است. قبل از ادامه، داده‌های میزبان و فایل بازیابی را بررسی کنید.');
    }
    backupRestorePreviouslyBlocked.current=false;
    recoveryReload.current=false;setSyncing(false);
  };
  const syncFromServer=async()=>{
    if(recoveryReload.current||saving.current){
      setToast('یک عملیات ذخیره یا بازخوانی هنوز در جریان است.');
      return;
    }
    if((blocked.current||dirty.current)&&!window.confirm('تغییرات ذخیره‌نشده وجود دارد. ابتدا از آن‌ها خروجی JSON بگیر. اطلاعات از سرور جایگزین شوند؟'))return;
    recoveryReload.current=true;blocked.current=true;setSyncing(true);
    try{
      // Do ancillary reads first: no later await may invalidate a successful
      // authoritative state replacement or clear newer recovery data.
      await refreshLan();await refreshUsers();await refresh(true);
      clearCardUndo();dirty.current=false;blocked.current=false;
      setPendingRecovery(false);setSavingError('');
      clearRecoveredFailure();setSelected('all');setEditorId(null);
    }catch(error){
      blocked.current=true;setPendingRecovery(true);
      setSavingError('بازخوانی نسخه سرور موفق نبود: '+(error?.message||String(error)));
    }finally{
      recoveryReload.current=false;setSyncing(false);
    }
  };
  const saveRecovery=()=>{
    let recovery=latestUnsavedRecovery.current;
    if(!recovery){
      // Recovery from a previous session is useful only when no newer failed
      // snapshot is held in memory. A denied read must not disable download.
      try{
        const stored=localStorage.getItem('madar-unsaved-recovery');
        if(stored){
          const parsed=JSON.parse(stored);
          if(parsed&&Array.isArray(parsed.tasks)&&Array.isArray(parsed.projects))recovery=parsed;
        }
      }catch{}
    }
    if(!recovery)recovery=latestData.current||data;
    if(!recovery){setSavingError('داده‌ای برای دریافت نسخهٔ بازیابی در دسترس نیست.');return;}
    try{
      const snapshot=JSON.stringify(recovery);
      const file=new Blob([snapshot],{type:'application/json;charset=utf-8'});
      const anchor=document.createElement('a');anchor.href=URL.createObjectURL(file);
      anchor.download='madar-unsaved-recovery.json';anchor.click();
      setTimeout(()=>URL.revokeObjectURL(anchor.href),1000);
    }catch(error){setSavingError('ساخت خروجی بازیابی ناموفق بود: '+(error?.message||String(error)));}
  };
  const discardRecovery=async()=>{
    if(recoveryReload.current||saving.current){
      setToast('یک عملیات ذخیره یا بازخوانی هنوز در جریان است.');
      return;
    }
    if(!window.confirm('تغییرات ذخیره‌نشده کنار گذاشته شود و نسخه موجود دوباره بارگیری شود؟'))return;
    recoveryReload.current=true;blocked.current=true;setSyncing(true);
    try{
      await refresh(true);
      dirty.current=false;blocked.current=false;
      setPendingRecovery(false);setSavingError('');
      clearRecoveredFailure();
    }
    catch(e){blocked.current=true;setPendingRecovery(true);setSavingError(e.message);}
    finally{recoveryReload.current=false;setSyncing(false);}
  };
  const openStandaloneDashboard=()=>{
    if(!canViewStandalone||!show('accountingDashboard'))return;
    if(dirty.current||saving.current||blocked.current){
      setToast('ابتدا تغییرات ذخیره‌نشدهٔ تسک‌منیجر را ذخیره کنید.');return;
    }
    window.location.assign('./accounting.html');
  };
  const openAccounting=source=>{
    if(!canManage)return;
    if(dirty.current||saving.current||blocked.current){
      setToast('قبل از انتقال به حسابداری، ذخیره کارت باید با موفقیت تمام شود.');return;
    }
    setAccountingSource(source||null);setEditorId(null);setAccountingOpen(true);
  };
  const prepareIndependentAccounting=async(task,expense=null)=>{
    if(!canManage){setToast('صدور سند مالی فقط برای مدیر مجاز است.');return;}
    if(dirty.current||saving.current||blocked.current){
      setToast('ابتدا ذخیره سفارش و هزینه‌های آن باید کامل شود.');return;
    }
    try{
      const result=await prepareStandaloneFromTask(api,{
        task,expense,day:todayISO()});
      setToast((result.existing?'این منبع قبلاً در حسابداری ثبت شده: ':
        'پیش‌نویس/کار به حسابداری مستقل ارسال شد: ')+result.id);
      setEditorId(null);
      window.location.assign('./accounting.html');
    }catch(err){setToast('ارسال به حسابداری ناموفق: '+String(err?.message||err));}
  };
  if(!data)return <div className="loading"><span className="logo-symbol"><img src="./madar-icon.svg" alt="" /></span><strong>مدار</strong><small>در حال آماده‌سازی فضای کار...</small>{savingError&&<span>{savingError}</span>}</div>;
  if(accountingOpen&&canManage)return <AccountingWorkspace api={api} projects={projects} tasks={tasks}
    canManage={canManage} initialSource={accountingSource} onExit={()=>{setAccountingOpen(false);setAccountingSource(null);refresh(true).catch(e=>setSavingError(e.message));}}/>;
  // New RIAL V2 is deliberately read-only/fail-closed until host supplies
  // authoritative company+period identity and a committed migration boundary.
  // Never reinterpret the existing TOMAN finance snapshot as a RIAL journal.
  if(rialJournalOpen&&canManage)return <div className="rjv-route">
    <form className="rjv-scope" onSubmit={async event=>{
      event.preventDefault();
      if(typeof api?.rialJournalActivate!=='function'){setRialActivationNotice('میزبان فعال‌سازی دفتر ریالی V2 را پشتیبانی نمی‌کند.');return;}
      if(!window.confirm('فقط یک دفتر ریالی جدید و خالی ایجاد می‌شود. هیچ فاکتور یا سند تومانی منتقل نمی‌شود. ادامه؟'))return;
      try{
        const result=await api.rialJournalActivate({
          companyId:rialCompanyId,fiscalPeriodId:rialFiscalPeriodId,
          startDate:rialFiscalStart,endDate:rialFiscalEnd});
        if(result?.currency!=='RIAL'||result?.migrationPerformed!==false){
          throw Error('پاسخ فعال‌سازی قابل اعتماد نیست.');}
        setRialActivationNotice('دفتر ریالی خالی فعال شد. داده‌های قدیمی منتقل نشده‌اند.');
        setRialRefresh(value=>value+1);
      }catch(error){setRialActivationNotice('فعال‌سازی متوقف شد: '+String(error?.message||error));}
    }}>
      <p>این دفترکل فعلاً فقط‌خواندنی است. شناسه‌های شرکت و دوره باید از دفتر ریالی V2 تأییدشده باشند؛ داده‌های تومانی قدیمی تبدیل خودکار نمی‌شوند.</p>
      <label>شناسه شرکت<input aria-label="شناسه شرکت دفتر ریالی" dir="ltr"
        value={rialCompanyId} maxLength={96} onChange={event=>setRialCompanyId(event.target.value)}/></label>
      <label>دوره مالی<input aria-label="شناسه دوره مالی ریالی" dir="ltr"
        value={rialFiscalPeriodId} maxLength={96} onChange={event=>setRialFiscalPeriodId(event.target.value)}/></label>
      <label>شروع دوره<input type="date" aria-label="شروع دوره ریالی"
        value={rialFiscalStart} onChange={event=>setRialFiscalStart(event.target.value)}/></label>
      <label>پایان دوره<input type="date" aria-label="پایان دوره ریالی"
        value={rialFiscalEnd} onChange={event=>setRialFiscalEnd(event.target.value)}/></label>
      <button type="submit" disabled={!canManage||typeof api?.rialJournalActivate!=='function'||
        !rialCompanyId||!rialFiscalPeriodId||!rialFiscalStart||!rialFiscalEnd}>
        فعال‌سازی دفتر خالی V2 (فقط با پایگاه یکپارچه)
      </button>
      {rialActivationNotice&&<p role="status">{rialActivationNotice}</p>}
    </form>
    <RialJournalPanel key={rialRefresh} api={api} companyId={rialCompanyId}
      fiscalPeriodId={rialFiscalPeriodId} canView={canManage} canPreview={false}
      onExit={()=>setRialJournalOpen(false)}/>
  </div>;
  return <div className="app-shell vitrea-layout">
    {updateInfo&&<div role="status" style={{position:'fixed',bottom:16,left:16,zIndex:1500,padding:12,borderRadius:12,background:'var(--surface, #eef3fa)',color:'var(--text, #17324b)',boxShadow:'0 4px 22px #0003',display:'flex',alignItems:'center',gap:12,maxWidth:440}}>
      <span>نسخه {updateInfo.latest} مدار منتشر شده است.</span>
      <button type="button" className="btn primary" disabled={updateBusy} onClick={actOnUpdate}>{updateBusy?'در حال پردازش…':updateDownloaded?'نصب بعد از خروج':'دریافت آپدیت'}</button>
      <button type="button" className="tiny-icon" aria-label="بعداً" onClick={()=>setUpdateInfo(null)}><X size={15}/></button>
    </div>}
    {mobileNavOpen&&<button type="button" className="mobile-nav-backdrop" aria-label="بستن فهرست پیمایش" onClick={()=>setMobileNavOpen(false)}/>}
    {desktopNavOpen&&<button type="button" className="vitrea-nav-backdrop" aria-label="بستن منوی کامل مدار" onClick={()=>{setDesktopNavOpen(false);quickDockTrigger.current?.focus();}}/>}
    <nav className="vitrea-quickdock" aria-label="میان‌برهای مدار">
      <SyncIndicator compact status={syncInfo} conflict={pendingRecovery||blocked.current}
        saving={dirty.current||saving.current} lastSync={lastSync} showDetails={openNetwork}/>
      <button type="button" className="vitrea-quickdock__refresh" onClick={manualRefresh}
        disabled={syncing} title="تازه‌سازی دستی و دریافت آخرین تغییرات" aria-label="تازه‌سازی اتصال">
        <RefreshCw size={19} className={syncing?'spin':''}/><span className="vitrea-quickdock__label" aria-hidden="true">تازه‌سازی</span></button>
      <span className="vitrea-quickdock__divider" aria-hidden="true"/>
      <button ref={quickDockTrigger} type="button" className="vitrea-quickdock__main" title="نمایش منوی کامل"
        aria-label="نمایش منوی کامل مدار" aria-controls="madar-sidebar" aria-expanded={desktopNavOpen||mobileNavOpen}
        onClick={()=>window.innerWidth<=860?setMobileNavOpen(true):setDesktopNavOpen(value=>!value)}><Menu size={20}/><span className="vitrea-quickdock__label" aria-hidden="true">فهرست مدار</span></button>
      {show('planner')&&<button type="button" title="برنامه‌ریزی" aria-label="برنامه‌ریزی"
        onClick={()=>setPlannerOpen(true)}><CalendarDays size={19}/><span className="vitrea-quickdock__label" aria-hidden="true">برنامه‌ریزی</span></button>}
      {show('reporting')&&<button type="button" title="گزارش و تحلیل" aria-label="گزارش و تحلیل"
        onClick={()=>setReportingOpen(true)}><BarChart3 size={19}/><span className="vitrea-quickdock__label" aria-hidden="true">گزارش‌ها</span></button>}
      <button type="button" onClick={()=>setNotificationsOpen(true)}
        title="اعلان‌های من" aria-label="اعلان‌ها"><Bell size={19}/><span className="vitrea-quickdock__label" aria-hidden="true">اعلان‌ها</span></button>
      {canManage&&<button type="button" onClick={openUserManagement}
        title={lanStatus.mode==='solo'?'تعریف کاربر: ابتدا میزبان شبکه را فعال کنید':'تعریف کاربران'}
        aria-label="تعریف کاربران"><Users size={19}/><span className="vitrea-quickdock__label" aria-hidden="true">کاربران</span></button>}
      <button type="button" onClick={()=>setCloudOpen(true)}
        title="Google Drive" aria-label="Google Drive"><Cloud size={19}/><span className="vitrea-quickdock__label" aria-hidden="true">پشتیبان‌گیری</span></button>
      <button type="button" title={uiTheme==='dark'?'انتخاب تم روشن':'انتخاب تم تاریک'}
        aria-label={uiTheme==='dark'?'انتخاب تم روشن':'انتخاب تم تاریک'}
        disabled={sharedThemeEnabled&&!canManage}
        onClick={toggleTheme}>
        {uiTheme==='dark'?<Sun size={19}/>:<Moon size={19}/>}<span className="vitrea-quickdock__label" aria-hidden="true">تغییر تم</span></button>
      <button type="button" title="تنظیمات" aria-label="تنظیمات مدار"
        onClick={()=>setSettingsOpen(true)}><Settings2 size={19}/><span className="vitrea-quickdock__label" aria-hidden="true">تنظیمات</span></button>
    </nav>
    <aside id="madar-sidebar" dir="rtl" role={mobileNavOpen||desktopNavOpen?'dialog':undefined}
      aria-modal={mobileNavOpen||desktopNavOpen?'true':undefined}
      aria-label={mobileNavOpen||desktopNavOpen?'فهرست پیمایش مدار':undefined}
      inert={!mobileNavOpen&&!desktopNavOpen}
      className={'sidebar'+(mobileNavOpen?' sidebar--mobile-open':'')+(desktopNavOpen?' sidebar--vitrea-open':'')}
      onClickCapture={event=>{if(event.target.closest('button')){setMobileNavOpen(false);setDesktopNavOpen(false);}}}>
      <button type="button" className="mobile-nav-close" aria-label="بستن فهرست" onClick={()=>{setMobileNavOpen(false);setDesktopNavOpen(false);quickDockTrigger.current?.focus();}}><X size={20}/></button>
      <div className="brand"><div className="brand-mark"><img src="./madar-icon.svg" alt="" /></div><div><strong>مدار</strong><small>فضای شخصی کارها</small></div></div>
      <div className="side-divider"/>
      <span className="sidebar-section">فضای کار</span>
      <div className="sidebar-nav" style={{padding:'0 12px 9px'}}>
        <label htmlFor="madar-active-workspace" className="sidebar-section">Workspace فعال</label>
        <select id="madar-active-workspace" aria-label="انتخاب فضای کاری" value={activeWorkspaceId||''} onChange={e=>{selectWorkspace(e.target.value);setMobileNavOpen(false);}} style={{width:'100%',padding:'9px',borderRadius:9}}>
          {workspaces.filter(w=>!w.archived).map(w=><option key={w.id} value={w.id}>{w.name}</option>)}
        </select>
      </div>
      <nav className="sidebar-nav" aria-label="پیمایش برنامه">
        <button title="همه کارها" className={selected==='all'?'active':''} onClick={()=>{setSelected('all');setBoardId(null);}}><LayoutGrid size={18}/> همه کارها <span>{filtered.length}</span></button>
        <button title="کارهای مهم" onClick={()=>{setSelected('all');setFilter('high');}}><Flag size={18}/> کارهای مهم</button>
      </nav>
      <details className="sidebar-group" aria-label="ابزارهای برنامه">
        <summary><BarChart3 size={17}/> گزارش‌ها و ابزارها <ChevronDown size={15}/></summary>
        <nav className="sidebar-nav" aria-label="ابزارهای تکمیلی">
          {show('reporting')&&<button onClick={()=>setReportingOpen(true)}><BarChart3 size={17}/> گزارش و تحلیل</button>}
          {show('planner')&&<button onClick={()=>setPlannerOpen(true)}><CalendarDays size={17}/> برنامه‌ریزی شخصی</button>}
          {show('activity')&&<button onClick={()=>setActivityOpen(true)}><Activity size={17}/> تاریخچه فعالیت</button>}
          {show('timeDashboard')&&<button onClick={()=>{setSelected('all');setMode('time');setFilter('all');}}><Clock3 size={17}/> داشبورد زمان</button>}
          <button onClick={()=>setTrashOpen(true)}><Trash2 size={17}/> زباله‌دان <span>{trashCards.length.toLocaleString('fa-IR')}</span></button>
          {show('trelloImport')&&<button onClick={()=>setTrelloImportOpen(true)}><FileInput size={17}/> ورود فایل Trello / Notion</button>}
          {show('trelloImport')&&<button onClick={()=>setPortableExportOpen(true)}><ArrowDownToLine size={17}/> خروجی قابل‌انتقال</button>}
          {show('calendarInterop')&&<button onClick={()=>setCalendarInteropOpen(true)}><CalendarDays size={17}/> تبادل فایل تقویم</button>}
        </nav>
      </details>
      {canViewStandalone&&show('accountingDashboard')&&<details className="sidebar-group" aria-label="بخش حسابداری">
        <summary><Wallet size={17}/> حسابداری <ChevronDown size={15}/></summary>
        <nav className="sidebar-nav" aria-label="برنامه حسابداری مستقل">
          <button type="button" onClick={openStandaloneDashboard}><Wallet size={17}/> ورود به نرم‌افزار حسابداری</button>
          {canManage&&<button type="button" onClick={()=>setRialJournalOpen(true)}><FileText size={17}/> دفتر ریالی V2 (آزمایشی)</button>}
        </nav>
      </details>}
      <div className="side-project-header"><span className="sidebar-section">پروژه‌های من</span>{canManage&&<button className="sidebar-plus" onClick={()=>setProjectModal(true)} aria-label="پروژه جدید"><Plus size={18}/></button>}</div>
      <nav className="sidebar-nav projects-nav" aria-label="پروژه‌ها">
        {visibleProjects.map(p=><div className="project-entry" key={p.id}><button title={'پروژه '+p.name} className={selected===p.id?'active':''} onClick={()=>{setSelected(p.id);setBoardId(null);setFilter('all');}}><span className="project-dot" style={{background:p.color}}/>{p.name}<span>{tasks.filter(t=>t.projectId===p.id&&!t.archived&&t.deleted!==true&&(!boards.length||workspaceBoards.some(b=>b.id===t.boardId))).length}</span></button>{show('projectAdministration')&&<button className="project-options" aria-label={'تنظیمات پروژه '+p.name} onClick={()=>{setProjectSettings(p.id);setProjectName(p.name);}}><MoreHorizontal size={15}/></button>}</div>)}
      </nav>
      {selected!=='all'&&<div className="workspace-board-nav">
        <div className="side-project-header"><span className="sidebar-section">بردهای پروژه</span>{canManage&&<button className="sidebar-plus" title="ساخت برد" onClick={()=>setBoardModal(true)}><Plus size={17}/></button>}</div>
        {workspaceBoards.filter(b=>b.projectId===selected).map(b=><button key={b.id} className={activeBoard?.id===b.id?'chosen':''} onClick={()=>{setBoardId(b.id);setAdvanced(a=>({...a,status:'all'}));}}><LayoutGrid size={14}/><span>{b.name}</span></button>)}
        {show('boardAdministration')&&boards.some(b=>b.projectId===selected&&b.workspaceId===activeWorkspaceId&&b.archived)&&<details className="archived-board-controls"><summary>بردهای بایگانی‌شده ({boards.filter(b=>b.projectId===selected&&b.workspaceId===activeWorkspaceId&&b.archived).length.toLocaleString('fa-IR')})</summary>
          {boards.filter(b=>b.projectId===selected&&b.workspaceId===activeWorkspaceId&&b.archived).map(b=><button key={b.id} onClick={()=>{restoreBoard(b.id);setAdvanced(a=>({...a,status:'all'}));}} title={'بازیابی '+b.name}><span>{b.name}</span><span>بازیابی</span></button>)}
        </details>}
      </div>}
      <div className="sidebar-bottom">
        {canManage&&<details className="sidebar-group sidebar-group--admin" aria-label="ابزارهای مدیریتی">
          <summary><ShieldCheck size={17}/> مدیریت <ChevronDown size={15}/></summary>
          <nav className="sidebar-nav" aria-label="مدیریت و دسترسی‌ها">
            {show('workspaceManagement')&&<button onClick={()=>setWorkspaceOpen(true)}><FolderOpen size={17}/> فضاهای کاری</button>}
            <button onClick={openUserManagement}><Users size={17}/> کاربران و دسترسی‌ها</button>
            {show('secureApiKeys')&&lanStatus.mode==='server'&&lanStatus.transport==='https'&&<button onClick={()=>setIntegrationOpen(true)}><ShieldCheck size={17}/> کلید API امن</button>}
          </nav>
        </details>}
        <button className="sidebar-settings" onClick={()=>setCloudOpen(true)}><Cloud size={18}/> پشتیبان‌گیری</button>
        <button className="sidebar-settings" onClick={()=>setSettingsOpen(true)}><Settings2 size={18}/> تنظیمات</button>
        <button className="sidebar-profile profile-click" title="ویرایش پروفایل من" onClick={()=>setProfileOpen(true)}><Avatar user={lanStatus.user} size={38}/><div><strong>{lanStatus.user?.displayName||lanStatus.user?.username||'فضای من'}</strong><span>{lanStatus.mode==='solo'?'حالت شخصی':'پروفایل و حساب شبکه'}</span></div><span className="profile-online"/></button>
      </div>
    </aside>

    <main className="workspace">
      <div className="vitrea-header-layout">
      <div className="vitrea-header-main">
      <div className="vitrea-top-row">
      <button type="button" className="vitrea-brand-capsule" title="بازگشت به برد کارها"
        onClick={openBoardView}>
        <img src="./madar-icon.svg" alt="" aria-hidden="true" /><strong>مدار</strong><i aria-hidden="true">|</i>
        <small>در جریان کسب و کار</small>
      </button>
      <nav className="vitrea-primary-nav" aria-label="بخش‌های اصلی مدار">
        <button type="button" aria-label="نمای کلی" aria-current={selected==='all'&&mode==='board'?'page':undefined}
          onClick={()=>{setSelected('all');setBoardId(null);setMode('board');setFilter('all');}}><LayoutDashboard size={16}/><span className="vitrea-primary-nav__label">نمای کلی</span></button>
        <button type="button" aria-label="برد کارها" aria-current={selected!=='all'&&mode==='board'?'page':undefined}
          onClick={openBoardView}><LayoutGrid size={16}/><span className="vitrea-primary-nav__label">برد کارها</span></button>
        <button type="button" aria-label="فهرست" aria-current={mode==='list'?'page':undefined}
          onClick={()=>setMode('list')}><ListChecks size={16}/><span className="vitrea-primary-nav__label">فهرست</span></button>
        <button type="button" aria-label="پروژه‌ها" aria-expanded={desktopNavOpen||mobileNavOpen} aria-controls="madar-sidebar"
          onClick={()=>window.innerWidth<=860?setMobileNavOpen(true):setDesktopNavOpen(true)}><FolderOpen size={16}/><span className="vitrea-primary-nav__label">پروژه‌ها</span></button>
        {show('planner')&&<button type="button" aria-label="برنامه‌ریزی" onClick={()=>setPlannerOpen(true)}><CalendarDays size={16}/><span className="vitrea-primary-nav__label">برنامه‌ریزی</span></button>}
        {canViewStandalone&&show('accountingDashboard')&&<button type="button" aria-label="حسابداری" onClick={openStandaloneDashboard}><Wallet size={16}/><span className="vitrea-primary-nav__label">حسابداری</span></button>}
      </nav>
      <button type="button" className="vitrea-account-capsule" onClick={()=>setProfileOpen(true)}
        aria-label="نمایش پروفایل من" title="پروفایل من">
        <Avatar user={lanStatus.user} size={32}/>
      </button>
      </div>
      <header className="topbar">
        <button className="mobile-nav-toggle" type="button" aria-controls="madar-sidebar"
          aria-expanded={mobileNavOpen} aria-label="بازکردن فهرست پیمایش"
          onClick={()=>setMobileNavOpen(true)}><Menu size={20}/></button>
        <SearchPlus query={search} onQueryChange={setSearch} resultCount={search.trim()?globalSearch.results.length:filtered.length}
          totalCount={tasks.length}
          placeholder="جست‌وجوی کامل در عنوان، توضیحات، برچسب و اعضا..."/>
        <div className="breadcrumb"><span>فضای کار من</span><ChevronLeft size={16}/>
          <strong>{selectedProject?.name||'همه کارها'}</strong></div>
      </header>
      </div>
      <div className="vitrea-header-clock"><ClockWidget calendar={calendar}/></div>
      </div>
      <div className="workspace-scroll">
        {search.trim()&&<>{globalSearch.error&&<p role="alert" className="warning">{globalSearch.error}</p>}
          <SearchResultsPanel query={search} results={globalSearch.results} canEdit={canEdit}
            formatDate={date=>displayDate(date,calendar,true)}
            onOpenTask={(id)=>{setSearch('');setEditorId(id);}}
            onRestoreArchived={(id)=>restoreArchivedTask(id)}
            onRestoreTrashed={(id)=>restoreTrashedCard(id)}
            onGoToLocation={navigateSearchLocation} onClose={()=>setSearch('')}/>
        </>}

        <section className="page-header" data-board-header={workspaceBoards.length&&mode==='board'?'true':'false'}><div className="page-heading"><h1 title={activeBoard?'برد فعال':'نمای کارها'}>{activeBoard?.name||selectedProject?.name||'همه‌چیز، روی مدار.'}</h1></div><div className="page-controls">{lanStatus.mode==='solo'&&canEdit&&<><button type="button" className="btn secondary" disabled={!canUndo} aria-label="بازگرداندن آخرین ویرایش کارت" aria-keyshortcuts="Control+Z" title="بازگرداندن آخرین ویرایش کارت (Ctrl+Z)" onClick={()=>reverseCardEdit('undo')}><Undo2 size={15}/> بازگشت</button><button type="button" className="btn secondary" disabled={!canRedo} aria-label="انجام دوباره آخرین ویرایش کارت" aria-keyshortcuts="Control+Shift+Z Control+Y" title="انجام دوباره ویرایش کارت (Ctrl+Y)" onClick={()=>reverseCardEdit('redo')}><Redo2 size={15}/> انجام دوباره</button></>}{activeBoard&&<button type="button" className="btn secondary" onClick={()=>setCardArchiveOpen(true)} title="آرشیو کارت‌ها"><Archive size={15}/> آرشیو کارت‌ها ({archivedCards.length.toLocaleString('fa-IR')})</button>}{show('boardAdministration')&&activeBoard&&<><button className="btn secondary" onClick={()=>{setRenameBoardId(activeBoard.id);setBoardName(activeBoard.name);}} title="تغییر نام برد"><MoreHorizontal size={15}/> تغییر نام برد</button><button className="btn secondary" onClick={archiveBoard} title="بایگانی برد"><Archive size={15}/> بایگانی برد</button></>}</div></section>
        {show('profitPeek')&&profitVisible&&<ProfitPeek api={api} projectId={selectedProject?.id||''}/>}
        {selectedProject&&<details className="project-file-panel project-file-panel--compact" key={selectedProject.id} defaultOpen={!!selectedProject.fileLinks?.length}>
          <summary><FolderOpen size={17}/> فایل‌های اشتراکی پروژه{!!selectedProject.fileLinks?.length&&<small>{selectedProject.fileLinks.length} لینک</small>}</summary>
          <SharedLinks links={selectedProject.fileLinks||[]} api={api} canEdit={canManage} onChange={fileLinks=>changeAdmin(s=>({...s,projects:s.projects.map(p=>p.id===selectedProject.id?{...p,fileLinks}:p)}))}/>
        </details>}
        {selectedProject&&(show('projectFinance')||show('automationRules'))&&<div className="page-controls page-controls--project-quick">{show('projectFinance')&&<button className="btn secondary" onClick={()=>setFinanceOpen(true)}><FileText size={16}/> قراردادها و فاکتورهای این پروژه</button>}{show('automationRules')&&<button className="btn secondary" onClick={()=>setRulesOpen(true)}><Zap size={16}/> قوانین خودکار پروژه</button>}</div>}
        {selected==='all'&&mode==='board'&&<VitreaOverview tasks={filtered}
          projects={visibleProjects} stages={viewStages} onOpenTask={setEditorId}
          onSelectProject={id=>{setSelected(id);setBoardId(null);setFilter('all');}}/>}
        {workspaceBoards.length ? <section className="board-section">
          <div className="board-toolbar"><div className="board-tabs"><button className={mode==='board'?'selected':''} aria-label="برد کارها" onClick={openBoardView} title="نمای برد"><LayoutGrid size={17}/> برد کارها</button><button className={mode==='list'?'selected':''} aria-label="فهرست" onClick={()=>switchBoardDisplay('list')} title="نمای فهرست"><ListChecks size={17}/> فهرست</button><button className={mode==='table'?'selected':''} aria-label="جدول" onClick={()=>switchBoardDisplay('table')} title="نمای جدول قابل تنظیم"><Table2 size={17}/> جدول</button>{show('timelineView')&&<button className={mode==='time'?'selected':''} aria-label="زمان‌بندی" onClick={()=>setMode('time')} title="زمان‌بندی"><BarChart3 size={17}/> زمان‌بندی</button>}</div><div className="board-filters">{show('advancedFilters')&&<AdvancedFilters key={'filters:'+advancedScope} identity={plannerIdentity(lanStatus)} scopeId={boardViewScope} tasks={tasks} users={users} stages={viewStages} priorities={priorities} value={advanced} onChange={setAdvanced}/>}<select aria-label="فیلتر سریع" title="فیلتر اولویت" className="filter-select" value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">همه اولویت‌ها</option><option value="high">اولویت بالا</option><option value="with-reports">دارای گزارش</option></select></div></div>
          {show('timeDashboard')&&mode==='time'?<TimeDashboard tasks={filtered} projects={projects} onOpen={setEditorId} calendar={calendar}/>:mode==='table'?<BoardTableView key={boardViewIdentity+'|'+boardViewScope} board={activeBoard} scopeId={boardViewScope} identity={boardViewIdentity} storage={localStorage} tasks={filtered} stages={viewStages} projects={visibleProjects} users={users} priorities={priorities} calendar={calendar} onOpen={setEditorId} onContextRequest={requestCardMenu}/>:mode==='board'?<div className="kanban" aria-label="برد کارها">{viewStages.map(stage=>{
            const items=boardGroups.get(stage.id)||[];
            const listKey=(activeBoard?.id||'legacy')+'|'+stage.id;
            const isCollapsed=collapsedLists[listKey]===true;
            const toggleCollapse=()=>setCollapsedLists(current=>({...current,[listKey]:!current[listKey]}));
            const laneMenu=<LaneActionsMenu stage={stage} count={items.length}
              canManage={canManage&&show('boardAdministration')} canEdit={canEdit}
              index={viewStages.indexOf(stage)} total={viewStages.length}
              onSave={fields=>updateStagePresentation(stage.id,fields)}
              onMove={direction=>{const index=viewStages.findIndex(item=>item.id===stage.id);const target=viewStages[index+direction];if(target)reorderStage(stage.id,target.id);}}
              onArchive={activeBoard?()=>{if(tasks.some(task=>task.boardId===activeBoard.id&&task.listId===stage.id&&task.deleted!==true)&&!window.confirm('این ستون بایگانی شود؟ کارت‌ها و اطلاعات مالی حذف نمی‌شوند و با بازیابی ستون دوباره در دسترس خواهند بود.'))return;updateBoardListArchive(stage.id);}:undefined}
              onCopyList={activeBoard?()=>copyBoardList(stage.id):undefined}
              onSort={activeBoard?sortBy=>sortBoardList(stage.id,sortBy):undefined}
              moveTargets={activeBoard?viewStages.filter(item=>item.id!==stage.id):[]}
              onMoveAll={activeBoard?targetId=>moveAllBoardList(stage.id,targetId):undefined}
              onAutomation={activeBoard&&canManage&&show('automationRules')?()=>{
                setAutomationListId(stage.id);setRulesOpen(true);
              }:undefined}
              onAddCard={()=>openAdd(stage.id)} onAddCardTop={()=>openAdd(stage.id,'start')}
              onToggleCollapse={toggleCollapse} collapsed={isCollapsed}
              contextRequest={laneContextRequest?.stageId===stage.id?laneContextRequest:null}
              onContextConsumed={id=>setLaneContextRequest(current=>current?.id===id?null:current)}/>;
            return <section className={'kanban-lane'+(isCollapsed?' kanban-lane--collapsed':'')} key={stage.id}
              style={{'--stage-accent':stage.color}} aria-label={'ستون '+stage.label}
              onContextMenuCapture={event=>{
                // React capture catches right-clicks on the header, its buttons,
                // the empty lane surface and the collapsed rail in WebView2.
                // Card/editor context stays separate from list operations.
                if(event.target.closest('.task-card,input,textarea,select,.lane-quick-add,[contenteditable="true"]'))return;
                event.preventDefault();
                event.stopPropagation();
                setLaneContextRequest({stageId:stage.id,id:++laneContextSequence.current,x:event.clientX,y:event.clientY});
              }}
              onDragOver={e=>{if(!isCollapsed&&(canEdit||canManage)){e.preventDefault();e.dataTransfer.dropEffect='move';}}}
              onDrop={e=>{if(isCollapsed)return;e.preventDefault();const plain=e.dataTransfer.getData('text/plain');const draggedStage=e.dataTransfer.getData('application/x-madar-stage')||(plain.startsWith('madar-stage:')?plain.slice(12):'');if(draggedStage){if(canManage)reorderStage(draggedStage,stage.id);return;}if(!canEdit)return;const id=e.dataTransfer.getData('application/x-madar-card')||plain;const task=tasks.find(t=>t.id===id);if(!task||activeBoard&&task.boardId!==activeBoard.id)return;const originBoard=boards.find(b=>b.id===task.boardId);if(task.boardId&&(!originBoard||!originBoard.stages.some(s=>s.id===stage.id)))return;if(activeBoard)reorderCard(id,stage.id);else taskUpdate(id,task.boardId?{listId:stage.id}:{status:stage.id});}}>
              {isCollapsed?<div className="lane-collapsed-content">
                <button type="button" className="lane-expand-control" aria-label={'بازکردن ستون '+stage.label}
                  aria-expanded={false} title={'بازکردن '+stage.label} onClick={toggleCollapse}><ChevronLeft size={19}/></button>
                <span className="lane-collapsed-count" title={items.length+' کارت'}>{items.length.toLocaleString('fa-IR')}</span>
                <strong className="lane-collapsed-title" title={stage.label}>{stage.label}</strong>
                <div className="lane-collapsed-menu">{laneMenu}</div>
              </div>:<>
              <div className="lane-head"><div className="lane-heading">{show('boardAdministration')&&<button className="stage-drag-handle" type="button" draggable title={'کشیدن و جابه‌جایی ستون '+stage.label} aria-label={'جابجایی ستون '+stage.label} onDragStart={e=>{e.stopPropagation();e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('application/x-madar-stage',stage.id);e.dataTransfer.setData('text/plain','madar-stage:'+stage.id);}} onKeyDown={e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();const i=viewStages.findIndex(item=>item.id===stage.id);const target=viewStages[i+(e.key==='ArrowLeft'?1:-1)];if(target)reorderStage(stage.id,target.id);}}}><GripVertical size={16}/></button>}<span className="stage-dot" style={{background:stage.color}}/><strong>{stage.label}</strong><span className="lane-count">{items.length.toLocaleString('fa-IR')}</span></div><div className="lane-stage-actions"><button className="lane-collapse-toggle" type="button" title={'جمع‌کردن '+stage.label} aria-label={'جمع‌کردن ستون '+stage.label} aria-expanded={true} onClick={toggleCollapse}><ChevronLeft size={17}/></button>{laneMenu}</div></div>
              <div className="lane-subtitle">{stage.subtitle}</div>
              <ProgressiveLane items={items} scopeKey={[activeWorkspaceId,activeBoard?.id||'legacy',selected,search,filter,lanStatus.mode,lanStatus.user?.username||'local'].join('|')} regionId={'madar-lane-'+viewStages.indexOf(stage)} label={stage.label} renderCard={(t,i)=><React.Fragment key={t.id}>
                {canEdit&&<div className="lane-insert-slot">
                  {adding?.boardId===activeBoard?.id&&adding?.listId===stage.id&&
                    ((adding?.placement==='before'&&adding?.anchorCardId===t.id)||(adding?.placement==='start'&&i===0))
                    ?renderLaneComposer(stage)
                    :<button type="button" className="lane-insert-before" aria-label={i===0?'افزودن کارت در ابتدای '+stage.label:'افزودن کارت پیش از '+t.title} title={i===0?'افزودن کارت در بالا':'افزودن کارت در این موقعیت'} onClick={()=>openAdd(stage.id,'before',t.id)}><Plus size={13}/> افزودن کارت</button>}
                </div>}
                <TaskCard task={t} project={projects.find(p=>p.id===t.projectId)} users={users} calendar={calendar} priorities={priorities} canEdit={canEdit} canManage={canManage} showCosts={show('profitPeek')} onOpen={setEditorId} onContextRequest={requestCardMenu} onDrag={()=>{}} onCardDrop={activeBoard?(id,anchor,placement)=>reorderCard(id,stage.id,anchor,placement):undefined} onKeyboardReorder={activeBoard?(id,direction)=>{const neighbor=items[i+direction];if(neighbor)reorderCard(id,stage.id,neighbor.id,direction<0?'before':'after');}:undefined} onToggleComplete={toggleCardComplete} onToggleStep={toggleChecklistStep}/>
              </React.Fragment>} empty={<div className="lane-empty-message">هنوز کارتی نیست</div>} />
              {canEdit&&(adding?.boardId===activeBoard?.id&&adding?.listId===stage.id&&
                (adding.placement==='end'||(adding.placement==='start'&&items.length===0))
                ?renderLaneComposer(stage)
                :<button type="button" className="lane-add-card" onClick={()=>openAdd(stage.id,'end')}>
                  <Plus size={16}/> افزودن کارت
                </button>)}
              </>}
            </section>;
          })}
          {canManage&&show('boardAdministration')&&
            <div className="kanban-add-list" aria-label="افزودن ستون جدید به برد">
              {addingLane?
                <form className="kanban-add-list__form" onSubmit={event=>{event.preventDefault();addLane();}}>
                  <input autoFocus aria-label="نام ستون جدید" maxLength={100} value={newLaneName}
                    placeholder="نام ستون جدید را وارد کنید..."
                    onChange={event=>setNewLaneName(event.target.value)}
                    onKeyDown={event=>{if(event.key==='Escape'){event.stopPropagation();setAddingLane(false);setNewLaneName('');}}}/>
                  <div className="kanban-add-list__actions">
                    <button type="submit" disabled={!newLaneName.trim()}><Plus size={15}/> افزودن لیست</button>
                    <button type="button" aria-label="انصراف از افزودن لیست" onClick={()=>{setAddingLane(false);setNewLaneName('');}}><X size={18}/></button>
                  </div>
                </form>:
                <button type="button" className="kanban-add-list__trigger" onClick={()=>setAddingLane(true)}><Plus size={20}/> افزودن یک لیست دیگر</button>}
            </div>}
        </div>:<div className="list-mode">{filtered.length?<ProgressiveLane items={filtered} scopeKey={[activeWorkspaceId,activeBoard?.id||'legacy',selected,search,filter,lanStatus.mode,lanStatus.user?.username||'local','list'].join('|')} regionId="madar-task-list" label="فهرست کارها" containerClassName="progressive-list-rows" renderCard={t=><button key={t.id} className="list-row" onClick={()=>setEditorId(t.id)} onContextMenu={event=>{event.preventDefault();requestCardMenu(t,event);}}><span className="list-title"><Circle size={16} color={viewStages.find(s=>s.id===(activeBoard?(t.listId||t.status):t.status))?.color}/>{t.title}</span><span>{projects.find(p=>p.id===t.projectId)?.name}</span><span>{displayDate(t.dueDate||t.createdAt,calendar,true)}</span><span className="priority" style={{color:priorityById(priorities,t.priority).color}}><Flag size={13}/>{priorityById(priorities,t.priority).label}</span><ChevronLeft size={16}/></button>} />:<div className="empty-list">کاری با این فیلتر پیدا نشد.</div>}</div>}
        </section> : <section className="workspace-empty-board" aria-label="راه‌اندازی برد فضای کاری">
          <LayoutGrid size={26} aria-hidden="true"/>
          <h2>این فضای کاری هنوز بردی ندارد</h2>
          <p>کارت‌ها داخل ستون‌های یک برد ساخته می‌شوند. ابتدا برای این فضا یک پروژه و برد بسازید یا پروژه موجود را به این فضا اضافه کنید.</p>
          {canManage&&<div className="workspace-empty-board__actions">
            <button className="btn primary" type="button" onClick={()=>{setProjectName('');setProjectModal(true);}}>
              <Plus size={17}/> ساخت اولین پروژه
            </button>
            {projects.length>0&&<div className="workspace-empty-board__attach">
              <label htmlFor="madar-workspace-project">پروژه موجود</label>
              <select id="madar-workspace-project" value={workspaceProjectToAttach||projects[0]?.id||''}
                onChange={event=>setWorkspaceProjectToAttach(event.target.value)}>
                {projects.map(project=><option key={project.id} value={project.id}>{project.name}</option>)}
              </select>
              <button type="button" className="btn secondary"
                onClick={()=>attachExistingProject(workspaceProjectToAttach||projects[0]?.id)}>
                <Plus size={16}/> ساخت برد در این فضا</button>
            </div>}
          </div>}
        </section>}
        <footer className="app-footer">
          <span>مدار · نسخه {packageInfo.version}</span>
          <a href="https://packpoc.com" target="_blank" rel="noopener noreferrer">Powered by packpoc.com</a>
        </footer>
      </div>
    </main>
    {savingError&&<div className="error-toast recovery-alert"><span>{savingError}</span>{pendingRecovery&&<div className="recovery-actions"><button onClick={saveRecovery}>دریافت تغییرات ذخیره‌نشده</button><button onClick={discardRecovery}>بازخوانی نسخه سرور</button></div>}</div>}
    <CardContextMenu request={cardContext} onClose={()=>setCardContext(null)}
      onOpen={id=>{setEditorInitialSection(null);setEditorId(id);}}
      onOpenSection={(id,section)=>{setEditorInitialSection(section);setEditorId(id);}}
      onDuplicate={id=>{const found=tasks.find(task=>task.id===id&&task.deleted!==true);if(found)duplicateTask(found);}}
      onToggleComplete={toggleCardComplete} onArchive={archiveTask} onDelete={deleteTask}
      canEdit={canEdit}/>
    {cardArchiveOpen&&<Modal title="آرشیو کارت‌ها" width={680} onClose={()=>setCardArchiveOpen(false)}>
      <div className="dialog-body">
        <p className="board-info-note">آرشیو کارت از حذف متفاوت است. شناسه، وضعیت، فاکتورها و پیوست‌های کارت محفوظ می‌مانند.</p>
        {archivedCards.length?archivedCards.map(task=>{
          const board=boards.find(item=>item.id===task.boardId);
          const workspace=workspaces.find(item=>item.id===board?.workspaceId);
          return <div className="similar-row" key={task.id} style={{padding:'12px 0'}}>
            <span><strong>{task.title}</strong><small>{board?.name||'برد قدیمی'}</small></span>
            <button type="button" disabled={!canEdit||!!board?.archived||!!workspace?.archived}
              onClick={()=>restoreArchivedTask(task.id)} aria-label={'بازگرداندن کارت '+task.title}>بازیابی کارت</button>
          </div>;
        }):<p className="shared-empty">در این فضای کاری کارت بایگانی‌شده‌ای وجود ندارد.</p>}
      </div>
    </Modal>}
    {show('projectFinance')&&financeOpen&&selectedProject&&<FinancePanel api={api} project={selectedProject} tasks={tasks.filter(t=>t.projectId===selectedProject.id)} onClose={()=>setFinanceOpen(false)}/>}
    {show('reporting')&&reportingOpen&&<ReportingPanel tasks={tasks.filter(t=>t.deleted!==true)} projects={projects} stages={viewStages} calendar={calendar} onOpenTask={setEditorId} onClose={()=>setReportingOpen(false)}/>}
    {trashOpen&&<Modal title="زباله‌دان کارت‌ها" width={680} onClose={()=>setTrashOpen(false)}>
      <div className="dialog-body">
        <p className="board-info-note">حذف دائمی انجام نمی‌شود. کارت، هزینه‌ها، فاکتورها و پیوست‌ها با شناسه اصلی نگهداری می‌شوند.</p>
        {trashCards.length?trashCards.map(t=>{
          const board=boards.find(b=>b.id===t.boardId);
          const workspace=workspaces.find(w=>w.id===board?.workspaceId);
          const containerArchived=board?.archived||workspace?.archived;
          return <div key={t.id} className="similar-row" style={{padding:'12px 0'}}>
            <span><strong>{t.title}</strong><small>{projects.find(p=>p.id===t.projectId)?.name||'پروژه قدیمی'} · {board?.name||'کارت قدیمی'}{containerArchived?' · فضای بایگانی‌شده':''}</small></span>
            <button type="button" disabled={!canEdit||!!containerArchived} onClick={()=>restoreTrashedCard(t.id)} aria-label={'بازیابی کارت '+t.title}>بازیابی کارت</button>
          </div>;
        }):<p className="shared-empty">در این فضای کاری کارت حذف‌شده‌ای وجود ندارد.</p>}
      </div>
    </Modal>}
    {show('workspaceManagement')&&workspaceOpen&&<Modal title="مدیریت فضاهای کاری" width={800} onClose={()=>setWorkspaceOpen(false)}><WorkspaceManager data={data} currentWorkspaceId={activeWorkspaceId} canManage={canManage} onChange={changeAdmin} onSelect={selectWorkspace}/></Modal>}
    {show('trelloImport')&&trelloImportOpen&&<TrelloImportPanel onClose={()=>setTrelloImportOpen(false)} onImport={changeAdmin}/>}
    {show('trelloImport')&&portableExportOpen&&<Modal title="خروجی قابل‌انتقال مدار" width={680} onClose={()=>setPortableExportOpen(false)}><PortableExportPanel state={data} canManage={canManage} onClose={()=>setPortableExportOpen(false)}/></Modal>}
    {show('planner')&&plannerOpen&&(plannerIdentity(lanStatus)
      ?<PlannerPanel tasks={tasks.filter(t=>t.deleted!==true)} projects={projects} calendar={calendar} onClose={()=>setPlannerOpen(false)} onOpenTask={id=>{setPlannerOpen(false);setEditorId(id);}} accountId={plannerIdentity(lanStatus)}/>
      :<Modal title="برنامه‌ریزی شخصی" onClose={()=>setPlannerOpen(false)}><p className="dialog-body">شناسه سرور یا حساب کاربری مشخص نیست. برای جلوگیری از تداخل برنامه‌های شخصی، ابتدا اتصال را تکمیل کنید.</p></Modal>)}
    {show('automationRules')&&rulesOpen&&selectedProject&&<RulesPanel api={api} project={selectedProject} users={users}
      initialListId={automationListId} listOptions={activeBoard?activeBoardLists(activeBoard):viewStages}
      priorityOptions={priorities}
      onManageButtons={scope=>{setRulesOpen(false);setAutomationListId(null);setAutomationButtonsScope(scope);}}
      onClose={()=>{setRulesOpen(false);setAutomationListId(null);}}/>}
    {automationButtonsScope&&selectedProject&&activeBoard&&
      <AutomationButtonsPanel modal api={api} project={selectedProject} boardId={activeBoard.id}
        users={users} initialScope={automationButtonsScope}
        cardOptions={tasks.filter(t=>t.boardId===activeBoard.id&&t.deleted!==true&&t.archived!==true).map(t=>({id:t.id,title:t.title}))}
        canManage={canManage} canRun={canEdit} onClose={()=>setAutomationButtonsScope(null)}/>}
    {toast&&<div className="toast"><CheckCircle2 size={18}/>{toast}</div>}
    {!!activeTask&&activeTask.deleted!==true&&<TaskEditor key={activeTask.id} task={activeTask} stages={activeTask.boardId?boards.find(b=>b.id===activeTask.boardId)?.stages||stages:stages} projects={projects} boards={boards} users={users} username={lanStatus.user?.username} calendar={calendar} api={api} allTasks={tasks.filter(t=>t.deleted!==true)} allTemplates={data.templates||[]} priorities={priorities} canEdit={canEdit} canManage={canManage} showCosts={show('taskCostControls')} showOperations={show('taskTime')} initialSection={editorInitialSection} onUpdate={taskUpdate} onBoardChange={board=>changeAdmin(s=>({...s,boards:s.boards.map(item=>item.id===board.id?board:item)}))} onUndo={lanStatus.mode==='solo'&&canEdit?()=>reverseCardEdit('undo'):undefined} onRedo={lanStatus.mode==='solo'&&canEdit?()=>reverseCardEdit('redo'):undefined} canUndo={canUndo} canRedo={canRedo} onDuplicate={duplicateTask} onOpenSale={task=>prepareIndependentAccounting(task)} onOpenPurchase={(task,expense)=>prepareIndependentAccounting(task,expense)} onClose={()=>{setEditorId(null);setEditorInitialSection(null);}} onArchive={()=>archiveTask(activeTask.id)} onDelete={()=>deleteTask(activeTask.id)}/>}

    {projectModal&&<Modal title="پروژه جدید" onClose={()=>setProjectModal(false)}><form className="dialog-body task-create" onSubmit={e=>{e.preventDefault();createProject();}}><label>نام پروژه<input autoFocus maxLength={180} value={projectName} onChange={e=>setProjectName(e.target.value)} placeholder="مثلاً: برنامه‌های شخصی" required/></label><div className="form-footer"><button className="btn secondary" type="button" onClick={()=>setProjectModal(false)}>انصراف</button><button type="submit" disabled={!projectName.trim()} className="btn primary"><Plus size={17}/> ساخت پروژه</button></div></form></Modal>}
    {boardModal&&<Modal title="برد جدید در پروژه" onClose={()=>setBoardModal(false)}><form className="dialog-body task-create" onSubmit={e=>{e.preventDefault();createBoard();}}><label>نام برد<input autoFocus maxLength={180} value={boardName} onChange={e=>setBoardName(e.target.value)} required placeholder="مثلاً: تولید محتوا"/></label><div className="form-footer"><button type="button" className="btn secondary" onClick={()=>setBoardModal(false)}>انصراف</button><button type="submit" className="btn primary" disabled={!boardName.trim()}>ساخت برد</button></div></form></Modal>}
    {renameBoardId&&<Modal title="تغییر نام برد" onClose={()=>{setRenameBoardId(null);setBoardName('');}}><form className="dialog-body task-create" onSubmit={e=>{e.preventDefault();renameBoard();}}><label>نام جدید برد<input autoFocus maxLength={180} value={boardName} onChange={e=>setBoardName(e.target.value)} required/></label><p className="board-info-note">کارت‌ها و مراحل برد حفظ می‌شوند.</p><div className="form-footer"><button type="button" className="btn secondary" onClick={()=>{setRenameBoardId(null);setBoardName('');}}>انصراف</button><button type="submit" className="btn primary" disabled={!boardName.trim()}>ذخیره نام</button></div></form></Modal>}
    {canManage&&show('projectAdministration')&&!!projectSettings&&<Modal title="تنظیمات پروژه" onClose={()=>{setProjectSettings(null);setProjectName('');}}><form className="dialog-body task-create" onSubmit={e=>{e.preventDefault();updateProject();}}><label>نام پروژه<input autoFocus maxLength={180} value={projectName} onChange={e=>setProjectName(e.target.value)} required/></label>{show('projectPricing')&&<label className="setting-toggle" style={{marginTop:18}}><input type="checkbox" checked={!!projects.find(p=>p.id===projectSettings)?.costEnabled} onChange={e=>changeAdmin(s=>({...s,projects:s.projects.map(p=>p.id===projectSettings?{...p,costEnabled:e.target.checked}:p)}))}/><span><strong>فعال کردن فیلد هزینه</strong><small>قیمت پروژه، هزینه کار و مراحل و محاسبه سود نشان داده می‌شود.</small></span></label>}{show('projectPricing')&&projects.find(p=>p.id===projectSettings)?.costEnabled&&<div className="project-price-field"><strong>قیمت پروژه</strong><MoneyField value={projects.find(p=>p.id===projectSettings)?.price||0} onChange={price=>changeAdmin(s=>({...s,projects:s.projects.map(p=>p.id===projectSettings?{...p,price}:p)}))}/></div>}<p className="project-setting-note">کارهای داخل این پروژه با تغییر نام محفوظ می‌مانند.</p><div className="form-footer"><button type="button" className="btn secondary" onClick={()=>{if(!window.confirm('پروژه حذف شود؟ کارهایش به پروژه دیگری منتقل خواهند شد.'))return;deleteProject();}} disabled={projects.length<=1||tasks.some(t=>t.projectId===projectSettings)} title={tasks.some(t=>t.projectId===projectSettings)?'ابتدا پروژه را خالی کنید؛ اسناد مالی نباید جدا شوند.':'حذف پروژه خالی'}>حذف پروژه</button><button type="submit" disabled={!projectName.trim()} className="btn primary"><Check size={17}/> ذخیره تغییرات</button></div></form></Modal>}
    {settingsOpen&&<SettingsPanel data={activeBoard?{...data,stages:activeBoard.stages}:data} priorityUsedIds={tasks.map(t=>t.priority)} onChange={updateSettingsForBoard} canManage={canManage} theme={uiTheme} onThemeChange={chooseTheme} updateApi={isDesktop?api:null} boardId={activeBoard?.id||null} onArchiveList={id=>updateBoardListArchive(id,false)} onRestoreList={id=>updateBoardListArchive(id,true)} onOpenBoardButtons={()=>{setSettingsOpen(false);setAutomationButtonsScope('board');}} calendar={calendar} onCalendarChange={async choice=>{try{await api.setPreferences({calendar:choice,widgetSettings});setCalendar(choice);}catch(e){setToast(e.message);}}} onClose={()=>setSettingsOpen(false)}/>}
    {lanOpen&&<LanPanel api={api} projects={projects} status={lanStatus} initialView={lanInitialView} onRefresh={refreshLan} onConnected={syncFromServer} onClose={()=>setLanOpen(false)}/>}
    {show('secureApiKeys')&&integrationOpen&&<IntegrationKeyPanel api={api} users={users} onClose={()=>setIntegrationOpen(false)}/>}
    {show('calendarInterop')&&calendarInteropOpen&&<CalendarFilePanel api={api} projects={projects} boards={boards} onClose={()=>setCalendarInteropOpen(false)} onImport={(project,events)=>changeAdmin(s=>importCalendarEvents(s,project,events,uid,now()))}/>}
    {notificationsOpen&&<NotificationsDialog api={api} onClose={()=>setNotificationsOpen(false)}/>}
    {activityOpen&&<ActivityDialog api={api} onClose={()=>setActivityOpen(false)}/>}
    {profileOpen&&<ProfilePanel api={api} user={lanStatus.user} onClose={()=>setProfileOpen(false)} onUpdated={async()=>{await refreshLan();await refreshUsers();}}/>}
    {cloudOpen&&<DrivePanel data={data} isClient={lanStatus.mode==='client'}
      onClose={()=>setCloudOpen(false)} onRestore={restoreState}
      onRestoreStart={startBackupRestore} onRestoreFinished={finishBackupRestore}/>}
  </div>;
}
