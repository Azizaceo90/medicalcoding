# Medical Coding & Billing System (Epic FHIR Integration)

A working prototype of a medical **coding and billing** system that integrates
with **Epic** via FHIR R4. It supports both **inpatient** and **outpatient**
coding of clinical documentation using **ICD-10** and **CPT/HCPCS** codes, and
performs **CPT code verification** (the core requirement) through a structured
edits engine.

> ⚠️ **Demonstration system.** The bundled code sets are small, illustrative
> subsets. **CPT® is a registered trademark of the American Medical
> Association (AMA); production use requires an AMA license.** ICD-10-CM/PCS are
> published by CMS/NCHS. Charges, RVUs, NCCI edits and MS-DRG weights here are
> simplified examples, not a substitute for licensed, current code sets.

## What it does

```
Epic (FHIR R4)  ──import──►  Encounter + Patient + Clinical Documentation
                                        │
                          Coder assigns ICD-10 + CPT/HCPCS codes
                                        │
                              CPT VERIFICATION + edits engine
                                        │
                       Claim (professional 837P / institutional 837I + MS-DRG)
                                        │
Epic (FHIR R4)  ◄──export──  FHIR Claim resource
```

### Inpatient vs. outpatient
| | Outpatient | Inpatient |
|---|---|---|
| Diagnoses | ICD-10-CM | ICD-10-CM (principal required) |
| Procedures | CPT / HCPCS | ICD-10-PCS (+ professional CPT) |
| Claim type | Professional (CMS-1500 / 837P) | Institutional (UB-04 / 837I) |
| Reimbursement | Fee schedule per line | **MS-DRG** assignment |

The active encounter's `encounter_class` automatically selects the correct
code systems, validation rules, and claim type.

## CPT verification

`POST /api/coding/verify-cpt` (and the encounter-level validator) run these
edits, returning structured issues with `error` / `warning` / `info` severity:

| Rule | Checks |
|---|---|
| `FORMAT_INVALID` | Valid CPT (Cat I/II/III) or HCPCS Level II syntax |
| `NOT_FOUND` | Code exists in the active code set |
| `DELETED_CODE` | Code is active (not deleted/retired) |
| `POS_MISMATCH` | Setting matches inpatient/outpatient place of service |
| `SEX_EDIT` / `AGE_EDIT` | Code consistent with patient sex / age |
| `MODIFIER_FORMAT` / `MODIFIER_UNEXPECTED` | Modifier syntax + appropriateness |
| `MEDICAL_NECESSITY` | A linked ICD-10 supports the procedure |
| `NCCI_BUNDLED` / `NCCI_BYPASSED` | Procedure-to-procedure bundling edits |
| `NO_PRINCIPAL_DX`, `NONBILLABLE_DX`, `PCS_OUTPATIENT`, … | Diagnosis edits |

Billing is **blocked** (`HTTP 422`) while any `error`-severity edit is unresolved.

## Deploy a live instance (public URL)

The app is container-ready and runs on any host. The fastest no-setup option is
**Render** (free tier, gives an `https://` URL):

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Azizaceo90/medicalcoding/tree/claude/affectionate-maxwell-z8WYm)

1. Click the button (or go to <https://dashboard.render.com> → **New → Blueprint**
   and connect this repo/branch). Render reads `render.yaml` automatically.
2. Approve the free **web service** and wait for the build.
3. Open the `https://medical-coding-billing-XXXX.onrender.com` URL Render gives
   you — that's your live, shareable link.

Other hosts:
- **Railway / Fly.io / Cloud Run** — use the included `Dockerfile`
  (`fly launch`, `railway up`, or `gcloud run deploy --source .`).
- **Any Docker host** — `docker build -t medcoding . && docker run -p 8000:8000 medcoding`.

## Quick start

```bash
pip install -r requirements.txt

# (optional) load the two sample Epic cases
python -m app.seed

python run.py            # http://127.0.0.1:8000
```

Open <http://127.0.0.1:8000> for the workflow UI, or
<http://127.0.0.1:8000/docs> for the OpenAPI explorer.

### Try it in the UI
1. **Import** the outpatient or inpatient case from the Epic sandbox.
2. **Verify a CPT code** (e.g. `99214`, modifier `25`).
3. **Assign codes** by searching ICD-10 and CPT, set the principal diagnosis and
   diagnosis pointers.
4. **Save & validate** to run the edits engine.
5. **Generate the claim** and **export the FHIR Claim** back to Epic.

## API overview

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/epic/status` | Epic connection mode |
| `POST` | `/api/epic/import` | Import patient/encounter/docs from Epic |
| `POST` | `/api/epic/encounters/{id}/export-claim` | Export FHIR Claim to Epic |
| `GET` | `/api/coding/search/icd` · `/cpt` | Code lookup |
| `POST` | `/api/coding/verify-cpt` | **Verify a single CPT/HCPCS code** |
| `POST` | `/api/coding/encounters/{id}/code` | Save coding + validate encounter |
| `GET` | `/api/coding/encounters/{id}/validate` | Re-run edits |
| `POST` | `/api/billing/encounters/{id}/claim` | Generate claim (after edits pass) |
| `GET/POST` | `/api/patients`, `/api/encounters` | CRUD |

## Configuration (environment variables)

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `sqlite:///medicalcoding.db` | Any SQLAlchemy URL (e.g. Postgres) |
| `EPIC_MOCK_MODE` | `true` | `false` to call a real Epic FHIR endpoint |
| `EPIC_FHIR_BASE_URL` | Epic public sandbox R4 | FHIR base URL |
| `EPIC_CLIENT_ID` / `EPIC_CLIENT_SECRET` | — | SMART backend-services OAuth2 |
| `EPIC_TOKEN_URL` | Epic sandbox token URL | OAuth2 token endpoint |
| `MEDICARE_CONVERSION_FACTOR` | `32.74` | RVU→charge fallback |

In **mock mode** (default) no network calls are made — import/export use canned
FHIR resources, so the full pipeline runs offline.

## Project layout

```
app/
  coding/      code sets, ICD & CPT lookups, verification/edits engine
  billing/     charge calculation, MS-DRG grouping, claim assembly
  epic/        FHIR R4 client + resource mappers (Patient/Encounter/Claim)
  routers/     FastAPI endpoints
  static/      single-page UI
data/          ICD-10 / CPT / NCCI + medical-necessity reference JSON
tests/         unit + end-to-end API tests
```

## Tests

```bash
python -m pytest -q
```

Covers CPT format/edit verification, NCCI bundling, encounter validation,
MS-DRG assignment, and the full import→code→bill→export API flow.

## Production notes

This prototype intentionally omits things a real deployment needs: licensed and
current ICD/CPT/HCPCS/NCCI/MS-DRG data, the full CMS grouper, SMART-on-FHIR
authorization with audit logging, PHI encryption at rest/in transit, and
HIPAA-compliant access controls. Treat it as an architectural reference.
```
