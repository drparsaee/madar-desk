import React, {useEffect, useState} from 'react';
import {
  DEFAULT_INTERFACE_MODE, INTERFACE_MODE_OPTIONS, interfaceModeStorageKey,
  isValidInterfaceMode, normalizeInterfaceMode, readInterfaceMode,
  writeInterfaceMode,
} from './interface_mode.js';
import './interface_mode.css';

function browserStorage() {
  try { return typeof window === 'undefined' ? null : window.localStorage; }
  catch { return null; }
}

/**
 * Account-switch-safe optional adapter for App.jsx. A newly observed identity
 * renders Basic until its own preference is read; it never inherits another
 * account's selected mode, even for the render preceding useEffect.
 */
export function useInterfaceModePreference(status, storage) {
  const activeStorage = storage === undefined ? browserStorage() : storage;
  const accountKey = interfaceModeStorageKey(status);
  const [choice, setChoice] = useState({accountKey:null, mode:DEFAULT_INTERFACE_MODE, persisted:true});

  useEffect(() => {
    setChoice({accountKey, mode:readInterfaceMode(activeStorage, status), persisted:true});
  }, [accountKey, activeStorage]);

  const current = choice.accountKey === accountKey ? choice :
    {accountKey, mode:DEFAULT_INTERFACE_MODE, persisted:true};

  const setMode = next => {
    if (!accountKey || !isValidInterfaceMode(next)) return false;
    const persisted = writeInterfaceMode(activeStorage, status, next);
    setChoice({accountKey, mode:next, persisted});
    return persisted;
  };

  return {mode:current.mode, setMode, persisted:current.persisted, accountReady:!!accountKey};
}

/** Fully controlled, keyboard-operable selector. Parent owns preference state. */
export function InterfaceModeSelector({mode=DEFAULT_INTERFACE_MODE, onChange, disabled=false, id='madar-interface-mode', compact=false}) {
  const selected = normalizeInterfaceMode(mode);
  const descriptionId = id + '-description';
  const selectedOption = INTERFACE_MODE_OPTIONS.find(option=>option.id===selected);
  return <div className={'interface-mode-selector'+(compact?' interface-mode-selector--compact':'')} dir="rtl">
    <label className="interface-mode-selector__label" htmlFor={id}>ابزارهای قابل نمایش</label>
    <select
      className="interface-mode-selector__select"
      id={id}
      value={selected}
      disabled={disabled}
      aria-describedby={descriptionId}
      onChange={event=>{
        const next = event.target.value;
        if (!disabled && isValidInterfaceMode(next) && next !== selected) onChange?.(next);
      }}
    >
      {INTERFACE_MODE_OPTIONS.map(option=><option key={option.id} value={option.id}>{option.label}</option>)}
    </select>
    <p className="interface-mode-selector__description" id={descriptionId}>{selectedOption.description}</p>
    <details className="interface-mode-selector__help">
      <summary>تفاوت این سه حالت چیست؟</summary>
      <p>این گزینه‌ها فقط شلوغی رابط را کم و زیاد می‌کنند؛ سطح دسترسی و مجوزهای کاربر تغییر نمی‌کند.</p>
      <ul>{INTERFACE_MODE_OPTIONS.map(option=><li key={option.id}><strong>{option.label}:</strong> {option.description}</li>)}</ul>
      <p>داشبورد سیستم حسابداری از مسیر «مدیریت مالی» و فقط با مجوز مربوط باز می‌شود.</p>
    </details>
  </div>;
}
