# Business Rules & Financial Calculations

Key formulas, ratios, and thresholds used in NPL analysis.

---

## Coverage Ratio (อัตราส่วนความคุ้มครองหลักประกัน)

- **Formula:** มูลค่าหลักประกันตามสัดส่วน (รวมสังหา) / ภาระหนี้คงเหลือ
- **pandas code:** `df['มูลค่าหลักประกันตามสัดส่วน (รวมสังหา)'] / df['ภาระหนี้คงเหลือ'].replace(0, float('nan'))`
- **Interpretation:**
  - > 1.0 = over-collateralized → institution fully protected, high recovery probability
  - = 1.0 = fully collateralized (breakeven)
  - 0.5–1.0 = under-collateralized → partial loss risk
  - < 0.5 = significantly under-collateralized → high loss risk
  - = 0 = Clean Loan (no collateral at all)
- **Thai banking context:** Thai banks system-wide maintained coverage ratio ~172% as of mid-2024 (total allowance / stage 3 loans)
- **Practical threshold:** Coverage ratio ≥ 1.0 = prioritize for enforcement (asset has enough value to cover debt); < 0.5 = expect significant shortfall

---

## Total Debt Burden Components

- **Formula:** ภาระหนี้คงเหลือ = เงินต้นคงเหลือ + ดอกเบี้ยรับรู้ + ดอกเบี้ยไม่รับรู้ + ดอกเบี้ยผิดนัด + ค่าใช้จ่าย
- **Note:** ภาระหนี้คงเหลือ is the single most important metric for ranking debtors by total exposure
- **Why it exceeds principal:** Years of accrued interest, default interest penalties, and legal expenses can make total burden 2–5x the original principal

---

## Counting Debtors

- **IMPORTANT:** Each row = 1 debtor. Use `len(df)` or `df.shape[0]` to count, NOT `df['จำนวนลูกหนี้'].sum()`
- **Reason:** จำนวนลูกหนี้ is always 1 per row, so sum = row count, but explicit len() is clearer
- **Total accounts:** 88,196 debtor records as of April 2026

---

## Over-Collateralized Debtors (คุ้มหนี้)

- **Definition:** Debtors where collateral value > outstanding debt
- **pandas code:** `df[df['มูลค่าหลักประกันตามสัดส่วน (รวมสังหา)'] > df['ภาระหนี้คงเหลือ']]`
- **Business meaning:** HIGH = GOOD. These debtors offer full recovery potential — pursue enforcement aggressively.
- **Strategy:** Prioritize these for groups 04/05 (seizure and auction) — guaranteed surplus after debt recovery

---

## Under-Collateralized / Clean Loan Risk

- **Definition:** Debtors where collateral value < outstanding debt OR no collateral
- **pandas code:** `df[df['มูลค่าหลักประกันตามสัดส่วน (รวมสังหา)'] < df['ภาระหนี้คงเหลือ']]`
- **Potential loss:** = ภาระหนี้คงเหลือ - มูลค่าหลักประกันตามสัดส่วน (รวมสังหา)
- **Strategy:** For large under-collateralized debts — litigation and wage garnishment; for small amounts — may be more cost-effective to offer settlement discount

---

## TDR vs Non-TDR

- **TDR (Troubled Debt Restructuring — การปรับโครงสร้างหนี้):**
  - Debtor agreed to modified repayment terms (lower rate, extended term, payment holiday)
  - BOT requires TDR offer BEFORE any debt sale or legal action (2025 Responsible Lending rules)
  - TDR debtors: more cooperative, lower litigation cost, higher eventual recovery
  - Modified terms typically: interest rate reduction, term extension up to 7 years for persistent cases
- **Non-TDR:**
  - No restructuring agreement reached
  - Higher collection cost (legal fees, court time)
  - Lower cooperation — may require full enforcement action
- **Filter TDR:** `df[df['สถานะการประนอมหนี้'] == 'TDR']`
- **Filter Non-TDR:** `df[df['สถานะการประนอมหนี้'] == 'Non-TDR']`

---

## Secured vs Clean Loan

