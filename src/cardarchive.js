/** Reversible archive of an individual card, distinct from board archive and trash.
 * Uses the same strict project-scope and board/workspace validation as card trash.
 * Host authentication and LAN ACL remain authoritative.
 */
import {selectedCard} from './cardtrash.js';

function toggle(state, cardId, options, archived) {
  const task=selectedCard(state,cardId,options);
  if(task.deleted===true)throw new Error('Cannot archive a deleted/trash card');
  if(task.archivedByBoard===true)throw new Error('Restore the board before changing board-owned archive');
  if((task.archived===true)===archived)return state;
  return {...state,tasks:state.tasks.map(item=>item===task?{...item,archived}:item)};
}

export const archiveCardState=(state,cardId,options={})=>toggle(state,cardId,options,true);
export const restoreArchivedCardState=(state,cardId,options={})=>toggle(state,cardId,options,false);
