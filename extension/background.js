const LOG = '[ClaudeMonitor:background]';
const log = (...a) => console.log(LOG, ...a);
const warn = (...a) => console.warn(LOG, ...a);

const SERVER_URL = 'http://localhost:8765/report';

log('background service worker روشن شد');

chrome.runtime.onMessage.addListener((message) => {
  if (message.type !== 'CLAUDE_STATUS') return;
  log('پیام CLAUDE_STATUS رسید، در حال ارسال به سرور لوکال...');
  fetch(SERVER_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(message.payload)
  })
    .then((res) => {
      if (!res.ok) {
        warn(`سرور لوکال با status ${res.status} جواب داد`);
      } else {
        log('با موفقیت به سرور لوکال ارسال شد (پورت 8765)');
      }
    })
    .catch((e) => {
      warn('اتصال به سرور لوکال fail شد — سرور روشنه؟ (python3 server.py را اجرا کردی؟). خطا:', e.message);
    });
});
