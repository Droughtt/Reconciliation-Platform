(() => {
  "use strict";

  // ---------- state ----------
  let token = sessionStorage.getItem("token");
  let me = null;
  let navId = 0;          // bumps on every navigation so slow responses can't overwrite newer pages
  let runCtx = null;      // data for the run page currently open
  let reviewFilter = "needs_review";

  const $ = (s) => document.querySelector(s);
  const view = $("#view");
  const drawer = $("#drawer");
  const overlay = $("#overlay");

  // ---------- labels ----------
  const STATUS = {
    matched: ["Matched", "green"],
    amount_mismatch: ["Amount mismatch", "amber"],
    date_mismatch: ["Date mismatch", "amber"],
    possible_match: ["Possible match", "blue"],
    duplicate: ["Duplicate", "blue"],
    unmatched_bank: ["Bank only", "red"],
    unmatched_ledger: ["Ledger only", "red"],
  };
  const FLAG = {
    needs_review: ["Needs review", "amber"],
    escalated: ["Escalated", "red"],
    explained: ["Explained", "green"],
    dismissed: ["Dismissed", "slate"],
  };
  const BATCH = {
    completed: ["Completed", "green"],
    failed: ["Failed", "red"],
    processing: ["Processing", "slate"],
  };

  // ---------- helpers ----------
  // Every value that comes from the API goes through esc() before it touches innerHTML.
  const esc = (v) =>
    String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const badge = ([label, tone]) => `<span class="badge ${tone}">${label}</span>`;
  const statusBadge = (s) => badge(STATUS[s] || [esc(s), "slate"]);
  const flagBadge = (s) => badge(FLAG[s] || [esc(s), "slate"]);
  const flagLabel = (s) => esc((FLAG[s] || [s])[0]);
  const kv = (k, v) => `<div class="kv"><span>${k}</span><span>${v}</span></div>`;

  const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" });
  const money = (v) => (v === null || v === undefined || v === "" ? "—" : inr.format(Number(v)));
  const day = (iso) => {
    const [y, m, d] = iso.split("-").map(Number);
    return new Date(y, m - 1, d).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  };
  const stamp = (iso) => new Date(iso).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });

  const refOf = (b, l) =>
    b && l && b.reference !== l.reference
      ? `${esc(b.reference)} <span class="muted">→</span> ${esc(l.reference)}`
      : esc((b || l).reference);

  const table = (heads, rows, empty) =>
    rows
      ? `<div class="table-wrap"><table><thead><tr>${heads.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>`
      : `<div class="empty">${empty}</div>`;

  function toast(msg, tone = "") {
    const el = document.createElement("div");
    el.className = `toast ${tone}`;
    el.textContent = msg;
    $("#toasts").append(el);
    requestAnimationFrame(() => el.classList.add("show"));
    setTimeout(() => {
      el.classList.remove("show");
      setTimeout(() => el.remove(), 320);
    }, 3800);
  }

  const PAGE = 10;
  let pageState = {}; // how many rows each table is showing, kept across quick refreshes

  function paginate() {
    view.querySelectorAll(".table-wrap").forEach((wrap, idx) => {
      const rows = [...wrap.querySelectorAll("tbody tr")];
      if (rows.length <= PAGE) return;
      const key = `${location.hash}|${idx}`;
      let shown = Math.min(pageState[key] || PAGE, rows.length);
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn ghost sm more";
      const sync = () => {
        rows.forEach((r, i) => (r.hidden = i >= shown));
        const left = rows.length - shown;
        btn.hidden = left <= 0;
        btn.textContent = `Show ${Math.min(PAGE, left)} more · ${left} remaining`;
        pageState[key] = shown;
      };
      btn.addEventListener("click", () => {
        shown += PAGE;
        sync();
      });
      sync();
      wrap.after(btn);
    });
  }

  function paint(html, animate = true) {
    if (animate) pageState = {};
    view.innerHTML = html;
    paginate();
    if (animate) {
      view.classList.remove("enter");
      void view.offsetWidth; // restart the CSS animation
      view.classList.add("enter");
    }
  }

  // ---------- API ----------
  class ApiError extends Error {
    constructor(message, status) {
      super(message);
      this.status = status;
    }
  }
  function errorMessage(data, status) {
    const flat = (v) => {
      if (v === null || v === undefined) return "";
      if (typeof v === "string") return v;
      if (Array.isArray(v)) return flat(v[0]);
      if (typeof v === "object") return flat(v.message ?? v.detail ?? Object.values(v)[0]);
      return String(v);
    };
    if (data && typeof data === "object") {
      if (data.detail) return flat(data.detail);
      const [key, val] = Object.entries(data)[0] || [];
      if (key) {
        const msg = flat(val);
        if (msg) return key === "non_field_errors" || key === "error" ? msg : `${key}: ${msg}`;
      }
    }
    return `Request failed (${status}). Please try again.`;
  }

  // credentials: "omit" keeps a Django admin session cookie out of API calls,
  // otherwise DRF's SessionAuthentication would demand a CSRF token.
  async function api(path, { method = "GET", body, form } = {}) {
    const headers = {};
    let payload;
    if (token) headers.Authorization = `Token ${token}`;
    if (form) payload = form;
    else if (body) {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }
    const res = await fetch(path, { method, headers, body: payload, credentials: "omit" });
    let data = null;
    try {
      data = await res.json();
    } catch {
      /* empty or non-JSON body */
    }
    if (res.status === 401 && token) {
      signOut();
      throw new ApiError("Session expired. Please sign in again.", 401);
    }
    if (!res.ok) throw new ApiError(errorMessage(data, res.status), res.status);
    return data;
  }

  const guard = (fn) => async (...args) => {
    try {
      return await fn(...args);
    } catch (err) {
      if (err.status !== 401) toast(err.message, "error");
    }
  };

  // ---------- who is signed in ----------
  const has = (...r) => me.is_superuser || me.roles.some((x) => r.includes(x));
  const canUpload = () => has("Administrator", "Analyst");
  const canReview = () => has("Administrator", "Reviewer");
  const canManageUsers = () => has("Administrator");
  const roleLabel = () => (me.is_superuser ? "Superuser" : me.roles.join(", ") || "No role");

  function signOut() {
    token = null;
    me = null;
    runCtx = null;
    sessionStorage.removeItem("token");
    view.innerHTML = "";
    closeDrawer();
    $("#app").classList.add("hidden");
    $("#login").classList.remove("hidden");
    history.replaceState(null, "", location.pathname);
  }

  async function start() {
    try {
      me = await api("/api/auth/me/");
    } catch {
      signOut();
      return;
    }
    $("#whoami").textContent = `${me.username} · ${roleLabel()}`;
    $("#users-tab").classList.toggle("hidden", !canManageUsers());
    $("#login").classList.add("hidden");
    $("#app").classList.remove("hidden");
    route();
  }

  $("#login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    const btn = form.querySelector("button");
    btn.disabled = true;
    const f = new FormData(form);
    try {
      const data = await api("/api/auth/token/", {
        method: "POST",
        body: { username: f.get("username"), password: f.get("password") },
      });
      token = data.token;
      sessionStorage.setItem("token", token);
      form.reset();
      await start();
    } catch (err) {
      toast(err.message, "error");
    } finally {
      btn.disabled = false;
    }
  });
  $("#logout").addEventListener("click", signOut);

  // ---------- drawer ----------
  function openDrawer(html) {
    drawer.innerHTML = html;
    drawer.scrollTop = 0;
    drawer.classList.add("open");
    overlay.classList.add("open");
    drawer.setAttribute("aria-hidden", "false");
  }
  function closeDrawer() {
    drawer.classList.remove("open");
    overlay.classList.remove("open");
    drawer.setAttribute("aria-hidden", "true");
  }
  overlay.addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (e) => e.key === "Escape" && closeDrawer());
  drawer.addEventListener("click", (e) => e.target.closest("[data-close]") && closeDrawer());

  // ---------- router ----------
  async function route(animate = true) {
    if (!me) return;
    navId++;
    const [, name = "imports", id] = location.hash.replace(/^#/, "").split("/");
    const active = ["runs", "review", "users"].includes(name) ? name : "imports";
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.view === active));
    try {
      if (name === "runs" && id) await viewRun(Number(id), animate);
      else if (name === "runs") await viewRuns(animate);
      else if (name === "review") await viewReview(animate);
      else if (name === "users") await viewUsers(animate);
      else await viewImports(animate);
    } catch (err) {
      if (err.status !== 401) toast(err.message, "error");
    }
  }
  window.addEventListener("hashchange", () => route());

  // ---------- imports ----------
  async function viewImports(animate) {
    const my = navId;
    const batches = await api("/api/imports/");
    if (my !== navId) return;

    const imported = batches.reduce((n, b) => n + b.imported_rows, 0);
    const rejected = batches.reduce((n, b) => n + b.failed_rows, 0);
    const last = batches[0]
      ? new Date(batches[0].created_at).toLocaleDateString("en-IN", { day: "numeric", month: "short" })
      : "—";

    const stats = `<div class="stats">
        <div class="stat"><span>Files</span><strong>${batches.length}</strong></div>
        <div class="stat"><span>Rows imported</span><strong>${imported}</strong></div>
        <div class="stat"><span>Rows rejected</span><strong class="${rejected ? "warn" : ""}">${rejected}</strong></div>
        <div class="stat"><span>Last upload</span><strong>${last}</strong></div>
      </div>`;

    const card = (kind, title, blurb) => `
      <form class="card upload-form">
        <input type="hidden" name="kind" value="${kind}">
        <div>
          <span class="card-title">${title}</span>
          <p class="muted small">${blurb}</p>
        </div>
        <input type="file" name="file" accept=".csv,text/csv" required>
        <div class="card-foot">
          <button class="link-quiet" type="button" data-guide>CSV format</button>
          <button class="btn" type="submit">Upload</button>
        </div>
      </form>`;

    const uploads = canUpload()
      ? `<div class="uploads">
           ${card("bank", "Bank statement", "Transactions as recorded by the bank.")}
           ${card("ledger", "Company ledger", "Transactions as recorded in your accounting system.")}
         </div>`
      : `<p class="note">Uploads are handled by analysts and administrators. Open any file's failed records from the table below.</p>`;

    const rows = batches
      .map(
        (b, i) => `<tr style="--i:${Math.min(i, 12)}">
          <td class="muted">#${b.id}</td>
          <td>${b.kind === "bank" ? "Bank" : "Ledger"}</td>
          <td class="strong">${esc(b.original_filename)}</td>
          <td>${badge(BATCH[b.status] || [esc(b.status), "slate"])}</td>
          <td class="num">${b.imported_rows} <span class="muted">/ ${b.total_rows}</span></td>
          <td class="num">${b.failed_rows ? `<button class="link" data-errors="${b.id}">${b.failed_rows} failed</button>` : `<span class="muted">0</span>`}</td>
          <td class="muted">${esc(b.uploaded_by)}</td>
          <td class="muted">${stamp(b.created_at)}</td>
        </tr>`
      )
      .join("");

    paint(
      `<h1>Imports</h1>
       <p class="sub">Upload bank and ledger CSV files. Rows that fail validation are reported, never silently dropped.</p>
       ${stats}
       ${uploads}
       ${table(["ID", "Type", "File", "Status", "Imported", "Failed", "By", "Uploaded"], rows, "No files uploaded yet.")}`,
      animate
    );
  }
  async function doUpload(form) {
    const btn = form.querySelector("button");
    btn.disabled = true;
    try {
      const batch = await api("/api/imports/", { method: "POST", form: new FormData(form) });
      toast(`Imported ${batch.imported_rows} rows, ${batch.failed_rows} failed`, batch.failed_rows ? "" : "ok");
      await route(false);
    } catch (err) {
      toast(err.message, "error");
      btn.disabled = false;
    }
  }

  const FIELD_LABELS = { reference: "Reference", date: "Date", amount: "Amount", description: "Description", none: "Extra cells" };

  const openBatchErrors = guard(async (id) => {
    const b = await api(`/api/imports/${id}/`);
    const sentence = (s) => s.charAt(0).toUpperCase() + s.slice(1) + (/[.!?]$/.test(s) ? "" : ".");

    const items = b.row_errors
      .map((r) => {
        // the reason starts with the field that failed, so highlight that cell
        const bad = ((r.reason.match(/^(date|amount|reference)/i) || [])[1] || "").toLowerCase();
        const cells = Object.entries(r.raw_data)
          .map(([key, val]) => {
            const text = Array.isArray(val) ? val.join(", ") : val;
            const label = FIELD_LABELS[key.toLowerCase()] || esc(key);
            const shown = text === "" || text === null ? `<em class="muted">empty</em>` : esc(text);
            return `<div class="cell ${key.toLowerCase() === bad ? "bad" : ""}"><span>${label}</span><strong>${shown}</strong></div>`;
          })
          .join("");
        return `<div class="item">
          <strong>Line ${r.row_number} of the file</strong>
          <div class="err">${esc(sentence(r.reason))}</div>
          <div class="cells">${cells}</div>
        </div>`;
      })
      .join("");

    openDrawer(`
      <button class="close" data-close aria-label="Close">×</button>
      <h2>Rows that need fixing</h2>
      <p class="sub">${esc(b.original_filename)} · ${b.failed_rows} of ${b.total_rows} rows were skipped. The rest were imported normally. Correct these rows in your CSV and upload it again.</p>
      ${items}`);
  });

  // ---------- runs ----------
  async function viewRuns(animate) {
    const my = navId;
    const [runs, batches] = await Promise.all([api("/api/reconciliation/runs/"), api("/api/imports/")]);
    if (my !== navId) return;

    const usable = (kind) => batches.filter((b) => b.kind === kind && b.status === "completed");
    const opt = (b) => `<option value="${b.id}">#${b.id} · ${esc(b.original_filename)}</option>`;
    const ready = usable("bank").length && usable("ledger").length;

    let form = `<p class="note">Your role can view runs but not start them.</p>`;
    if (canUpload()) {
      form = ready
        ? `<form id="new-run" class="card row">
             <label>Bank file <select name="bank_batch_id">${usable("bank").map(opt).join("")}</select></label>
             <label>Ledger file <select name="ledger_batch_id">${usable("ledger").map(opt).join("")}</select></label>
             <button class="btn" type="submit">Run reconciliation</button>
           </form>`
        : `<p class="note">Upload a bank file and a ledger file first, then you can start a run.</p>`;
    }

    const rows = runs
      .map(
        (r, i) => `<tr class="click" data-run="${r.id}" style="--i:${Math.min(i, 12)}">
          <td class="muted">#${r.id}</td>
          <td class="muted">Bank #${r.bank_batch} · Ledger #${r.ledger_batch}</td>
          <td>${Object.entries(r.summary).map(([s, n]) => `${statusBadge(s)} <span class="muted">${n}</span>`).join("&nbsp; ")}</td>
          <td class="muted">${esc(r.created_by)}</td>
          <td class="muted">${stamp(r.created_at)}</td>
        </tr>`
      )
      .join("");

    paint(
      `<h1>Runs</h1>
       <p class="sub">Each run compares one bank file with one ledger file.</p>
       ${form}
       ${table(["Run", "Files", "Results", "Started by", "When"], rows, "No runs yet.")}`,
      animate
    );
  }

  async function doRun(form) {
    const btn = form.querySelector("button");
    btn.disabled = true;
    const f = new FormData(form);
    try {
      const run = await api("/api/reconciliation/runs/", {
        method: "POST",
        body: { bank_batch_id: Number(f.get("bank_batch_id")), ledger_batch_id: Number(f.get("ledger_batch_id")) },
      });
      toast("Reconciliation complete", "ok");
      location.hash = `#/runs/${run.id}`;
    } catch (err) {
      toast(err.message, "error");
      btn.disabled = false;
    }
  }

  async function viewRun(id, animate) {
    const my = navId;
    const [summary, detail, flags] = await Promise.all([
      api(`/api/reports/runs/${id}/summary/`),
      api(`/api/reconciliation/runs/${id}/`),
      api(`/api/reconciliation/flags/?run=${id}`),
    ]);
    if (my !== navId) return;
    const flagByResult = new Map(flags.map((f) => [f.result.id, f]));
    const filter = runCtx && runCtx.id === id ? runCtx.filter : "all";
    runCtx = { id, summary, results: detail.results, flagByResult, filter };
    paint(runPage(), animate);
  }

  function runPage() {
    const { id, summary, results, flagByResult, filter } = runCtx;
    const t = summary.totals;
    const chips = [["all", "All", results.length], ...Object.entries(summary.results_by_status).map(([s, n]) => [s, (STATUS[s] || [s])[0], n])]
      .map(([key, label, n]) => `<button class="chip ${filter === key ? "active" : ""}" data-filter="${esc(key)}">${esc(label)} <span>${n}</span></button>`)
      .join("");

    const side = (x) => (x ? `<div class="num">${money(x.amount)}</div><div class="muted small">${day(x.date)}</div>` : `<span class="muted">—</span>`);
    const shown = filter === "all" ? results : results.filter((r) => r.status === filter);
    const rows = shown
      .map((r, i) => {
        const f = flagByResult.get(r.id);
        return `<tr class="${f ? "click" : ""}" ${f ? `data-flag="${f.id}"` : ""} style="--i:${Math.min(i, 12)}">
          <td>${statusBadge(r.status)}</td>
          <td class="strong">${refOf(r.bank, r.ledger)}</td>
          <td>${side(r.bank)}</td>
          <td>${side(r.ledger)}</td>
          <td class="num">${money(r.amount_difference)}</td>
          <td>${f ? flagBadge(f.status) : `<span class="muted">—</span>`}</td>
        </tr>`;
      })
      .join("");

    const failedBank = summary.bank_file.failed_rows;
    const failedLedger = summary.ledger_file.failed_rows;
    const warn = failedBank || failedLedger
      ? `<p class="note">${failedBank} bank and ${failedLedger} ledger rows were rejected at import and are not part of this run.</p>`
      : "";

    return `<a class="back" href="#/runs">← All runs</a>
      <div class="titlebar">
        <div>
          <h1>Run #${id}</h1>
          <p class="sub">${esc(summary.bank_file.file)} vs ${esc(summary.ledger_file.file)} · by ${esc(summary.created_by)} · ${stamp(summary.created_at)}</p>
        </div>
        <button class="btn ghost" id="export" type="button">Export CSV</button>
      </div>
      <div class="stats">
        <div class="stat"><span>Bank total</span><strong>${money(t.bank_total)}</strong></div>
        <div class="stat"><span>Ledger total</span><strong>${money(t.ledger_total)}</strong></div>
        <div class="stat"><span>Net difference</span><strong class="${Number(t.net_difference) === 0 ? "" : "warn"}">${money(t.net_difference)}</strong></div>
        <div class="stat"><span>Open flags</span><strong>${summary.open_flags}</strong></div>
      </div>
      ${warn}
      <div class="chips">${chips}</div>
      ${table(["Result", "Reference", "Bank", "Ledger", "Difference", "Review"], rows, "No results for this filter.")}`;
  }

  const exportCsv = guard(async () => {
    const q = runCtx.filter === "all" ? "" : `?status=${encodeURIComponent(runCtx.filter)}`;
    const res = await fetch(`/api/reports/runs/${runCtx.id}/export/${q}`, {
      headers: { Authorization: `Token ${token}` },
      credentials: "omit",
    });
    if (!res.ok) throw new ApiError("Export failed", res.status);
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = `reconciliation_run_${runCtx.id}${runCtx.filter === "all" ? "" : "_" + runCtx.filter}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  });

  // ---------- review queue ----------
  const REVIEW_FILTERS = [["needs_review", "Needs review"], ["escalated", "Escalated"], ["explained", "Explained"], ["dismissed", "Dismissed"], ["all", "All"]];

  async function viewReview(animate) {
    const my = navId;
    const q = reviewFilter === "all" ? "" : `?status=${reviewFilter}`;
    const flags = await api(`/api/reconciliation/flags/${q}`);
    if (my !== navId) return;

    const chips = REVIEW_FILTERS.map(([k, label]) => `<button class="chip ${reviewFilter === k ? "active" : ""}" data-rfilter="${k}">${label}</button>`).join("");
    const rows = flags
      .map((f, i) => {
        const r = f.result;
        return `<tr class="click" data-flag="${f.id}" style="--i:${Math.min(i, 12)}">
          <td>${statusBadge(r.status)}</td>
          <td class="strong">${refOf(r.bank, r.ledger)}</td>
          <td class="num">${money((r.bank || r.ledger).amount)}</td>
          <td class="num">${money(r.amount_difference)}</td>
          <td class="muted reason">${esc(r.reason)}</td>
          <td>${flagBadge(f.status)}</td>
          <td class="muted">${stamp(f.updated_at)}</td>
        </tr>`;
      })
      .join("");

    paint(
      `<h1>Review queue</h1>
       <p class="sub">An anomaly is a reason to investigate, not a verdict. Record what you found and why.</p>
       <div class="chips">${chips}</div>
       ${table(["Result", "Reference", "Amount", "Difference", "Reason", "Review", "Updated"], rows, "Nothing here. Nice and quiet.")}`,
      animate
    );
  }

  const openFlag = guard(async (id) => {
    const f = await api(`/api/reconciliation/flags/${id}/`);
    const r = f.result;
    const sideText = (x) => (x ? `${esc(x.reference)} · ${money(x.amount)} · ${day(x.date)}` : "Not present");
    const options = Object.entries(FLAG)
      .filter(([k]) => k !== f.status)
      .map(([k, [label]]) => `<option value="${k}">${label}</option>`)
      .join("");

    
const reviewerAccess = canReview();
const analystAccess = has("Analyst") && !reviewerAccess;

const flagStatusOptions = Object.entries(FLAG)
  .filter(([k]) => k !== f.status)
  .filter(([k]) => reviewerAccess || (analystAccess && k === "escalated"))
  .map(([k, [label]]) => `<option value="${k}">${label}</option>`)
  .join("");

const form = reviewerAccess || analystAccess
  ? `<form id="flag-form" class="stack" data-id="${f.id}">
       <label>Decision <select name="status">${flagStatusOptions}</select></label>
       <label>Note <textarea name="notes" rows="3" placeholder="Required to dismiss or escalate"></textarea></label>
       <button class="btn" type="submit">${analystAccess ? "Escalate flag" : "Save decision"}</button>
     </form>`
  : `<p class="note">Only reviewers can change flags.</p>`;


    const events = f.events.length
      ? f.events
          .map(
            (ev) => `<li><div class="dot"></div><div>
              <strong>${esc(ev.changed_by)}</strong> ${flagLabel(ev.old_status)} → ${flagLabel(ev.new_status)}
              ${ev.notes ? `<div class="quote">${esc(ev.notes)}</div>` : ""}
              <div class="muted small">${stamp(ev.created_at)}</div>
            </div></li>`
          )
          .join("")
      : `<li class="muted">No decisions yet.</li>`;

    openDrawer(`
      <button class="close" data-close aria-label="Close">×</button>
      <div class="drawer-head">${statusBadge(r.status)} ${flagBadge(f.status)}</div>
      <h2>${refOf(r.bank, r.ledger)}</h2>
      <p class="sub">${esc(r.reason)}</p>
      <div class="kvs">
        ${kv("Bank", sideText(r.bank))}
        ${kv("Ledger", sideText(r.ledger))}
        ${r.amount_difference !== null ? kv("Difference (bank − ledger)", money(r.amount_difference)) : ""}
        ${kv("Confidence", `${r.confidence}%`)}
      </div>
      <h3>Review</h3>
      ${form}
      <h3>History</h3>
      <ul class="timeline">${events}</ul>`);
  });

  drawer.addEventListener("submit", async (e) => {
    if (e.target.id !== "flag-form") return;
    e.preventDefault();
    const form = e.target;
    const btn = form.querySelector("button");
    btn.disabled = true;
    const f = new FormData(form);
    try {
      await api(`/api/reconciliation/flags/${form.dataset.id}/`, {
        method: "PATCH",
        body: { status: f.get("status"), notes: f.get("notes") },
      });
      toast("Decision saved", "ok");
      await openFlag(form.dataset.id);
      await route(false);
    } catch (err) {
      toast(err.message, "error");
      btn.disabled = false;
    }
  });
    // ---------- users (administrators only) ----------
  const ROLES = ["Administrator", "Analyst", "Reviewer"];

  async function viewUsers(animate) {
    if (!canManageUsers()) {
      location.hash = "#/imports";
      return;
    }
    const my = navId;
    const users = await api("/api/auth/users/");
    if (my !== navId) return;

    const rows = users
      .map((u, i) => {
        const locked = u.role === "Superuser" || u.username === me.username;
        const roleCell = locked
          ? `${badge([esc(u.role || "No role"), "slate"])}${u.username === me.username ? ` <span class="muted small">you</span>` : ""}`
          : `<select data-role-user="${u.id}" aria-label="Role for ${esc(u.username)}">
               ${u.role ? "" : `<option value="" selected disabled>No role</option>`}
               ${ROLES.map((r) => `<option ${u.role === r ? "selected" : ""}>${r}</option>`).join("")}
             </select>`;
        const action = locked
          ? `<span class="muted">—</span>`
          : `<button class="btn ghost sm" data-toggle-user="${u.id}" data-active="${u.is_active}">${u.is_active ? "Deactivate" : "Activate"}</button>`;
        return `<tr style="--i:${Math.min(i, 12)}">
          <td class="strong">${esc(u.username)}</td>
          <td>${roleCell}</td>
          <td>${u.is_active ? badge(["Active", "green"]) : badge(["Inactive", "slate"])}</td>
          <td class="muted">${u.last_login ? stamp(u.last_login) : "Never"}</td>
          <td>${action}</td>
        </tr>`;
      })
      .join("");

    paint(
      `<h1>Users</h1>
       <p class="sub">Give each person the smallest role that lets them do their job. Deactivate instead of deleting, so the audit trail stays intact.</p>
       <form id="new-user" class="card row">
         <label>Username <input name="username" autocomplete="off" required></label>
         <label>Password <input name="password" type="password" autocomplete="new-password" required></label>
         <label>Role <select name="role">${ROLES.map((r) => `<option>${r}</option>`).join("")}</select></label>
         <button class="btn" type="submit">Add user</button>
       </form>
       ${table(["Username", "Role", "Status", "Last sign-in", ""], rows, "No users yet.")}`,
      animate
    );
  }

  async function doCreateUser(form) {
    const btn = form.querySelector("button");
    btn.disabled = true;
    const f = new FormData(form);
    try {
      await api("/api/auth/users/", {
        method: "POST",
        body: { username: f.get("username"), password: f.get("password"), role: f.get("role") },
      });
      toast("User created", "ok");
      await route(false);
    } catch (err) {
      toast(err.message, "error");
      btn.disabled = false;
    }
  }

  const toggleUser = guard(async (id, wasActive) => {
    await api(`/api/auth/users/${id}/`, { method: "PATCH", body: { is_active: !wasActive } });
    toast(wasActive ? "User deactivated" : "User activated", "ok");
    await route(false);
  });

  view.addEventListener("change", async (e) => {
    const sel = e.target.closest("[data-role-user]");
    if (!sel) return;
    try {
      await api(`/api/auth/users/${sel.dataset.roleUser}/`, { method: "PATCH", body: { role: sel.value } });
      toast("Role updated", "ok");
    } catch (err) {
      if (err.status !== 401) toast(err.message, "error");
    }
    await route(false); // re-draw so a rejected change snaps back
  });

  // ---------- page-level events (one listener, works for every view) ----------
  view.addEventListener("click", (e) => {
    const t = e.target;
    let el;
    if ((el = t.closest("[data-errors]"))) return openBatchErrors(el.dataset.errors);
    if ((el = t.closest("[data-flag]"))) return openFlag(el.dataset.flag);
    if ((el = t.closest("[data-run]"))) { location.hash = `#/runs/${el.dataset.run}`; return; }
    if ((el = t.closest("[data-filter]"))) { runCtx.filter = el.dataset.filter; paint(runPage(), false); return; }
    if ((el = t.closest("[data-rfilter]"))) { reviewFilter = el.dataset.rfilter; route(false); return; }
    if ((el = t.closest("[data-toggle-user]"))) return toggleUser(el.dataset.toggleUser, el.dataset.active === "true");
    if (t.closest("#export")) exportCsv();
  });
  view.addEventListener("submit", (e) => {
    if (e.target.classList.contains("upload-form")) { e.preventDefault(); doUpload(e.target); }
    if (e.target.id === "new-run") { e.preventDefault(); doRun(e.target); }
    if (e.target.id === "new-user") { e.preventDefault(); doCreateUser(e.target); }
  });

    // ---------- CSV format guide ----------
  function openGuide() {
    openDrawer(`
      <button class="close" data-close aria-label="Close">×</button>
      <h2>CSV format guide</h2>
      <p class="sub">What the importer accepts, and what happens next.</p>
      <dl class="guide">
        <dt>Columns</dt><dd>Required: reference, date, amount. Optional: description. Header names are not case-sensitive.</dd>
        <dt>Dates</dt><dd>YYYY-MM-DD, DD-MM-YYYY or DD/MM/YYYY. A date like 01/10/2026 is read as 1 October 2026.</dd>
        <dt>Amounts</dt><dd>Positive numbers with at most two decimals. A ₹ sign and thousands commas are fine.</dd>
        <dt>References</dt><dd>Up to 100 characters. They are trimmed and uppercased, so inv-1001 matches INV-1001.</dd>
        <dt>File</dt><dd>UTF-8 .csv, up to 5 MB. The same file can't be uploaded twice as the same type.</dd>
        <dt>Bad rows</dt><dd>Rejected one by one and listed under Failed. They never stop the rest of the file.</dd>
      </dl>
      <h3>Example</h3>
      <code class="sample">reference,date,amount,description
INV-1001,2026-10-01,50000.00,Vendor Alpha
INV-1002,2026-10-02,"12,000.50",Vendor Beta</code>
      <h3>How rows are compared</h3>
      <dl class="guide">
        <dt>Matched</dt><dd>Same reference, date and amount.</dd>
        <dt>Date or amount mismatch</dt><dd>Same reference and dates within 5 days, but the date or the amount differs.</dd>
        <dt>Possible match</dt><dd>Different references, same amount and close dates, only when there is exactly one candidate.</dd>
        <dt>Bank only / Ledger only</dt><dd>Nothing comparable on the other side.</dd>
        <dt>Duplicate</dt><dd>An identical record beyond the one that matched.</dd>
      </dl>`);
  }
  document.addEventListener("click", (e) => {
    if (e.target.closest("[data-guide]")) openGuide();
  });
  
  // ---------- theme ----------
  const themeBtn = $("#theme");
  const systemDark = window.matchMedia("(prefers-color-scheme: dark)");
  const currentTheme = () => document.documentElement.dataset.theme || (systemDark.matches ? "dark" : "light");
  function applyTheme(t) {
    if (t) document.documentElement.dataset.theme = t;
    themeBtn.textContent = currentTheme() === "dark" ? "Light mode" : "Dark mode";
  }
  themeBtn.addEventListener("click", () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    try { localStorage.setItem("theme", next); } catch { /* storage blocked, theme just won't persist */ }
    applyTheme(next);
  });
  let savedTheme = null;
  try { savedTheme = localStorage.getItem("theme"); } catch { /* ignore */ }
  applyTheme(savedTheme);

  // ---------- go ----------
  if (token) start();
  else $("#login").classList.remove("hidden");
})();