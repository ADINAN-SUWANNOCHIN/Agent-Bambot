# Collection Groups — Operational Guide

Each group represents a stage in the NPL collection lifecycle.
Column: `รหัสชื่อกลุ่มการดำเนินงาน`
ALWAYS filter with .str.contains('keyword', na=False) — values have code prefixes.

---

## Overview — Thai NPL Collection Lifecycle

Standard progression for NPL accounts in Thailand:
1. Debt becomes NPL (>90 days past due per BOT definition)
2. Institution attempts negotiation → if successful: group 01 (restructuring)
3. If negotiation fails → group 02 (pre-litigation, demand letters)
4. If no response → group 03 (court proceedings filed)
5. Court judgment obtained → group 04 (asset seizure via กรมบังคับคดี)
6. Assets seized → group 05 (scheduled for public auction)
7. Debtor declared insolvent → group 06 (bankruptcy proceedings)
8. Debt fully provisioned, unrecoverable → group 07 (written off books)

Under BOT's 2025 Responsible Lending rules: institutions MUST offer TDR terms at least once before moving to legal proceedings or selling the debt.

---

## 01 กลุ่มประนอมหนี้ — Debt Restructuring

- **Filter keyword:** `ประนอมหนี้`
- **Aliases users may say:** ประนอม, restructure, TDR group, ปรับโครงสร้าง
- **Meaning:** Debtor is actively cooperating under a restructured repayment plan
- **Risk level:** Lowest — debtor is engaged and making modified payments
- **Recovery outlook:** Highest probability among all groups
- **TDR status:** Usually TDR (debtor agreed to restructure under BOT definition)
- **BOT context:** Under BOT 2025 Responsible Lending Notification, restructuring must be offered before legal action. Options include: interest rate reduction, term extension, temporary payment holiday, or debt-to-equity conversion (for corporates).
- **Typical restructuring period:** Negotiated per case; BOT allows up to 7 years for persistent distressed debtors
- **Watch for:** Debtors who re-default on restructured terms → should escalate to group 02 or 03
- **Collection action:** Monthly monitoring of restructuring plan compliance

---

## 02 กลุ่มยังไม่ได้ดำเนินคดี — Not Yet Litigated

- **Filter keyword:** `ยังไม่ได้ดำเนินคดี`
- **Aliases:** ยังไม่ดำเนินคดี, pre-litigation, ยังไม่ฟ้อง
- **Meaning:** Debt is NPL but legal proceedings have not been filed yet
- **Risk level:** Medium — window for negotiation still open before escalation costs increase
- **Recovery outlook:** Moderate — depends on debtor's willingness to engage
- **Typical actions at this stage:**
  - Demand letters sent (หนังสือทวงถาม)
  - Phone/field contact attempts
  - TDR terms offered (BOT requires this before filing suit)
  - Asset investigation to assess if litigation is worthwhile
- **Transition trigger:** If debtor unresponsive after required TDR offer → escalate to group 03
- **Note:** Litigation costs (court fees, lawyer fees) are not worthwhile for small debts — some accounts may remain here long-term or move to group 07 directly

---

## 03 กลุ่มดำเนินคดี — Under Litigation

- **Filter keyword:** `ดำเนินคดี`
- **Aliases:** ดำเนินคดี, litigation, ฟ้องร้อง, ฟ้อง
- **Meaning:** Civil lawsuit has been filed against the debtor in court
- **Risk level:** High — debtor-creditor relationship has broken down
- **Recovery outlook:** Depends on court outcome and whether debtor has seizable assets
- **Legal process in Thailand:**
  - Case filed at Civil Court (ศาลแพ่ง) or Provincial Court
  - Court summons issued to debtor
  - Hearings held — debtor may contest or default
  - If debtor defaults (ไม่สู้คดี): judgment typically obtained in 3–6 months
  - If contested: may take 1–3+ years
- **Transition trigger:** Court judgment obtained → move to group 04 (enforcement)
- **Note:** During litigation, debtor may still approach institution to settle — often results in negotiated settlement and return to group 01

---

## 04 กลุ่มบังคับคดียึดทรัพย์ — Asset Seizure Enforcement

