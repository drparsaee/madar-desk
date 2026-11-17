/** Transient, non-authoritative feedback for all Madar views.
 *
 * The durable inbox remains in its existing host-backed dialogs. This module
 * never synthesizes a collaboration notification, financial receipt, backend
 * acknowledgement, or successful operation.
 */
import React, {useEffect, useRef} from 'react';
import {sileo, Toaster} from 'sileo';
import './mtr_sileo_feedback.css';

const TYPES = new Set(['success', 'error', 'warning', 'info']);
const FAILURE = /(?:خطا|ناموفق|موفق نبود|انجام نشد|نامعتبر|معتبر نیست|امکان‌پذیر نیست|باز نشد|ثبت نشد|failure|failed|error|rejected|denied)/i;
const CAUTION = /(?:تعارض|آفلاین|در صف|در انتظار|نامشخص|هنوز|تأیید نشده|ابتدا|مجاز نیست|خاموش|مسدود|غیرفعال|دسترسی لازم|نیاز است|فقط در)/i;

/** No raw credentials, local filesystem paths, URLs or backend error details. */
export function safeFeedbackText(raw) {
  if(typeof raw !== 'string') return '';
  let text = raw
    .replace(/[\u0000-\u001f\u007f\u202a-\u202e\u2066-\u2069]/g, ' ')
    .replace(/\b(?:Bearer\s+\S+|sk-[A-Za-z0-9_-]+|gh[pousr]_[A-Za-z0-9_]+)\b/gi, '[اطلاعات محرمانه]')
    .replace(/\b(?:password|token|secret|api[_-]?key|authorization)\s*[:=]\s*\S+/gi, '[اطلاعات محرمانه]')
    .replace(/(?:https?:\/\/|wss?:\/\/)\S+/gi, '[پیوند محفوظ]')
    .replace(/(?:[A-Za-z]:\\|\\\\)[^\s،؛]+/g, '[مسیر محفوظ]')
    .replace(/\s+/g, ' ').trim();
  // Error details from native/web bridges may include credentials or project
  // data. The persistent inline error keeps the existing recovery affordance.
  if(FAILURE.test(text) && /[:：]/.test(text)) {
    text = text.split(/[:：]/, 1)[0].trim() + '؛ جزئیات در پیام خطای برنامه باقی مانده است.';
  }
  return text.slice(0, 170);
}

function safeFailureSummary(raw) {
  // Never echo the unknown portion of a native/peer/backend error into a
  // transient popup. The existing persistent inline error remains available.
  if(/ذخیره|کارت/.test(raw))
    return 'ذخیره انجام نشد؛ جزئیات و بازیابی را در پیام برنامه بررسی کنید.';
  if(/تراز|حسابداری|مالی/.test(raw))
    return 'عملیات تبادل تراز انجام نشد؛ وضعیت را در برنامه مربوط بررسی کنید.';
  if(/به‌روز|نسخه|دانلود|نصب/.test(raw))
    return 'به‌روزرسانی انجام نشد؛ وضعیت نسخه را بررسی کنید.';
  if(/اتصال|شبکه|همگام|سرور/.test(raw))
    return 'ارتباط یا همگام‌سازی انجام نشد؛ وضعیت اتصال را بررسی کنید.';
  if(/تقویم|ورود|فایل|پشتیبان/.test(raw))
    return 'عملیات فایل انجام نشد؛ جزئیات را در همان بخش بررسی کنید.';
  return 'عملیات انجام نشد؛ جزئیات را در پیام برنامه بررسی کنید.';
}

export function normalizeMadarFeedback(input) {
  const payload = typeof input === 'string' ? {title: input} : input;
  if(!payload || typeof payload !== 'object') return null;
  if(typeof payload.title !== 'string')return null;
  const failed = FAILURE.test(payload.title) || payload.type === 'error';
  const title = failed ? safeFailureSummary(payload.title) : safeFeedbackText(payload.title);
  if(!title) return null;
  // Never classify an arbitrary optimistic UI message as completed persistence.
  const type = failed ? 'error'
    : TYPES.has(payload.type) ? payload.type
      : CAUTION.test(title) ? 'warning' : 'info';
  return {type, title};
}

export function emitMadarFeedback(input, sender = sileo) {
  const value = normalizeMadarFeedback(input);
  if(!value) return null;
  return sender[value.type]({title: value.title, duration: value.type === 'error' ? 6500 : 4500,
    position: 'top-center'});
}

/** Legacy App.jsx messages retain one-shot semantics; clearing is not a toast. */
export function MadarFeedbackRelay({message, errorMessage = ''}) {
  const seen = useRef({message: '', error: ''});
  useEffect(() => {
    if(message && message !== seen.current.message) emitMadarFeedback(message);
    seen.current.message = message || '';
  }, [message]);
  useEffect(() => {
    if(errorMessage && errorMessage !== seen.current.error)
      emitMadarFeedback({type: 'error', title: errorMessage});
    seen.current.error = errorMessage || '';
  }, [errorMessage]);
  // Other sections may import emitMadarFeedback directly after their own
  // acknowledged actions. No generic DOM event can forge a "success" toast.
  return null;
}

export function MadarSileoFeedback({message = '', errorMessage = '', theme = 'system'}) {
  return <>
    <Toaster position="top-center" theme={theme} options={{duration: 4500}}/>
    <MadarFeedbackRelay message={message} errorMessage={errorMessage}/>
  </>;
}
