import React, {useEffect, useMemo, useState} from 'react';
import {Archive, ArrowUpDown, FolderOpen, RotateCcw, Search, Trash2, X} from 'lucide-react';
import {SearchPlus} from './searchplus.jsx';
import {sortTaskSearchResults} from './task_search_results.js';
import './task_search_results.css';

const FILTERS = [
  {id: 'all', label: 'همه'},
  {id: 'active', label: 'فعال'},
  {id: 'archived', label: 'بایگانی'},
  {id: 'trash', label: 'زباله‌دان'}
];
const STATUS = {active: 'فعال', archived: 'بایگانی', trash: 'زباله‌دان'};
const ARCHIVE_LOCATION = {
  board: 'برد بایگانی‌شده',
  list: 'فهرست بایگانی‌شده',
  workspace: 'فضای کاری بایگانی‌شده',
  card: 'کارت بایگانی‌شده'
};
const PAGE_SIZE = 60;

/**
 * Presentational, read-only panel for searchTaskLocations() result DTOs.
 *
 * On click: onOpenTask(id, result) opens active cards; onRestoreArchived(id,
 * result) restores individually archived cards; onRestoreTrashed(id, result)
 * restores trash cards; onGoToLocation(result) navigates to their parent.
 * All callbacks are optional and MUST enforce authorization in App/host.
 */
export function SearchResultsPanel({
  query = '', onQueryChange, results = [], onOpenTask, onRestoreArchived,
  onRestoreTrashed, onGoToLocation, onClose, canEdit = false,
  formatDate = value => new Date(value).toLocaleDateString('fa-IR')
}) {
  const [statusFilter, setStatusFilter] = useState('all');
  const [sortBy, setSortBy] = useState('date');
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  useEffect(() => { setVisibleCount(PAGE_SIZE); }, [query, statusFilter, sortBy]);
  const sorted = useMemo(() => sortTaskSearchResults(results, sortBy), [results, sortBy]);
  const filtered = useMemo(() =>
    sorted.filter(result => statusFilter === 'all' || result.status === statusFilter),
    [sorted, statusFilter]);
  const counts = useMemo(() => ({
    all: results.length,
    active: results.filter(item => item.status === 'active').length,
    archived: results.filter(item => item.status === 'archived').length,
    trash: results.filter(item => item.status === 'trash').length
  }), [results]);
  return <section dir="rtl" className="tsr-panel" aria-label="نتایج جست‌وجوی همه کارت‌ها">
    <header className="tsr-header">
      <div><h2><Search size={19} aria-hidden="true"/> جست‌وجوی همه کارت‌ها</h2>
        <p>کارت‌های فعال، بایگانی‌شده و زباله‌دان در پروژه‌های مجاز</p></div>
      {onClose && <button type="button" className="tsr-icon-button" aria-label="بستن نتایج جست‌وجو" onClick={onClose}><X size={18}/></button>}
    </header>
    {onQueryChange && <SearchPlus query={query} onQueryChange={onQueryChange} resultCount={results.length}
      placeholder="جست‌وجو در همه کارت‌ها..."/>}
    <div className="tsr-toolbar">
      <div role="group" className="tsr-filters" aria-label="وضعیت کارت">
        {FILTERS.map(item => <button key={item.id} type="button"
          aria-pressed={statusFilter === item.id}
          onClick={() => setStatusFilter(item.id)}>
          {item.label} <span>{counts[item.id].toLocaleString('fa-IR')}</span>
        </button>)}
      </div>
      <label className="tsr-sort"><ArrowUpDown size={15} aria-hidden="true"/> مرتب‌سازی
        <select value={sortBy} onChange={event => setSortBy(event.target.value)} aria-label="مرتب‌سازی نتایج">
          <option value="date">آخرین تغییر</option>
          <option value="cardOrder">ترتیب کارت‌ها در فهرست</option>
        </select>
      </label>
    </div>
    <div className="tsr-results" role="list" aria-live="polite">
      {!query.trim() ? <p className="tsr-empty">عبارتی برای جست‌وجو وارد کنید.</p>
        : filtered.length === 0 ? <p className="tsr-empty">کارتی با این عبارت و وضعیت پیدا نشد.</p>
        : filtered.slice(0, visibleCount).map(result =>
          <article key={result.id} role="listitem" className="tsr-result">
            <div className="tsr-result-main">
              <strong dir="auto">{result.title || 'کارت بدون عنوان'}</strong>
              <span className={'tsr-status tsr-status--' + result.status}>
                {result.status === 'trash' ? <Trash2 size={13}/> : result.status === 'archived' ? <Archive size={13}/> : null}
                {STATUS[result.status] || result.status}
              </span>
            </div>
            <div className="tsr-location">
              <FolderOpen size={14} aria-hidden="true"/>
              <span>{[result.projectName, result.workspaceName, result.boardName, result.listName]
                .filter(Boolean).join(' / ') || 'موقعیت نامشخص'}</span>
              {result.archiveScope && <em>{ARCHIVE_LOCATION[result.archiveScope]}</em>}
            </div>
            {result.labels?.length > 0 && <div className="tsr-labels" aria-label="برچسب‌های کارت">
              {result.labels.map((label, index) =>
                <span key={index} style={label.color ? {borderColor: label.color} : undefined}>{label.name}</span>)}
            </div>}
            <div className="tsr-result-footer">
              <time dateTime={result.date || undefined}>{result.date ? formatDate(result.date) : 'بدون تاریخ'}</time>
              <div className="tsr-actions">
                {result.status === 'active' && onOpenTask &&
                  <button type="button" onClick={() => onOpenTask(result.id, result)}>باز کردن کارت</button>}
                {result.status === 'archived' && result.archiveScope === 'card' &&
                  canEdit && onRestoreArchived &&
                  <button type="button" onClick={() => onRestoreArchived(result.id, result)}><RotateCcw size={14}/> بازیابی کارت</button>}
                {result.status === 'trash' && !['board', 'workspace'].includes(result.archiveScope) &&
                  canEdit && onRestoreTrashed &&
                  <button type="button" onClick={() => onRestoreTrashed(result.id, result)}><RotateCcw size={14}/> بازیابی کارت</button>}
                {result.boardId && onGoToLocation &&
                  <button type="button" onClick={() => onGoToLocation(result)} className="tsr-secondary">نمایش محل</button>}
              </div>
            </div>
          </article>)}
    </div>
    {visibleCount < filtered.length &&
      <button type="button" className="tsr-load-more"
        onClick={() => setVisibleCount(count => count + PAGE_SIZE)}>
        نمایش بیشتر ({(filtered.length - visibleCount).toLocaleString('fa-IR')} نتیجه باقی‌مانده)
      </button>}
  </section>;
}

export default SearchResultsPanel;