- **Filter keyword:** `บังคับคดียึดทรัพย์`
- **Aliases:** ยึดทรัพย์, seizure, enforcement, บังคับคดี
- **Meaning:** Court judgment obtained. Assets are being seized via Legal Execution Department (กรมบังคับคดี — LED).
- **Risk level:** High — but recovery is actively in progress
- **Recovery outlook:** Depends on seized asset value vs outstanding debt. Coverage ratio is key.
- **Legal process:**
  - Creditor files writ of execution (หมายบังคับคดี) with the court
  - LED officer locates and seizes debtor's assets (land, buildings, bank accounts, vehicles)
  - Assets appraised: under 10M THB by LED officer; 10–50M THB by LED-appointed appraiser; over 50M THB by Ministry-approved appraiser
  - Seized assets → scheduled for public auction (→ group 05)
- **Note:** Debtor can still pay in full at this stage to stop the process (ไถ่ถอนหลักประกัน)

---

## 05 กลุ่มรอประกาศขายทอดตลาด — Awaiting Auction

- **Filter keyword:** `ขายทอดตลาด`
- **Aliases:** ขายทอดตลาด, auction, ประมูล, รอขาย
- **Meaning:** Assets have been seized and are scheduled for public auction by กรมบังคับคดี
- **Risk level:** Medium — recovery amount will be determined by auction outcome
- **Recovery outlook:** Collateral coverage ratio is the primary indicator (collateral value vs debt)
- **Thai auction process (กรมบังคับคดี):**
  - LED announces auction publicly (minimum 15 days notice)
  - Opening bid set at appraised value
  - Auctioneer announces price 3 times — highest bidder wins
  - If no bidders at appraised price: price reduced and re-auctioned (typically 10–20% reduction)
  - Multiple rounds allowed — minimum floor price applies
  - Proceeds distributed: secured creditor first, then unsecured, then debtor (if surplus)
- **If auction fails repeatedly:** Asset may be returned to debtor or written off

---

## 06 กลุ่มล้มละลาย — Bankruptcy

- **Filter keyword:** `ล้มละลาย`
- **Aliases:** ล้มละลาย, bankrupt, bankruptcy, insolvency
- **Meaning:** Debtor is under formal bankruptcy proceedings (พระราชบัญญัติล้มละลาย)
- **Risk level:** Very high — recovery is uncertain, slow, and typically partial
- **Recovery outlook:** Poor to moderate. Depends on assets remaining in the bankruptcy estate.
- **Thai bankruptcy process:**
  - Filed at Central Bankruptcy Court (ศาลล้มละลายกลาง)
  - Triggered when: debtor owes creditor ≥1M THB (individual) or ≥2M THB (corporate) and is insolvent
  - Court appoints Official Receiver (เจ้าพนักงานพิทักษ์ทรัพย์) to manage debtor's assets
  - Creditors file proof of claim
  - Individual bankruptcy: auto-discharged after 3 years (5–10 years if misconduct)
  - Corporate: assets liquidated, proceeds distributed by priority
- **Priority of payment:** Secured creditors first → preferential claims (wages, taxes) → unsecured creditors
- **Key flag:** While debtor is in bankruptcy, individual collection action by creditors is STAYED — must go through Official Receiver

---

## 07 กลุ่มตัดหนี้สูญ — Written-Off

- **Filter keyword:** `ตัดหนี้สูญ`
- **Aliases:** ตัดหนี้สูญ, write-off, หนี้สูญ, bad debt, ตัดออก, write off
- **Meaning:** Debt has been removed from active books as uncollectable under BOT/accounting rules
- **Risk level:** Resolved from accounting perspective — fully provisioned before write-off
- **Recovery outlook:** Any recovery post-write-off is treated as windfall income (กำไรจากการตัดหนี้สูญ)
- **BOT write-off criteria (general):**
  - Loan must be classified as "Loss" (สงสัยจะสูญ) — typically >360 days past due
  - 100% provision must already be booked against the loan
  - Institution must have exhausted reasonable collection efforts
  - Board/management approval required per internal policy
- **Important:** Write-off is an ACCOUNTING action only — the legal claim still exists
  - Collection efforts MAY continue after write-off (collector's decision)
  - Any cash recovered is booked as income
- **These debtors still appear in the dataset for portfolio tracking and any future recovery**

---

## 08 อื่นๆ — Others

- **Filter keyword:** `อื่นๆ`
- **Aliases:** อื่นๆ, other, miscellaneous
- **Meaning:** Accounts that don't fit neatly into groups 01–07
- **Typical cases:** Accounts under special review, regulatory holds, interbank transfers in progress, or accounts pending reclassification
- **Note:** Small in volume but may warrant investigation if queried — usually transitional status
