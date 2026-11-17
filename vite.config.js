import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import {resolve} from 'node:path';

export default defineConfig(({mode})=>{
  let webApiProxy;
  // Opt-in local development only. Production must reverse-proxy the API from
  // the PWA's HTTPS origin; never embed a server URL into the browser bundle.
  if(mode==='web'&&process.env.MADAR_WEB_API_PROXY){
    const target=new URL(process.env.MADAR_WEB_API_PROXY);
    if(target.protocol!=='http:'||!['127.0.0.1','localhost','[::1]'].includes(target.hostname)||
       !target.port||target.pathname!=='/'||target.search||target.hash||
       target.username||target.password)
      throw Error('MADAR_WEB_API_PROXY must be an uncredentialed HTTP loopback origin with a port.');
    webApiProxy={'/api/web/v1':{target:target.origin,changeOrigin:false}};
  }
  return {
  plugins: [react()],
  base: './',
  build: {rollupOptions: {input: mode==='web'
    ? {main: resolve(process.cwd(), 'index.html')}
    : {main: resolve(process.cwd(), 'index.html'), accounting: resolve(process.cwd(), 'accounting.html')}}},
  server: {
    host: '127.0.0.1', port: 5173, strictPort: true,
    ...(webApiProxy?{proxy:webApiProxy}:{}),
    // Binary installer outputs are immutable build artifacts, never live UI
    // sources. Watching them can hit Windows EBUSY during Inno compilation.
    watch: {ignored: ['**/release/**', '**/.qa-inno-*/**', '**/.qa-p0-pyinstaller/**']},
  }
  };
});
