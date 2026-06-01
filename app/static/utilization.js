"use strict";

const $ = (id) => document.getElementById(id);
let currentSummary = null;

async function api(path) {
  const res = await fetch(path);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw { status: res.status, data };
  return data;
}

const LOS_LABEL = {
  at_or_below_benchmark: ["At/below benchmark", "los-ok"],
  above_gmlos: ["Above GMLOS", "los-warn"],
  outlier: ["Outlier — review", "los-bad"],
  unknown: ["Unknown", ""],
};

async function loadList() {
  const { encounters } = await api("/api/utilization/inpatient-encounters");
  const list = $("list");
  if (!encounters.length) {
    list.innerHTML = '<p class="muted">No inpatient encounters yet. Import the inpatient sample on the <a href="/">main page</a>.</p>';
    return;
  }
  list.innerHTML = "";
  for (const e of encounters) {
    const [label] = LOS_LABEL[e.los_status] || ["", ""];
    const div = document.createElement("div");
    div.className = "enc-item";
    div.onclick = () => loadSummary(e.encounter_id);
    div.innerHTML = `
      <div><strong>${e.patient}</strong>
        <span class="muted"> · MRN ${e.mrn} · DRG ${e.drg || "—"} · LOS ${e.length_of_stay_days ?? "—"}d</span></div>
      <span class="pill ${e.ready_for_submission ? "outpatient" : ""}">
        ${e.ready_for_submission ? "ready" : "not ready"} · ${label}</span>`;
    list.appendChild(div);
  }
}

async function loadSummary(id) {
  currentSummary = await api(`/api/utilization/encounters/${id}/summary`);
  renderSummary(currentSummary);
}

function renderSummary(s) {
  $("summary").classList.remove("hidden");

  $("ready").innerHTML = s.ready_for_submission
    ? `<div class="ready-banner ready-yes">✓ Ready for submission</div>`
    : `<div class="ready-banner ready-no">✗ Not ready — ${s.submission_blockers.length} blocker(s) below</div>`;

  $("patient-line").innerHTML = `
    <p><strong>${s.patient.name}</strong>
      <span class="tag">${s.patient.sex}</span>
      <span class="muted">age ${s.patient.age ?? "?"} · MRN ${s.patient.mrn} · ${s.stay.reason || "—"}</span></p>`;

  const drg = s.drg;
  $("metrics").innerHTML = `
    ${metric("MS-DRG", drg ? drg.drg : "—", drg ? drg.description : "no DRG derived")}
    ${metric("Length of stay", (s.stay.length_of_stay_days ?? "—") + " d", `${s.stay.admit_date || "?"} → ${s.stay.discharge_date || "ongoing"}`)}
    ${metric("DRG weight", drg ? drg.weight.toFixed(4) : "—", drg ? `GMLOS ${drg.gmlos} d` : "")}
    ${metric("Est. reimbursement", s.estimated_reimbursement != null ? "$" + s.estimated_reimbursement.toLocaleString() : "—", "DRG-based")}
  `;

  renderLos(s.length_of_stay_review);
  renderDxPx(s);
  renderBlockers(s);
}

function metric(label, value, sub) {
  return `<div class="metric"><div class="label">${label}</div><div class="value">${value}</div><div class="sub">${sub || ""}</div></div>`;
}

function renderLos(r) {
  if (r.actual_days == null || r.gmlos == null) {
    $("los-review").innerHTML = '<p class="muted">Length-of-stay benchmark unavailable (no DRG or no dates).</p>';
    return;
  }
  const [label, cls] = LOS_LABEL[r.status] || ["", ""];
  const pct = Math.min((r.actual_days / Math.max(r.amlos || r.gmlos, r.actual_days)) * 100, 100);
  const variance = r.variance_days > 0 ? `+${r.variance_days}` : `${r.variance_days}`;
  $("los-review").innerHTML = `
    <h3>Length-of-stay review</h3>
    <p>Actual <strong>${r.actual_days} d</strong> vs GMLOS ${r.gmlos} d / AMLOS ${r.amlos} d
       — <span class="${cls === "los-ok" ? "status-ok" : "status-bad"}">${label}</span>
       (variance ${variance} d)</p>
    <div class="los-bar"><span class="${cls}" style="width:${pct}%"></span></div>`;
}

function renderDxPx(s) {
  const dx = [];
  if (s.principal_diagnosis)
    dx.push(`<tr><td><span class="tag">${s.principal_diagnosis.code}</span></td><td>${s.principal_diagnosis.description || ""}</td><td><strong>Principal</strong></td></tr>`);
  for (const d of s.secondary_diagnoses)
    dx.push(`<tr><td><span class="tag">${d.code}</span></td><td>${d.description || ""}</td><td>Secondary${d.poa ? " · POA " + d.poa : ""}</td></tr>`);
  const px = s.procedures.map(
    (p) => `<tr><td><span class="tag">${p.code}</span></td><td>${p.description || ""}</td><td>${p.system}</td></tr>`
  );
  $("dx-px").innerHTML = `
    <h3>Diagnoses</h3>
    <table><thead><tr><th>Code</th><th>Description</th><th>Type</th></tr></thead><tbody>${dx.join("") || '<tr><td colspan="3" class="muted">None</td></tr>'}</tbody></table>
    <h3 style="margin-top:14px">Procedures</h3>
    <table><thead><tr><th>Code</th><th>Description</th><th>System</th></tr></thead><tbody>${px.join("") || '<tr><td colspan="3" class="muted">None</td></tr>'}</tbody></table>`;
}

function renderBlockers(s) {
  $("blockers").innerHTML = s.submission_blockers.length
    ? "<h3>Blockers</h3>" + s.submission_blockers.map((b) => `<div class="issue error">${b}</div>`).join("")
    : '<p class="status-ok">No blockers — all submission requirements met.</p>';
  $("advisories").innerHTML = s.advisories.length
    ? "<h3>Advisories</h3>" + s.advisories.map((a) => `<div class="issue warning">${a}</div>`).join("")
    : "";
}

function downloadPacket() {
  if (!currentSummary) return;
  const blob = new Blob([JSON.stringify(currentSummary, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `utilization-encounter-${currentSummary.encounter_id}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

loadList();
