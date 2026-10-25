/** Stable per-host namespace; namespaces separate UI records, not OS security boundaries. */
export function plannerIdentity(status) {
  const mode = status?.mode === 'client' ? 'client' : status?.mode === 'server' ? 'server' : 'solo';
  const username = typeof status?.user?.username === 'string' ? status.user.username : '';
  if (mode === 'client') {
    const url = typeof status?.url === 'string' ? status.url.trim() : '';
    if (!/^https?:\/\/[^\s]+$/i.test(url) || !username) return null;
    const fingerprint = typeof status?.fingerprint === 'string' ? status.fingerprint : '';
    return JSON.stringify([mode, url, fingerprint, username]);
  }
  return JSON.stringify([mode, username || 'local']);
}
