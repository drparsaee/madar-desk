import React, {useEffect, useState} from 'react';
import './clock_widget.css';

/**
 * Display the device's local time and calendar as stable, fixed-position
 * flip-style hour/minute tiles. No appearance or placement preferences affect
 * the display. We keep dates separate from task/financial event timestamps.
 */
export function formatClockParts(date, calendar = 'jalali') {
  const locale = calendar === 'gregorian' ? 'fa-IR-u-ca-gregory' : 'fa-IR-u-ca-persian';
  const dateParts = Object.fromEntries(new Intl.DateTimeFormat(locale, {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
  }).formatToParts(date).filter(part => part.type !== 'literal')
    .map(part => [part.type, part.value]));
  // Fliqlo's flip numerals use conventional, easy-to-read Latin digits. The
  // date remains Persian, including its native numerals and weekday spelling.
  const timeParts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(date).filter(part => part.type !== 'literal')
    .map(part => [part.type, part.value]));

  return {
    hour: timeParts.hour,
    minute: timeParts.minute,
    date: `${dateParts.weekday}، ${dateParts.day} ${dateParts.month} ${dateParts.year}`,
  };
}

/** Compatibility only: historic settings panes no longer render clock controls. */
export function WidgetSettings() { return null; }

export function ClockWidget({calendar = 'jalali'}) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    let timeout;
    const tick = () => {
      clearTimeout(timeout);
      setNow(new Date());
      // Align with the next minute. Nothing needs a 1-second interval now.
      timeout = setTimeout(tick, 60_000 - Date.now() % 60_000 + 30);
    };
    tick();
    document.addEventListener('visibilitychange', tick);
    return () => {
      clearTimeout(timeout);
      document.removeEventListener('visibilitychange', tick);
    };
  }, []);

  const {hour, minute, date} = formatClockParts(now, calendar);
  return <div className="clock-widget clock-widget--fixed" dir="rtl">
    <div className="live-clock clock-widget__display" role="timer" aria-live="off"
      aria-label={`ساعت ${hour} و ${minute} دقیقه؛ ${date}`}>
      <div className="clock-widget__tiles" dir="ltr" aria-hidden="true">
        <span className="clock-widget__flip-page" data-unit="hour">{hour}</span>
        <span className="clock-widget__separator">:</span>
        <span className="clock-widget__flip-page" data-unit="minute">{minute}</span>
      </div>
      <span className="clock-widget__date"><bdi>{date}</bdi></span>
    </div>
  </div>;
}
