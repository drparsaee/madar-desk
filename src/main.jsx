import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import './styles.css';
import {installButtonHints} from './button_hints.js';
import './mobile_navigation.css';
import './unslop_general.css';
createRoot(document.getElementById('root')).render(<App />);
installButtonHints(document);