- **Secured Loan (มีหลักประกัน):**
  - Has physical collateral (land, building, machinery, vehicle)
  - Creditor can seize and auction asset via กรมบังคับคดี if debtor defaults
  - Recovery bounded by collateral value and auction outcome
  - Under TFRS 9: collateral value deducted from exposure before ECL provision calculated
- **Clean Loan (ไม่มีหลักประกัน):**
  - No physical collateral
  - Recovery depends entirely on debtor's income, bank accounts, or other assets found during execution
  - Higher provision requirement under TFRS 9 (no collateral offset)
  - Higher risk — suitable for settlement offers or write-off if debtor untraceable
- **Filter Secured:** `df[df['สถานะหลักประกัน'] == 'Secured Loan']`
- **Filter Clean:** `df[df['สถานะหลักประกัน'] == 'Clean Loan']`

---

## Asset Grade Meaning (เกรดทรัพย์)

- **A** — Prime quality: excellent location, high liquidity, marketable quickly at full appraised value. Minimal uncertainty.
- **B** — Good quality: acceptable location and condition, marketable within reasonable timeframe (6–12 months). Small discount risk.
- **C** — Fair quality: limited marketability due to location, legal encumbrances, condition, or oversupply in local market. Expect 20–40% discount to appraised value at auction.
- **D** — Poor quality: highly illiquid, distressed condition, disputed title, remote location, or severely encumbered. Auction proceeds may be 50%+ below appraised value.
- **null (59% of records):** No grade assigned — typically Clean Loan (no collateral to grade) or collateral not yet formally appraised
- **Impact on provisioning:** Lower grade = higher LGD (Loss Given Default) = more provision required under TFRS 9

---

## TFRS 9 Expected Credit Loss (ECL) Framework

Thai banks adopted TFRS 9 from January 2020. For NPL accounts (Stage 3):

- **ECL formula:** PD × LGD × EAD
  - PD (Probability of Default) = for Stage 3 NPLs, effectively 100%
  - LGD (Loss Given Default) = 1 − (collateral value recovery / outstanding exposure)
  - EAD (Exposure at Default) = ภาระหนี้คงเหลือ
- **Key rule:** Collateral value must be deducted from EAD before calculating ECL
- **Stage 3 loans:** 100% ECL provision on the difference between book value and PV of expected cash flows
- **Implication for this dataset:** Accounts still on books in groups 01–06 have live provision requirements. Group 07 (written-off) have already been fully provisioned and removed.

---

## Recovery Priority Logic

Priority for collection action (highest effort → highest return):

**Tier 1 — Highest Priority:**
- Secured Loan + TDR + coverage ratio ≥ 1.0 + grade A or B
- Reasoning: Cooperative debtor, full collateral coverage, quality asset → predictable recovery

**Tier 2 — High Priority:**
- Secured Loan + Non-TDR + coverage ratio ≥ 1.0 + active enforcement (groups 03/04)
- Reasoning: Asset covers debt even without cooperation — enforce aggressively

**Tier 3 — Medium Priority:**
- Secured Loan + coverage ratio 0.5–1.0 + TDR or litigation
- Reasoning: Partial recovery likely — worth pursuing but expect shortfall

**Tier 4 — Low Priority:**
- Clean Loan + Non-TDR + no enforcement activity
- Reasoning: No collateral, uncooperative — high cost, low recovery probability

**Tier 5 — Write-off candidates:**
- Clean Loan + Non-TDR + group 06 or 07 + zero cash collected
- Reasoning: Recovery unlikely — maintain for tracking only

---

## Cash Collection Performance

- **Cash received column:** `เงินรับประเภท CASH`
- **LGO1 received column:** `เงินรับประเภท LGO1` (Legal execution / court-ordered proceeds)
- **Total received:** `df['เงินรับประเภท CASH'] + df['เงินรับประเภท LGO1']`
- **Debtors with zero cash:** `df[df['เงินรับประเภท CASH'] == 0]` — no voluntary payment at all
- **Collection rate:** (CASH + LGO1) / ภาระหนี้คงเหลือ × 100%
- **Healthy sign:** Any positive CASH from a Non-TDR debtor suggests opening for negotiation
