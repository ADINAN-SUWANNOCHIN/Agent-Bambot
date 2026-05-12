# Column Dictionary — NPL Outstanding Dataset

Every column in the dataset. Aliases are terms users may say instead of the exact column name.

---

## ปี
- **Exact column name:** `ปี`
- **English:** year
- **Aliases:** year, ปี, ช่วงเวลา
- **Current value:** 2026 (single snapshot)
- **Note:** All rows are the same year — filtering by year will return full dataset

---

## เดือน
- **Exact column name:** `เดือน`
- **English:** month
- **Aliases:** month, เดือน, งวด
- **Current value:** Apr (single snapshot, April 2026)

---

## รหัสลูกหนี้
- **Exact column name:** `รหัสลูกหนี้`
- **English:** debtor ID, debtor code
- **Aliases:** รหัสลูกหนี้, debtor ID, เลขลูกหนี้, รหัส, ชื่อลูกหนี้, ลูกหนี้
- **Type:** string, unique per row
- **Note:** Each row is exactly one debtor account

---

## วันที่ซื้อ Port
- **Exact column name:** `วันที่ซื้อ Port`
- **English:** portfolio purchase date
- **Aliases:** วันที่ซื้อ, purchase date, วันซื้อ port, วันที่รับโอน
- **Type:** datetime
- **Note:** Date the debt portfolio was acquired by this institution from the originating bank

---

## รหัส Port
- **Exact column name:** `รหัส Port`
- **English:** portfolio code
- **Aliases:** port, รหัส port, portfolio, พอร์ต
- **Type:** string (293 unique values: NPL001 – NPL293)
- **Note:** Groups debtors by portfolio batch — each batch was purchased at a different time and price

---

## รหัสชื่อกลุ่มการดำเนินงาน
- **Exact column name:** `รหัสชื่อกลุ่มการดำเนินงาน`
- **English:** operation group, collection group
- **Aliases:** กลุ่มการดำเนินงาน, collection group, กลุ่ม, สถานะการดำเนินงาน, กลุ่มลูกหนี้
- **Type:** string
- **CRITICAL — always use .str.contains() to filter, NOT ==**
- **Valid values:**
  - `01 กลุ่มประนอมหนี้` — debt restructuring (aliases: ประนอม, restructure, TDR group)
  - `02 กลุ่มยังไม่ได้ดำเนินคดี` — not yet litigated (aliases: ยังไม่ดำเนินคดี, pre-litigation)
  - `03 กลุ่มดำเนินคดี` — under litigation (aliases: ดำเนินคดี, litigation, ฟ้อง)
  - `04 กลุ่มบังคับคดียึดทรัพย์` — asset seizure enforcement (aliases: ยึดทรัพย์, seizure, บังคับคดี)
  - `05 กลุ่มรอประกาศขายทอดตลาด` — awaiting auction (aliases: ขายทอดตลาด, auction, ประมูล)
  - `06 กลุ่มล้มละลาย` — bankruptcy (aliases: ล้มละลาย, bankrupt)
  - `07 กลุ่มตัดหนี้สูญ` — written-off (aliases: ตัดหนี้สูญ, write-off, หนี้สูญ, bad debt, ตัดออก)
  - `08 อื่นๆ` — others

---

## รหัสชื่อการดำเนินงาน
- **Exact column name:** `รหัสชื่อการดำเนินงาน`
- **English:** operation sub-group, operation name
- **Aliases:** การดำเนินงาน, sub-group, ประเภทการดำเนินงาน
- **Type:** string (detailed breakdown within each group)

---

## สถานะการประนอมหนี้
- **Exact column name:** `สถานะการประนอมหนี้`
- **English:** debt restructuring status
- **Aliases:** สถานะประนอม, TDR status, restructure status
- **Valid values:**
  - `TDR` — Troubled Debt Restructuring: debtor agreed to modified repayment terms per BOT guidelines. Lower risk, more cooperative.
  - `Non-TDR` — Debtor has NOT agreed to restructure. Higher collection difficulty. May require litigation.

---

## เกรดทรัพย์
- **Exact column name:** `เกรดทรัพย์`
- **English:** asset grade, collateral grade
- **Aliases:** เกรด, grade, คุณภาพทรัพย์, asset quality
- **Valid values and general meaning:**
  - `A` — Best quality: prime location, liquid, easy to appraise and sell quickly at or near appraised value
  - `B` — Good quality: acceptable location and condition, marketable within reasonable time
  - `C` — Fair quality: some limitations on marketability (remote location, legal encumbrance, or condition issues)
  - `D` — Poor quality: difficult to sell, highly illiquid, significant uncertainty in realized value
