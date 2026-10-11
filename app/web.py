"""
The simple web edit page.

WhatsApp bot -> sends a link -> /edit/<token> -> user checks the text, fixes
mistakes, optionally auto-corrects spelling/grammar -> taps "Send to my
WhatsApp" -> the finished file arrives in the chat.

No template library: the page is one HTML string with a little JavaScript.
"""

import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.background import BackgroundTask

from app.config import OUTPUT_DIR, DOWNLOAD_DIR, public_base_url
from app.db.models import SessionLocal, EditJob
from app.generators.convert import convert, FORMAT_MAP
from app.messaging import deliver
from app.utils.autocorrect import autocorrect_grid
from app.utils.formats import FORMAT_LABEL
from app.utils.grid import grid_to_structured, normalize_grid

router = APIRouter()

WARN_BELOW = 0.75   # cells the reader was less sure about than this are highlighted

FORMAT_OPTIONS = [("excel", "Excel (.xlsx)"), ("word", "Word (.docx)"),
                  ("pdf", "PDF"), ("csv", "CSV"), ("txt", "Text (.txt)")]

PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SnapDocc</title>
<style>
  :root { --ink:#1f2937; --muted:#6b7280; --line:#e5e7eb; --brand:#0f766e; --bg:#f3f4f6; }
  * { box-sizing: border-box; }
  [hidden] { display:none !important; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  main { max-width:760px; margin:0 auto; padding:20px 14px 40px; }
  .card { background:#fff; border-radius:16px; padding:20px; box-shadow:0 2px 12px rgba(0,0,0,.06); }
  h1 { margin:0; font-size:22px; } h1 span { color:var(--brand); }
  .sub { margin:4px 0 12px; color:var(--muted); font-size:14px; }
  .badge { margin:0 0 12px; font-size:13px; padding:8px 12px; border-radius:10px;
           background:#f0fdfa; color:#115e59; }
  .badge.warn { background:#fef9c3; color:#854d0e; }
  details { margin:0 0 14px; }
  summary { cursor:pointer; color:var(--brand); font-size:14px; font-weight:600; }
  details img { display:block; max-width:100%; max-height:360px; margin-top:10px;
                border:1px solid var(--line); border-radius:10px; }
  .scroll { overflow-x:auto; border:1px solid var(--line); border-radius:10px; }
  table { border-collapse:collapse; width:100%; min-width:360px; }
  th, td { padding:0; border-bottom:1px solid var(--line); }
  th { background:#f0fdfa; }
  input[type=text] { width:100%; min-width:90px; border:0; padding:10px; font-size:16px;
                     background:transparent; color:inherit; font-family:inherit; }
  th input { font-weight:600; }
  input[type=text].warn { background:#fef9c3; }
  input[type=text]:focus { outline:2px solid var(--brand); outline-offset:-2px; background:#fff; }
  .x { border:0; background:none; color:#9ca3af; font-size:20px; padding:6px 10px; cursor:pointer; }
  .x:hover { color:#dc2626; }
  button { font:inherit; cursor:pointer; }
  button:disabled { opacity:.6; cursor:default; }
  .btn { border:1px solid var(--line); background:#fff; padding:10px 14px; border-radius:10px; font-size:15px; }
  .btn:hover { background:#f9fafb; }
  .primary { background:var(--brand); color:#fff; border:0; padding:12px 22px; border-radius:10px;
             font-size:16px; font-weight:600; }
  .primary:hover:not(:disabled) { background:#115e59; }
  .row { display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin:14px 0; }
  select { font:inherit; font-size:16px; padding:10px; border:1px solid var(--line); border-radius:10px; background:#fff; }
  #msg { font-size:14px; color:var(--brand); }
  .end { display:flex; flex-wrap:wrap; gap:10px; align-items:center; justify-content:space-between;
         margin-top:18px; padding-top:16px; border-top:1px solid var(--line); }
  #status { margin-top:14px; padding:12px 14px; border-radius:10px; font-size:15px; }
  #status.ok { background:#dcfce7; color:#166534; }
  #status.err { background:#fee2e2; color:#991b1b; }
</style></head>
<body><main><div class="card">
  <h1>Snap<span>Docc</span></h1>
  <p class="sub">Check what was read from your photo, fix anything, then send it to your WhatsApp.</p>
  <p class="badge __BADGE_CLASS__">__BADGE__</p>
  <details id="photo" hidden>
    <summary>&#128247; Show my photo</summary>
    <img src="/edit/__TOKEN__/photo" alt="Your photo" onerror="document.getElementById('photo').hidden = true">
  </details>
  <div class="row">
    <button class="btn" type="button" id="fix">&#10024; Auto-correct spelling &amp; grammar</button>
    <span id="msg"></span>
  </div>
  <div class="scroll"><table id="t"><thead></thead><tbody></tbody></table></div>
  <div class="row"><button class="btn" type="button" id="add">+ Add row</button></div>
  <div class="end">
    <label>Format&nbsp; <select id="fmt">__OPTIONS__</select></label>
    <button class="primary" type="button" id="send">Send to my WhatsApp</button>
  </div>
  <div id="status" hidden></div>
  <div class="row" id="fallback" hidden>
    <form method="post" action="/edit/__TOKEN__/download" id="dl">
      <input type="hidden" name="payload" id="dlPayload"><input type="hidden" name="fmt" id="dlFmt">
      <button class="btn" type="submit">Download the file instead</button>
    </form>
  </div>
</div></main>
<script>
const TOKEN = "__TOKEN__";
let grid = __GRID__;
const t = document.getElementById("t");
const $ = id => document.getElementById(id);

function box(value, warn) {
  const i = document.createElement("input");
  i.type = "text"; i.value = value;
  if (warn) i.classList.add("warn");
  i.addEventListener("input", () => i.classList.remove("warn"));   // you touched it: no longer doubtful
  return i;
}

function render() {
  const hr = t.tHead; hr.innerHTML = "";
  const tr = hr.insertRow();
  grid.headers.forEach(h => { const th = document.createElement("th"); th.appendChild(box(h, false)); tr.appendChild(th); });
  tr.appendChild(document.createElement("th"));
  t.tBodies[0].innerHTML = "";
  grid.rows.forEach((row, ri) => addRow(row, (grid.flags || [])[ri] || []));
}

function addRow(values, flags) {
  const tr = t.tBodies[0].insertRow();
  values.forEach((v, ci) => tr.insertCell().appendChild(box(v, flags && flags[ci])));
  const b = document.createElement("button");
  b.type = "button"; b.className = "x"; b.title = "Remove row"; b.textContent = "\\u00d7";
  b.onclick = () => tr.remove();
  tr.insertCell().appendChild(b);
}

function read() {
  return {
    headers: [...t.tHead.rows[0].querySelectorAll("input")].map(i => i.value),
    rows: [...t.tBodies[0].rows].map(r => [...r.querySelectorAll("input")].map(i => i.value)),
  };
}

function readFlags() {
  return [...t.tBodies[0].rows].map(r => [...r.querySelectorAll("input")].map(i => i.classList.contains("warn")));
}

function show(kind, text) {
  const s = $("status"); s.hidden = !text; s.className = kind; s.textContent = text;
}

$("add").onclick = () => addRow(grid.headers.map(() => ""), []);

$("fix").onclick = async () => {
  $("msg").textContent = "Fixing...";
  const flags = readFlags();
  try {
    const r = await fetch("/edit/" + TOKEN + "/autocorrect", {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(read()),
    });
    if (!r.ok) throw new Error();
    const d = await r.json();
    grid = {headers: d.headers, rows: d.rows, flags: d.rows.length === flags.length ? flags : []};
    render();
    $("msg").textContent = d.method === "groq" ? "Fixed with AI" : "Fixed with spell-checker";
  } catch (e) { $("msg").textContent = "Couldn't auto-correct, try again."; }
};

$("send").onclick = async () => {
  const btn = $("send");
  btn.disabled = true; btn.textContent = "Sending..."; show("", "");
  const fd = new FormData();
  fd.append("payload", JSON.stringify(read())); fd.append("fmt", $("fmt").value);
  try {
    const r = await fetch("/edit/" + TOKEN + "/send", {method: "POST", body: fd});
    const d = await r.json().catch(() => ({}));
    if (r.ok && d.ok) {
      show("ok", d.queued
        ? "\\u2705 File ready! Open WhatsApp and reply \\"ok\\" - it arrives right away."
        : "\\u2705 Sent! Open WhatsApp - your file is in the chat.");
    } else {
      show("err", "Couldn't send to WhatsApp: " + (d.error || "something went wrong") + ".");
      $("fallback").hidden = false;
    }
  } catch (e) {
    show("err", "Couldn't reach the server. Check your internet and try again.");
    $("fallback").hidden = false;
  }
  btn.disabled = false; btn.textContent = "Send to my WhatsApp";
};

$("dl").onsubmit = () => { $("dlPayload").value = JSON.stringify(read()); $("dlFmt").value = $("fmt").value; };

if (__HAS_PHOTO__) $("photo").hidden = false;
render();
</script></body></html>"""

NOT_FOUND = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<body style="font-family:system-ui,sans-serif;text-align:center;padding:60px 20px;color:#1f2937">
<h2>This link has expired or doesn't exist</h2>
<p>Send your photo to the SnapDocc WhatsApp number again to get a fresh link.</p></body>"""


def _load_job(token):
    """Return (job, grid) or (None, None) if the link is unknown/expired."""
    db = SessionLocal()
    try:
        job = db.query(EditJob).filter_by(token=token).first()
        if job is None or job.is_expired():
            return None, None
        return job, json.loads(job.grid_json)
    finally:
        db.close()


def _parse_payload(payload):
    """Validate the table sent by the page. Returns a grid, or None if it is bad."""
    try:
        data = json.loads(payload)
        return normalize_grid(data.get("headers"), data.get("rows"))
    except Exception:
        return None


@router.get("/edit/{token}", response_class=HTMLResponse)
def edit_page(token: str):
    job, grid = _load_job(token)
    if job is None:
        return HTMLResponse(NOT_FOUND, status_code=404)

    confs = grid.get("confs")
    flags = [[c < WARN_BELOW for c in row] for row in confs] if confs else []
    has_flags = any(any(row) for row in flags)

    if job.engine == "groq-qwen":
        badge, badge_class = "Read by AI (Qwen). Please still check the numbers.", ""
    else:
        badge, badge_class = "Read by basic OCR, which makes more mistakes. Please check carefully.", "warn"
    if has_flags:
        badge += " Yellow cells are ones the reader wasn't sure about."

    options = "".join(
        f'<option value="{value}"{" selected" if value == job.fmt else ""}>{label}</option>'
        for value, label in FORMAT_OPTIONS)
    page_grid = {"headers": grid["headers"], "rows": grid["rows"], "flags": flags}
    # "<" is escaped so text like "</script>" in a cell can never break out of the script tag
    grid_js = json.dumps(page_grid).replace("<", "\\u003c")
    has_photo = bool(job.image_path) and Path(job.image_path).is_file()

    html = (PAGE.replace("__TOKEN__", token).replace("__OPTIONS__", options)
                .replace("__BADGE_CLASS__", badge_class).replace("__BADGE__", badge)
                .replace("__HAS_PHOTO__", "true" if has_photo else "false")
                .replace("__GRID__", grid_js))
    return HTMLResponse(html)


@router.get("/edit/{token}/photo")
def edit_photo(token: str):
    job, _ = _load_job(token)
    if job is None or not job.image_path or not Path(job.image_path).is_file():
        return HTMLResponse("Not found", status_code=404)
    return FileResponse(job.image_path, media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=3600"})


@router.post("/edit/{token}/autocorrect")
async def autocorrect(token: str, request: Request):
    job, _ = _load_job(token)
    if job is None:
        return JSONResponse({"error": "expired"}, status_code=404)
    data = await request.json()
    grid, method = autocorrect_grid(data.get("headers"), data.get("rows"))
    return {**grid, "method": method}


@router.post("/edit/{token}/send")
def send_to_whatsapp(token: str, payload: str = Form(...), fmt: str = Form("excel")):
    """Build the file from the (edited) table and send it to the user's WhatsApp chat."""
    job, _ = _load_job(token)
    if job is None:
        return JSONResponse({"ok": False, "error": "this link has expired"}, status_code=404)
    if fmt not in FORMAT_MAP:
        return JSONResponse({"ok": False, "error": "unknown format"}, status_code=400)
    grid = _parse_payload(payload)
    if grid is None:
        return JSONResponse({"ok": False, "error": "the table data was not valid"}, status_code=400)
    base = public_base_url()
    if not base:
        return JSONResponse({"ok": False, "error": "PUBLIC_BASE_URL is not set on the server"},
                            status_code=500)

    out_dir = OUTPUT_DIR / uuid.uuid4().hex      # random folder = unguessable link
    path = convert(grid_to_structured(grid), fmt, out_dir, stem="SnapDocc")
    label = FORMAT_LABEL.get(fmt, fmt)
    try:
        status = deliver(job.phone, job.bot_number, f"✅ Here's your edited {label} file.",
                         f"{base}/files/{out_dir.name}/{path.name}")
    except Exception as e:
        reason = (getattr(e, "msg", None) or str(e)).strip().replace("\n", " ")[:160]
        print(f"[web] could not send WhatsApp message: {e}")
        return JSONResponse({"ok": False, "error": reason or "WhatsApp rejected the message"},
                            status_code=502)
    return {"ok": True, "queued": status == "queued"}


@router.post("/edit/{token}/download")
def download(token: str, payload: str = Form(...), fmt: str = Form("excel")):
    """Fallback only (shown if sending to WhatsApp fails): download the file instead."""
    job, _ = _load_job(token)
    if job is None:
        return HTMLResponse(NOT_FOUND, status_code=404)
    if fmt not in FORMAT_MAP:
        return HTMLResponse("Unknown format.", status_code=400)
    grid = _parse_payload(payload)
    if grid is None:
        return HTMLResponse("Bad data.", status_code=400)

    path = convert(grid_to_structured(grid), fmt, DOWNLOAD_DIR,
                   stem=f"snapdocc_{token[:8]}_{uuid.uuid4().hex[:4]}")
    return FileResponse(path, filename=f"SnapDocc.{path.suffix.lstrip('.')}",
                        background=BackgroundTask(path.unlink, missing_ok=True))
