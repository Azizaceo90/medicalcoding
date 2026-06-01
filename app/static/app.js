"use strict";

// --- Application state ----------------------------------------------------
const state = {
  encounterId: null,
  encounter: null,
  patient: null,
  diagnoses: [], // {code, description, is_principal}
  procedures: [], // {code, description, modifiers:[], diagnosis_pointers:[]}
};

const $ = (id) => document.getElementById(id);

async function api(method, path, body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw { status: res.status, data };
  return data;
}

// --- Epic status ----------------------------------------------------------
async function loadEpicStatus() {
  try {
    const s = await api("GET", "/api/epic/status");
    $("epic-badge").textContent = `Epic: ${s.mock_mode ? "Sandbox (mock)" : "Live"} · R4`;
  } catch {
    $("epic-badge").textContent = "Epic: unavailable";
  }
}

// --- Import / encounter list ---------------------------------------------
async function importEncounter(scenario) {
  try {
    const r = await api("POST", "/api/epic/import", { encounter_key: scenario });
    await loadEncounters();
    selectEncounter(r.encounter_id);
  } catch (e) {
    alert("Import failed: " + JSON.stringify(e.data));
  }
}

async function loadEncounters() {
  const encounters = await api("GET", "/api/encounters");
  const list = $("encounter-list");
  if (!encounters.length) {
    list.innerHTML = '<p class="muted">No encounters yet — import one above.</p>';
    return;
  }
  const patients = await api("GET", "/api/patients");
  const pmap = Object.fromEntries(patients.map((p) => [p.id, p]));
  list.innerHTML = "";
  for (const enc of encounters) {
    const p = pmap[enc.patient_id] || {};
    const div = document.createElement("div");
    div.className = "enc-item" + (enc.id === state.encounterId ? " active" : "");
    div.onclick = () => selectEncounter(enc.id);
    div.innerHTML = `
      <div>
        <strong>${p.last_name || "?"}, ${p.first_name || ""}</strong>
        <span class="muted"> · MRN ${p.mrn || "?"} · ${enc.reason || "—"}</span>
      </div>
      <span class="pill ${enc.encounter_class}">${enc.encounter_class} · ${enc.status}</span>`;
    list.appendChild(div);
  }
}

async function selectEncounter(id) {
  state.encounterId = id;
  state.diagnoses = [];
  state.procedures = [];
  state.encounter = await api("GET", `/api/encounters/${id}`);
  state.patient = await api("GET", `/api/patients/${state.encounter.patient_id}`);
  $("workspace").classList.remove("hidden");
  await loadEncounters();
  renderEncounterHeader();
  await loadDocuments();
  renderDxTable();
  renderPxTable();
  $("validation-summary").innerHTML = '<span class="muted">Save coding to run edits.</span>';
  $("validation-detail").innerHTML = "";
  $("claim-result").innerHTML = "";
}

function renderEncounterHeader() {
  const e = state.encounter, p = state.patient;
  $("encounter-header").innerHTML = `
    <p><strong>${p.last_name}, ${p.first_name}</strong>
      <span class="tag">${p.sex}</span>
      <span class="muted">age ${p.age ?? "?"} · DOB ${p.birth_date || "?"} · MRN ${p.mrn}</span></p>
    <p><span class="pill ${e.encounter_class}">${e.encounter_class}</span>
      <span class="muted"> Reason: ${e.reason || "—"} · Admit ${e.admit_date || "—"} · D/C ${e.discharge_date || "—"}</span></p>`;
}

async function loadDocuments() {
  const docs = await api("GET", `/api/encounters/${state.encounterId}/documents`);
  $("documents").innerHTML = docs
    .map((d) => `<div class="issue info"><strong>${d.doc_type}</strong> — ${d.author || "Unknown"}<br>${d.text}</div>`)
    .join("") || '<p class="muted">No documents.</p>';
}

// --- CPT verification -----------------------------------------------------
async function verifyCpt() {
  const code = $("verify-code").value.trim();
  if (!code) return;
  const modifiers = $("verify-mods").value.split(",").map((m) => m.trim()).filter(Boolean);
  const body = {
    code,
    modifiers,
    encounter_class: state.encounter?.encounter_class,
    patient_sex: state.patient?.sex,
    patient_age: state.patient?.age,
    supporting_icd: state.diagnoses.map((d) => d.code),
  };
  const r = await api("POST", "/api/coding/verify-cpt", body);
  const head = r.valid
    ? `<span class="status-ok">✓ ${r.code} valid</span>`
    : `<span class="status-bad">✗ ${r.code} has errors</span>`;
  $("verify-result").innerHTML =
    `<p>${head} <span class="muted">${r.description || ""} ${r.category ? "(Cat " + r.category + ")" : ""}</span></p>` +
    renderIssues(r.issues);
}

