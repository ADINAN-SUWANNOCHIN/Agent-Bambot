# Column Dictionary — NPA Outstanding & Collection Tables

NPA = Non-Performing Asset. Key: `รหัสตลาด`. One row = one property/asset.

---

## รหัสตลาด
- **Exact column name:** `รหัสตลาด`
- **English:** asset market code, asset ID
- **Aliases:** รหัสทรัพย์, asset code, รหัส, asset ID
- **Type:** string, unique per asset row
- **Note:** Primary key. Use instead of รหัสลูกหนี้ (does not exist in NPA).

---

## จังหวัด / อำเภอ / ตำบล — location columns
- **Exact column names:** `จังหวัด`, `อำเภอ`, `ตำบล`
- **English:** province, district, sub-district
- **CRITICAL:** These columns exist DIRECTLY in NPA outstanding — use them as-is.
- **No prefix needed** — unlike NPL outstandingcol which uses `ที่อยู่ทรัพย์ - จังหวัด`
- **Province queries:** `df['จังหวัด'].unique()` or groupby `จังหวัด`
- **District queries:** groupby `['จังหวัด', 'อำเภอ']`

---

## ประเภททรัพย์
- **Exact column name:** `ประเภททรัพย์`
- **English:** asset/property type
- **Aliases:** ประเภทอสังหา, ประเภทของ, ชนิดทรัพย์, property type
- **Common values:** ที่ดิน, ที่ดินพร้อมสิ่งปลูกสร้าง, ห้องชุด, อาคาร, โรงงาน
- **Filter with:** `.str.contains('ที่ดิน', na=False)` for land types

---

## จำนวนชิ้นทรัพย์
- **Exact column name:** `จำนวนชิ้นทรัพย์`
- **English:** number of asset pieces / collateral count
- **Aliases:** จำนวนชิ้น, กี่ชิ้น, หลายชิ้น, ชิ้นทรัพย์
- **Note:** Pre-computed count of asset pieces in this NPA record. Use directly for "มากกว่า N ชิ้น" queries.
- **Code:** `df[df['จำนวนชิ้นทรัพย์'] > 3]`

---

## จำนวนแปลง
- **Exact column name:** `จำนวนแปลง`
- **English:** number of land plots
- **Aliases:** กี่แปลง, จำนวนที่ดิน, แปลงที่ดิน
- **Note:** Number of distinct land plots within this asset record.

---

## ราคาประเมิน
- **Exact column name:** `ราคาประเมิน`
- **English:** appraisal value, assessed value
- **Aliases:** ราคาประเมิน, appraised value, มูลค่าประเมิน, ราคาทรัพย์, ราคาที่ดิน
- **Unit:** Thai Baht (฿)
- **Note:** Official appraisal value of the asset. Primary valuation metric.

---

## ราคาประเมินที่ดิน / ราคาประเมินสิ่งปลูกสร้าง
- **Exact column names:** `ราคาประเมินที่ดิน`, `ราคาประเมินสิ่งปลูกสร้าง`
- **English:** land appraisal value, building appraisal value
- **Note:** Breakdown of total appraisal into land portion and structure portion.

---

## ราคาตั้งขาย / ราคาพิเศษ
- **Exact column names:** `ราคาตั้งขาย`, `ราคาพิเศษ`
- **English:** asking price / listed price, special/discounted price
- **Unit:** Thai Baht (฿)
- **Note:** ราคาตั้งขาย = standard listing price. ราคาพิเศษ = promotional/negotiated price.

---

## ต้นทุนรวม / ต้นทุุนสุทธิ
- **Exact column names:** `ต้นทุนรวม`, `ต้นทุุนสุทธิ`
- **English:** total cost basis, net cost
- **Unit:** Thai Baht (฿)
- **Note:** ต้นทุนรวม includes all acquisition + holding costs. Used for margin calculation.
- **Margin code:** `df['ราคาประเมิน'] / df['ต้นทุนรวม'].replace(0, float('nan'))`

---

## ต้นทุนต่อราคาประเมิน
- **Exact column name:** `ต้นทุนต่อราคาประเมิน`
- **English:** cost-to-appraisal ratio
- **Note:** Pre-computed ratio. Lower = better margin. Use directly instead of computing manually.

