"""
سرور لوکال برای جمع‌آوری وضعیت چند اکانت Claude.
اجرا:
    python3 server.py
داشبورد: http://localhost:8765
"""

import json
import os
import html as htmllib
import http.server
import socketserver
import uuid as uuidlib
from datetime import datetime, timezone
from urllib.parse import urlparse

DB_PATH = os.path.join(os.path.dirname(__file__), "status.json")
PORT = 8765


def load_db():
    if not os.path.exists(DB_PATH):
        return {}
    with open(DB_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def save_db(db):
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def esc(s):
    return htmllib.escape(s if isinstance(s, str) else json.dumps(s, ensure_ascii=False) if s is not None else "", quote=True)


def fmt_pct(usage, key):
    if not usage or usage.get(key) is None:
        return None
    try:
        v = float(usage[key])
        return v * 100 if v <= 1 else v
    except (TypeError, ValueError):
        return None


def pct_class(pct):
    if pct is None:
        return "unknown"
    if pct >= 90:
        return "danger"
    if pct >= 60:
        return "warn"
    return "ok"


WEEKDAYS_FA = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]
MONTHS_FA = ["ژانویه", "فوریه", "مارس", "آوریل", "مه", "ژوئن", "ژوئیه", "اوت", "سپتامبر", "اکتبر", "نوامبر", "دسامبر"]


def fmt_dt_fa(iso_str):
    """تاریخ خوانا به فارسی از یک رشته‌ی ISO می‌سازه، مثل: پنجشنبه ۲۵ سپتامبر، ساعت ۱۵:۱۰"""
    if not iso_str:
        return "-"
    try:
        s = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return esc(iso_str)
    weekday = WEEKDAYS_FA[dt.weekday()]
    month = MONTHS_FA[dt.month - 1]
    return f"{weekday} {dt.day} {month}، ساعت {dt.strftime('%H:%M')}"


def to_epoch_ms(iso_str):
    if not iso_str:
        return None
    try:
        s = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return int(dt.timestamp() * 1000)
    except (ValueError, TypeError):
        return None


def count_chat_tokens(chat):
    total = 0
    for m in chat.get("messages", []) or []:
        t = m.get("tokens")
        if isinstance(t, (int, float)):
            total += t
    return total


def count_account_tokens(info):
    return sum(count_chat_tokens(c) for c in (info.get("chats") or {}).values())


def collect_chat_files(chat):
    """همه‌ی فایل‌های این چت (چه آپلود کاربر، چه ساخته‌ی Claude) با مشخص کردن این‌که فایل رو کی تولید کرده."""
    files = []
    for m in chat.get("messages", []) or []:
        role = m.get("role")
        for f in (m.get("files") or []):
            if f and f.get("fileName"):
                files.append({
                    "fileName": f.get("fileName"),
                    "downloadUrl": f.get("downloadUrl"),
                    "fileUuid": f.get("fileUuid"),
                    "createdBy": "claude" if role == "assistant" else "user",
                    "createdAt": m.get("createdAt"),
                })
    return files


def total_notes_count(chat):
    chat_notes = len(chat.get("notes", []) or [])
    msg_notes = sum(len(v or []) for v in (chat.get("messageNotes") or {}).values())
    return chat_notes + msg_notes


def display_title(chat, chat_url):
    """اسمی که کاربر خودش برای چت گذاشته اولویت داره، وگرنه همون اسمی که کلاد گذاشته."""
    return chat.get("customTitle") or chat.get("title") or chat_url


