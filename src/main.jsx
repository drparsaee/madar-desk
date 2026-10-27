import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import './styles.css';
import {installFloatingLabels} from './floating_labels.js';
import './floating_labels.css';
createRoot(document.getElementById('root')).render(<App />);
installFloatingLabels(document);