- **WARNING:** 52,408 null values (59% of records). Always use .dropna() when filtering by this column.
- **Note:** Null grade typically means Clean Loan (no collateral) or collateral not yet formally appraised
- **Impact:** Higher grade (A) = higher LGD recovery. Lower grade (D) = institution may recover significantly less than appraised value

---

## ประเภทหลักประกัน
- **Exact column name:** `ประเภทหลักประกัน`
- **English:** collateral type
- **Aliases:** ประเภทหลักประกัน, collateral type, ประเภททรัพย์, ชนิดหลักประกัน
- **Common values:** ที่ดินพร้อมสิ่งปลูกสร้าง, ที่ดินเปล่า, เครื่องจักร, ไม่มีหลักประกัน, อาคารสิ่งปลูกสร้าง
- **Note:** ไม่มีหลักประกัน = no collateral (same as Clean Loan)

---

## ประเภทหลักประกัน TFRS
- **Exact column name:** `ประเภทหลักประกัน TFRS`
- **English:** TFRS 9 collateral classification
- **Aliases:** TFRS, หลักประกัน TFRS, ประเภท TFRS
- **Valid values under TFRS 9 (effective Jan 2020 in Thailand):**
  - `สังหาริมทรัพย์` — movable assets (equipment, vehicles, machinery)
  - `เพื่ออยู่อาศัย` — residential property (houses, townhouses, semi-detached)
  - `ที่ดินเปล่า` — vacant/undeveloped land
  - `เพื่อการพาณิชย์` — commercial property (office, retail, warehouse)
  - `ห้องชุด` — condominium units
  - `ไม่พบข้อมูล` — collateral type not identified
- **Note:** TFRS 9 requires collateral value to be deducted from loan exposure before calculating ECL (Expected Credit Loss) provisions

---

## สถานะหลักประกัน
- **Exact column name:** `สถานะหลักประกัน`
- **English:** collateral status
- **Aliases:** สถานะหลักประกัน, secured status, ประเภทสินเชื่อ
- **Valid values:**
  - `Secured Loan` — has collateral backing. Lower risk. Recovery likely if collateral value sufficient.
  - `Clean Loan` — no collateral. Higher risk. Recovery depends on debtor income/cooperation only.

---

## รหัสพนักงาน
- **Exact column name:** `รหัสพนักงาน`
- **English:** employee ID, officer ID, case officer
- **Aliases:** รหัสพนักงาน, officer, เจ้าหน้าที่, พนักงาน, ผู้รับผิดชอบ
- **Note:** The case officer responsible for this debtor account. 4 null values.

---

## ชื่อกลุ่มงาน
- **Exact column name:** `ชื่อกลุ่มงาน`
- **English:** work group / team
- **Aliases:** กลุ่มงาน, work group, team
- **Type:** string (63 unique values, format: A01P, A02N, etc.)
- **Note:** Sub-team within a department responsible for managing a specific set of debtor accounts

---

## ชื่อฝ่ายงาน
- **Exact column name:** `ชื่อฝ่ายงาน`
- **English:** department
- **Aliases:** ฝ่าย, department, ฝ่ายงาน
- **Type:** string (23 unique values, format: B01P, B02Q, etc.)
- **Note:** Department-level grouping above work group (ชื่อกลุ่มงาน)

---

## ชื่อสายงาน
- **Exact column name:** `ชื่อสายงาน`
- **English:** division / business line
- **Aliases:** สาย, สายงาน, division, business unit
- **Type:** string (10 unique values, format: C01X, C02R, etc.)
- **Note:** Highest-level organizational grouping. Encompasses multiple departments.

---

## จำนวนลูกหนี้
- **Exact column name:** `จำนวนลูกหนี้`
- **English:** number of debtors
- **Note:** Always equals 1. Each row = exactly 1 debtor. Use COUNT(rows) not SUM(จำนวนลูกหนี้) when counting debtors.

---

## ต้นทุนคงเหลือ (เกณฑ์ทุน)
- **Exact column name:** `ต้นทุนคงเหลือ (เกณฑ์ทุน)`
- **English:** remaining cost, book value, cost basis
- **Aliases:** ต้นทุนคงเหลือ, book value, cost basis, ราคาทุน
- **Unit:** Thai Baht (฿), full amount
- **HIGH = BAD** — represents institution's remaining investment/carrying value in this NPL account
- **Note:** This is the price paid to acquire the debt, adjusted for any payments received. Lower than original face value of debt since NPL portfolios are purchased at discount.

---

## เงินต้นคงเหลือ
- **Exact column name:** `เงินต้นคงเหลือ`
- **English:** remaining principal, outstanding principal
- **Aliases:** เงินต้น, principal, เงินต้นค้าง, ยอดเงินต้น
- **Unit:** Thai Baht (฿), full amount
- **HIGH = BAD** — more principal owed means more exposure