PAGE = """<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>وضعیت اکانت‌های Claude</title>
<style>
  :root {{
    --bg: #0f1115;
    --panel: #171a21;
    --panel-2: #1e222b;
    --panel-3: #262b36;
    --border: #2a2f3a;
    --text: #e8e9ec;
    --text-dim: #9aa1ad;
    --accent: #7c9eff;
    --ok: #35c46b;
    --warn: #e8b339;
    --danger: #ef5555;
    --human: #7c9eff;
    --assistant: #35c46b;
    --note: #ff9d4d;
    --note-bg: rgba(255,157,77,.14);
    --note-border: rgba(255,157,77,.45);
    --link: #c792ea;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: 'Vazirmatn', 'Segoe UI', Tahoma, sans-serif;
    background: radial-gradient(circle at 20% -10%, #1a2030 0%, var(--bg) 45%);
    color: var(--text);
    margin: 0;
    padding: 28px 20px 60px;
  }}
  .top-bar {{
    display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px;
    max-width: 1200px; margin: 0 auto 22px;
  }}
  h1 {{ font-size: 21px; margin: 0; font-weight: 700; }}
  h1 .count {{ color: var(--accent); }}
  .top-bar-actions {{ display: flex; gap: 8px; flex-wrap: wrap; }}
  .refresh-link, .tool-btn {{
    font-size: 13px; color: var(--text-dim); text-decoration: none;
    border: 1px solid var(--border); padding: 6px 14px; border-radius: 20px; transition: all .15s;
    background: var(--panel); cursor: pointer; font-family: inherit;
  }}
  .refresh-link:hover, .tool-btn:hover {{ color: var(--text); border-color: var(--accent); }}

  .accounts-grid {{
    max-width: 1200px; margin: 0 auto 32px;
    display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 16px;
  }}
  .overview-card {{ background: var(--panel); border: 1px solid var(--border); border-radius: 16px; padding: 18px 18px 16px; }}
  .overview-card h2 {{ font-size: 17px; margin: 0 0 10px; font-weight: 700; }}
  .meter {{ margin-bottom: 12px; }}
  .meter:last-child {{ margin-bottom: 0; }}
  .meter-head {{ display: flex; justify-content: space-between; align-items: baseline; font-size: 12.5px; color: var(--text-dim); margin-bottom: 5px; }}
  .meter-head .pct {{ font-size: 14px; font-weight: 700; }}
  .meter-head .pct.ok {{ color: var(--ok); }}
  .meter-head .pct.warn {{ color: var(--warn); }}
  .meter-head .pct.danger {{ color: var(--danger); }}
  .meter-head .pct.unknown {{ color: var(--text-dim); }}
  .bar-track {{ height: 7px; border-radius: 6px; background: #2a2f3a; overflow: hidden; }}
  .bar-fill {{ height: 100%; border-radius: 6px; transition: width .4s ease; }}
  .bar-fill.ok {{ background: var(--ok); }}
  .bar-fill.warn {{ background: var(--warn); }}
  .bar-fill.danger {{ background: var(--danger); }}
  .bar-fill.unknown {{ background: #444; }}
  .meter-foot {{ display: flex; justify-content: space-between; font-size: 11.5px; color: var(--text-dim); margin-top: 5px; }}
  .countdown {{ font-variant-numeric: tabular-nums; color: var(--accent); font-weight: 600; }}
  .free-status {{ margin-top: 12px; padding: 8px 10px; border-radius: 10px; font-size: 12.5px; display: flex; align-items: center; gap: 6px; }}
  .free-status.reached {{ background: rgba(239,85,85,.12); color: var(--danger); }}
  .free-status.free {{ background: rgba(53,196,107,.12); color: var(--ok); }}
  .stat-row {{ display: flex; gap: 14px; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border); font-size: 12px; color: var(--text-dim); }}
  .stat-row b {{ color: var(--text); font-size: 13px; }}

  .chats-header {{
    max-width: 1200px; margin: 0 auto 12px; display: flex; align-items: center; justify-content: space-between;
    gap: 12px; flex-wrap: wrap;
  }}
  .section-title {{ font-size: 15px; color: var(--text-dim); font-weight: 600; }}
  #search {{
    flex: 1; min-width: 220px; max-width: 500px;
    padding: 10px 14px; font-size: 13.5px; border-radius: 10px;
    border: 1px solid var(--border); background: var(--panel); color: var(--text); outline: none;
    transition: border-color .15s;
  }}
  #search:focus {{ border-color: var(--accent); }}
  #search::placeholder {{ color: var(--text-dim); }}

  .chat-list {{ max-width: 1200px; margin: 0 auto 32px; display: flex; flex-direction: column; gap: 10px; }}
  .chat-card {{
    background: var(--panel); border: 1px solid var(--border); border-radius: 14px;
    transition: border-color .15s;
  }}
  .chat-card:hover {{ border-color: var(--accent); }}
  .chat-row {{
    padding: 14px 16px; display: flex; align-items: center; justify-content: space-between; gap: 14px; flex-wrap: wrap;
    cursor: pointer;
  }}
  .chat-row .chat-main {{ flex: 1; min-width: 240px; }}
  .chat-row .chat-title {{ font-size: 14.5px; font-weight: 600; margin-bottom: 4px; display: flex; align-items: center; gap: 6px; }}
  .chat-row .chat-title .orig-title {{ font-size: 11px; color: var(--text-dim); font-weight: 400; }}
  .rename-btn {{
    background: none; border: none; color: var(--text-dim); cursor: pointer; font-size: 12px; padding: 2px 4px; border-radius: 6px; flex-shrink: 0;
  }}
  .rename-btn:hover {{ color: var(--accent); background: rgba(124,158,255,.12); }}
  .rename-box {{ display: flex; gap: 6px; align-items: center; flex: 1; }}
  .rename-box input {{
    flex: 1; padding: 4px 8px; font-size: 13.5px; border-radius: 8px; border: 1px solid var(--accent);
    background: var(--bg); color: var(--text); font-family: inherit;
  }}
  .rename-box button {{ font-size: 11px; padding: 4px 10px; border-radius: 8px; border: 1px solid var(--border); background: var(--panel-2); color: var(--text); cursor: pointer; font-family: inherit; }}
  .rename-box button.save {{ border-color: var(--accent); color: var(--accent); }}
  .modal-head h3 {{ display: flex; align-items: center; gap: 8px; }}
  .chat-row .chat-meta {{ font-size: 12px; color: var(--text-dim); display: flex; gap: 10px; flex-wrap: wrap; }}
  .chat-row .chat-note-badge {{
    font-size: 11.5px; color: var(--note); background: var(--note-bg); border: 1px solid var(--note-border);
    padding: 3px 10px; border-radius: 20px; white-space: nowrap; cursor: pointer; font-family: inherit; font-weight: 600;
  }}
  .chat-row .chat-note-badge:hover {{ filter: brightness(1.15); }}
  .chat-row .download-btn {{
    font-size: 12.5px; color: var(--link); border: 1px solid var(--link);
    padding: 6px 14px; border-radius: 20px; white-space: nowrap; background: rgba(199,146,234,.1); cursor: pointer; font-family: inherit;
  }}
  .chat-row .download-btn:hover {{ background: rgba(199,146,234,.22); }}
  .chat-row .link-badge {{
    font-size: 11px; color: var(--link); background: rgba(199,146,234,.12); border: 1px solid rgba(199,146,234,.4);
    padding: 3px 10px; border-radius: 20px; white-space: nowrap; cursor: pointer; font-family: inherit;
  }}
  .chat-row .file-badge {{
    font-size: 11.5px; color: var(--accent); background: rgba(124,158,255,.12);
    padding: 3px 10px; border-radius: 20px; white-space: nowrap;
  }}
  .chat-row .open-btn {{
    font-size: 12.5px; color: var(--text-dim); border: 1px solid var(--border);
    padding: 6px 14px; border-radius: 20px; white-space: nowrap; background: transparent;
  }}
  .chat-row:hover .open-btn {{ color: var(--accent); border-color: var(--accent); }}
  .empty {{ color: var(--text-dim); font-size: 13px; padding: 20px; text-align: center; max-width: 1200px; margin: 0 auto; }}

  /* ستاره‌گذاری روی چت */
  .star-btn {{
    background: none; border: none; cursor: pointer; font-size: 17px; padding: 2px 4px;
    line-height: 1; flex-shrink: 0; filter: grayscale(1) opacity(.55); transition: filter .15s, transform .15s;
  }}
  .star-btn:hover {{ transform: scale(1.15); }}
  .star-btn.starred {{ filter: none; opacity: 1; }}
  .chat-card.is-starred {{ border-color: rgba(232,179,57,.55); }}

  /* آرشیو کردن چت */
  .archive-check-wrap {{
    display: flex; align-items: center; gap: 4px; font-size: 11px; color: var(--text-dim);
    flex-shrink: 0; cursor: pointer; user-select: none;
  }}
  .archive-check-wrap input {{ cursor: pointer; accent-color: var(--accent); width: 15px; height: 15px; }}
  .chats-header .tool-btn.active-toggle {{ color: var(--accent); border-color: var(--accent); }}
  .archived-section {{ display: none; }}
  .archived-section.open {{ display: block; }}
  .archived-section-head {{
    max-width: 1200px; margin: 18px auto 10px; padding-top: 12px; border-top: 1px dashed var(--border);
    font-size: 13px; color: var(--text-dim); font-weight: 600;
  }}
  .chat-card.archived-card {{ opacity: .78; }}

  /* پنل یادداشت‌های زیر هر چت (باز/بسته با دکمه) */
  .chat-notes-panel {{
    display: none; padding: 0 16px 14px; border-top: 1px solid var(--border);
  }}
  .chat-notes-panel.open {{ display: block; }}
  .chat-notes-panel .notes-title {{ font-size: 12.5px; font-weight: 600; color: var(--text-dim); margin: 12px 0 8px; }}

  /* مودال جزئیات چت */
  .modal-overlay {{
    display: none; position: fixed; inset: 0; background: rgba(6,7,10,.72);
    z-index: 100; align-items: flex-start; justify-content: center; padding: 30px 16px; overflow-y: auto;
  }}
  .modal-overlay.open {{ display: flex; }}
  .modal {{
    background: var(--panel); border: 1px solid var(--border); border-radius: 16px;
    max-width: 900px; width: 100%; padding: 20px 22px 26px; max-height: calc(100vh - 60px); overflow-y: auto;
  }}
  .modal-head {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 4px; }}
  .modal-head h3 {{ font-size: 17px; margin: 0 0 4px; }}
  .modal-head .modal-sub {{ font-size: 12px; color: var(--text-dim); }}
  .modal-close {{
    background: var(--panel-2); border: 1px solid var(--border); color: var(--text-dim);
    border-radius: 10px; width: 32px; height: 32px; cursor: pointer; font-size: 15px; flex-shrink: 0;
  }}
  .modal-close:hover {{ color: var(--text); border-color: var(--accent); }}
  .modal-actions {{ display: flex; gap: 8px; margin: 14px 0; flex-wrap: wrap; }}
  .modal-actions a, .modal-actions button {{
    font-size: 12.5px; color: var(--accent); background: rgba(124,158,255,.1); border: 1px solid transparent;
    padding: 7px 14px; border-radius: 20px; text-decoration: none; cursor: pointer; font-family: inherit;
  }}
  .modal-actions a:hover, .modal-actions button:hover {{ background: rgba(124,158,255,.2); }}

  .files-box {{ margin: 14px 0; padding: 12px 14px; background: var(--panel-2); border-radius: 12px; border: 1px solid var(--border); }}
  .files-box .files-title {{ font-size: 12.5px; color: var(--text-dim); margin-bottom: 8px; font-weight: 600; }}
  .file-item {{ display: flex; justify-content: space-between; align-items: center; font-size: 13px; padding: 6px 0; border-top: 1px solid var(--border); gap: 8px; flex-wrap: wrap; }}
  .file-item:first-child {{ border-top: none; }}
  .file-item .file-name {{ display: flex; align-items: center; gap: 6px; }}
  .file-item .file-src {{
    font-size: 10.5px; padding: 2px 8px; border-radius: 10px; white-space: nowrap;
  }}
  .file-item .file-src.claude {{ background: rgba(53,196,107,.15); color: var(--ok); }}
  .file-item .file-src.user {{ background: rgba(124,158,255,.15); color: var(--accent); }}
  .file-item a {{ font-size: 12px; color: var(--accent); }}

  table.msg-table {{ width: 100%; border-collapse: collapse; margin-top: 6px; }}
  table.msg-table th, table.msg-table td {{ border: 1px solid var(--border); padding: 7px 9px; text-align: right; font-size: 13px; vertical-align: top; }}
  table.msg-table th {{ background: var(--panel-2); color: var(--text-dim); font-weight: 600; }}
  .msg {{ white-space: pre-wrap; max-width: 560px; }}
  .human {{ color: var(--human); font-weight: 600; }}
  .assistant {{ color: var(--assistant); font-weight: 600; }}
  .ts {{ color: var(--text-dim); font-size: 11px; }}
  .tok {{ color: var(--text-dim); font-size: 11px; }}
  a {{ color: var(--accent); }}

  .msg-note-btn {{
    margin-top: 6px; font-size: 10.5px; color: var(--note); background: var(--note-bg);
    border: 1px solid var(--note-border); padding: 2px 8px; border-radius: 8px; cursor: pointer; font-family: inherit;
  }}
  .msg-note-btn:hover {{ filter: brightness(1.15); }}
  .msg-notes-list {{ margin-top: 6px; display: flex; flex-direction: column; gap: 5px; }}
  .msg-note-item {{
    background: var(--note-bg); border: 1px solid var(--note-border); border-right: 3px solid var(--note);
    border-radius: 8px; padding: 6px 8px; font-size: 11.5px;
    display: flex; justify-content: space-between; gap: 8px; align-items: flex-start;
  }}
  .msg-note-item .txt {{ white-space: pre-wrap; flex: 1; }}
  .msg-note-item .actions {{ display: flex; gap: 4px; flex-shrink: 0; }}
  .msg-note-item .del, .msg-note-item .edit {{ background: none; border: none; cursor: pointer; font-size: 11px; padding: 0 4px; }}
  .msg-note-item .del {{ color: var(--danger); }}
  .msg-note-item .edit {{ color: var(--accent); }}
  .msg-note-add {{ display: none; margin-top: 6px; gap: 6px; }}
  .msg-note-add.open {{ display: flex; }}
  .msg-note-add textarea {{
    flex: 1; min-height: 34px; font-family: inherit; font-size: 12px; padding: 6px 8px;
    border-radius: 8px; border: 1px solid var(--border); background: var(--bg); color: var(--text); resize: vertical;
  }}
  .msg-note-add button {{
    padding: 6px 12px; cursor: pointer; border-radius: 8px; border: 1px solid var(--accent);
    background: var(--accent); color: #10131a; font-size: 11.5px; font-weight: 600;
  }}

  /* یادداشت‌های کل چت */
  .notes-box {{ margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--border); }}
  .notes-box .notes-title {{ font-size: 13.5px; font-weight: 600; margin-bottom: 10px; }}
  .note-item {{
    background: var(--note-bg); border: 1px solid var(--note-border); border-right: 3px solid var(--note); border-radius: 10px;
    padding: 10px 12px; margin-bottom: 8px; display: flex; justify-content: space-between; gap: 10px; align-items: flex-start;
  }}
  .note-item .note-text {{ font-size: 13px; white-space: pre-wrap; flex: 1; }}
  .note-item .note-meta {{ font-size: 10.5px; color: var(--text-dim); margin-top: 4px; }}
  .note-item .note-actions {{ display: flex; gap: 4px; flex-shrink: 0; }}
  .note-item .note-del, .note-item .note-edit {{
    background: none; border: none; cursor: pointer; font-size: 12px;
    padding: 4px 8px; border-radius: 8px;
  }}
  .note-item .note-del {{ color: var(--danger); }}
  .note-item .note-del:hover {{ background: rgba(239,85,85,.12); }}
  .note-item .note-edit {{ color: var(--accent); }}
  .note-item .note-edit:hover {{ background: rgba(124,158,255,.12); }}
  .note-edit-box {{ display: flex; flex-direction: column; gap: 6px; flex: 1; }}
  .note-edit-box textarea {{
    width: 100%; min-height: 44px; box-sizing: border-box; font-family: inherit; font-size: 13px;
    padding: 8px 10px; border-radius: 10px; border: 1px solid var(--border); background: var(--bg); color: var(--text); resize: vertical;
  }}
  .note-edit-box .edit-actions {{ display: flex; gap: 6px; }}
  .note-edit-box .edit-actions button {{
    font-size: 11.5px; padding: 4px 10px; border-radius: 8px; cursor: pointer; font-family: inherit; border: 1px solid var(--border); background: var(--panel-2); color: var(--text);
  }}
  .note-edit-box .edit-actions button.save {{ border-color: var(--accent); color: var(--accent); }}

  .chain-box {{ font-size: 12px; color: var(--text-dim); margin: 10px 0; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }}
  .chain-box a {{ color: var(--link); }}
  .link-select-row {{ margin: 14px 0; padding: 12px 14px; background: var(--panel-2); border-radius: 12px; border: 1px solid var(--border); display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
  .link-select-row label {{ font-size: 12.5px; color: var(--text-dim); font-weight: 600; }}
  .link-select-row select {{
    flex: 1; min-width: 200px; padding: 7px 10px; border-radius: 8px; border: 1px solid var(--border);
    background: var(--bg); color: var(--text); font-family: inherit; font-size: 12.5px;
  }}
  .note-add {{ display: flex; gap: 8px; margin-top: 10px; align-items: flex-start; }}
  .note-add textarea {{
    flex: 1; min-height: 44px; box-sizing: border-box; font-family: inherit; font-size: 13px;
    padding: 8px 10px; border-radius: 10px; border: 1px solid var(--border); background: var(--bg); color: var(--text); resize: vertical;
  }}
  .note-add button {{
    padding: 8px 16px; cursor: pointer; border-radius: 10px; border: 1px solid var(--accent);
    background: var(--accent); color: #10131a; font-size: 12.5px; font-weight: 600; white-space: nowrap; font-family: inherit;
  }}
  .note-add button:hover {{ opacity: .85; }}
  .no-notes {{ color: var(--text-dim); font-size: 12.5px; }}
  .hidden {{ display: none !important; }}

  /* نوار عمودی چسبیده به گوشه‌ی چپ: نمای گرافی زنجیره‌ی چت‌های وصل‌شده. با کلیک، مثل کشو باز می‌شه */
  .graph-widget {{
    position: fixed; top: 0; bottom: 0; left: 0; width: 42px;
    background: var(--panel); border-left: none; border: 1px solid var(--border);
    box-shadow: 0 8px 24px rgba(0,0,0,.35); z-index: 90; overflow: hidden;
    transition: width .2s ease; display: flex; flex-direction: column;
  }}
  .graph-widget.expanded {{
    width: 42vw; max-width: 620px; min-width: 320px;
  }}
  @media (max-width: 900px) {{ .graph-widget.expanded {{ width: 100vw; max-width: none; }} }}
  .graph-widget-head {{
    padding: 12px 4px; font-size: 12px; font-weight: 600; color: var(--text-dim);
    display: flex; justify-content: flex-start; align-items: center; cursor: pointer; gap: 10px;
    writing-mode: vertical-rl; text-orientation: mixed; flex: 1; white-space: nowrap;
  }}
  .graph-widget.expanded .graph-widget-head {{
    writing-mode: horizontal-tb; flex: none; justify-content: space-between; padding: 10px 14px;
    border-bottom: 1px solid var(--border);
  }}
  .graph-widget-head:hover {{ color: var(--text); }}
  .graph-widget-head-actions {{ display: none; align-items: center; gap: 10px; }}
  .graph-widget.expanded .graph-widget-head-actions {{ display: flex; }}
  .graph-archive-toggle {{
    display: flex; align-items: center; gap: 4px; font-size: 11px; color: var(--text-dim); cursor: pointer; user-select: none;
  }}
  .graph-archive-toggle input {{ cursor: pointer; accent-color: var(--accent); }}
  .graph-close-btn {{
    background: var(--panel-2); border: 1px solid var(--border); color: var(--text-dim); border-radius: 8px;
    width: 26px; height: 26px; font-size: 13px; cursor: pointer; flex-shrink: 0;
  }}
  .graph-close-btn:hover {{ color: var(--text); border-color: var(--accent); }}
  .graph-widget-body {{ padding: 10px 12px; overflow: auto; display: none; flex: 1; }}
  .graph-widget.expanded .graph-widget-body {{ display: flex; flex-direction: column; }}
  #graphSvgWrap {{ flex: 1; display: flex; align-items: flex-start; justify-content: center; overflow: auto; }}
  .graph-widget svg {{ display: block; width: auto; height: auto; max-width: 100%; }}
  .graph-widget .gnode circle {{ fill: var(--link); stroke: var(--panel); stroke-width: 2; cursor: pointer; }}
  .graph-widget .gnode:hover circle {{ fill: var(--accent); }}
  .graph-widget .gnode text {{ fill: var(--text); font-size: 8px; cursor: pointer; }}
  .graph-widget.expanded .gnode text {{ font-size: 11px; }}
  .graph-widget .gnode.gnode-archived circle {{ fill: var(--text-dim); opacity: .55; }}
  .graph-widget .gnode.gnode-archived text {{ fill: var(--text-dim); }}
  .graph-widget .gedge {{ stroke: var(--border); stroke-width: 1.5; }}
  .graph-widget .no-chains {{ color: var(--text-dim); font-size: 12px; padding: 6px 2px; }}
</style>

</head>
<body>
<div class="top-bar">
  <h1>وضعیت اکانت‌های Claude &nbsp;<span class="count">({count} اکانت)</span></h1>
  <div class="top-bar-actions">
    <button class="tool-btn" onclick="openAllNotesModal()">🗒 همه‌ی یادداشت‌ها</button>
    <a class="refresh-link" href="/">↻ بروزرسانی</a>
  </div>
</div>

<div class="accounts-grid">
{overview_html}
</div>

<div class="chats-header">
  <div class="section-title">💬 چت‌ها ({chat_count} مورد)</div>
  <input id="search" type="text" placeholder="جستجو در همه‌ی چت‌ها، پیام‌ها و یادداشت‌ها..." oninput="filterChats(this.value)" />
  <button class="tool-btn" id="toggleAllBtn" onclick="toggleAllNotes()">📝 نمایش یادداشت‌های همه‌ی چت‌ها</button>
  <button class="tool-btn" id="toggleArchivedBtn" onclick="toggleArchivedView()">🗄 نمایش آرشیو (<span id="archivedCount">{archived_count}</span>)</button>
</div>
<div class="chat-list" id="chatList">
{chatlist_html}
</div>

<div class="archived-section" id="archivedSection">
  <div class="archived-section-head">🗄 چت‌های آرشیوشده</div>
  <div class="chat-list" id="archivedChatList">
{archived_chatlist_html}
  </div>
</div>

<div class="modal-overlay" id="modalOverlay" onclick="if(event.target===this) closeModal()">
  <div class="modal" id="modalBody"></div>
</div>

<div class="graph-widget" id="graphWidget">
  <div class="graph-widget-head" onclick="toggleGraphWidget()">
    <span>🕸 زنجیره‌ی چت‌ها (<span id="graphChainCount">0</span>)</span>
    <div class="graph-widget-head-actions">
      <label class="graph-archive-toggle" onclick="event.stopPropagation()">
        <input type="checkbox" id="graphShowArchived" onchange="renderGraphWidget()" /> نمایش آرشیو
      </label>
      <button class="graph-close-btn" onclick="event.stopPropagation();toggleGraphWidget()" title="بستن">✕</button>
    </div>
  </div>
  <div class="graph-widget-body" id="graphWidgetBody">
    <div id="graphSvgWrap"></div>
  </div>
</div>

<script>
const CHAT_DATA = {chat_data_json};
let allNotesExpanded = false;

function fmtRemaining(ms) {{
  if (ms <= 0) return 'به‌زودی ریست می‌شود';
  const totalMin = Math.floor(ms / 60000);
  const days = Math.floor(totalMin / 1440);
  const hours = Math.floor((totalMin % 1440) / 60);
  const mins = totalMin % 60;
  const secs = Math.floor((ms % 60000) / 1000);
  if (days > 0) return days + ' روز و ' + hours + ' ساعت مانده';
  if (hours > 0) return hours + ' ساعت و ' + mins + ' دقیقه مانده';
  if (mins > 0) return mins + ' دقیقه و ' + secs + ' ثانیه مانده';
  return secs + ' ثانیه مانده';
}}

function tickCountdowns() {{
  const now = Date.now();
  document.querySelectorAll('[data-resets-at]').forEach(function(el) {{
    const target = parseInt(el.getAttribute('data-resets-at'), 10);
    if (!target) {{ el.textContent = '-'; return; }}
    el.textContent = fmtRemaining(target - now);
  }});
}}
tickCountdowns();
setInterval(tickCountdowns, 1000);
renderGraphWidget();

function filterChats(q) {{
  q = q.trim().toLowerCase();
  document.querySelectorAll('#chatList .chat-card, #archivedChatList .chat-card').forEach(function(card) {{
    const text = card.getAttribute('data-searchtext') || '';
    card.classList.toggle('hidden', !!q && !text.includes(q));
  }});
}}

/* ---------- نمایش/عدم‌نمایش بخش آرشیو ---------- */
let archivedViewOpen = false;
function toggleArchivedView() {{
  archivedViewOpen = !archivedViewOpen;
  document.getElementById('archivedSection').classList.toggle('open', archivedViewOpen);
  document.getElementById('toggleArchivedBtn').classList.toggle('active-toggle', archivedViewOpen);
}}

/* ---------- آرشیو کردن / درآوردن از آرشیو ---------- */
function toggleArchive(chatKey, archived) {{
  const chat = CHAT_DATA[chatKey];
  if (!chat) return;
  fetch('/archive', {{
    method: 'POST', headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ accountLabel: chat.accountLabel, chatUrl: chat.chatUrl, archived: archived }})
  }}).then(function(r) {{ return r.json(); }}).then(function(res) {{
    chat.archived = !!res.archived;
    const card = document.querySelector('.chat-card[data-chat-key="' + cssAttrEsc(chatKey) + '"]');
    if (!card) return;
    card.setAttribute('data-archived', chat.archived ? '1' : '0');
    card.classList.toggle('archived-card', chat.archived);
    const targetList = document.getElementById(chat.archived ? 'archivedChatList' : 'chatList');
    targetList.appendChild(card);
    document.getElementById('archivedCount').textContent = document.querySelectorAll('#archivedChatList .chat-card[data-archived="1"]').length;
    renderGraphWidget();
  }});
}}

/* ---------- ستاره/نشان‌کردن چت ---------- */
function toggleStar(chatKey, ev) {{
  if (ev) ev.stopPropagation();
  const chat = CHAT_DATA[chatKey];
  if (!chat) return;
  const newVal = !chat.starred;
  fetch('/star', {{
    method: 'POST', headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ accountLabel: chat.accountLabel, chatUrl: chat.chatUrl, starred: newVal }})
  }}).then(function(r) {{ return r.json(); }}).then(function(res) {{
    chat.starred = !!res.starred;
    const btn = document.getElementById('star-' + cssEsc(chatKey));
    if (btn) btn.classList.toggle('starred', chat.starred);
    const card = document.querySelector('.chat-card[data-chat-key="' + cssAttrEsc(chatKey) + '"]');
    if (card) {{
      card.setAttribute('data-starred', chat.starred ? '1' : '0');
      card.classList.toggle('is-starred', chat.starred);
      if (chat.starred) card.parentElement.prepend(card);
    }}
  }});
}}

function cssAttrEsc(s) {{
  return String(s).replace(/["\\\\]/g, '\\\\$&');
}}

/* ---------- بزرگ/کوچک کردن ویجت گراف (کشوی نیم‌صفحه از بغل) ---------- */
let graphWidgetOpen = false;

/* با زدن روی نوار عمودی، مستقیم به‌صورت کشو از سمت چپ باز می‌شه؛ با ضربدر یا کلیک دوباره بسته می‌شه */
function toggleGraphWidget() {{
  graphWidgetOpen = !graphWidgetOpen;
  const w = document.getElementById('graphWidget');
  w.classList.toggle('expanded', graphWidgetOpen);
  document.getElementById('graphWidgetBody').classList.toggle('open', graphWidgetOpen);
  if (graphWidgetOpen) renderGraphWidget();
}}

function esc(s) {{
  const d = document.createElement('div');
  d.textContent = (s === null || s === undefined) ? '' : String(s);
  return d.innerHTML;
}}

function fmtDate(iso) {{
  if (!iso) return '-';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString('fa-IR', {{ dateStyle: 'medium', timeStyle: 'short' }});
}}

/* ---------- باز/بسته کردن پنل یادداشتِ زیر هر چت (بدون باز شدن مودال کامل) ---------- */
function toggleChatNotes(chatKey, ev) {{
  if (ev) ev.stopPropagation();
  const panel = document.getElementById('notesPanel-' + cssEsc(chatKey));
  if (!panel) return;
  const isOpen = panel.classList.toggle('open');
  if (isOpen) panel.innerHTML = renderChatNotesPanel(chatKey);
}}

function cssEsc(s) {{
  return s.replace(/[^a-zA-Z0-9\\u0600-\\u06FF_-]/g, '_');
}}

/* ---------- اسم دلخواه برای چت (جدا از اسمی که کلاد میزاره) ---------- */
function startRenameRow(chatKey, ev) {{
  if (ev) ev.stopPropagation();
  const wrap = document.getElementById('title-' + cssEsc(chatKey));
  const chat = CHAT_DATA[chatKey];
  if (!wrap || !chat) return;
  const curText = wrap.querySelector('.title-text').textContent;
  wrap.innerHTML = '<div class="rename-box">' +
    '<input type="text" value="' + esc(curText) + '" onclick="event.stopPropagation()" onkeydown="if(event.key===\\'Enter\\')this.nextElementSibling.click(); if(event.key===\\'Escape\\')renameRowCancel(\\'' + chatKey + '\\')" />' +
    '<button class="save" onclick="event.stopPropagation();saveRenameRow(\\'' + chatKey + '\\', this)">ذخیره</button>' +
    '<button onclick="event.stopPropagation();renameRowCancel(\\'' + chatKey + '\\')">انصراف</button>' +
  '</div>';
  wrap.querySelector('input').focus();
}}

function renameRowCancel(chatKey) {{
  const wrap = document.getElementById('title-' + cssEsc(chatKey));
  const chat = CHAT_DATA[chatKey];
  if (wrap) wrap.innerHTML = renderTitleHtml(chatKey, chat);
}}

function renderTitleHtml(chatKey, chat) {{
  const origHtml = chat.customTitle ? '<span class="orig-title">(اسم کلاد: ' + esc(chat.origTitle) + ')</span>' : '';
  return '<span class="title-text">' + esc(chat.title) + '</span>' + origHtml +
    '<button class="rename-btn" onclick="startRenameRow(\\'' + chatKey + '\\', event)">✏️</button>';
}}

function saveRenameRow(chatKey, btn) {{
  const wrap = document.getElementById('title-' + cssEsc(chatKey));
  const input = wrap.querySelector('input');
  const newTitle = input.value.trim();
  const chat = CHAT_DATA[chatKey];
  fetch('/rename', {{
    method: 'POST', headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ accountLabel: chat.accountLabel, chatUrl: chat.chatUrl, customTitle: newTitle }})
  }}).then(function(r) {{ return r.json(); }}).then(function(res) {{
    chat.title = res.customTitle || res.origTitle;
    chat.origTitle = res.origTitle;
    chat.customTitle = res.customTitle;
    wrap.innerHTML = renderTitleHtml(chatKey, chat);
    const modalOverlay = document.getElementById('modalOverlay');
    if (modalOverlay.classList.contains('open') && modalOverlay.getAttribute('data-current-chat') === chatKey) {{
      const h3 = document.querySelector('#modalBody .modal-head h3');
      if (h3) h3.innerHTML = renderModalTitleHtml(chatKey, chat);
    }}
  }});
}}

function noteItemHtml(chatKey, n, delFn, editFn) {{
  return '<div class="note-item"><div style="flex:1"><div class="note-text">' + esc(n.text) + '</div>' +
    '<div class="note-meta">' + fmtDate(n.createdAt) + (n.editedAt ? ' (ویرایش‌شده)' : '') + '</div></div>' +
    '<div class="note-actions">' +
    '<button class="note-edit" onclick="' + editFn + '">ویرایش</button>' +
    '<button class="note-del" onclick="' + delFn + '">حذف</button>' +
    '</div></div>';
}}

function renderChatNotesPanel(chatKey) {{
  const chat = CHAT_DATA[chatKey];
  const notes = (chat && chat.notes) || [];
  const notesHtml = notes.length
    ? notes.map(function(n) {{
        return noteItemHtml(chatKey, n,
          "deleteChatNoteInline('" + chatKey + "','" + n.id + "', this)",
          "editChatNoteInline('" + chatKey + "','" + n.id + "', this)");
      }}).join('')
    : '';

  const msgNotesEntries = Object.keys((chat && chat.messageNotes) || {{}});
  let msgNotesHtml = '';
  if (msgNotesEntries.length) {{
    msgNotesHtml = '<div class="notes-title">📝 یادداشت‌های روی پیام‌ها</div>' +
      msgNotesEntries.map(function(idx) {{
        const arr = chat.messageNotes[idx] || [];
        return arr.map(function(n) {{
          return noteItemHtml(chatKey, n,
            "deleteMsgNoteInline('" + chatKey + "'," + idx + ",'" + n.id + "', this)",
            "editMsgNoteInline('" + chatKey + "'," + idx + ",'" + n.id + "', this)");
        }}).join('');
      }}).join('');
  }}

  const emptyHtml = (!notes.length && !msgNotesEntries.length) ? '<div class="no-notes">هنوز یادداشتی برای این چت نگذاشتی.</div>' : '';

  return '<div class="notes-title">📝 یادداشت‌های کلی چت (' + notes.length + ')</div>' +
    '<div>' + notesHtml + '</div>' +
    emptyHtml +
    msgNotesHtml +
    '<div class="note-add">' +
      '<textarea placeholder="یادداشت جدید بنویس..." onclick="event.stopPropagation()"></textarea>' +
      '<button onclick="addChatNoteInline(\\'' + chatKey + '\\', this)">افزودن</button>' +
    '</div>';
}}

function startNoteEdit(container, curText, onSave) {{
  container.innerHTML = '<div class="note-edit-box"><textarea>' + esc(curText) + '</textarea>' +
    '<div class="edit-actions"><button class="save">ذخیره</button><button class="cancel">انصراف</button></div></div>';
  const box = container.querySelector('.note-edit-box');
  box.querySelector('.save').onclick = function() {{ onSave(box.querySelector('textarea').value.trim()); }};
  box.querySelector('.cancel').onclick = function() {{ onSave(null); }};
}}

function editChatNoteInline(chatKey, noteId, btn) {{
  const item = btn.closest('.note-item');
  const chat = CHAT_DATA[chatKey];
  const note = (chat.notes || []).find(function(n) {{ return n.id === noteId; }});
  if (!note) return;
  startNoteEdit(item, note.text, function(newText) {{
    if (newText === null) {{ item.parentElement.parentElement.innerHTML = renderChatNotesPanel(chatKey); return; }}
    if (!newText) return;
    fetch('/note', {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ accountLabel: chat.accountLabel, chatUrl: chat.chatUrl, scope: 'chat', action: 'edit', noteId: noteId, text: newText }})
    }}).then(function(r) {{ return r.json(); }}).then(function(res) {{
      chat.notes = res.notes || [];
      const panel = document.getElementById('notesPanel-' + cssEsc(chatKey));
      if (panel) panel.innerHTML = renderChatNotesPanel(chatKey);
      if (document.getElementById('notesList')) document.getElementById('notesList').innerHTML = renderModalChatNotes(chatKey);
    }});
  }});
}}

function addChatNoteInline(chatKey, btn) {{
  const ta = btn.parentElement.querySelector('textarea');
  const text = ta.value.trim();
  if (!text) return;
  const chat = CHAT_DATA[chatKey];
  fetch('/note', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ accountLabel: chat.accountLabel, chatUrl: chat.chatUrl, scope: 'chat', action: 'add', text: text }})
  }}).then(function(r) {{ return r.json(); }}).then(function(res) {{
    chat.notes = res.notes || [];
    const panel = document.getElementById('notesPanel-' + cssEsc(chatKey));
    if (panel) panel.innerHTML = renderChatNotesPanel(chatKey);
    refreshChatRowBadge(chatKey);
  }});
}}

function deleteChatNoteInline(chatKey, noteId, btn) {{
  const chat = CHAT_DATA[chatKey];
  fetch('/note', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ accountLabel: chat.accountLabel, chatUrl: chat.chatUrl, scope: 'chat', action: 'delete', noteId: noteId }})
  }}).then(function(r) {{ return r.json(); }}).then(function(res) {{
    chat.notes = res.notes || [];
    const panel = document.getElementById('notesPanel-' + cssEsc(chatKey));
    if (panel) panel.innerHTML = renderChatNotesPanel(chatKey);
    refreshChatRowBadge(chatKey);
  }});
}}

function deleteMsgNoteInline(chatKey, idx, noteId) {{
  const chat = CHAT_DATA[chatKey];
  fetch('/note', {{
    method: 'POST', headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ accountLabel: chat.accountLabel, chatUrl: chat.chatUrl, scope: 'message', messageIndex: idx, action: 'delete', noteId: noteId }})
  }}).then(function(r) {{ return r.json(); }}).then(function(res) {{
    chat.messageNotes = res.messageNotes || {{}};
    const panel = document.getElementById('notesPanel-' + cssEsc(chatKey));
    if (panel) panel.innerHTML = renderChatNotesPanel(chatKey);
    refreshChatRowBadge(chatKey);
  }});
}}

function editMsgNoteInline(chatKey, idx, noteId, btn) {{
  const item = btn.closest('.note-item');
  const chat = CHAT_DATA[chatKey];
  const arr = (chat.messageNotes && chat.messageNotes[idx]) || [];
  const note = arr.find(function(n) {{ return n.id === noteId; }});
  if (!note) return;
  startNoteEdit(item, note.text, function(newText) {{
    const panel = document.getElementById('notesPanel-' + cssEsc(chatKey));
    if (newText === null) {{ if (panel) panel.innerHTML = renderChatNotesPanel(chatKey); return; }}
    if (!newText) return;
    fetch('/note', {{
      method: 'POST', headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ accountLabel: chat.accountLabel, chatUrl: chat.chatUrl, scope: 'message', messageIndex: idx, action: 'edit', noteId: noteId, text: newText }})
    }}).then(function(r) {{ return r.json(); }}).then(function(res) {{
      chat.messageNotes = res.messageNotes || {{}};
      if (panel) panel.innerHTML = renderChatNotesPanel(chatKey);
    }});
  }});
}}

function toggleAllNotes() {{
  allNotesExpanded = !allNotesExpanded;
  document.querySelectorAll('.chat-notes-panel').forEach(function(panel) {{
    const chatKey = panel.getAttribute('data-chat-key');
    if (allNotesExpanded) {{
      panel.classList.add('open');
      panel.innerHTML = renderChatNotesPanel(chatKey);
    }} else {{
      panel.classList.remove('open');
    }}
  }});
  document.getElementById('toggleAllBtn').textContent = allNotesExpanded
    ? '📝 بستن یادداشت‌های همه‌ی چت‌ها'
    : '📝 نمایش یادداشت‌های همه‌ی چت‌ها';
}}

function refreshChatRowBadge(chatKey) {{
  const chat = CHAT_DATA[chatKey];
  const card = document.querySelector('.chat-card[data-chat-key="' + chatKey + '"]');
  if (!card) return;
  const badge = card.querySelector('.chat-note-badge');
  const count = totalNotesCount(chat);
  if (badge) badge.textContent = '📝 ' + count + ' یادداشت';
}}

function totalNotesCount(chat) {{
  const chatNotes = (chat.notes || []).length;
  const msgNotes = Object.values(chat.messageNotes || {{}}).reduce(function(sum, arr) {{ return sum + arr.length; }}, 0);
  return chatNotes + msgNotes;
}}

/* ---------- مودال جزئیات کامل چت ---------- */
function renderModalTitleHtml(chatKey, chat) {{
  const origSub = chat.customTitle ? '<span class="orig-title">(اسم کلاد: ' + esc(chat.origTitle) + ')</span>' : '';
  return '<span class="title-text">' + esc(chat.title) + '</span>' + origSub +
    '<button class="rename-btn" onclick="startRenameModal(\\'' + chatKey + '\\')">✏️</button>';
}}

function startRenameModal(chatKey) {{
  const h3 = document.querySelector('#modalBody .modal-head h3');
  const chat = CHAT_DATA[chatKey];
  if (!h3 || !chat) return;
  h3.innerHTML = '<div class="rename-box">' +
    '<input type="text" value="' + esc(chat.title) + '" onkeydown="if(event.key===\\'Enter\\')this.nextElementSibling.click(); if(event.key===\\'Escape\\')this.closest(\\'h3\\').innerHTML=renderModalTitleHtml(\\'' + chatKey + '\\', CHAT_DATA[\\'' + chatKey + '\\'])" />' +
    '<button class="save" onclick="saveRenameModal(\\'' + chatKey + '\\')">ذخیره</button>' +
  '</div>';
  h3.querySelector('input').focus();
}}

function saveRenameModal(chatKey) {{
  const h3 = document.querySelector('#modalBody .modal-head h3');
  const newTitle = h3.querySelector('input').value.trim();
  const chat = CHAT_DATA[chatKey];
  fetch('/rename', {{
    method: 'POST', headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ accountLabel: chat.accountLabel, chatUrl: chat.chatUrl, customTitle: newTitle }})
  }}).then(function(r) {{ return r.json(); }}).then(function(res) {{
    chat.title = res.customTitle || res.origTitle;
    chat.origTitle = res.origTitle;
    chat.customTitle = res.customTitle;
    h3.innerHTML = renderModalTitleHtml(chatKey, chat);
    const wrap = document.getElementById('title-' + cssEsc(chatKey));
    if (wrap) wrap.innerHTML = renderTitleHtml(chatKey, chat);
  }});
}}

function openModal(chatKey) {{
  const chat = CHAT_DATA[chatKey];
  if (!chat) return;
  const overlay = document.getElementById('modalOverlay');
  const body = document.getElementById('modalBody');

  let filesHtml = '';
  if (chat.files && chat.files.length) {{
    filesHtml = '<div class="files-box"><div class="files-title">📎 فایل‌های این چت (' + chat.files.length + ')</div>' +
      chat.files.map(function(f) {{
        const srcClass = f.createdBy === 'claude' ? 'claude' : 'user';
        const srcLabel = f.createdBy === 'claude' ? 'ساخته‌ی Claude' : 'آپلود کاربر';
        return '<div class="file-item"><span class="file-name">📄 ' + esc(f.fileName) +
          ' <span class="file-src ' + srcClass + '">' + srcLabel + '</span></span>' +
          (f.downloadUrl ? '<a href="' + esc(f.downloadUrl) + '" target="_blank">دانلود ↓</a>' : '<span style="color:var(--text-dim);font-size:11px">لینک دانلود نامشخص</span>') +
          '</div>';
      }}).join('') + '</div>';
  }}

  let rowsHtml = (chat.messages || []).map(function(m, idx) {{
    const roleClass = m.role === 'human' ? 'human' : 'assistant';
    const roleLabel = m.role === 'human' ? 'کاربر' : 'Claude';
    const tok = (typeof m.tokens === 'number') ? ('~' + m.tokens.toLocaleString('fa-IR') + ' توکن') : '-';
    let fileNote = '';
    if (m.files && m.files.length) {{
      fileNote = '<div style="margin-top:6px;font-size:11.5px;color:var(--accent)">📎 ساخته/ضمیمه: ' +
        m.files.map(function(f) {{ return esc(f.fileName); }}).join('، ') + '</div>';
    }}
    const msgNotes = (chat.messageNotes && chat.messageNotes[idx]) || [];
    const msgNotesHtml = '<div class="msg-notes-list" id="msgNotesList-' + idx + '">' + renderMsgNoteItems(chatKey, idx, msgNotes) + '</div>';

    return '<tr><td class="' + roleClass + '">' + roleLabel + '</td>' +
      '<td class="msg">' + esc(m.text) + fileNote +
        '<button class="msg-note-btn" onclick="toggleMsgNoteAdd(' + idx + ')">📝 یادداشت روی این پیام</button>' +
        msgNotesHtml +
        '<div class="msg-note-add" id="msgNoteAdd-' + idx + '">' +
          '<textarea id="msgNoteText-' + idx + '" placeholder="یادداشت برای همین پیام..."></textarea>' +
          '<button onclick="addMsgNote(\\'' + chatKey + '\\',' + idx + ')">ثبت</button>' +
        '</div>' +
      '</td>' +
      '<td class="ts">' + fmtDate(m.createdAt) + '</td>' +
      '<td class="tok">' + tok + '</td></tr>';
  }}).join('');

  const notesHtml = renderModalChatNotes(chatKey);

  body.innerHTML =
    '<div class="modal-head">' +
      '<div><h3>' + renderModalTitleHtml(chatKey, chat) + '</h3>' +
      '<div class="modal-sub">اکانت: ' + esc(chat.accountLabel) + ' &nbsp;•&nbsp; ' + (chat.messages || []).length + ' پیام &nbsp;•&nbsp; آخرین بروزرسانی: ' + fmtDate(chat.lastUpdated) + '</div></div>' +
      '<button class="modal-close" onclick="closeModal()">✕</button>' +
    '</div>' +
    '<div class="modal-actions">' +
      '<a href="' + esc(chat.chatUrl) + '" target="_blank">🔗 باز کردن در Claude</a>' +
      '<button onclick="exportChatJson(\\'' + chatKey + '\\')">⬇ اکسپورت JSON این چت</button>' +
    '</div>' +
    buildChainHtml(chatKey) +
    buildLinkSelectHtml(chatKey) +
    filesHtml +
    '<table class="msg-table"><tr><th>فرستنده</th><th>متن</th><th>زمان</th><th>توکن</th></tr>' + rowsHtml + '</table>' +
    '<div class="notes-box">' +
      '<div class="notes-title">📝 یادداشت‌های کلی این چت (' + (chat.notes ? chat.notes.length : 0) + ')</div>' +
      '<div id="notesList">' + notesHtml + '</div>' +
      '<div class="note-add">' +
        '<textarea id="newNoteText" placeholder="یادداشت جدید برای کل چت..."></textarea>' +
        '<button onclick="addNote(\\'' + chatKey + '\\')">افزودن</button>' +
      '</div>' +
    '</div>';

  overlay.classList.add('open');
  overlay.setAttribute('data-current-chat', chatKey);
}}

function toggleMsgNoteAdd(idx) {{
  const el = document.getElementById('msgNoteAdd-' + idx);
  if (el) el.classList.toggle('open');
}}

function renderMsgNoteItems(chatKey, idx, notes) {{
  return (notes || []).map(function(n) {{
    return noteItemHtml(chatKey, n,
      "deleteMsgNote('" + chatKey + "'," + idx + ",'" + n.id + "')",
      "editMsgNote('" + chatKey + "'," + idx + ",'" + n.id + "', this)");
  }}).join('');
}}

function addMsgNote(chatKey, idx) {{
  const ta = document.getElementById('msgNoteText-' + idx);
  const text = ta.value.trim();
  if (!text) return;
  const chat = CHAT_DATA[chatKey];
  fetch('/note', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ accountLabel: chat.accountLabel, chatUrl: chat.chatUrl, scope: 'message', messageIndex: idx, action: 'add', text: text }})
  }}).then(function(r) {{ return r.json(); }}).then(function(res) {{
    chat.messageNotes = res.messageNotes || {{}};
    const list = document.getElementById('msgNotesList-' + idx);
    list.innerHTML = renderMsgNoteItems(chatKey, idx, chat.messageNotes[idx]);
    ta.value = '';
    document.getElementById('msgNoteAdd-' + idx).classList.remove('open');
    refreshChatRowBadge(chatKey);
  }});
}}

function deleteMsgNote(chatKey, idx, noteId) {{
  const chat = CHAT_DATA[chatKey];
  fetch('/note', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ accountLabel: chat.accountLabel, chatUrl: chat.chatUrl, scope: 'message', messageIndex: idx, action: 'delete', noteId: noteId }})
  }}).then(function(r) {{ return r.json(); }}).then(function(res) {{
    chat.messageNotes = res.messageNotes || {{}};
    const list = document.getElementById('msgNotesList-' + idx);
    list.innerHTML = renderMsgNoteItems(chatKey, idx, chat.messageNotes[idx]);
    refreshChatRowBadge(chatKey);
  }});
}}

function editMsgNote(chatKey, idx, noteId, btn) {{
  const item = btn.closest('.note-item');
  const chat = CHAT_DATA[chatKey];
  const arr = (chat.messageNotes && chat.messageNotes[idx]) || [];
  const note = arr.find(function(n) {{ return n.id === noteId; }});
  if (!note) return;
  startNoteEdit(item, note.text, function(newText) {{
    const list = document.getElementById('msgNotesList-' + idx);
    if (newText === null) {{ list.innerHTML = renderMsgNoteItems(chatKey, idx, arr); return; }}
    if (!newText) return;
    fetch('/note', {{
      method: 'POST', headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ accountLabel: chat.accountLabel, chatUrl: chat.chatUrl, scope: 'message', messageIndex: idx, action: 'edit', noteId: noteId, text: newText }})
    }}).then(function(r) {{ return r.json(); }}).then(function(res) {{
      chat.messageNotes = res.messageNotes || {{}};
      list.innerHTML = renderMsgNoteItems(chatKey, idx, chat.messageNotes[idx]);
    }});
  }});
}}

function renderModalChatNotes(chatKey) {{
  const chat = CHAT_DATA[chatKey];
  const notes = (chat && chat.notes) || [];
  if (!notes.length) return '<div class="no-notes">هنوز یادداشت کلی‌ای برای این چت نگذاشتی.</div>';
  return notes.map(function(n) {{
    return noteItemHtml(chatKey, n,
      "deleteNote('" + chatKey + "','" + n.id + "')",
      "editNote('" + chatKey + "','" + n.id + "', this)");
  }}).join('');
}}

function editNote(chatKey, noteId, btn) {{
  const item = btn.closest('.note-item');
  const chat = CHAT_DATA[chatKey];
  const note = (chat.notes || []).find(function(n) {{ return n.id === noteId; }});
  if (!note) return;
  startNoteEdit(item, note.text, function(newText) {{
    if (newText === null) {{ document.getElementById('notesList').innerHTML = renderModalChatNotes(chatKey); return; }}
    if (!newText) return;
    fetch('/note', {{
      method: 'POST', headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ accountLabel: chat.accountLabel, chatUrl: chat.chatUrl, scope: 'chat', action: 'edit', noteId: noteId, text: newText }})
    }}).then(function(r) {{ return r.json(); }}).then(function(res) {{
      chat.notes = res.notes || [];
      document.getElementById('notesList').innerHTML = renderModalChatNotes(chatKey);
      const panel = document.getElementById('notesPanel-' + cssEsc(chatKey));
      if (panel) panel.innerHTML = renderChatNotesPanel(chatKey);
    }});
  }});
}}

/* ---------- زنجیره‌ی ادامه‌ی چت‌ها (اتصال چت به چت قبلی) ---------- */
function buildChainHtml(chatKey) {{
  const chain = [];
  let cur = chatKey;
  let guard = 0;
  while (cur && CHAT_DATA[cur] && guard < 20) {{
    chain.unshift(cur);
    cur = CHAT_DATA[cur].parentKey;
    guard++;
  }}
  if (chain.length <= 1) return '';
  return '<div class="chain-box">🔗 زنجیره: ' + chain.map(function(k, i) {{
    const c = CHAT_DATA[k];
    const label = esc(c.title || k);
    if (k === chatKey) return '<b>' + label + '</b>';
    return '<a href="javascript:void(0)" onclick="openModal(\\'' + k + '\\')">' + label + '</a>';
  }}).join(' ← ') + '</div>';
}}

function buildLinkSelectHtml(chatKey) {{
  const chat = CHAT_DATA[chatKey];
  const options = ['<option value="">— بدون اتصال (چت مستقل) —</option>'];
  Object.keys(CHAT_DATA).sort().forEach(function(k) {{
    if (k === chatKey) return;
    const c = CHAT_DATA[k];
    const sel = (chat.parentKey === k) ? ' selected' : '';
    options.push('<option value="' + esc(k) + '"' + sel + '>' + esc(c.accountLabel) + ' — ' + esc(c.title || k) + '</option>');
  }});
  return '<div class="link-select-row">' +
    '<label>⛓ این چت ادامه‌ی کدوم چته؟</label>' +
    '<select onchange="linkChat(\\'' + chatKey + '\\', this.value)">' + options.join('') + '</select>' +
  '</div>';
}}

function linkChat(chatKey, parentKey) {{
  const chat = CHAT_DATA[chatKey];
  fetch('/link', {{
    method: 'POST', headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ accountLabel: chat.accountLabel, chatUrl: chat.chatUrl, parentKey: parentKey || null }})
  }}).then(function(r) {{ return r.json(); }}).then(function(res) {{
    chat.parentKey = res.parentKey || null;
    const card = document.querySelector('.chat-card[data-chat-key="' + chatKey + '"]');
    if (card) {{
      const existing = card.querySelector('.link-badge');
      if (existing) existing.remove();
      if (chat.parentKey && CHAT_DATA[chat.parentKey]) {{
        const badge = document.createElement('span');
        badge.className = 'link-badge';
        badge.textContent = '⛓ ادامه از: ' + (CHAT_DATA[chat.parentKey].title || chat.parentKey);
        badge.onclick = function(ev) {{ ev.stopPropagation(); openModal(chat.parentKey); }};
        card.querySelector('.chat-row').insertBefore(badge, card.querySelector('.open-btn'));
      }}
    }}
    renderGraphWidget();
  }});
}}

function closeModal() {{
  document.getElementById('modalOverlay').classList.remove('open');
}}
document.addEventListener('keydown', function(e) {{ if (e.key === 'Escape') closeModal(); }});

function addNote(chatKey) {{
  const ta = document.getElementById('newNoteText');
  const text = ta.value.trim();
  if (!text) return;
  const chat = CHAT_DATA[chatKey];
  fetch('/note', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ accountLabel: chat.accountLabel, chatUrl: chat.chatUrl, scope: 'chat', action: 'add', text: text }})
  }}).then(function(r) {{ return r.json(); }}).then(function(res) {{
    chat.notes = res.notes || [];
    ta.value = '';
    document.getElementById('notesList').innerHTML = renderModalChatNotes(chatKey);
    refreshChatRowBadge(chatKey);
  }});
}}

function deleteNote(chatKey, noteId) {{
  const chat = CHAT_DATA[chatKey];
  fetch('/note', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ accountLabel: chat.accountLabel, chatUrl: chat.chatUrl, scope: 'chat', action: 'delete', noteId: noteId }})
  }}).then(function(r) {{ return r.json(); }}).then(function(res) {{
    chat.notes = res.notes || [];
    document.getElementById('notesList').innerHTML = renderModalChatNotes(chatKey);
    refreshChatRowBadge(chatKey);
  }});
}}

function exportChatJson(chatKey) {{
  const chat = CHAT_DATA[chatKey];
  const blob = new Blob([JSON.stringify(chat, null, 2)], {{ type: 'application/json' }});
  downloadBlob(blob, (chat.title || 'chat').replace(/[^a-zA-Z0-9\\u0600-\\u06FF _-]/g, '_') + '.json');
}}

function downloadChatBtn(chatKey, ev) {{
  if (ev) ev.stopPropagation();
  exportChatJson(chatKey);
}}

/* ---------- مودال «همه‌ی یادداشت‌ها» (دسترسی سریع به یادداشت‌های همه‌ی چت‌ها) ---------- */
function openAllNotesModal() {{
  const overlay = document.getElementById('modalOverlay');
  const body = document.getElementById('modalBody');

  const rows = [];
  Object.keys(CHAT_DATA).forEach(function(key) {{
    const chat = CHAT_DATA[key];
    (chat.notes || []).forEach(function(n) {{
      rows.push({{ key: key, chat: chat, note: n, scope: 'chat', idx: null }});
    }});
    Object.keys(chat.messageNotes || {{}}).forEach(function(idx) {{
      (chat.messageNotes[idx] || []).forEach(function(n) {{
        rows.push({{ key: key, chat: chat, note: n, scope: 'message', idx: idx }});
      }});
    }});
  }});
  rows.sort(function(a, b) {{ return (b.note.createdAt || '').localeCompare(a.note.createdAt || ''); }});

  const listHtml = rows.length ? rows.map(function(r, i) {{
    const delFn = r.scope === 'chat'
      ? "deleteNote('" + r.key + "','" + r.note.id + "')"
      : "deleteMsgNote('" + r.key + "'," + r.idx + ",'" + r.note.id + "')";
    return '<div class="note-item" id="allNote-' + i + '">' +
      '<div style="flex:1">' +
        '<div style="font-size:11px;color:var(--text-dim);margin-bottom:4px">' +
          esc(r.chat.accountLabel) + ' — <a href="javascript:void(0)" onclick="closeModal();setTimeout(function(){{openModal(\\'' + r.key + '\\')}},50)">' + esc(r.chat.title || r.key) + '</a>' +
        '</div>' +
        '<div class="note-text">' + esc(r.note.text) + '</div>' +
        '<div class="note-meta">' + fmtDate(r.note.createdAt) + '</div>' +
      '</div>' +
      '<div class="note-actions"><button class="note-del" onclick="' + delFn + ';openAllNotesModal();">حذف</button></div>' +
    '</div>';
  }}).join('') : '<div class="no-notes">هنوز هیچ یادداشتی ثبت نشده.</div>';

  body.innerHTML =
    '<div class="modal-head">' +
      '<div><h3>🗒 همه‌ی یادداشت‌ها</h3><div class="modal-sub">' + rows.length + ' یادداشت، از همه‌ی چت‌ها و اکانت‌ها</div></div>' +
      '<button class="modal-close" onclick="closeModal()">✕</button>' +
    '</div>' +
    '<div>' + listHtml + '</div>';

  overlay.classList.add('open');
}}

function downloadBlob(blob, filename) {{
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}}

function truncateLabel(s, n) {{
  s = s || '';
  return s.length > n ? s.slice(0, n) + '…' : s;
}}

function renderGraphWidget() {{
  const showArchived = document.getElementById('graphShowArchived') && document.getElementById('graphShowArchived').checked;
  const children = {{}};
  // این گراف اصلاً لازم نیست یک درخت یکپارچه باشه؛ هر زنجیره‌ی جدا (مؤلفه‌ی ناهم‌بند) جدا کنار بقیه رسم می‌شه
  const keys = Object.keys(CHAT_DATA).filter(function(k) {{
    return showArchived || !CHAT_DATA[k].archived;
  }});
  const keySet = {{}}; keys.forEach(function(k) {{ keySet[k] = true; }});
  keys.forEach(function(k) {{
    const p = CHAT_DATA[k].parentKey;
    if (p && keySet[p]) {{
      (children[p] = children[p] || []).push(k);
    }}
  }});
  const roots = keys.filter(function(k) {{
    const p = CHAT_DATA[k].parentKey;
    return (!p || !keySet[p]) && (children[k] || []).length > 0;
  }});

  document.getElementById('graphChainCount').textContent = roots.length;
  const wrap = document.getElementById('graphSvgWrap');

  if (!roots.length) {{
    wrap.innerHTML = '<div class="no-chains">هنوز هیچ چتی به چت دیگه‌ای وصل نشده. از داخل جزئیات هر چت می‌تونی «ادامه‌ی کدوم چته» رو انتخاب کنی.</div>';
    return;
  }}

  const expanded = document.getElementById('graphWidget').classList.contains('expanded');
  const XGAP = expanded ? 78 : 42, YGAP = expanded ? 64 : 38, R = expanded ? 11 : 7, PAD = expanded ? 24 : 16;
  const positions = {{}};
  let xCounter = 0;

  function layout(key, depth) {{
    const kids = children[key] || [];
    if (!kids.length) {{
      positions[key] = {{ x: xCounter * XGAP, y: depth * YGAP }};
      xCounter++;
    }} else {{
      kids.forEach(function(c) {{ layout(c, depth + 1); }});
      const xs = kids.map(function(c) {{ return positions[c].x; }});
      positions[key] = {{ x: (Math.min.apply(null, xs) + Math.max.apply(null, xs)) / 2, y: depth * YGAP }};
    }}
  }}
  roots.forEach(function(r) {{ layout(r, 0); xCounter++; }});

  let maxX = 0, maxY = 0;
  Object.values(positions).forEach(function(p) {{ maxX = Math.max(maxX, p.x); maxY = Math.max(maxY, p.y); }});
  const w = maxX + PAD * 2, h = maxY + PAD * 2 + 14;

  const edges = [];
  const nodes = [];
  function walk(key) {{
    const pos = positions[key];
    const cx = pos.x + PAD, cy = pos.y + PAD;
    (children[key] || []).forEach(function(c) {{
      const cpos = positions[c];
      edges.push('<line class="gedge" x1="' + cx + '" y1="' + cy + '" x2="' + (cpos.x + PAD) + '" y2="' + (cpos.y + PAD) + '"></line>');
      walk(c);
    }});
    const chat = CHAT_DATA[key];
    const label = esc(truncateLabel(chat.title, expanded ? 18 : 12) + (chat.archived ? ' 🗄' : ''));
    nodes.push(
      '<g class="gnode' + (chat.archived ? ' gnode-archived' : '') + '" onclick="closeModal();setTimeout(function(){{openModal(\\'' + key + '\\')}},50)">' +
        '<title>' + esc(chat.title) + '</title>' +
        '<circle cx="' + cx + '" cy="' + cy + '" r="' + R + '"></circle>' +
        '<text x="' + cx + '" y="' + (cy + R + 10) + '" text-anchor="middle">' + label + '</text>' +
      '</g>'
    );
  }}
  roots.forEach(walk);

  wrap.innerHTML = '<svg viewBox="0 0 ' + w + ' ' + h + '" width="' + w + '" height="' + h + '">' + edges.join('') + nodes.join('') + '</svg>';
}}
</script>
</body>
</html>
"""