---

## ระยะเวลาถือครอง NPA (ปี)
- **Exact column name:** `ระยะเวลาถือครอง NPA (ปี)`
- **English:** NPA holding period in years
- **Aliases:** ระยะเวลาถือครอง, holding period, ถือครองมากี่ปี, อายุทรัพย์, นานแค่ไหน
- **CRITICAL:** Use this column DIRECTLY — do NOT compute from ปี/เดือน.
- **Code:** `df[df['ระยะเวลาถือครอง NPA (ปี)'] > 3]`

---

## สถานะทรัพย์
- **Exact column name:** `สถานะทรัพย์`
- **English:** asset status
- **Aliases:** สถานะ, status ทรัพย์, สถานะการขาย
- **Note:** Current disposal status of the asset (e.g. available, sold, under negotiation). Use exact values from schema.

---

## ประเภทการขายทรัพย์
- **Exact column name:** `ประเภทการขายทรัพย์`
- **English:** asset disposal/sale type
- **Aliases:** วิธีขาย, รูปแบบการขาย, ประเภทการจำหน่าย
- **Note:** Method of disposal (e.g. outright sale, installment sale, rental). Use exact values from schema.

---

## เกรดทรัพย์
- **Exact column name:** `เกรดทรัพย์`
- **English:** asset grade, quality grade
- **Valid values:** A (best), B, C, D (worst)
- **Note:** May contain nulls. Use `.fillna('')` when filtering.

---

## พื้นที่ (ตรว.) / พื้นที่ (ตรม.)
- **Exact column names:** `พื้นที่ (ตรว.)`, `พื้นที่ (ตรม.)`
- **English:** area in square wah (ตรว.), area in square meters (ตรม.)
- **Note:** Use ตรว. for land price-per-area calculations: `ราคาประเมิน / พื้นที่ (ตรว.)`
- **Thai land unit conversions:** 1 ไร่ = 400 ตรว. = 1,600 ตรม. | 1 งาน = 100 ตรว. = 400 ตรม. | 1 ตรว. = 4 ตรม.
- **Price per ตรว. code:** `df['ราคาต่อตรว'] = df['ราคาประเมิน'] / df['พื้นที่ (ตรว.)'].replace(0, float('nan'))`

---

## YTD ผลเรียกเก็บ
- **Exact column name:** `YTD ผลเรียกเก็บ`
- **English:** year-to-date collection result
- **Unit:** Thai Baht (฿)
- **Note:** Cumulative collection proceeds for this asset year-to-date.

---

## ชื่อพนักงาน / ชื่อกลุ่มงาน / ชื่อฝ่ายงาน / ชื่อสายงาน
- **Exact column names:** `ชื่อพนักงาน`, `ชื่อกลุ่มงาน`, `ชื่อฝ่ายงาน`, `ชื่อสายงาน`
- **English:** officer name, work group, department, division
- **Note:** Org hierarchy: สายงาน > ฝ่ายงาน > กลุ่มงาน > พนักงาน
- **SCOPE: NPA outstanding table only.** These columns do NOT exist in the NPA collection table.
  Do NOT use `ชื่อกลุ่มงาน` in collection (df_coll) queries — filter by `จังหวัด` or `เขต` instead.

---

## NPA Collection Table columns
- `รหัสตลาด` — asset ID (join key to outstanding table)
- `จังหวัด`, `เขต`, `ตำบล` — location
- `ประเภททรัพย์`, `ประเภทการขายทรัพย์`, `ประเภทผลเรียกเก็บ`
- `Full Payment` — full payment received (฿) — ซื้อขาด
- `Installment Payment` — partial/installment payment (฿) — ผ่อนชำระ
- `Others (ค่าเช่า, ริบเงิน, ดอกเบี้ย)` — other income: rent, forfeited deposits, interest
- `Total Actual` — total = Full + Installment + Others. **Use this for ผลเรียกเก็บ queries.**
- `รหัสลูกค้า`, `ชื่อนามสกุล` — buyer/customer info (when asset sold on installment)
- **CRITICAL — เดือน values:** Full English month names — `'March'`, `'December'` (NOT `'Mar'`/`'Dec'`)