---

## ดอกเบี้ยรับรู้
- **Exact column name:** `ดอกเบี้ยรับรู้`
- **English:** recognized interest, accrued interest
- **Aliases:** ดอกเบี้ยรับรู้, accrued interest, recognized interest
- **Unit:** Thai Baht (฿)
- **Note:** Interest that has been formally recognized as income on the institution's books

---

## ดอกเบี้ยไม่รับรู้
- **Exact column name:** `ดอกเบี้ยไม่รับรู้`
- **English:** unrecognized interest, suspended interest
- **Aliases:** ดอกเบี้ยไม่รับรู้, suspended interest, ดอกเบี้ยค้าง
- **Unit:** Thai Baht (฿)
- **Note:** Interest accrued but NOT recognized as income because the loan is classified as NPL. Under TFRS 9, interest on stage 3 loans uses effective interest rate on net carrying amount only.

---

## ดอกเบี้ยผิดนัด
- **Exact column name:** `ดอกเบี้ยผิดนัด`
- **English:** default interest, penalty interest
- **Aliases:** ดอกเบี้ยผิดนัด, penalty interest, ดอกเบี้ยปรับ, เบี้ยปรับ
- **Unit:** Thai Baht (฿)
- **Note:** Additional interest charged due to payment default. Typically a surcharge above the contractual rate.

---

## ค่าใช้จ่าย
- **Exact column name:** `ค่าใช้จ่าย`
- **English:** expenses, collection expenses
- **Aliases:** ค่าใช้จ่าย, expenses, ค่าดำเนินคดี
- **Unit:** Thai Baht (฿)
- **Note:** Costs incurred in collecting this debt — typically legal fees, court filing fees, appraisal fees, auction administration costs

---

## ภาระหนี้คงเหลือ
- **Exact column name:** `ภาระหนี้คงเหลือ`
- **English:** total outstanding debt burden, total debt outstanding
- **Aliases:** ภาระหนี้, หนี้คงเหลือ, total debt, หนี้รวม, ยอดหนี้, debt outstanding, หนี้สิน, total outstanding
- **Unit:** Thai Baht (฿)
- **HIGH = BAD** — represents total exposure including principal + all interest + penalties + expenses
- **Formula:** เงินต้นคงเหลือ + ดอกเบี้ยรับรู้ + ดอกเบี้ยไม่รับรู้ + ดอกเบี้ยผิดนัด + ค่าใช้จ่าย
- **This is the PRIMARY metric for ranking debtors by total debt size**

---

## มูลค่าหลักประกันตามสัดส่วน (รวมสังหา)
- **Exact column name:** `มูลค่าหลักประกันตามสัดส่วน (รวมสังหา)`
- **English:** collateral value including movable assets
- **Aliases:** มูลค่าหลักประกัน, collateral value, มูลค่าทรัพย์, ราคาหลักประกัน, ราคาทรัพย์, collateral, หลักประกัน
- **Unit:** Thai Baht (฿)
- **HIGH = GOOD** — higher collateral means better loan security and higher recovery probability
- **IMPORTANT:** This is the PRIMARY collateral column to use when user asks about collateral value
- **"ตามสัดส่วน" means:** Value is allocated proportionally when multiple loans share one collateral asset

---

## มูลค่าหลักประกันตามสัดส่วน (ไม่รวมสังหา)
- **Exact column name:** `มูลค่าหลักประกันตามสัดส่วน (ไม่รวมสังหา)`
- **English:** collateral value excluding movable assets (immovable property only)
- **Aliases:** มูลค่าหลักประกัน ไม่รวมสังหา, immovable collateral, อสังหาริมทรัพย์
- **Unit:** Thai Baht (฿)
- **HIGH = GOOD**
- **Note:** Excludes vehicles, machinery, equipment. Only land and buildings counted here.

---

## เงินรับประเภท CASH
- **Exact column name:** `เงินรับประเภท CASH`
- **English:** cash received, cash payment received
- **Aliases:** เงินรับ, cash received, รับชำระ, ชำระเงิน
- **Unit:** Thai Baht (฿)
- **Note:** Actual cash payments collected from this debtor. Zero means no collection has occurred.

---

## เงินรับประเภท LGO1
- **Exact column name:** `เงินรับประเภท LGO1`
- **English:** LGO1 payment received
- **Aliases:** LGO1, เงินรับ LGO1
- **Unit:** Thai Baht (฿)
- **Note:** Non-cash recovery channel — typically proceeds from Legal Execution (กรมบังคับคดี) asset auctions or court-ordered payments, as opposed to voluntary cash payments by the debtor
