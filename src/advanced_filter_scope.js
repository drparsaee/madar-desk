/** Ephemeral active filters must never follow a different user/host/board.
 * Saved filter presets are stored separately by AdvancedFilters.
 */
export const EMPTY_ADVANCED_FILTER=Object.freeze({
  priority:'all',member:'all',label:'all',status:'all',due:'all',attachments:false,
});
export function readScopedAdvancedFilter(state,scope){
  return state?.scope===scope&&state?.value&&typeof state.value==='object'
    ?state.value:EMPTY_ADVANCED_FILTER;
}
export function updateScopedAdvancedFilter(state,scope,next){
  const previous=readScopedAdvancedFilter(state,scope);
  return {scope,value:typeof next==='function'?next(previous):next};
}
