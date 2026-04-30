"""
Heritage Portal — End-to-End bootstrap() Simulation for RH User
Simulates exactly what the server does when an RH user calls /api/bootstrap
Run: python diagnose_scope3.py
"""

import sqlite3
import json
import time


from pathlib import Path

BASE_DIR = Path(__file__).parent.absolute()

SQLITE_PATH  = str(BASE_DIR / "Database" / "portal.db")

# ── Pick an RH user to simulate (change this to the one that's showing zeros)
TEST_RH_USERNAME = "rh.krishnagiri@heritagefoods.in"

def get_db():
    conn = sqlite3.connect(SQLITE_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def section(title):
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)

def ok(msg):   print(f"  ✅  {msg}")
def warn(msg): print(f"  ⚠️   {msg}")
def fail(msg): print(f"  ❌  {msg}")
def info(msg): print(f"  ℹ️   {msg}")

conn = get_db()
snap_date = conn.execute("SELECT MAX(snapshot_date) FROM proc_period_snapshot").fetchone()[0]

# ─────────────────────────────────────────────────────────────
# Step 0: Get the RH user
# ─────────────────────────────────────────────────────────────
section(f"Step 0 — RH User: {TEST_RH_USERNAME}")
user = conn.execute(
    "SELECT * FROM users WHERE username=?", (TEST_RH_USERNAME,)
).fetchone()
if not user:
    fail(f"User '{TEST_RH_USERNAME}' not found. Edit TEST_RH_USERNAME at the top of this script.")
    conn.close()
    exit(1)

scope = {
    "zone":       user["scope_zone"]   or "",
    "region":     user["scope_region"] or "",
    "plant_code": str(user["scope_plant"] or ""),
}
info(f"role={user['role']}, scope={scope}")

# ─────────────────────────────────────────────────────────────
# Step 1: Simulate _build_cache — fetch hpc_list exactly as the server does
# ─────────────────────────────────────────────────────────────
section("Step 1 — Fetch hpc_list from DB (as _build_cache does)")

yr_mth_hpc = (
    "yr=(SELECT MAX(yr) FROM proc_monthly_hpc) AND "
    "mth=(SELECT MAX(mth) FROM proc_monthly_hpc "
    "WHERE yr=(SELECT MAX(yr) FROM proc_monthly_hpc))"
)

hpc_list_raw = conn.execute(f"""
    WITH true_farmers AS (
        SELECT hpc_plant_key, COUNT(DISTINCT farmer_code) AS distinct_farmers
        FROM proc_monthly_farmer
        WHERE yr = (SELECT MAX(yr) FROM proc_monthly_farmer)
          AND mth = (SELECT MAX(mth) FROM proc_monthly_farmer WHERE yr = (SELECT MAX(yr) FROM proc_monthly_farmer))
          AND farmer_code_seq != '9999'
        GROUP BY hpc_plant_key
    )
    SELECT s.hpc_plant_key, s.hpc_name, s.plant_name, s.plant_code, s.region, s.zone,
           COALESCE(hc.hpr_name, s.hpr_name) AS hpr_name,
           COALESCE(hc.mobile_no, s.mobile_no) AS mobile_no,
           ROUND(s.mtd,1) AS mtd, ROUND(s.lm,1) AS lm, ROUND(s.lmtd,1) AS lmtd,
           ROUND(s.lymtd,1) AS lymtd,
           s.yoy_growth_pct, s.mom_growth_pct,
           COALESCE(tf.distinct_farmers, 0) AS mtd_farmers,
           ROUND(s.lm_farmers,0) AS lm_farmers,
           ROUND(s.mtd_avg_fat,3) AS mtd_avg_fat,
           ROUND(s.mtd_rate,2) AS mtd_rate,
           ROUND(s.mtd_payout,0) AS mtd_payout
    FROM proc_period_snapshot s
    LEFT JOIN true_farmers tf ON s.hpc_plant_key = tf.hpc_plant_key
    LEFT JOIN hpr_contacts hc ON s.hpc_plant_key = hc.hpc_plant_key
    WHERE s.snapshot_date=?
    ORDER BY s.mtd DESC
""", (snap_date,)).fetchall()
hpc_list_raw = [dict(r) for r in hpc_list_raw]
ok(f"Total HPCs in full hpc_list: {len(hpc_list_raw)}")

# ─────────────────────────────────────────────────────────────
# Step 2: Simulate _filter_by_scope for this RH user
# ─────────────────────────────────────────────────────────────
section("Step 2 — _filter_by_scope(hpc_list, scope)")

def _filter_by_scope(arr, scope, skip_plant=False):
    zone   = scope.get("zone", "")
    region = scope.get("region", "")
    plant  = scope.get("plant_code", "")
    if not zone and not region and not plant:
        return arr
    out = []
    for item in arr:
        if zone   and item.get("zone",   "") != zone:   continue
        if region and item.get("region", "") != region: continue
        if not skip_plant and plant:
            item_plant = str(item.get("plant_code") or "")
            if item_plant and item_plant != str(plant):
                continue
            elif not item_plant:
                hpk = str(item.get("hpc_plant_key") or "")
                if hpk and not (hpk.startswith(str(plant)+"-") or
                                hpk.startswith(str(plant)+"_") or
                                hpk == str(plant)):
                    continue
        out.append(item)
    return out