function renderIssues(issues) {
  if (!issues || !issues.length) return '<p class="muted">No edits triggered.</p>';
  return issues
    .map(
      (i) =>
        `<div class="issue ${i.severity}"><span class="rule">${i.rule}</span> — ${i.message}</div>`
    )
    .join("");
}

// --- Code search ----------------------------------------------------------
let icdTimer, cptTimer;
function searchIcd() {
  clearTimeout(icdTimer);
  icdTimer = setTimeout(async () => {
    const q = $("dx-search").value.trim();
    if (q.length < 1) return ($("dx-search-results").innerHTML = "");
    const { results } = await api("GET", `/api/coding/search/icd?q=${encodeURIComponent(q)}`);
    $("dx-search-results").innerHTML = results
      .map(
        (r) =>
          `<div onclick='addDx(${JSON.stringify({ code: r.code, description: r.description, system: r.system }).replace(/'/g, "&#39;")})'>
            <span class="tag">${r.code}</span> ${r.description} <span class="muted">${r.system}${r.billable === false ? " · non-billable" : ""}</span></div>`
      )
      .join("");
  }, 200);
}

function searchCpt() {
  clearTimeout(cptTimer);
  cptTimer = setTimeout(async () => {
    const q = $("px-search").value.trim();
    if (q.length < 1) return ($("px-search-results").innerHTML = "");
    const { results } = await api("GET", `/api/coding/search/cpt?q=${encodeURIComponent(q)}`);
    $("px-search-results").innerHTML = results
      .map(
        (r) =>
          `<div onclick='addPx(${JSON.stringify({ code: r.code, description: r.short }).replace(/'/g, "&#39;")})'>
            <span class="tag">${r.code}</span> ${r.short} <span class="muted">${r.status !== "active" ? r.status : "Cat " + r.category}</span></div>`
      )
      .join("");
  }, 200);
}

// --- Diagnosis table ------------------------------------------------------
function addDx(dx) {
  if (state.diagnoses.some((d) => d.code === dx.code)) return;
  dx.is_principal = state.diagnoses.length === 0; // first dx defaults to principal
  dx.system = dx.system && dx.system.includes("PCS") ? "ICD-10-PCS" : "ICD-10-CM";
  state.diagnoses.push(dx);
  $("dx-search").value = "";
  $("dx-search-results").innerHTML = "";
  renderDxTable();
}

function renderDxTable() {
  const tb = $("dx-table").querySelector("tbody");
  tb.innerHTML = state.diagnoses
    .map(
      (d, i) => `<tr>
        <td><span class="tag">${d.code}</span></td>
        <td>${d.description || ""}</td>
        <td><input type="radio" name="principal" ${d.is_principal ? "checked" : ""} onclick="setPrincipal(${i})"></td>
        <td><button onclick="removeDx(${i})">✕</button></td></tr>`
    )
    .join("");
}
function setPrincipal(i) {
  state.diagnoses.forEach((d, j) => (d.is_principal = j === i));
}
function removeDx(i) {
  state.diagnoses.splice(i, 1);
  renderDxTable();
}

// --- Procedure table ------------------------------------------------------
function addPx(px) {
  if (state.procedures.some((p) => p.code === px.code)) return;
  px.modifiers = [];
  px.system = /^[0-9A-HJ-NP-Z]{7}$/i.test(px.code) ? "ICD-10-PCS" : (/^[A-Z]\d{4}$/i.test(px.code) ? "HCPCS" : "CPT");
  px.diagnosis_pointers = state.diagnoses.length ? [1] : [];
  state.procedures.push(px);
  $("px-search").value = "";
  $("px-search-results").innerHTML = "";
  renderPxTable();
}

