// این اسکریپت داخل هر تب claude.ai اجرا میشه.
// به‌جای خوندن متن صفحه، مستقیم از API داخلی خود claude.ai استفاده می‌کنیم
// (همون API ای که خود سایت برای صفحه usage و چت‌ها استفاده می‌کنه).
// چون این fetch از داخل خود صفحه‌ی claude.ai اجرا میشه، کوکی‌های session
// خودکار همراهش میره و نیازی به توکن جدا نیست.

const LOG = '[ClaudeMonitor:content]';
const DEBUG = true; // بذار false تا لاگ‌ها خاموش شن
const log = (...a) => { if (DEBUG) console.log(LOG, ...a); };
const warn = (...a) => console.warn(LOG, ...a);

log('content script بارگذاری شد روی', location.href);

// آخرین عدد مصرفی که از استریم پیام (injected-sse-watcher.js) رسیده
let lastSseUsage = { session: null, weekly: null, receivedAt: null };
window.addEventListener('message', (event) => {
  if (event.source !== window) return;
  if (!event.data || event.data.source !== 'claude-monitor-sse') return;
  lastSseUsage = {
    session: event.data.session,
    weekly: event.data.weekly,
    receivedAt: new Date().toISOString()
  };
  log('از injected-sse-watcher پیام رسید و ذخیره شد:', lastSseUsage);
});

let cachedOrgId = null;

async function getOrgId() {
  if (cachedOrgId) return cachedOrgId;
  const res = await fetch('/api/organizations', { credentials: 'include' });
  if (!res.ok) {
    warn('گرفتن organizations fail شد، status:', res.status);
    return null;
  }
  const orgs = await res.json();
  if (Array.isArray(orgs) && orgs.length > 0) {
    cachedOrgId = orgs[0].uuid;
    log('orgId پیدا شد:', cachedOrgId);
  } else {
    warn('آرایه‌ی organizations خالیه یا فرمتش عوض شده:', orgs);
  }
  return cachedOrgId;
}

function getConversationIdFromUrl() {
  const m = location.pathname.match(/\/chat\/([a-f0-9-]{36})/i);
  return m ? m[1] : null;
}

async function fetchUsage(orgId) {
  // خروجی کامل (status + json خام) رو برمی‌گردونیم تا اگه ساختار جواب فرق داشت
  // بتونیم خودِ جواب خام رو تو داشبورد ببینیم و بفهمیم اسم فیلدها چیه.
  try {
    const res = await fetch(`/api/organizations/${orgId}/usage`, { credentials: 'include' });
    const text = await res.text();
    let json = null;
    try { json = JSON.parse(text); } catch (e) { /* ignore */ }
    log('پاسخ /usage — status:', res.status, 'json:', json, json ? '' : `raw: ${text.slice(0, 200)}`);
    return { ok: res.ok, status: res.status, json, raw: json ? null : text.slice(0, 500) };
  } catch (e) {
    warn('fetchUsage خطا داد:', e.message);
    return { ok: false, status: 0, json: null, raw: String(e) };
  }
}

async function fetchFullConversation(orgId, conversationId) {
  const url = `/api/organizations/${orgId}/chat_conversations/${conversationId}?tree=True&rendering_mode=messages&render_all_tools=true`;
  const res = await fetch(url, { credentials: 'include' });
  if (!res.ok) return null;
  return res.json();
}

// تخمین ساده‌ی تعداد توکن از روی طول متن (~۴ کاراکتر انگلیسی یا ~۲ حرف فارسی به ازای هر توکن).
// این دقیقاً همون عددی که Anthropic حساب می‌کنه نیست، ولی برای مقایسه‌ی نسبی بین چت‌ها کافیه.
function estimateTokens(text) {
  if (!text) return 0;
  const persianChars = (text.match(/[\u0600-\u06FF]/g) || []).length;
  const otherChars = text.length - persianChars;
  return Math.ceil(persianChars / 2 + otherChars / 4);
}

