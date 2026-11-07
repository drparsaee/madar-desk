import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import './styles.css';
import {installButtonHints} from './button_hints.js';
import './mobile_navigation.css';
import './unslop_general.css';
import './checkbox_motion.css';
import './mobile_board_density.css';
createRoot(document.getElementById('root')).render(<App />);
installButtonHints(document);
// Manifest/service worker only in the explicitly requested web build. The
// Windows installer and its pywebview host remain independent.
if(import.meta.env.MODE==='web'){
  const manifest=document.createElement('link');
  manifest.rel='manifest';
  manifest.href=import.meta.env.BASE_URL+'manifest.webmanifest';
  document.head.append(manifest);
  if(import.meta.env.PROD&&'serviceWorker' in navigator&&
      (location.protocol==='https:'||['127.0.0.1','localhost'].includes(location.hostname))){
    window.addEventListener('load',()=>{
      navigator.serviceWorker.register(import.meta.env.BASE_URL+'service-worker.js',
        {scope:import.meta.env.BASE_URL}).catch(error=>
        console.warn('Madar web offline shell not available:',error));
    });
  }
}