filtered_hpcs = _filter_by_scope(hpc_list_raw, scope)
ok(f"HPCs after _filter_by_scope: {len(filtered_hpcs)}")

if len(filtered_hpcs) == 0:
    fail("ZERO HPCs after filtering — this is why the dashboard shows zeros!")
    info(f"Scope used: zone='{scope['zone']}', region='{scope['region']}'")
    # Show what values actually exist
    actual_zones   = {h['zone']   for h in hpc_list_raw}
    actual_regions = {h['region'] for h in hpc_list_raw}
    info(f"Zones in data:   {sorted(actual_zones)}")
    info(f"Regions in data: {sorted(actual_regions)}")
else:
    # Show sample of what was matched
    info("Sample of matched HPCs:")
    for h in filtered_hpcs[:3]:
        print(f"    {h['hpc_plant_key']} | {h['hpc_name']} | zone={h['zone']} | region={h['region']} | mtd={h['mtd']}")
    print(f"    ... and {len(filtered_hpcs)-3} more")

# ─────────────────────────────────────────────────────────────
# Step 3: Simulate _recompute_snapshot
# ─────────────────────────────────────────────────────────────
section("Step 3 — _recompute_snapshot output")

total_mtd   = sum(h.get("mtd",   0) or 0 for h in filtered_hpcs)
total_lymtd = sum(h.get("lymtd", 0) or 0 for h in filtered_hpcs)
total_lm    = sum(h.get("lm",    0) or 0 for h in filtered_hpcs)
total_lmtd  = sum(h.get("lmtd",  0) or 0 for h in filtered_hpcs)
total_farmers = int(sum(h.get("mtd_farmers", 0) or 0 for h in filtered_hpcs))

print(f"""
    mtd            = {total_mtd}
    lymtd          = {total_lymtd}
    lm             = {total_lm}
    lmtd           = {total_lmtd}
    total_farmers  = {total_farmers}
    yoy_pct        = {round((total_mtd - total_lymtd) / total_lymtd * 100, 1) if total_lymtd else 'N/A'}%
    total_hpcs     = {len(filtered_hpcs)}
""")

if total_mtd == 0 and total_lymtd == 0:
    fail("Snapshot recompute returns ALL ZEROS — confirms the zeros on dashboard")
elif total_mtd == 0:
    warn("MTD is zero but LYMTD is not — partial data issue")
else:
    ok("Snapshot values look correct")

# Check each HPC's mtd individually
zero_mtd = [h for h in filtered_hpcs if not h.get("mtd")]
nonzero_mtd = [h for h in filtered_hpcs if h.get("mtd")]
info(f"HPCs with mtd=0:     {len(zero_mtd)}")
info(f"HPCs with mtd>0:     {len(nonzero_mtd)}")
if nonzero_mtd:
    ok(f"Non-zero mtd example: {nonzero_mtd[0]['hpc_name']} = {nonzero_mtd[0]['mtd']}")

# ─────────────────────────────────────────────────────────────
# Step 4: Simulate monthly_hpc fetch and filter
# ─────────────────────────────────────────────────────────────
section("Step 4 — monthly_hpc fetch and filter")

monthly_hpc_raw = conn.execute(f"""
    SELECT mh.hpc_plant_key, mh.milk_type,
           s.zone, s.region, s.plant_code,
           ROUND(mh.total_qty_ltr,0) AS total_qty_ltr,
           ROUND(mh.total_net_price,0) AS total_net_price
    FROM proc_monthly_hpc mh
    JOIN proc_period_snapshot s ON mh.hpc_plant_key = s.hpc_plant_key
     AND s.snapshot_date = ?
    WHERE {yr_mth_hpc}
""", (snap_date,)).fetchall()
monthly_hpc_raw = [dict(r) for r in monthly_hpc_raw]

filtered_mhpc = _filter_by_scope(monthly_hpc_raw, scope)
ok(f"monthly_hpc rows after filter: {len(filtered_mhpc)}")
total_ltr = sum(m.get("total_qty_ltr", 0) or 0 for m in filtered_mhpc)
total_pay = sum(m.get("total_net_price", 0) or 0 for m in filtered_mhpc)
info(f"Total qty_ltr: {total_ltr:,.0f}, Total payout: ₹{total_pay:,.0f}")

if len(filtered_mhpc) == 0:
    fail("monthly_hpc is empty after filter — payout and productivity metrics will be zero")

# ─────────────────────────────────────────────────────────────
# Step 5: Simulate scorecard_history SQL for this RH user
# ─────────────────────────────────────────────────────────────
section("Step 5 — scorecard_history SQL simulation")