// از پیام‌های خام API، یک لیست ساده {role, text, createdAt, tokens, files} می‌سازه
function extractFiles(m) {
  const out = [];
  const collections = [m.attachments, m.files_v2, m.files].filter(Array.isArray);
  for (const list of collections) {
    for (const f of list) {
      if (!f) continue;
      const fileUuid = f.file_uuid || f.id || null;
      const fileName = f.file_name || f.name || 'فایل بدون‌نام';
      // مسیر دانلود استاندارد Claude برای فایل‌های ضمیمه/تولیدشده
      const downloadUrl = fileUuid ? `https://claude.ai/api/${fileUuid}/download` : (f.download_url || f.url || null);
      out.push({ fileUuid, fileName, downloadUrl });
    }
  }
  return out;
}

function extractMessages(conversationJson) {
  if (!conversationJson || !Array.isArray(conversationJson.chat_messages)) return [];
  return conversationJson.chat_messages.map((m) => {
    let text = '';
    if (Array.isArray(m.content)) {
      text = m.content
        .filter((c) => c.type === 'text' && typeof c.text === 'string')
        .map((c) => c.text)
        .join('\n');
    } else if (typeof m.text === 'string') {
      text = m.text;
    }
    return {
      uuid: m.uuid || null,
      role: m.sender, // 'human' یا 'assistant'
      text,
      createdAt: m.created_at || null,
      tokens: estimateTokens(text),
      files: extractFiles(m)
    };
  });
}

// برای اکانت رایگان، endpoint مصرف همیشه null برمی‌گردونه (چون صفحه‌ی Usage
// اصلاً برای پلن رایگان وجود نداره). تنها سیگنال واقعی، همون بنر هشدار
// روی صفحه‌ست که فرمتش معمولا این شکلیه:
// "Claude usage limit reached. Your limit will reset at 1pm (Etc/GMT+5)."
function scanFreeLimitBanner() {
  const text = document.body.innerText || '';
  const m = text.match(/usage limit reached[^.]*\.?\s*(?:Your limit will reset at|resets at|available again at)?\s*([^.\n]{0,60})/i);
  if (m) {
    return { limitReached: true, resetText: m[1].trim() };
  }
  return { limitReached: false, resetText: null };
}
function pick(obj, keys) {
  for (const k of keys) {
    if (obj && obj[k] !== undefined) return obj[k];
  }
  return undefined;
}

function usageSummary(usageJson) {
  if (!usageJson) return null;
  const five = pick(usageJson, ['five_hour', 'session', 'five_hour_limit']);
  const seven = pick(usageJson, ['seven_day', 'weekly', 'seven_day_limit']);
  const out = {};
  if (five) {
    out.sessionUtilization = pick(five, ['utilization', 'usage_percentage', 'percent_used']);
    out.sessionResetsAt = pick(five, ['resets_at', 'reset_at', 'resetsAt']);
  }
  if (seven) {
    out.weeklyUtilization = pick(seven, ['utilization', 'usage_percentage', 'percent_used']);
    out.weeklyResetsAt = pick(seven, ['resets_at', 'reset_at', 'resetsAt']);
  }
  return out;
}

