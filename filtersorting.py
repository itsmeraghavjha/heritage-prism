"""
Heritage Portal — Frontend Filter Fix Patcher
Applies role-aware filter locking to index.html:
  - ZH  : zone locked, can filter by region + plant + milk
  - RH  : zone + region locked, can filter by plant + milk
  - Plant: fully locked (no sub-filtering)
  - CXO : unchanged — full control

Run: python patch_index.py
A backup is written to index.html.bak before any changes.
"""

import re
import shutil
import sys

# ── CONFIG ───────────────────────────────────────────────────────────────────
HTML_PATH   = r"templates/index.html"    # adjust path if needed
BACKUP_PATH = r"templates/index.html.bak"

# ─────────────────────────────────────────────────────────────────────────────

def apply(src: str, label: str, old: str, new: str) -> str:
    if old not in src:
        print(f"  ✗  PATCH FAILED — '{label}' anchor not found. Skipping.")
        return src
    result = src.replace(old, new, 1)
    print(f"  ✓  {label}")
    return result


def main():
    try:
        with open(HTML_PATH, "r", encoding="utf-8") as f:
            src = f.read()
    except FileNotFoundError:
        print(f"ERROR: {HTML_PATH} not found. Edit HTML_PATH at the top of this script.")
        sys.exit(1)

    shutil.copy(HTML_PATH, BACKUP_PATH)
    print(f"Backup → {BACKUP_PATH}\n")

    # ── PATCH 1 ── Add LOCKED_SCOPE variable after gF declaration ────────────
    src = apply(src, "Add LOCKED_SCOPE variable",
        old="let D=null, charts={}, gF={zone:'',region:'',plant_code:'', milk:''};",
        new=("let D=null, charts={}, gF={zone:'',region:'',plant_code:'', milk:''};\n"
             "let LOCKED_SCOPE = { zone: '', region: '', plant_code: '' }; // min scope for current user role")
    )

    # ── PATCH 2 ── Replace the old blanket-disable block in boot() ───────────
    src = apply(src, "Replace role-disable block in boot()",
        old=(
            "      if(u.role==='plant'||u.role==='rh'||u.role==='zh'){ \n"
            "        ['gfZone','gfRegion','gfPlant'].forEach(id=>{ const el=document.getElementById(id); if(el) el.disabled=true; }); \n"
            "        document.getElementById('scopeBtn').style.opacity='0.5'; \n"
            "        document.getElementById('scopeBtn').style.pointerEvents='none'; \n"
            "      }"
        ),
        new=(
            "      // Build LOCKED_SCOPE BEFORE populateFilters so cascading dropdowns are correct\n"
            "      if (u.role === 'zh') {\n"
            "        LOCKED_SCOPE = { zone: u.scope_zone||'', region: '', plant_code: '' };\n"
            "      } else if (u.role === 'rh') {\n"
            "        LOCKED_SCOPE = { zone: u.scope_zone||'', region: u.scope_region||'', plant_code: '' };\n"
            "      } else if (u.role === 'plant') {\n"
            "        LOCKED_SCOPE = { zone: u.scope_zone||'', region: u.scope_region||'', plant_code: String(u.scope_plant||'') };\n"
            "      }\n"
            "      // Pre-load gF so populateFilters cascades region/plant options correctly\n"
            "      gF.zone       = LOCKED_SCOPE.zone;\n"
            "      gF.region     = LOCKED_SCOPE.region;\n"
            "      gF.plant_code = LOCKED_SCOPE.plant_code;"
        )
    )

    # ── PATCH 3 ── After populateFilters(), disable locked dropdowns ──────────
    src = apply(src, "Disable locked dropdowns after populateFilters",
        old="msg('Building filters…'); fill(72); populateFilters();\n    msg('Loading targets…');",
        new=(
            "msg('Building filters…'); fill(72); populateFilters();\n"
            "    // Disable locked dropdowns (must run AFTER populateFilters so option values exist)\n"
            "    if (D.user && D.user.role !== 'cxo' && D.user.role !== 'admin') {\n"
            "      if (LOCKED_SCOPE.zone)  { const el=document.getElementById('gfZone');  if(el) el.disabled=true; }\n"
            "      if (LOCKED_SCOPE.region){ const el=document.getElementById('gfRegion');if(el) el.disabled=true; }\n"
            "      if (LOCKED_SCOPE.plant_code) {\n"
            "        const el=document.getElementById('gfPlant'); if(el) el.disabled=true;\n"
            "        document.getElementById('scopeBtn').style.opacity='0.5';\n"
            "        document.getElementById('scopeBtn').style.pointerEvents='none';\n"
            "      }\n"
            "      updateScopeLabel();\n"
            "    }\n"
            "    msg('Loading targets…');"
        )
    )

    # ── PATCH 4 ── Add LOCKED_SCOPE enforcement inside applyFilter() ─────────
    src = apply(src, "Enforce LOCKED_SCOPE inside applyFilter",
        old=(
            "  gF.zone = z;\n"
            "  gF.region = r;\n"
            "  gF.plant_code = p;\n"
            "  gF.milk = m;\n"
            "\n"
            "  // Rebuild the options so dropdowns only show valid siblings"
        ),
        new=(
            "  // Enforce locked scope — user can never filter above their assignment\n"
            "  if (LOCKED_SCOPE.zone)       z = LOCKED_SCOPE.zone;\n"
            "  if (LOCKED_SCOPE.region)     r = LOCKED_SCOPE.region;\n"
            "  if (LOCKED_SCOPE.plant_code) p = LOCKED_SCOPE.plant_code;\n"
            "\n"
            "  gF.zone = z;\n"
            "  gF.region = r;\n"
            "  gF.plant_code = p;\n"
            "  gF.milk = m;\n"
            "\n"
            "  // Rebuild the options so dropdowns only show valid siblings"
        )
    )

    # ── PATCH 5 ── Replace the inline scope-label block at bottom of applyFilter
    # (the block that sets scopeLabel, fbChip, fbClear, fbAll, sdClear)
    src = apply(src, "Replace inline scope-label block in applyFilter with updateScopeLabel()",
        old=(
            "  const label = [gF.zone, gF.region, pLabel, mLabel].filter(Boolean).join(' › ') || 'All India';\n"
            "  \n"
            "  document.getElementById('scopeLabel').textContent = label;\n"
            "  document.getElementById('fbChip').classList.toggle('on', active);\n"
            "  document.getElementById('fbChipTxt').textContent = label;\n"
            "  document.getElementById('fbClear').classList.toggle('on', active);\n"
            "  document.getElementById('fbAll').style.display = active ? 'none' : '';\n"
            "  document.getElementById('sdClear').classList.toggle('on', active);\n"
            "  \n"
            "  // Refresh the data on the active tab"
        ),
        new=(
            "  updateScopeLabel();\n"
            "\n"
            "  // Refresh the data on the active tab"
        )
    )

    # ── PATCH 6 ── Replace clearFilter() ─────────────────────────────────────
    src = apply(src, "Replace clearFilter()",
        old=(
            "function clearFilter() {\n"
            "  // <-- ADD 'gfMilk' TO THIS ARRAY -->\n"
            "  ['gfZone','gfRegion','gfPlant','gfMilk'].forEach(id => document.getElementById(id).value = '');\n"
            "  applyFilter();\n"
            "}"
        ),
        new=(
            "function clearFilter() {\n"
            "  // Reset to locked scope (never to fully empty — respects role assignment)\n"
            "  document.getElementById('gfZone').value   = LOCKED_SCOPE.zone;\n"
            "  document.getElementById('gfRegion').value = LOCKED_SCOPE.region;\n"
            "  document.getElementById('gfPlant').value  = LOCKED_SCOPE.plant_code;\n"
            "  document.getElementById('gfMilk').value   = '';\n"
            "  gF.zone       = LOCKED_SCOPE.zone;\n"
            "  gF.region     = LOCKED_SCOPE.region;\n"
            "  gF.plant_code = LOCKED_SCOPE.plant_code;\n"
            "  gF.milk       = '';\n"
            "  updateFilterOptions();\n"
            "  updateScopeLabel();\n"
            "  const tab = document.querySelector('.tab.on')?.getAttribute('onclick')?.match(/'(\\w+)'/)?.[1] || 'scorecard';\n"
            "  renderTab(tab);\n"
            "}"
        )
    )

    # ── PATCH 7 ── Add updateScopeLabel() function after clearFilter() ────────
    src = apply(src, "Add updateScopeLabel() function",
        old="function toggleScope() {",
        new=(
            "function updateScopeLabel() {\n"
            "  const z=gF.zone, r=gF.region, m=gF.milk;\n"
            "  const pSel=document.getElementById('gfPlant');\n"
            "  const pRaw=pSel&&pSel.value?(pSel.options[pSel.selectedIndex]?.text||pSel.value):null;\n"
            "  const pTxt=(pRaw&&pRaw!=='All Plants')?pRaw:null;\n"
            "  const parts=[z,r,pTxt,m].filter(Boolean);\n"
            "  const label=parts.length?parts.join(' › '):'All India';\n"
            "  document.getElementById('scopeLabel').textContent=label;\n"
            "  // 'active' only for filters the user added ON TOP of their locked scope\n"
            "  const aboveLocked=(!LOCKED_SCOPE.region&&!!gF.region)||(!LOCKED_SCOPE.plant_code&&!!gF.plant_code)||!!gF.milk;\n"
            "  document.getElementById('fbChip').classList.toggle('on',aboveLocked);\n"
            "  document.getElementById('fbChipTxt').textContent=label;\n"
            "  document.getElementById('fbClear').classList.toggle('on',aboveLocked);\n"
            "  document.getElementById('fbAll').style.display=aboveLocked?'none':'';\n"
            "  document.getElementById('sdClear').classList.toggle('on',aboveLocked);\n"
            "}\n\n"
            "function toggleScope() {"
        )
    )

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(src)

    print(f"\nDone. Patched file written to {HTML_PATH}")
    print("If anything looks wrong, restore from backup: copy templates/index.html.bak templates/index.html")


if __name__ == "__main__":
    main()