scope_clauses, scope_params = [], []
if scope.get("zone"):
    scope_clauses.append("s.zone = ?")
    scope_params.append(scope["zone"])
if scope.get("region"):
    scope_clauses.append("s.region = ?")
    scope_params.append(scope["region"])
scope_and = ("AND " + " AND ".join(scope_clauses)) if scope_clauses else ""

cur = conn.execute("SELECT yr, mth FROM proc_monthly_hpc ORDER BY yr DESC, mth DESC LIMIT 1").fetchone()
curr_yr, curr_mth = cur["yr"], cur["mth"]
lm_yr  = curr_yr  if curr_mth > 1 else curr_yr - 1
lm_mth = curr_mth - 1 if curr_mth > 1 else 12

info(f"Scorecard period: LM = {lm_yr}-{lm_mth:02d}")
info(f"Scope clauses: {scope_and}")
info(f"Scope params:  {scope_params}")

# Test the HPC aggregate query for LM
hpc_agg = conn.execute(f"""
    SELECT SUM(mh.total_qty_ltr) as total_ltr,
           SUM(mh.total_fat_kg) as total_fat_kg,
           SUM(mh.total_net_price) as total_net_price,
           SUM(mh.avg_fat * mh.total_qty_ltr) / NULLIF(SUM(mh.total_qty_ltr), 0) as fat,
           COUNT(DISTINCT mh.hpc_plant_key) as hpcs
    FROM proc_monthly_hpc mh
    JOIN proc_period_snapshot s ON mh.hpc_plant_key = s.hpc_plant_key
     AND s.snapshot_date = ?
    WHERE mh.yr = ? AND mh.mth = ? {scope_and}
""", [snap_date, lm_yr, lm_mth] + scope_params).fetchone()

info(f"Scorecard LM result: total_ltr={hpc_agg['total_ltr']}, fat={hpc_agg['fat']}, hpcs={hpc_agg['hpcs']}")
if not hpc_agg["total_ltr"]:
    fail("Scorecard LM query returns NULL/zero — scorecard will be blank")
else:
    ok(f"Scorecard LM data present: {hpc_agg['total_ltr']:,.0f} litres across {hpc_agg['hpcs']} HPCs")

# ─────────────────────────────────────────────────────────────
# Step 6: Check farmer_rfm filter
# ─────────────────────────────────────────────────────────────
section("Step 6 — farmer_rfm filter")

has_rfm = conn.execute(
    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='proc_farmer_rfm'"
).fetchone()[0]

if has_rfm:
    rfm_count_total = conn.execute("SELECT COUNT(*) FROM proc_farmer_rfm WHERE snapshot_date=?", (snap_date,)).fetchone()[0]
    
    # Simulate the filter
    rfm_raw = conn.execute(f"""
        SELECT r.farmer_code, r.hpc_plant_key, r.region, r.zone,
               CAST(s.plant_code AS TEXT) AS plant_code, r.tier, r.lpd
        FROM proc_farmer_rfm r
        JOIN proc_period_snapshot s ON r.hpc_plant_key = s.hpc_plant_key
         AND s.snapshot_date = ?
        WHERE r.snapshot_date = ?
          AND r.farmer_name NOT LIKE '%SAMPLE MILK%'
    """, (snap_date, snap_date)).fetchall()
    rfm_raw = [dict(r) for r in rfm_raw]
    
    filtered_rfm = _filter_by_scope(rfm_raw, scope)
    info(f"Total RFM rows: {rfm_count_total:,}")
    ok(f"RFM rows after filter: {len(filtered_rfm):,}")
    if len(filtered_rfm) == 0:
        fail("farmer_rfm is empty after filter — farmer table will be blank")
else:
    warn("proc_farmer_rfm table does not exist")

# ─────────────────────────────────────────────────────────────
# Step 7: What does the final bootstrap() response look like?
# ─────────────────────────────────────────────────────────────
section("Step 7 — Final bootstrap() response summary")

print(f"""
    user.role          = {user['role']}
    scope_zone         = '{scope['zone']}'
    scope_region       = '{scope['region']}'

    hpc_list rows      = {len(filtered_hpcs)}
    monthly_hpc rows   = {len(filtered_mhpc)}
    farmer_rfm rows    = {len(filtered_rfm) if has_rfm else 'N/A'}

    snapshot.mtd       = {total_mtd}
    snapshot.lymtd     = {total_lymtd}
    snapshot.farmers   = {total_farmers}
""")

if len(filtered_hpcs) > 0 and total_mtd > 0:
    ok("All data looks correct — if dashboard shows zeros, the issue is in the FRONTEND code")
    warn("Check: does index.html correctly handle the 'rh' role in its rendering logic?")
    warn("Check: is the frontend reading snapshot.mtd or something else for the KPIs?")
elif len(filtered_hpcs) == 0:
    fail("hpc_list is empty — API is returning no data, dashboard will show zeros")
    fail("Check _filter_by_scope and scope values")
else:
    warn("hpc_list has rows but mtd=0 — data issue in proc_period_snapshot")

conn.close()