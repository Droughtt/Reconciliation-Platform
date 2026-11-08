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

  function paint(html, animate = true) {
    view.innerHTML = html;
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
    if (!data) return `Request failed (${status})`;
    if (data.detail) return data.detail;
    const first = Object.entries(data)[0];
    if (first) {
      const [key, val] = first;
      const msg = Array.isArray(val) ? val[0] : val;
      return key === "non_field_errors" ? msg : `${key}: ${msg}`;
    }
    return `Request failed (${status})`;
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
    const active = name === "runs" || name === "review" ? name : "imports";
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.view === active));
    try {
      if (name === "runs" && id) await viewRun(Number(id), animate);
      else if (name === "runs") await viewRuns(animate);
      else if (name === "review") await viewReview(animate);
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

    const upload = canUpload()
      ? `<form id="upload" class="card row">
           <select name="kind" aria-label="File type">
             <option value="bank">Bank statement</option>
             <option value="ledger">Company ledger</option>
           </select>
           <input type="file" name="file" accept=".csv,text/csv" required>
           <button class="btn" type="submit">Upload</button>
         </form>`
      : `<p class="note">Your role can view imports but not upload files.</p>`;

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
       ${upload}
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

  const openBatchErrors = guard(async (id) => {
    const b = await api(`/api/imports/${id}/`);
    openDrawer(`
      <button class="close" data-close aria-label="Close">×</button>
      <h2>Failed records</h2>
      <p class="sub">${esc(b.original_filename)} · ${b.failed_rows} of ${b.total_rows} rows were rejected.</p>
      ${b.row_errors
        .map(
          (r) => `<div class="item">
            <strong>Row ${r.row_number}</strong>
            <div class="err">${esc(r.reason)}</div>
            <code>${esc(JSON.stringify(r.raw_data))}</code>
          </div>`
        )
        .join("")}`);
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

    const form = canReview()
      ? `<form id="flag-form" class="stack" data-id="${f.id}">
           <label>Decision <select name="status">${options}</select></label>
           <label>Note <textarea name="notes" rows="3" placeholder="Required to dismiss or escalate"></textarea></label>
           <button class="btn" type="submit">Save decision</button>
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

  // ---------- page-level events (one listener, works for every view) ----------
  view.addEventListener("click", (e) => {
    const t = e.target;
    let el;
    if ((el = t.closest("[data-errors]"))) return openBatchErrors(el.dataset.errors);
    if ((el = t.closest("[data-flag]"))) return openFlag(el.dataset.flag);
    if ((el = t.closest("[data-run]"))) { location.hash = `#/runs/${el.dataset.run}`; return; }
    if ((el = t.closest("[data-filter]"))) { runCtx.filter = el.dataset.filter; paint(runPage(), false); return; }
    if ((el = t.closest("[data-rfilter]"))) { reviewFilter = el.dataset.rfilter; route(false); return; }
    if (t.closest("#export")) exportCsv();
  });
  view.addEventListener("submit", (e) => {
    if (e.target.id === "upload") { e.preventDefault(); doUpload(e.target); }
    if (e.target.id === "new-run") { e.preventDefault(); doRun(e.target); }
  });

  // ---------- go ----------
  if (token) start();
  else $("#login").classList.remove("hidden");
})();