async function report() {
  log('--- شروع چرخه‌ی report ---');
  chrome.storage.local.get(['accountLabel'], async (res) => {
    if (chrome.runtime.lastError) {
      warn('chrome.storage.local.get خطا داد (احتمالاً extension context invalidated شده، صفحه رو رفرش کن):', chrome.runtime.lastError.message);
      return;
    }
    const accountLabel = res.accountLabel || 'بدون‌نام';
    log('accountLabel:', accountLabel);

    const orgId = await getOrgId().catch((e) => { warn('getOrgId throw کرد:', e.message); return null; });
    if (!orgId) {
      warn('orgId پیدا نشد، report متوقف شد');
      return;
    }

    const usageResult = await fetchUsage(orgId).catch((e) => ({ ok: false, status: 0, json: null, raw: String(e) }));
    let usage = usageSummary(usageResult.json);
    log('usage از REST API (/usage):', usage);

    // اگه از استریم پیام (real-time، دقیق‌ترین منبع، مخصوصا برای اکانت رایگان)
    // چیزی داریم، همون رو اولویت بده؛ فقط اگه هیچی نداشتیم فال‌بک به API/DOM
    const isApiUsageEmpty = !usage || (usage.sessionUtilization == null && usage.weeklyUtilization == null);
    log('isApiUsageEmpty:', isApiUsageEmpty, '| lastSseUsage:', lastSseUsage);
    if (lastSseUsage.session || lastSseUsage.weekly) {
      usage = {
        ...usage,
        sessionUtilization: lastSseUsage.session ? lastSseUsage.session.percentage / 100 : usage?.sessionUtilization,
        sessionResetsAt: lastSseUsage.session ? new Date(lastSseUsage.session.resetsAt).toISOString() : usage?.sessionResetsAt,
        weeklyUtilization: lastSseUsage.weekly ? lastSseUsage.weekly.percentage / 100 : usage?.weeklyUtilization,
        weeklyResetsAt: lastSseUsage.weekly ? new Date(lastSseUsage.weekly.resetsAt).toISOString() : usage?.weeklyResetsAt,
        source: 'sse-stream (' + lastSseUsage.receivedAt + ')'
      };
      log('usage نهایی از SSE ساخته شد:', usage);
    } else if (isApiUsageEmpty) {
      // اگه از استریم هم چیزی نرسیده (هنوز پیامی نفرستادی)، فال‌بک به اسکن بنر هشدار
      const banner = scanFreeLimitBanner();
      log('فال‌بک به اسکن بنر هشدار صفحه:', banner);
      usage = {
        ...usage,
        freePlanLimitReached: banner.limitReached,
        freePlanResetText: banner.resetText
      };
    }

    const usageDebug = {
      status: usageResult.status,
      ok: usageResult.ok,
      raw: usageResult.json || usageResult.raw
    };

    const conversationId = getConversationIdFromUrl();
    log('conversationId از URL:', conversationId);
    let messages = null;
    if (conversationId) {
      const convo = await fetchFullConversation(orgId, conversationId).catch((e) => {
        warn('fetchFullConversation خطا داد:', e.message);
        return null;
      });
      if (!convo) {
        warn('conversation fetch خالی برگشت (شاید 404 یا خطای شبکه)');
      }
      messages = extractMessages(convo);
      const totalTokens = messages.reduce((sum, m) => sum + (m.tokens || 0), 0);
      log(`تعداد پیام‌های استخراج‌شده از این چت: ${messages.length}, مجموع توکن تخمینی: ${totalTokens}`);
    } else {
      log('توی این صفحه conversationId نیست (صفحه‌ی چت باز نیست)، messages ارسال نمیشه');
    }

    const payload = {
      accountLabel,
      chatUrl: location.href,
      chatTitle: document.title,
      usage,
      usageDebug, // برای دیباگ: جواب خام API مصرف، تا اگه چیزی نیومد بشه فهمید چرا
      messages, // کل تاریخچه‌ی همین چت، از اول تا الان
      checkedAt: new Date().toISOString()
    };

    log('در حال ارسال payload به background script:', payload);
    chrome.runtime.sendMessage({ type: 'CLAUDE_STATUS', payload }, () => {
      if (chrome.runtime.lastError) {
        warn('sendMessage به background خطا داد:', chrome.runtime.lastError.message);
      } else {
        log('payload با موفقیت به background ارسال شد');
      }
    });
  });
}

setTimeout(report, 3000);
setInterval(report, 30000);

const observer = new MutationObserver(() => {
  clearTimeout(window.__claudeMonitorDebounce);
  window.__claudeMonitorDebounce = setTimeout(report, 4000);
});
observer.observe(document.body, { childList: true, subtree: true });

// وقتی مسیر تغییر کرد (رفتن به یک چت دیگه) هم زودتر گزارش بده
let lastPath = location.pathname;
setInterval(() => {
  if (location.pathname !== lastPath) {
    lastPath = location.pathname;
    setTimeout(report, 1500);
  }
}, 1000);
