/**
 * Desktop startup only: discover and cache a verified stable GitHub update.
 * Installation remains a distinct, explicit user action. The native bridge
 * independently rediscovers the release and validates size, SHA-256 and URL.
 */
export async function checkAndCacheAvailableUpdate(api,{onFound=()=>{}}={}) {
  if(!api||typeof api.releaseCheck!=='function'||typeof api.releaseDownload!=='function')
    throw new TypeError('Desktop update bridge is missing');
  const metadata=await api.releaseCheck();
  const info=metadata?.available===true?metadata:null;
  onFound(info);
  if(!info)return {info:null,downloaded:false};
  const result=await api.releaseDownload();
  if(result?.verified!==true)throw new Error('Update was not verified by the desktop host');
  return {info,downloaded:true};
}