def render_meter(title, pct, resets_at_iso, emoji):
    cls = pct_class(pct)
    pct_txt = f"{pct:.0f}%" if pct is not None else "—"
    width = max(0, min(100, pct)) if pct is not None else 0
    resets_ms = to_epoch_ms(resets_at_iso)
    resets_ms_attr = str(resets_ms) if resets_ms is not None else "null"
    resets_readable = fmt_dt_fa(resets_at_iso)
    return f"""
    <div class="meter">
      <div class="meter-head">
        <span>{emoji} {title}</span>
        <span class="pct {cls}">{pct_txt}</span>
      </div>
      <div class="bar-track"><div class="bar-fill {cls}" style="width:{width}%"></div></div>
      <div class="meter-foot">
        <span>ریست: {resets_readable}</span>
        <span class="countdown" data-resets-at="{resets_ms_attr}">…</span>
      </div>
    </div>
    """


def render_overview_card(label, info):
    usage = info.get("usage") or {}
    session_pct = fmt_pct(usage, "sessionUtilization")
    weekly_pct = fmt_pct(usage, "weeklyUtilization")

    meters = render_meter("سشن ۵ ساعته", session_pct, usage.get("sessionResetsAt"), "⏱")
    meters += render_meter("سقف هفتگی", weekly_pct, usage.get("weeklyResetsAt"), "📅")

    free_html = ""
    if usage.get("freePlanLimitReached") is not None:
        if usage.get("freePlanLimitReached"):
            free_html = (
                f"<div class='free-status reached'>🚫 پلن رایگان: به سقف مصرف رسیده — "
                f"ریست: {esc(usage.get('freePlanResetText') or '-')}</div>"
            )
        else:
            free_html = "<div class='free-status free'>✅ پلن رایگان: آزاد، محدودیتی نیست</div>"

    total_tokens = count_account_tokens(info)
    chat_count = len(info.get("chats") or {})
    tokens_txt = f"{int(total_tokens):,}".replace(",", "٬")

    return f"""
    <div class="overview-card">
      <h2>👤 {esc(label)}</h2>
      {meters}
      {free_html}
      <div class="stat-row">
        <span>💬 چت‌ها: <b>{chat_count}</b></span>
        <span>🔢 توکن تخمینی مصرفی: <b>{tokens_txt}</b></span>
      </div>
    </div>
    """


