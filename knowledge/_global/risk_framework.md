# NPL Risk Assessment Framework

How to evaluate and interpret debtor risk profiles under Thai banking standards.

---

## Risk Signal Combinations

### High Recovery Potential (Low Risk)
A debtor is considered high recovery potential when:
- สถานะหลักประกัน = Secured Loan
- Coverage ratio > 1.0 (collateral value > total debt)
- สถานะการประนอมหนี้ = TDR (debtor cooperating)
- กลุ่มการดำเนินงาน = 01 กลุ่มประนอมหนี้
- เกรดทรัพย์ = A or B (quality collateral, marketable)
- เงินรับประเภท CASH สะสมในเดือน YTD > 0 (actively making payments)

### Medium Recovery — Needs Action
- Secured Loan but coverage ratio 0.5–1.0
- Non-TDR but litigation in progress (group 03 or 04) — enforcement may force payment
- TDR but collateral is low quality (grade C or D) — recovery uncertain at auction
- Secured Loan + coverage ratio > 1 but Non-TDR (no cooperation, but asset can be seized)

### Low Recovery / High Loss Risk
- Clean Loan (no collateral) — recovery depends on debtor income only
- กลุ่มล้มละลาย (group 06) — assets under Official Receiver control, timeline years long
- กลุ่มตัดหนี้สูญ (group 07) — already written off, recovery is bonus only
- Coverage ratio = 0 (Clean Loan)
- Non-TDR + no active legal proceedings + zero cash collected
- เกรดทรัพย์ = D (collateral value highly uncertain at auction)

---

## Prioritization for Collection Action

When asked "which debtors should we focus on" or "best candidates for collection":
Priority = debtors with HIGH debt AND HIGH collateral coverage AND cooperative/enforceable status

```python
# High value + recoverable: Secured + coverage >= 1.0
df['coverage_ratio'] = df['มูลค่าหลักประกันตามสัดส่วน (รวมสังหา)'] / df['ภาระหนี้คงเหลือ'].replace(0, float('nan'))
priority = df[
    (df['สถานะหลักประกัน'] == 'Secured Loan') &
    (df['coverage_ratio'] >= 1.0)
].nlargest(10, 'ภาระหนี้คงเหลือ')
```

Additional filters for tighter prioritization:
```python
# Tier 1: Secured + TDR + full coverage
tier1 = df[
    (df['สถานะหลักประกัน'] == 'Secured Loan') &
    (df['สถานะการประนอมหนี้'] == 'TDR') &
    (df['มูลค่าหลักประกันตามสัดส่วน (รวมสังหา)'] >= df['ภาระหนี้คงเหลือ'])
]
```

---

## Portfolio Health Indicators

### Overall Exposure
- **Total outstanding debt:** `df['ภาระหนี้คงเหลือ'].sum()` → total portfolio debt burden
- **Total collateral coverage:** `df['มูลค่าหลักประกันตามสัดส่วน (รวมสังหา)'].sum()`
- **Portfolio coverage ratio:** total collateral / total debt → if > 1.0 portfolio is theoretically fully covered
- **Thai banking benchmark:** System-wide NPL coverage ratio ~172–177% (2024 data — allowance basis)

### Concentration Risk
- **Written-off exposure:** % of total debt in group 07 → high = large already-absorbed losses
- **Clean Loan exposure:** count and % of total debt in Clean Loans → unrecoverable without debtor cooperation
- **Bankruptcy exposure:** debt in group 06 → slow recovery, years until resolution
- **Group distribution:** `df.groupby('รหัสชื่อกลุ่มการดำเนินงาน')['ภาระหนี้คงเหลือ'].sum()`

### Collection Efficiency
- **Accounts with cash collected:** `(df['เงินรับประเภท CASH สะสมในเดือน YTD'] > 0).sum()` / total accounts
- **Total cash collected rate:** `df['เงินรับประเภท CASH สะสมในเดือน YTD'].sum()` / `df['ภาระหนี้คงเหลือ'].sum()`
- **Low collection signal:** If majority of group 01 (TDR) accounts show zero CASH สะสมในเดือน YTD → restructuring plans may be failing

### Asset Quality Distribution
- **Grade A/B share:** % of collateral by value — higher = more liquid portfolio
- **Grade D/null share:** high % = uncertain auction outcomes → mark-to-market risk
- **Clean Loan %:** % of total accounts with no collateral → floor on loss exposure

---

## Interpreting Query Results Correctly

| Result shows | Correct framing |
|---|---|
| HIGH ภาระหนี้คงเหลือ | BAD — large exposure for institution |
| HIGH เงินต้นคงเหลือ | BAD — more principal at risk |
| HIGH มูลค่าหลักประกัน | GOOD — well secured, recovery likely |
| HIGH coverage ratio | GOOD — over-collateralized |
| LOW เงินรับ CASH | CONCERN — no collection occurring |
| HIGH เกรด D count | BAD — illiquid collateral, auction risk |
| Group 07 (write-off) | Resolved accounting-wise — but legal claim persists |
| TDR status | Positive — debtor cooperating |

---

## Thai Banking Regulatory Context

### BOT (Bank of Thailand) NPL Definition
- Loan is classified NPL when payment is overdue > 90 days (3 months) — this is the primary trigger
- Qualitative factors (unwillingness to pay, restructuring failure) can also trigger NPL regardless of days overdue
- Once NPL, all facilities to that debtor are typically classified NPL (cross-default)
- BOT 5-category classification: Pass → Special Mention (1–90d) → Substandard (90–180d) → Doubtful (180–360d) → Loss (>360d)
- Preemptive TDR window: Special Mention stage (before 90 days) — most cost-effective intervention point

### TFRS 9 Three-Stage Model (effective Jan 2020)
- **Stage 1** (performing): 12-month ECL provision; Pass / Special Mention loans
- **Stage 2** (credit deteriorated): Lifetime ECL provision; significant risk increase but not yet impaired
- **Stage 3** (NPL/Loss): Lifetime ECL, 100% provision on uncovered portion; Substandard / Doubtful / Loss loans
- NPL accounts in this dataset = all Stage 3
- ECL formula: **PD × LGD × EAD** where LGD = 1 − (collateral value recovery / exposure); higher collateral = lower LGD = lower ECL
- Interest income on Stage 3: computed on net carrying amount (after provisions), not gross balance

### BOT Responsible Lending (2025)
- Institutions must offer TDR terms at least ONCE before:
  1. Selling the debt to a third party
  2. Filing a lawsuit
  3. Terminating the credit contract
- 60-day waiting period after TDR offer before proceeding with legal action

### Write-off Requirements (BOT)
- Loan must be classified as "Loss" (สงสัยจะสูญ / หนี้สูญ)
- 100% specific provision must be booked
- Typically: >360 days past due with no viable recovery path
- Board or management committee approval per internal policy
- Legal claim survives write-off — collection can (and often does) continue

---

## Red Flags for Escalation

1. **TDR debtor in group 01 with zero CASH received for 3+ months** → restructuring plan failing, consider reclassification
2. **High ภาระหนี้คงเหลือ + Clean Loan + Non-TDR + group 02** → large unsecured exposure with no action — immediate litigation evaluation needed
3. **Coverage ratio < 0.3 + grade D** → auction proceeds will likely fall well below debt — consider settlement offer or early write-off
4. **Group 05 (awaiting auction) with coverage ratio < 1.0** → prepare for shortfall — calculate expected loss now
5. **Group 06 (bankruptcy) with large ภาระหนี้คงเหลือ** → ensure proof of claim filed with Official Receiver and tracked
