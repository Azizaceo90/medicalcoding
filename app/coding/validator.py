"""CPT verification + encounter-level coding validation.

The verifier returns structured ``Issue`` records (severity + machine-readable
``rule`` id + human message) rather than raising, so a UI can surface every
problem at once. Severity ``error`` blocks billing; ``warning`` / ``info`` do
not but should be reviewed by a coder.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

from app.coding import cpt as cpt_lib
from app.coding import icd as icd_lib
from app.coding import codesets

Severity = str  # "error" | "warning" | "info"


@dataclass
class Issue:
    rule: str
    severity: Severity
    message: str
    code: str | None = None

    def dict(self) -> dict:
        return asdict(self)


@dataclass
class VerificationResult:
    code: str
    valid: bool
    category: str | None = None
    description: str | None = None
    issues: list[Issue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    def dict(self) -> dict:
        return {
            "code": self.code,
            "valid": self.valid,
            "category": self.category,
            "description": self.description,
            "has_errors": self.has_errors,
            "issues": [i.dict() for i in self.issues],
        }


# --------------------------------------------------------------------------- #
# Single-code CPT verification
# --------------------------------------------------------------------------- #
def verify_cpt(
    code: str,
    *,
    modifiers: list[str] | None = None,
    encounter_class: str | None = None,
    patient_sex: str | None = None,
    patient_age: int | None = None,
    supporting_icd: list[str] | None = None,
) -> VerificationResult:
    """Verify a single CPT/HCPCS code against every applicable edit.

    Every argument except ``code`` is optional; checks that lack their context
    (e.g. no patient age supplied) are simply skipped rather than failing.
    """
    code = code.strip().upper()
    modifiers = [m.strip().upper() for m in (modifiers or []) if m.strip()]
    issues: list[Issue] = []

    # 1. Format ------------------------------------------------------------- #
    category = cpt_lib.classify_format(code)
    if category is None:
        issues.append(
            Issue(
                "FORMAT_INVALID",
                "error",
                f"'{code}' is not a syntactically valid CPT or HCPCS code.",
                code,
            )
        )
        return VerificationResult(code=code, valid=False, issues=issues)

    # 2. Existence in the code set ------------------------------------------ #
    row = cpt_lib.lookup(code)
    if row is None:
        issues.append(
            Issue(
                "NOT_FOUND",
                "error",
                f"'{code}' has a valid {category} format but is not present "
                f"in the active CPT/HCPCS code set.",
                code,
            )
        )
        return VerificationResult(
            code=code, valid=False, category=category, issues=issues
        )

    description = row.get("short")

    # 3. Active status ------------------------------------------------------ #
    if row.get("status") != "active":
        when = row.get("deleted_date", "")
        issues.append(
            Issue(
                "DELETED_CODE",
                "error",
                f"'{code}' is {row.get('status')}"
                + (f" (effective {when})" if when else "")
                + "; choose an active replacement code.",
                code,
            )
        )

    # 4. Place of service / encounter class -------------------------------- #
    allowed_pos = row.get("pos", [])
    if encounter_class and allowed_pos and encounter_class not in allowed_pos:
        issues.append(
            Issue(
                "POS_MISMATCH",
                "warning",
                f"'{code}' is typically reported in {', '.join(allowed_pos)} "
                f"settings, but this is an {encounter_class} encounter.",
                code,
            )
        )

    # 5. Sex edit ----------------------------------------------------------- #
    code_sex = row.get("sex", "any")
    if patient_sex and code_sex not in ("any", patient_sex.lower()):
        issues.append(
            Issue(
                "SEX_EDIT",
                "error",
                f"'{code}' is sex-specific ({code_sex}) and is inconsistent "
                f"with patient sex '{patient_sex}'.",
                code,
            )
        )

    # 6. Age edit ----------------------------------------------------------- #
    if patient_age is not None:
        amin, amax = row.get("age_min", 0), row.get("age_max", 124)
        if not (amin <= patient_age <= amax):
            issues.append(
                Issue(
                    "AGE_EDIT",
                    "warning",
                    f"'{code}' is expected for ages {amin}-{amax}; patient "
                    f"age is {patient_age}.",
                    code,
                )
            )

    # 7. Modifiers ---------------------------------------------------------- #
    valid_mods = set(row.get("valid_modifiers", []))
    for mod in modifiers:
        if not cpt_lib.is_valid_modifier_format(mod):
            issues.append(
                Issue(
                    "MODIFIER_FORMAT",
                    "error",
                    f"Modifier '{mod}' is not a valid 2-character modifier.",
                    code,
                )
            )
        elif valid_mods and mod not in valid_mods:
            issues.append(
                Issue(
                    "MODIFIER_UNEXPECTED",
                    "warning",
                    f"Modifier '{mod}' is not on the expected list for "
                    f"'{code}' ({', '.join(sorted(valid_mods)) or 'none'}).",
                    code,
                )
            )

    # 8. Medical necessity (does any linked ICD support this CPT?) ---------- #
    if supporting_icd is not None:
        necessity = codesets.medical_necessity_index().get(code)
        if necessity is not None:
            linked = {c.strip().upper() for c in supporting_icd}
            if not (linked & necessity):
                issues.append(
                    Issue(
                        "MEDICAL_NECESSITY",
                        "warning",
                        f"None of the linked diagnoses {sorted(linked) or '[]'} "
                        f"support medical necessity for '{code}'. Expected one "
                        f"of: {', '.join(sorted(necessity))}.",
                        code,
                    )
                )

    valid = not any(i.severity == "error" for i in issues)
    return VerificationResult(
        code=code,
        valid=valid,
        category=category,
        description=description,
        issues=issues,
    )


# --------------------------------------------------------------------------- #
# NCCI procedure-to-procedure bundling across a set of codes
# --------------------------------------------------------------------------- #
def check_ncci(procedures: list[dict]) -> list[Issue]:
    """Detect NCCI PTP bundling conflicts within one encounter's procedures.

    ``procedures`` items: {"code": str, "modifiers": list[str]}.
    modifier_indicator semantics: "0" = never unbundle; "1" = a bypass
    modifier (e.g. 59, XS) may allow both; "9" = edit not active.
    """
    issues: list[Issue] = []
    ncci = codesets.ncci_index()
    bypass = {"59", "XE", "XS", "XP", "XU", "91"}

    codes = [(p["code"].strip().upper(), set(p.get("modifiers", []))) for p in procedures]
    for i, (c1, _) in enumerate(codes):
        for j, (c2, mods2) in enumerate(codes):
            if i == j:
                continue
            edit = ncci.get((c1, c2))
            if not edit:
                continue
            indicator = edit.get("modifier_indicator", "0")
            if indicator == "9":
                continue
            if indicator == "1" and (mods2 & bypass):
                issues.append(
                    Issue(
                        "NCCI_BYPASSED",
                        "info",
                        f"'{c2}' is bundled into '{c1}' but a bypass modifier "
                        f"is appended — ensure documentation supports a "
                        f"distinct service. {edit['rationale']}",
                        c2,
                    )
                )
            else:
                issues.append(
                    Issue(
                        "NCCI_BUNDLED",
                        "error",
                        f"'{c2}' is not separately reportable with '{c1}'. "
                        f"{edit['rationale']}",
                        c2,
                    )
                )
    return issues


# --------------------------------------------------------------------------- #
# Whole-encounter validation
# --------------------------------------------------------------------------- #
def validate_encounter(
    *,
    encounter_class: str,
    patient_sex: str | None,
    patient_age: int | None,
    diagnoses: list[dict],
    procedures: list[dict],
) -> dict:
    """Validate every diagnosis and procedure on an encounter.

    diagnoses items: {"code", "system", "is_principal"}
    procedures items: {"code", "modifiers", "diagnosis_pointers"}
    Returns a serialisable summary with per-code results and global issues.
    """
    results: list[dict] = []
    global_issues: list[Issue] = []

    # --- Diagnoses -------------------------------------------------------- #
    dx_codes = [d["code"].strip().upper() for d in diagnoses]
    principal = [d for d in diagnoses if d.get("is_principal")]

    if not diagnoses:
        global_issues.append(
            Issue("NO_DIAGNOSIS", "error", "Encounter has no diagnosis codes.")
        )
    if len(principal) == 0 and diagnoses:
        global_issues.append(
            Issue(
                "NO_PRINCIPAL_DX",
                "error" if encounter_class == "inpatient" else "warning",
                "No principal diagnosis is designated. Inpatient claims "
                "require a principal diagnosis for MS-DRG assignment.",
            )
        )
    if len(principal) > 1:
        global_issues.append(
            Issue(
                "MULTIPLE_PRINCIPAL_DX",
                "error",
                "More than one diagnosis is flagged as principal.",
            )
        )

    seen_dx: set[str] = set()
    for d in diagnoses:
        code = d["code"].strip().upper()
        system = d.get("system", "ICD-10-CM")
        dx_issues: list[Issue] = []

        if code in seen_dx:
            dx_issues.append(Issue("DUPLICATE_DX", "warning", f"Duplicate diagnosis '{code}'.", code))
        seen_dx.add(code)

        if system == "ICD-10-PCS":
            if not icd_lib.is_valid_pcs_format(code):
                dx_issues.append(Issue("FORMAT_INVALID", "error", f"'{code}' is not a valid ICD-10-PCS format.", code))
            elif icd_lib.lookup_pcs(code) is None:
                dx_issues.append(Issue("NOT_FOUND", "error", f"ICD-10-PCS '{code}' not found in code set.", code))
            if encounter_class != "inpatient":
                dx_issues.append(Issue("PCS_OUTPATIENT", "error", f"ICD-10-PCS procedure '{code}' may only be reported on inpatient claims.", code))
        else:
            row = icd_lib.lookup_cm(code)
            if not icd_lib.is_valid_cm_format(code):
                dx_issues.append(Issue("FORMAT_INVALID", "error", f"'{code}' is not a valid ICD-10-CM format.", code))
            elif row is None:
                dx_issues.append(Issue("NOT_FOUND", "error", f"ICD-10-CM '{code}' not found in code set.", code))
            elif not row.get("billable", True):
                dx_issues.append(Issue("NONBILLABLE_DX", "error", f"'{code}' is a non-billable header; a more specific code is required.", code))
            if row and patient_sex and row.get("sex", "any") not in ("any", patient_sex.lower()):
                dx_issues.append(Issue("SEX_EDIT", "error", f"Diagnosis '{code}' is sex-specific and inconsistent with patient sex.", code))

        results.append(
            {
                "type": "diagnosis",
                "code": code,
                "system": system,
                "valid": not any(i.severity == "error" for i in dx_issues),
                "issues": [i.dict() for i in dx_issues],
            }
        )

    # --- Procedures ------------------------------------------------------- #
    for p in procedures:
        code = p["code"].strip().upper()
        mods = p.get("modifiers", [])
        pointers = p.get("diagnosis_pointers", [])
        # Resolve diagnosis pointers (1-based) to actual ICD codes for the
        # medical-necessity check.
        linked_icd = [dx_codes[i - 1] for i in pointers if 1 <= i <= len(dx_codes)]

        res = verify_cpt(
            code,
            modifiers=mods,
            encounter_class=encounter_class,
            patient_sex=patient_sex,
            patient_age=patient_age,
            supporting_icd=linked_icd if pointers else None,
        )
        d = res.dict()
        d["type"] = "procedure"
        # Flag procedures with no diagnosis pointer (payers require linkage).
        if not pointers:
            d["issues"].append(
                Issue(
                    "NO_DX_POINTER",
                    "warning",
                    f"Procedure '{code}' has no diagnosis pointer; payers "
                    f"require each service be linked to a diagnosis.",
                    code,
                ).dict()
            )
            d["valid"] = d["valid"] and True  # warning does not invalidate
        results.append(d)

    # --- NCCI across procedures ------------------------------------------- #
    ncci_issues = check_ncci(
        [{"code": p["code"], "modifiers": p.get("modifiers", [])} for p in procedures]
    )
    global_issues.extend(ncci_issues)

    error_count = sum(
        1
        for r in results
        for i in r["issues"]
        if i["severity"] == "error"
    ) + sum(1 for i in global_issues if i.severity == "error")

    return {
        "encounter_class": encounter_class,
        "billable": error_count == 0,
        "error_count": error_count,
        "warning_count": sum(
            1 for r in results for i in r["issues"] if i["severity"] == "warning"
        )
        + sum(1 for i in global_issues if i.severity == "warning"),
        "results": results,
        "global_issues": [i.dict() for i in global_issues],
    }