function renderPxTable() {
  const tb = $("px-table").querySelector("tbody");
  tb.innerHTML = state.procedures
    .map(
      (p, i) => `<tr>
        <td><span class="tag">${p.code}</span></td>
        <td>${p.description || ""}</td>
        <td><input style="min-width:60px" value="${p.modifiers.join(",")}" onchange="setMods(${i}, this.value)" placeholder="25,95"></td>
        <td><input style="min-width:50px" value="${p.diagnosis_pointers.join(",")}" onchange="setPtrs(${i}, this.value)" placeholder="1,2"></td>
        <td><button onclick="removePx(${i})">✕</button></td></tr>`
    )
    .join("");
}
function setMods(i, v) {
  state.procedures[i].modifiers = v.split(",").map((m) => m.trim()).filter(Boolean);
}
function setPtrs(i, v) {
  state.procedures[i].diagnosis_pointers = v.split(",").map((n) => parseInt(n.trim(), 10)).filter((n) => !isNaN(n));
}
function removePx(i) {
  state.procedures.splice(i, 1);
  renderPxTable();
}

// --- Submit coding & validate --------------------------------------------
async function submitCoding() {
  const payload = {
    diagnoses: state.diagnoses.map((d, i) => ({
      code: d.code,
      system: d.system,
      description: d.description,
      is_principal: d.is_principal,
      sequence: i + 1,
    })),
    procedures: state.procedures.map((p) => ({
      code: p.code,
      system: p.system,
      description: p.description,
      modifiers: p.modifiers,
      diagnosis_pointers: p.diagnosis_pointers,
    })),
  };
  try {
    const v = await api("POST", `/api/coding/encounters/${state.encounterId}/code`, payload);
    renderValidation(v);
    await loadEncounters();
  } catch (e) {
    alert("Coding failed: " + JSON.stringify(e.data));
  }
}

function renderValidation(v) {
  const head = v.billable
    ? `<span class="status-ok">✓ Billable</span>`
    : `<span class="status-bad">✗ ${v.error_count} blocking error(s)</span>`;
  $("validation-summary").innerHTML =
    `${head} <span class="muted">· ${v.error_count} errors · ${v.warning_count} warnings · ${v.encounter_class}</span>`;

  let html = "";
  if (v.global_issues?.length) {
    html += "<h3>Encounter-level edits</h3>" + renderIssues(v.global_issues);
  }
  for (const r of v.results) {
    if (!r.issues.length) continue;
    html += `<h3>${r.type} ${r.code}</h3>` + renderIssues(r.issues);
  }
  $("validation-detail").innerHTML = html || '<p class="muted">All codes passed with no edits.</p>';
}

// --- Billing --------------------------------------------------------------
async function generateClaim() {
  try {
    const r = await api("POST", `/api/billing/encounters/${state.encounterId}/claim`);
    renderValidation(r.validation);
    renderClaim(r.claim);
    await loadEncounters();
  } catch (e) {
    if (e.status === 422) {
      renderValidation(e.data.detail.validation);
      $("claim-result").innerHTML = `<p class="status-bad">${e.data.detail.message}</p>`;
    } else {
      alert("Billing failed: " + JSON.stringify(e.data));
    }
  }
}

function renderClaim(c) {
  const lines = c.lines
    .map(
      (l) =>
        `<tr><td><span class="tag">${l.code}</span></td><td>${l.description || ""}</td>
         <td>${l.modifiers || ""}</td><td>${l.units}</td><td>$${l.line_charge.toFixed(2)}</td></tr>`
    )
    .join("");
  const drg = c.drg_code
    ? `<p><strong>MS-DRG ${c.drg_code}</strong> — ${c.drg_description}</p>`
    : "";
  $("claim-result").innerHTML = `
    <p class="status-ok">Claim ${c.claim_number} · ${c.claim_type} · ${c.status}</p>
    ${drg}
    <table><thead><tr><th>Code</th><th>Description</th><th>Mods</th><th>Units</th><th>Charge</th></tr></thead>
    <tbody>${lines}</tbody></table>
    <p><strong>Total: $${c.total_charge.toFixed(2)}</strong></p>`;
}

async function exportClaim() {
  try {
    const r = await api("POST", `/api/epic/encounters/${state.encounterId}/export-claim`);
    $("claim-result").innerHTML +=
      `<h3>FHIR Claim sent to Epic</h3>
       <p class="status-ok">${r.epic_response.disposition || r.epic_response.outcome || "submitted"}</p>
       <details><summary>View FHIR Claim resource</summary><pre>${JSON.stringify(r.fhir_claim, null, 2)}</pre></details>`;
  } catch (e) {
    alert("Export failed: " + JSON.stringify(e.data));
  }
}

// --- Init -----------------------------------------------------------------
loadEpicStatus();
loadEncounters();