def make_chat_key(label, chat_url):
    return f"{label}::{chat_url}"


def render_chat_row(label, chat_url, chat, chat_titles):
    msgs = chat.get("messages", []) or []
    chat_tokens = int(count_chat_tokens(chat))
    files = collect_chat_files(chat)
    notes_count = total_notes_count(chat)

    search_parts = [chat.get("title") or "", chat.get("customTitle") or "", label]
    for m in msgs:
        search_parts.append(m.get("text") or "")
    for n in (chat.get("notes") or []):
        search_parts.append(n.get("text") or "")
    for arr in (chat.get("messageNotes") or {}).values():
        for n in (arr or []):
            search_parts.append(n.get("text") or "")
    search_text = esc(" ".join(search_parts).lower())

    key = make_chat_key(label, chat_url)
    key_attr = esc(key)
    key_js = key.replace("\\", "\\\\").replace("'", "\\'")
    key_css = "".join(c if (c.isalnum() or c in "_-") else "_" for c in key)

    note_badge = f"<button class='chat-note-badge' onclick=\"toggleChatNotes('{key_js}', event)\">📝 {notes_count} یادداشت</button>"
    file_badge = f"<span class='file-badge'>📎 {len(files)} فایل</span>" if files else ""
    download_btn = f"<button class='download-btn' onclick=\"downloadChatBtn('{key_js}', event)\">⬇ دانلود</button>"

    is_starred = bool(chat.get("starred"))
    is_archived = bool(chat.get("archived"))
    star_btn = (
        f"<button class='star-btn{' starred' if is_starred else ''}' id='star-{key_css}' "
        f"onclick=\"toggleStar('{key_js}', event)\" title=\"نشان‌کردن چت\">⭐</button>"
    )
    archive_check = (
        f"<label class='archive-check-wrap' onclick=\"event.stopPropagation()\">"
        f"<input type='checkbox' {'checked' if is_archived else ''} onchange=\"toggleArchive('{key_js}', this.checked)\" /> آرشیو"
        f"</label>"
    )

    link_badge = ""
    parent_key = chat.get("parentKey")
    if parent_key and parent_key in chat_titles:
        parent_title = chat_titles.get(parent_key) or parent_key
        parent_key_js = parent_key.replace("\\", "\\\\").replace("'", "\\'")
        link_badge = (
            f"<span class='link-badge' onclick=\"event.stopPropagation();openModal('{parent_key_js}')\">"
            f"⛓ ادامه از: {esc(parent_title)}</span>"
        )

    tokens_txt = f"{chat_tokens:,}".replace(",", "٬")

    title = display_title(chat, chat_url)
    orig_title = chat.get("title") or chat_url
    orig_html = f"<span class='orig-title'>(اسم کلاد: {esc(orig_title)})</span>" if chat.get("customTitle") else ""

    card_classes = "chat-card"
    if is_starred:
        card_classes += " is-starred"
    if is_archived:
        card_classes += " archived-card"

    return f"""
    <div class="{card_classes}" data-chat-key="{key_attr}" data-searchtext="{search_text}" data-archived="{'1' if is_archived else '0'}" data-starred="{'1' if is_starred else '0'}">
      <div class="chat-row" onclick="openModal('{key_js}')">
        {star_btn}
        <div class="chat-main">
          <div class="chat-title" id="title-{key_css}">
            <span class="title-text">{esc(title)}</span>
            {orig_html}
            <button class="rename-btn" onclick="startRenameRow('{key_js}', event)">✏️</button>
          </div>
          <div class="chat-meta">
            <span>👤 {esc(label)}</span>
            <span>💬 {len(msgs)} پیام</span>
            <span>🔢 ~{tokens_txt}</span>
            <span>🕒 {fmt_dt_fa(chat.get('lastUpdated'))}</span>
          </div>
        </div>
        {note_badge}
        {file_badge}
        {link_badge}
        {archive_check}
        {download_btn}
        <span class="open-btn">جزئیات کامل ›</span>
      </div>
      <div class="chat-notes-panel" id="notesPanel-{key_css}" data-chat-key="{key_attr}"></div>
    </div>
    """


