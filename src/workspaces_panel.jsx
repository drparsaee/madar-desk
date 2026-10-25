import React, {useEffect, useState} from 'react';
import {Archive, Check, FolderOpen, LayoutGrid, Pencil, Plus, RefreshCcw, X} from 'lucide-react';
import {
  LEGACY_WORKSPACE_ID, activeWorkspaceId, archiveWorkspaceState,
  createWorkspaceState, generateWorkspaceId, moveBoardWorkspaceState,
  renameWorkspaceState, restoreWorkspaceState, selectWorkspaceId,
  validateWorkspaceLinks,
} from './workspaces_logic.js';
import './workspaces_panel.css';

/**
 * Drop-in manager for the existing v1 task state. NOT an authenticated host.
 * onChange(updater) must be an App.changeAdmin-style state updater:
 *   updater(currentState) => nextState.
 * onSelect(workspaceId) only changes parent navigation, not persisted state.
 * A read-only user can switch workspaces; mutations require canManage=true.
 */
export function WorkspaceManager({
  data, currentWorkspaceId, canManage=false, onChange, onSelect, idFactory,
}) {
  const [newName, setNewName] = useState('');
  const [rename, setRename] = useState(null);
  const [error, setError] = useState('');
  let state;
  let selectedId;
  let invalid = '';
  try {
    state = validateWorkspaceLinks(data);
    selectedId = activeWorkspaceId(state, currentWorkspaceId);
  } catch (reason) {
    invalid = reason.message || 'اطلاعات Workspace معتبر نیست';
  }

  useEffect(() => {
    // Repair only the *local navigation selection*, never modify persisted
    // data and never silently rewrite a missing/archived workspace ID.
    if (!invalid && selectedId !== currentWorkspaceId && typeof onSelect === 'function')
      onSelect(selectedId);
  }, [invalid, selectedId, currentWorkspaceId, onSelect]);

  const mutate = (transition, {chooseId} = {}) => {
    try {
      if (!canManage) throw new Error('فقط مدیر می‌تواند فضاهای کاری را تغییر دهد');
      if (typeof onChange !== 'function') throw new Error('تابع ثبت تغییرات تعریف نشده است');
      // Preflight synchronously so stale references never navigate to ghosts.
      const preview = transition(data);
      onChange(previous => transition(previous));
      if (chooseId != null && typeof onSelect === 'function')
        onSelect(selectWorkspaceId(preview, chooseId));
      setError('');
      return true;
    } catch (reason) {
      setError(reason.message || 'تغییر Workspace انجام نشد');
      return false;
    }
  };

  const choose = id => {
    try {
      const selected = selectWorkspaceId(data, id);
      onSelect?.(selected);
      setError('');
    } catch (reason) {
      setError(reason.message || 'Workspace معتبر نیست');
    }
  };

  const create = event => {
    event.preventDefault();
    if (!canManage || !state) return;
    try {
      const id = generateWorkspaceId(state, idFactory);
      const name = newName;
      if (mutate(previous => createWorkspaceState(previous, id, name, {canManage}), {chooseId:id}))
        setNewName('');
    } catch (reason) {
      setError(reason.message);
    }
  };

  if (invalid) {
    return <section className="workspaces-panel" dir="rtl" aria-label="مدیریت فضاهای کاری">
      <p className="workspaces-error" role="alert">{invalid}</p>
    </section>;
  }

  const active = state.workspaces.filter(w => !w.archived);
  const archived = state.workspaces.filter(w => w.archived);
  const boards = state.boards.filter(board => board.workspaceId === selectedId);
  const selected = state.workspaces.find(w => w.id === selectedId);
  const countBoards = id => state.boards.filter(b => b.workspaceId === id).length;

  return <section className="workspaces-panel" dir="rtl" aria-label="مدیریت فضاهای کاری">
    <header className="workspaces-heading">
      <div><strong>فضاهای کاری</strong><small>مدیریت مستقل بردها بدون تغییر پروژه یا هزینه کارت‌ها</small></div>
      <span className="workspaces-count">{active.length.toLocaleString('fa-IR')} فعال</span>
    </header>
    {error && <p className="workspaces-error" role="alert">{error}</p>}
    <nav className="workspaces-list" aria-label="انتخاب فضای کاری">
      {active.map(workspace => <div className="workspaces-row" key={workspace.id}>
        <button type="button" className={selectedId === workspace.id ? 'workspaces-selected' : ''}
          aria-current={selectedId === workspace.id ? 'page' : undefined}
          onClick={() => choose(workspace.id)}>
          <FolderOpen size={15}/>
          <span>{workspace.name}</span>
          <small>{countBoards(workspace.id).toLocaleString('fa-IR')} برد</small>
        </button>
        {canManage && <div className="workspaces-actions">
          <button type="button" title={'تغییر نام ' + workspace.name}
            aria-label={'تغییر نام ' + workspace.name}
            onClick={() => {setRename({id:workspace.id, name:workspace.name});setError('');}}>
            <Pencil size={14}/>
          </button>
          <button type="button" title={'بایگانی ' + workspace.name}
            aria-label={'بایگانی ' + workspace.name}
            disabled={workspace.id === LEGACY_WORKSPACE_ID || active.length < 2}
            onClick={() => {
              mutate(previous => archiveWorkspaceState(previous, workspace.id, {canManage}), {
                chooseId: workspace.id === selectedId ? active.find(w => w.id !== workspace.id)?.id : selectedId,
              });
            }}>
            <Archive size={14}/>
          </button>
        </div>}
      </div>)}
    </nav>
    {canManage && rename && <form className="workspaces-inline" onSubmit={event => {
      event.preventDefault();
      const originalId = rename.id;
      if (mutate(previous => renameWorkspaceState(previous, originalId, rename.name, {canManage})))
        setRename(null);
    }}>
      <label>نام تازه فضای کاری
        <input aria-label="نام تازه فضای کاری" maxLength={180}
          value={rename.name} onChange={event => setRename({...rename,name:event.target.value})}/>
      </label>
      <button type="submit" aria-label="ثبت تغییر نام"><Check size={15}/> ثبت</button>
      <button type="button" aria-label="انصراف تغییر نام" onClick={() => setRename(null)}><X size={15}/></button>
    </form>}
    {canManage && <form className="workspaces-inline" onSubmit={create}>
      <label>ایجاد فضای کاری
        <input maxLength={180} aria-label="نام Workspace جدید" value={newName}
          placeholder="نام فضای کاری جدید" onChange={event => setNewName(event.target.value)}/>
      </label>
      <button type="submit" disabled={!newName.trim() || state.workspaces.length >= 100}>
        <Plus size={15}/> ساخت Workspace
      </button>
    </form>}
    {canManage && archived.length > 0 && <details className="workspaces-archive">
      <summary>فضاهای بایگانی‌شده ({archived.length.toLocaleString('fa-IR')})</summary>
      {archived.map(workspace => <div className="workspaces-row" key={workspace.id}>
        <span>{workspace.name} ({countBoards(workspace.id).toLocaleString('fa-IR')} برد)</span>
        <button type="button" onClick={() => mutate(
          previous => restoreWorkspaceState(previous, workspace.id, {canManage}),
          {chooseId:workspace.id})}
          aria-label={'بازیابی ' + workspace.name}><RefreshCcw size={14}/> بازیابی</button>
      </div>)}
    </details>}
    <div className="workspaces-boards">
      <strong><LayoutGrid size={16}/> بردهای «{selected?.name}»</strong>
      {!boards.length && <p>این فضای کاری هنوز بردی ندارد.</p>}
      {boards.map(board => <div className="workspaces-boardrow" key={board.id}>
        <span>{board.name}{board.archived ? ' (بایگانی‌شده)' : ''}</span>
        {canManage && <label>انتقال به
          <select aria-label={'فضای مقصد برد ' + board.name} value={board.workspaceId}
            onChange={event => {
              const destination = event.target.value;
              mutate(previous => moveBoardWorkspaceState(previous, board.id, destination, {canManage}));
            }}>
            {active.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
          </select>
        </label>}
      </div>)}
    </div>
    <p className="workspaces-help">بایگانی فضای کاری، کارت یا برد را حذف و بایگانی نمی‌کند. انتقال برد فقط محل نمایش آن را تغییر می‌دهد.</p>
  </section>;
}

export default WorkspaceManager;
