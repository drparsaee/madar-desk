/** Client-side appearance preference. Never modifies shared task/finance state. */
export function themeScope(lanStatus) {
  const mode=lanStatus?.mode==='client'?'client':lanStatus?.mode==='server'?'server':'solo';
  const name=lanStatus?.user?.username;
  return 'madar-ui-theme:'+mode+':'+(typeof name==='string'&&name.trim()?name:'local');
}

export function readTheme(storage,scope,fallback='dark') {
  try {
    const value=storage.getItem(scope);
    if(value==='light'||value==='dark')return value;
  } catch { /* Local storage may be denied in hardened WebView2. */ }
  return fallback==='light'?'light':'dark';
}

export function writeTheme(storage,scope,theme) {
  if(theme!=='light'&&theme!=='dark')throw new TypeError('Invalid theme preference');
  try {
    storage.setItem(scope,theme);
    // Independent finance WebView uses the current locally selected theme.
    storage.setItem('madar-ui-theme',theme);
  } catch { /* Memory-only choice remains valid when local storage is blocked. */ }
  return theme;
}