def build_chat_data_json(db):
    """داده‌ی کامل هر چت برای استفاده‌ی JS سمت کلاینت (مودال، اکسپورت)."""
    data = {}
    for label, info in db.items():
        for chat_url, chat in (info.get("chats") or {}).items():
            key = make_chat_key(label, chat_url)
            message_notes = chat.get("messageNotes") or {}
            data[key] = {
                "accountLabel": label,
                "chatUrl": chat_url,
                "title": display_title(chat, chat_url),
                "origTitle": chat.get("title") or chat_url,
                "lastUpdated": chat.get("lastUpdated"),
                "messages": chat.get("messages", []) or [],
                "files": collect_chat_files(chat),
                "notes": chat.get("notes", []) or [],
                "messageNotes": message_notes,
                "parentKey": chat.get("parentKey"),
                "archived": bool(chat.get("archived")),
                "starred": bool(chat.get("starred")),
            }
    return data


def render_dashboard(db):
    items = sorted(db.items())
    overview_html = "".join(render_overview_card(label, info) for label, info in items)

    chat_titles = {}
    for label, info in items:
        for chat_url, chat in (info.get("chats") or {}).items():
            chat_titles[make_chat_key(label, chat_url)] = display_title(chat, chat_url)

    active_rows = []
    archived_rows = []
    total_chats = 0
    archived_count = 0
    for label, info in items:
        chats = info.get("chats") or {}
        for chat_url, chat in chats.items():
            total_chats += 1
            row_html = render_chat_row(label, chat_url, chat, chat_titles)
            entry = (chat.get("lastUpdated", ""), bool(chat.get("starred")), row_html)
            if chat.get("archived"):
                archived_count += 1
                archived_rows.append(entry)
            else:
                active_rows.append(entry)

    # اول بر اساس تاریخ (جدید بالا)، بعد ستاره‌دارها رو بالای لیست خودشون می‌بریم (ترتیب پایدار پایتون حفظ می‌شه)
    active_rows.sort(key=lambda t: t[0], reverse=True)
    active_rows.sort(key=lambda t: t[1], reverse=True)
    archived_rows.sort(key=lambda t: t[0], reverse=True)
    archived_rows.sort(key=lambda t: t[1], reverse=True)

    total_chats -= archived_count
    chatlist_html = "".join(r[2] for r in active_rows) or "<div class='empty'>هنوز چتی ثبت نشده</div>"
    archived_chatlist_html = "".join(r[2] for r in archived_rows) or "<div class='empty'>آرشیو خالیه</div>"

    # مهم: متن پیام‌ها/یادداشت‌ها ممکنه به‌صورت کاملاً معمولی رشته‌ی "</script>" رو توی خودش داشته باشه
    # (مثلاً وقتی موضوع چت درباره‌ی کد HTML/JS باشه). اگه این رشته بدون تغییر وسط تگ <script> این صفحه
    # قرار بگیره، مرورگر تگ اسکریپت رو همون‌جا "می‌بنده"، بقیه‌ی جیسون به‌صورت متن خام روی صفحه ریخته
    # می‌شه و همه‌ی دکمه‌ها از کار می‌افتن (چون کد جاوااسکریپت بعدش اصلاً اجرا نمی‌شه).
    # با جایگزینی "</" با "<\/" (که توی JSON کاملاً معتبره) از این مشکل جلوگیری می‌کنیم.
    chat_data_json = json.dumps(build_chat_data_json(db), ensure_ascii=False).replace("</", "<\\/")

    return PAGE.format(
        count=len(db),
        chat_count=total_chats,
        archived_count=archived_count,
        overview_html=overview_html or "<div class='empty'>هنوز داده‌ای نیامده</div>",
        chatlist_html=chatlist_html,
        archived_chatlist_html=archived_chatlist_html,
        chat_data_json=chat_data_json,
    )


