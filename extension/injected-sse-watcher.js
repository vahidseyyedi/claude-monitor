// این فایل با world:"MAIN" تزریق میشه، یعنی داخل خودِ context صفحه‌ی claude.ai
// اجرا میشه (نه isolated world اکستنشن‌ها). این لازمه چون باید window.fetch
// همون چیزی رو پچ کنیم که خودِ صفحه استفاده می‌کنه.
//
// وقتی پیام می‌فرستی، claude.ai یک درخواست POST به:
//   /api/organizations/{org}/chat_conversations/{convo}/completion
// می‌زنه که جوابش یک استریم SSE هست. یکی از رکوردهای این استریم به اسم
// "message_limit" دقیقاً همون درصد مصرف سشن (۵ ساعته) و هفتگی رو داره —
// این تنها جایی هست که برای اکانت رایگان این عدد اصلاً منتشر میشه.

(function () {
  const LOG = '[ClaudeMonitor:SSE]';
  const DEBUG = true; // بذار false تا لاگ‌ها خاموش شن
  const log = (...a) => { if (DEBUG) console.log(LOG, ...a); };
  const warn = (...a) => console.warn(LOG, ...a);

  const COMPLETION_RE = /\/api\/organizations\/([^/]+)\/chat_conversations\/([^/]+)\/(retry_)?completion/;
  const prevFetch = window.fetch;

  log('نصب شد، منتظر fetch به completion API...');

  function parseWindow(win, label) {
    if (!win) {
      log(`پنجره‌ی ${label} در پاسخ نیست`);
      return null;
    }
    if (typeof win.utilization !== 'number') {
      warn(`پنجره‌ی ${label}: فیلد utilization عددی نیست، شکل واقعی شیء:`, win);
      return null;
    }
    const exceeded = win.status === 'exceeded_limit';
    let resetsAt = null;
    if (win.resets_at != null) {
      // resets_at ممکنه ثانیه (unix) یا میلی‌ثانیه یا رشته‌ی ISO باشه؛
      // هر سه حالت رو امتحان می‌کنیم و اگه هیچکدوم معتبر نبود، هشدار می‌دیم
      const raw = win.resets_at;
      if (typeof raw === 'number') {
        // اگه عدد به اندازه‌ی کافی بزرگه، احتمالاً از قبل میلی‌ثانیه‌ست
        resetsAt = raw > 1e12 ? raw : raw * 1000;
      } else {
        const parsed = Date.parse(raw);
        resetsAt = Number.isNaN(parsed) ? null : parsed;
      }
      if (resetsAt !== null && Number.isNaN(new Date(resetsAt).getTime())) {
        warn(`پنجره‌ی ${label}: resets_at قابل تبدیل به تاریخ معتبر نیست:`, raw);
        resetsAt = null;
      }
    } else {
      log(`پنجره‌ی ${label}: resets_at در پاسخ نبود`);
    }
    const result = {
      percentage: exceeded ? 100 : Math.round(win.utilization * 100),
      resetsAt
    };
    log(`پنجره‌ی ${label} پارس شد:`, result, 'خام:', win);
    return result;
  }

  function emit(messageLimit) {
    if (!messageLimit) {
      log('message_limit خالی/نال بود، ردش می‌کنیم');
      return;
    }
    if (!messageLimit.windows) {
      warn('message_limit.windows وجود نداره، شکل کامل message_limit:', messageLimit);
      return;
    }
    log('کلیدهای windows موجود:', Object.keys(messageLimit.windows));
    const session = parseWindow(messageLimit.windows['5h'], '5h/session');
    const weekly = parseWindow(messageLimit.windows['7d'], '7d/weekly');
    log('در حال postMessage به content script:', { session, weekly });
    window.postMessage({ source: 'claude-monitor-sse', session, weekly }, '*');
  }

  async function pump(response) {
    log('شروع خوندن استریم SSE از', response.url);
    let recordCount = 0;
    let messageLimitCount = 0;
    try {
      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const records = buffer.split('\n\n');
        buffer = records.pop(); // آخری ممکنه ناقص باشه، نگهش می‌داریم
        for (const record of records) {
          recordCount++;
          if (!record.includes('"message_limit"')) continue;
          messageLimitCount++;
          const dataLine = record.split('\n').find((l) => l.startsWith('data:'));
          if (!dataLine) {
            warn('رکورد شامل message_limit بود ولی خط data: پیدا نشد. رکورد خام:', record);
            continue;
          }
          try {
            const json = JSON.parse(dataLine.slice(5).trim());
            if (json.message_limit) {
              emit(json.message_limit);
            } else {
              warn('data JSON پارس شد ولی فیلد message_limit نداشت:', json);
            }
          } catch (e) {
            warn('پارس JSON این رکورد fail شد:', e.message, 'خط خام:', dataLine.slice(0, 300));
          }
        }
      }
    } catch (e) {
      warn('استریم با خطا قطع شد:', e.message);
    }
    log(`استریم تموم شد. مجموع رکوردها: ${recordCount}, رکوردهای دارای message_limit: ${messageLimitCount}`);
    if (messageLimitCount === 0) {
      warn('هیچ رکورد message_limit توی این استریم نبود — یعنی یا فرمت پاسخ Claude عوض شده، یا این endpoint دیگه این داده رو نمی‌فرسته.');
    }
  }

  window.fetch = async function (...args) {
    const response = await prevFetch.apply(this, args);
    try {
      const input = args[0];
      let url = input instanceof Request ? input.url : String(input ?? '');
      if (url.startsWith('/')) url = location.origin + url;
      const bareUrl = url.split('?')[0];
      if (!COMPLETION_RE.test(bareUrl)) return response;

      log('درخواست completion رصد شد:', bareUrl, 'content-type:', response.headers.get('content-type'));

      if (!response.body) {
        warn('پاسخ body نداره، نمی‌تونیم استریم رو بخونیم');
        return response;
      }
      if (!response.headers.get('content-type')?.includes('event-stream')) {
        warn('content-type پاسخ event-stream نیست، شاید ساختار API عوض شده:', response.headers.get('content-type'));
        return response;
      }
      pump(response.clone());
    } catch (e) {
      warn('خطا توی هوک فچ:', e.message, e.stack);
    }
    return response;
  };
})();