class Handler(http.server.BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return None

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/report":
            payload = self._read_json()
            if payload is None:
                self._send_json({"error": "bad json"}, 400)
                return

            label = payload.get("accountLabel", "بدون‌نام")
            now = payload.get("checkedAt") or datetime.now(timezone.utc).isoformat()

            db = load_db()
            account = db.setdefault(label, {"usage": None, "usageDebug": None, "chats": {}})

            if payload.get("usage"):
                account["usage"] = payload["usage"]
            if payload.get("usageDebug"):
                account["usageDebug"] = payload["usageDebug"]

            chat_url = payload.get("chatUrl")
            if chat_url and payload.get("messages") is not None:
                existing = account["chats"].get(chat_url, {})
                account["chats"][chat_url] = {
                    "title": payload.get("chatTitle"),
                    "messages": payload["messages"],
                    "lastUpdated": now,
                    "notes": existing.get("notes", []),  # یادداشت‌های کلیِ قبلی حفظ میشن
                    "messageNotes": existing.get("messageNotes", {}),  # یادداشت‌های تک‌پیامیِ قبلی حفظ میشن
                    "parentKey": existing.get("parentKey"),  # اتصال به چت قبلی هم حفظ میشه
                    "customTitle": existing.get("customTitle"),  # اسمی که خودت گذاشتی هم حفظ میشه
                    "archived": existing.get("archived", False),  # وضعیت آرشیو هم حفظ میشه
                    "starred": existing.get("starred", False),  # وضعیت ستاره هم حفظ میشه
                }

            save_db(db)
            self._send_json({"ok": True})
            return

        if path == "/rename":
            payload = self._read_json()
            if payload is None:
                self._send_json({"error": "bad json"}, 400)
                return
            label = payload.get("accountLabel")
            chat_url = payload.get("chatUrl")
            custom_title = (payload.get("customTitle") or "").strip()

            db = load_db()
            account = db.get(label)
            if not account or chat_url not in account.get("chats", {}):
                self._send_json({"error": "chat not found"}, 404)
                return

            chat = account["chats"][chat_url]
            chat["customTitle"] = custom_title or None
            save_db(db)
            self._send_json({"ok": True, "customTitle": chat["customTitle"], "origTitle": chat.get("title") or chat_url})
            return

        if path == "/link":
            payload = self._read_json()
            if payload is None:
                self._send_json({"error": "bad json"}, 400)
                return
            label = payload.get("accountLabel")
            chat_url = payload.get("chatUrl")
            parent_key = payload.get("parentKey")

            db = load_db()
            account = db.get(label)
            if not account or chat_url not in account.get("chats", {}):
                self._send_json({"error": "chat not found"}, 404)
                return

            chat = account["chats"][chat_url]
            my_key = make_chat_key(label, chat_url)

            if parent_key:
                # از حلقه شدن زنجیره جلوگیری کن (چت نباید خودش یا نوه‌ی خودش رو والد خودش بکنه)
                seen = set()
                cur = parent_key
                loops = False
                while cur:
                    if cur == my_key:
                        loops = True
                        break
                    if cur in seen:
                        break
                    seen.add(cur)
                    p_label, _, p_url = cur.partition("::")
                    p_account = db.get(p_label)
                    p_chat = (p_account or {}).get("chats", {}).get(p_url)
                    cur = p_chat.get("parentKey") if p_chat else None
                if loops:
                    self._send_json({"error": "loop"}, 400)
                    return
                chat["parentKey"] = parent_key
            else:
                chat["parentKey"] = None

            save_db(db)
            self._send_json({"ok": True, "parentKey": chat.get("parentKey")})
            return

        if path == "/archive":
            payload = self._read_json()
            if payload is None:
                self._send_json({"error": "bad json"}, 400)
                return
            label = payload.get("accountLabel")
            chat_url = payload.get("chatUrl")

            db = load_db()
            account = db.get(label)
            if not account or chat_url not in account.get("chats", {}):
                self._send_json({"error": "chat not found"}, 404)
                return

            chat = account["chats"][chat_url]
            chat["archived"] = bool(payload.get("archived"))
            save_db(db)
            self._send_json({"ok": True, "archived": chat["archived"]})
            return

        if path == "/star":
            payload = self._read_json()
            if payload is None:
                self._send_json({"error": "bad json"}, 400)
                return
            label = payload.get("accountLabel")
            chat_url = payload.get("chatUrl")

            db = load_db()
            account = db.get(label)
            if not account or chat_url not in account.get("chats", {}):
                self._send_json({"error": "chat not found"}, 404)
                return

            chat = account["chats"][chat_url]
            chat["starred"] = bool(payload.get("starred"))
            save_db(db)
            self._send_json({"ok": True, "starred": chat["starred"]})
            return

        if path == "/note":
            payload = self._read_json()
            if payload is None:
                self._send_json({"error": "bad json"}, 400)
                return
            label = payload.get("accountLabel")
            chat_url = payload.get("chatUrl")
            action = payload.get("action", "add")
            scope = payload.get("scope", "chat")  # 'chat' یا 'message'

            db = load_db()
            account = db.get(label)
            if not account or chat_url not in account.get("chats", {}):
                self._send_json({"error": "chat not found"}, 404)
                return

            chat = account["chats"][chat_url]

            if scope == "message":
                msg_idx = str(payload.get("messageIndex"))
                message_notes = chat.setdefault("messageNotes", {})
                notes_list = message_notes.setdefault(msg_idx, [])
                if action == "add":
                    text = (payload.get("text") or "").strip()
                    if text:
                        notes_list.append({
                            "id": uuidlib.uuid4().hex[:10],
                            "text": text,
                            "createdAt": datetime.now(timezone.utc).isoformat(),
                        })
                elif action == "edit":
                    note_id = payload.get("noteId")
                    text = (payload.get("text") or "").strip()
                    for n in notes_list:
                        if n.get("id") == note_id and text:
                            n["text"] = text
                            n["editedAt"] = datetime.now(timezone.utc).isoformat()
                elif action == "delete":
                    note_id = payload.get("noteId")
                    message_notes[msg_idx] = [n for n in notes_list if n.get("id") != note_id]
                    if not message_notes[msg_idx]:
                        del message_notes[msg_idx]
                save_db(db)
                self._send_json({"ok": True, "messageNotes": chat.get("messageNotes", {})})
                return
            else:
                notes = chat.setdefault("notes", [])
                if action == "add":
                    text = (payload.get("text") or "").strip()
                    if text:
                        notes.append({
                            "id": uuidlib.uuid4().hex[:10],
                            "text": text,
                            "createdAt": datetime.now(timezone.utc).isoformat(),
                        })
                elif action == "edit":
                    note_id = payload.get("noteId")
                    text = (payload.get("text") or "").strip()
                    for n in notes:
                        if n.get("id") == note_id and text:
                            n["text"] = text
                            n["editedAt"] = datetime.now(timezone.utc).isoformat()
                elif action == "delete":
                    note_id = payload.get("noteId")
                    chat["notes"] = [n for n in notes if n.get("id") != note_id]
                save_db(db)
                self._send_json({"ok": True, "notes": chat["notes"]})
                return

        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        if self.path in ("/", "/dashboard"):
            db = load_db()
            body = render_dashboard(db).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self._cors()
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/export/all":
            db = load_db()
            body = json.dumps(db, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", "attachment; filename=claude-monitor-export.json")
            self._cors()
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/export/files":
            db = load_db()
            all_files = []
            for label, info in db.items():
                for chat_url, chat in (info.get("chats") or {}).items():
                    for f in collect_chat_files(chat):
                        all_files.append({
                            "accountLabel": label,
                            "chatTitle": chat.get("title") or chat_url,
                            "chatUrl": chat_url,
                            **f,
                        })
            body = json.dumps(all_files, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", "attachment; filename=claude-monitor-all-files.json")
            self._cors()
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    with socketserver.TCPServer(("localhost", PORT), Handler) as httpd:
        print(f"سرور روشن شد: http://localhost:{PORT}")
        httpd.serve_forever()
