# Query Examples & Intent Mapping

Maps natural language queries to correct pandas logic and column usage.

---

## Debtor Rankings

### Top debtors by outstanding debt
- User may say: ลูกหนี้ที่มีหนี้มากที่สุด, top debtors, หนี้สูงสุด, ยอดหนี้มากที่สุด, ลูกหนี้รายใหญ่, ใครเป็นหนี้มากสุด, ยอดค้างชำระสูงสุด, หนี้เยอะที่สุด, ภาระหนี้สูง, หนี้หนักสุด, biggest debtors, largest debt
- Column: `ภาระหนี้คงเหลือ` (NOT หนี้สิน, NOT เงินต้น alone)
- Code: `df.nlargest(N, 'ภาระหนี้คงเหลือ')`

### Top debtors by remaining principal
- User may say: เงินต้นมากที่สุด, highest principal, ยอดเงินต้นสูง, ต้นมากสุด, เงินต้นค้างเยอะ, principal สูง
- Column: `เงินต้นคงเหลือ`
- Code: `df.nlargest(N, 'เงินต้นคงเหลือ')`

### Top debtors by collateral value
- User may say: มูลค่าหลักประกันสูงสุด, highest collateral, ทรัพย์มีมูลค่ามาก, ทรัพย์แพงสุด, ราคาทรัพย์สูง, ทรัพย์มาก, มีทรัพย์เยอะ, collateral value สูง
- Column: `มูลค่าหลักประกันตามสัดส่วน (รวมสังหา)`
- Code: `df.nlargest(N, 'มูลค่าหลักประกันตามสัดส่วน (รวมสังหา)')`

---

## Filtering by Collection Group

### Written-off debtors
- User may say: ตัดหนี้สูญ, write-off, หนี้สูญ, bad debt, ตัดออก, หนี้ตาย, หนี้เสียตัดแล้ว, write off แล้ว, กลุ่ม 07, กลุ่มตัดหนี้
- Code: `df[df['รหัสชื่อกลุ่มการดำเนินงาน'].str.contains('ตัดหนี้สูญ', na=False)]`

### Bankruptcy debtors
- User may say: ล้มละลาย, bankrupt, bankruptcy, ตกล้มละลาย, ฟ้องล้มละลาย, คดีล้มละลาย, กลุ่ม 06, กลุ่มล้มละลาย
- Code: `df[df['รหัสชื่อกลุ่มการดำเนินงาน'].str.contains('ล้มละลาย', na=False)]`

### Debt restructuring group (กำลังประนอมหนี้อยู่)
- User may say: กลุ่มประนอมหนี้, กลุ่ม 01, group 01, กลุ่มการดำเนินงานประนอม
- NOTE: "TDR", "อยู่ระหว่างประนอม", "ประนอมหนี้" alone → use สถานะการประนอมหนี้ == 'TDR' instead (see TDR Analysis section)
- Code: `df[df['รหัสชื่อกลุ่มการดำเนินงาน'].str.contains('ประนอมหนี้', na=False)]`

### Under litigation (ฟ้องร้องแล้ว)
- User may say: ดำเนินคดี, litigation, ฟ้อง, ฟ้องร้อง, ขึ้นศาล, อยู่ในคดี, คดีความ, ถูกฟ้อง, กลุ่ม 03
- Code: `df[df['รหัสชื่อกลุ่มการดำเนินงาน'].str.contains('ดำเนินคดี', na=False)]`

### Awaiting auction
- User may say: ขายทอดตลาด, auction, ประมูล, รอขาย, รอขายทอด, เตรียมประมูล, รอประกาศขาย, กลุ่ม 05
- Code: `df[df['รหัสชื่อกลุ่มการดำเนินงาน'].str.contains('ขายทอดตลาด', na=False)]`

### Asset seizure enforcement (ยึดทรัพย์แล้ว)
- User may say: ยึดทรัพย์, seizure, บังคับคดี, enforcement, ถูกยึด, อายัดทรัพย์, ยึดของแล้ว, กลุ่ม 04
- Code: `df[df['รหัสชื่อกลุ่มการดำเนินงาน'].str.contains('บังคับคดียึดทรัพย์', na=False)]`

### Pre-litigation (ยังไม่ฟ้อง)
- User may say: ยังไม่ดำเนินคดี, ยังไม่ฟ้อง, pre-litigation, ก่อนฟ้อง, ยังไม่ขึ้นศาล, ยังไม่ถูกฟ้อง, กลุ่ม 02
- Code: `df[df['รหัสชื่อกลุ่มการดำเนินงาน'].str.contains('ยังไม่ได้ดำเนินคดี', na=False)]`

---

## Collateral Analysis

### Debtors with more than N collateral pieces — use outstandingcol table
- User may say: มีหลักประกันมากกว่า 3 ชิ้น, ลูกหนี้ที่มีหลายชิ้นทรัพย์, มีทรัพย์หลายชิ้น, หลักประกันเกิน N ชิ้น, multiple collateral pieces
- CRITICAL: This query needs the **outstandingcol** table (df), NOT outstanding table.
- STRUCTURAL WARNING: outstandingcol has ONE ROW PER COLLATERAL ITEM. One debtor with 5 pieces = 5 rows.
  - NEVER use len(df) on outstandingcol for debtor counts — that counts collateral rows, not debtors.
  - ALWAYS use .nunique() or .drop_duplicates('รหัสลูกหนี้') when counting unique debtors.
- Column `จำนวนทรัพย์หลักประกัน` = pre-computed total piece count per debtor, REPEATED on every row.
  - NEVER .sum() or .mean() this column — it is already the total count, not a per-row counter.
- Code:
```python
# Count unique debtors with more than N pieces
filtered = df[df['จำนวนทรัพย์หลักประกัน'] > 3]
result_df = filtered.drop_duplicates(subset='รหัสลูกหนี้')  # one row per debtor for display
result = len(result_df)  # = number of unique debtors (NOT len(filtered))
```

### Province/location of collateral — use outstandingcol table
- User may say: ที่ดินที่จังหวัดอะไรบ้าง, หลักประกันอยู่จังหวัดไหน, collateral province, ทรัพย์อยู่แถวไหน, กระจายตามจังหวัด
- CRITICAL: Province is in outstandingcol table ONLY. Column name: `ที่อยู่ทรัพย์ - จังหวัด`
- District: `ที่อยู่ทรัพย์ - อำเภอ`, Sub-district: `ที่อยู่ทรัพย์ - ตำบล`
- Code (list provinces):
```python
result = df['ที่อยู่ทรัพย์ - จังหวัด'].dropna().value_counts().reset_index()
result.columns = ['จังหวัด', 'จำนวนหลักประกัน']
```
- Code (filter land collateral by province):
```python
land = df[df['ประเภทหลักประกัน'].str.contains('ที่ดิน', na=False)]
result = land['ที่อยู่ทรัพย์ - จังหวัด'].dropna().value_counts().reset_index()
result.columns = ['จังหวัด', 'จำนวนหลักประกัน']
```

### Debtors where collateral exceeds debt (over-collateralized)
- User may say: หลักประกันมากกว่าหนี้, collateral > debt, ปลอดภัย, คุ้มหนี้, ทรัพย์คุ้มหนี้, หลักประกันคุ้ม, ทรัพย์เกินหนี้, ราคาทรัพย์สูงกว่าหนี้, มูลค่าทรัพย์เกินภาระ
- Code: `df[df['มูลค่าหลักประกันตามสัดส่วน (รวมสังหา)'] > df['ภาระหนี้คงเหลือ']]`

### Debtors with no collateral (Clean Loan)
- User may say: ไม่มีหลักประกัน, clean loan, unsecured, ไม่มีทรัพย์, ไม่มีของค้ำ, ไม่มีค้ำประกัน, สินเชื่อไม่มีประกัน, หนี้ไม่มีทรัพย์, ไม่มีทรัพย์สินค้ำ
- Code: `df[df['สถานะหลักประกัน'] == 'Clean Loan']`

### Debtors with collateral (Secured Loan)
- User may say: มีหลักประกัน, secured loan, มีทรัพย์ค้ำประกัน, มีทรัพย์, มีของค้ำ, มีค้ำประกัน, หนี้มีหลักประกัน, มีทรัพย์สิน
- Code: `df[df['สถานะหลักประกัน'] == 'Secured Loan']`

### Coverage ratio calculation
- User may say: อัตราหลักประกัน, coverage ratio, หลักประกันต่อหนี้, อัตราความคุ้ม, สัดส่วนทรัพย์ต่อหนี้, ทรัพย์คิดเป็นกี่เปอร์เซ็นต์ของหนี้
- Code: `df['coverage'] = df['มูลค่าหลักประกันตามสัดส่วน (รวมสังหา)'] / df['ภาระหนี้คงเหลือ'].replace(0, float('nan'))`

### Filter by TFRS collateral type (สังหาริมทรัพย์ / ไม่ใช่สังหาริมทรัพย์)
- User may say: สังหาริมทรัพย์, ไม่ใช่สังหาริมทรัพย์, movable, immovable, TFRS collateral, ทรัพย์เคลื่อนย้ายได้, ทรัพย์เคลื่อนย้ายไม่ได้, ลูกหนี้สังหาริมทรัพย์, ลูกหนี้ไม่ใช่สังหาริมทรัพย์
- สังหาริมทรัพย์ = movable: รถ, รถยนต์, เครื่องจักร, ยานพาหนะ (use TFRS column)
- ไม่ใช่สังหาริมทรัพย์ = immovable: บ้าน, ที่ดิน, อาคาร, คอนโด, ห้องชุด, เพื่ออยู่อาศัย, เพื่อการพาณิชย์ (use TFRS column)
- TABLE: ALWAYS use **outstanding** (df) for TFRS debtor-count queries — "กี่คน/กี่ราย" = one row per debtor.
  Do NOT use outstandingcol for this — outstandingcol has one row per collateral ITEM, not per debtor.
- MUST use column: 'ประเภทหลักประกัน TFRS' (NOT 'ประเภทหลักประกัน')
- Values in this column: สังหาริมทรัพย์, เพื่ออยู่อาศัย, ที่ดินเปล่า, เพื่อการพาณิชย์, ห้องชุด, ไม่พบข้อมูล
- Code (count movable debtors — กี่คน):
```python
df = df[(df['ปี'] == 2026) & (df['เดือน'] == 'Mar')]
filtered_df = df[df['ประเภทหลักประกัน TFRS'] == 'สังหาริมทรัพย์']
result = filtered_df['รหัสลูกหนี้'].nunique()
result_df = filtered_df
```
- Code (count immovable debtors):
```python
df = df[(df['ปี'] == 2026) & (df['เดือน'] == 'Mar')]
filtered_df = df[df['ประเภทหลักประกัน TFRS'] != 'สังหาริมทรัพย์']
result = filtered_df['รหัสลูกหนี้'].nunique()
result_df = filtered_df
```

### Filter by original collateral type (เครื่องจักร, ที่ดิน, รถยนต์ etc.)
- User may say: เครื่องจักร, ที่ดินพร้อมสิ่งปลูกสร้าง, รถยนต์, อาคาร, ที่ดินเปล่า, โรงงาน, สิ่งปลูกสร้าง
- MUST use column: 'ประเภทหลักประกัน' (NOT 'ประเภทหลักประกัน TFRS')
- Code: `df[df['ประเภทหลักประกัน'].str.contains('เครื่องจักร', na=False)]`

### Debtors by collateral grade
- User may say: เกรดทรัพย์, asset grade, ทรัพย์เกรด A, ทรัพย์คุณภาพดี, ทรัพย์คุณภาพต่ำ, เกรด D, ทรัพย์แย่, ทรัพย์ดี, grade A, grade D
- WARNING: 'เกรดทรัพย์' is 59% null — always handle NaN
- Code (grade A): `df[df['เกรดทรัพย์'].fillna('') == 'A']`
- Code (grade D): `df[df['เกรดทรัพย์'].fillna('') == 'D']`

---

## Holding Age / Debtor Age (อายุการถือครอง)

### How holding age is calculated
- 'ปี' and 'เดือน' = snapshot/pull date only — DO NOT use for age calculation
- Correct column: 'วันที่ซื้อ Port' = portfolio purchase date
- Age formula (open accounts): (today - วันที่ซื้อ Port) in years
- For closed accounts (future): use 'วันที่ปิดบัญชี' as end date if it exists

### Filter debtors by holding age (open accounts)
- User may say: อายุการถือครองเกิน, ถือครองมานานกว่า, debt older than, อายุเกิน, อายุหนี้, อายุบัญชี, เก่าแค่ไหน, นานแค่ไหน, ถือมานานแค่ไหน, เป็นหนี้มานาน, ค้างมานาน, ระยะเวลาการถือครอง, how old, how long, duration, age of account, อายุเท่าไหร่, ถือครองมากี่ปี, ค้างชำระนานแค่ไหน, เป็นหนี้กี่ปีแล้ว, ค้างนาน, หนี้เก่า, บัญชีเก่า
- Code:
```python
df['อายุ_ปี'] = (pd.Timestamp.now() - pd.to_datetime(df['วันที่ซื้อ Port'])).dt.days / 365.25
result = df[df['อายุ_ปี'] > N]
```

### Count debtors with holding age > N years AND TDR
- User may say: ลูกหนี้ที่มีอายุการถือครองเกิน 10 ปี และยังอยู่ระหว่างประนอมหนี้, ถือมานานเกิน 10 ปีและยัง TDR, เป็นหนี้มานานและยังประนอมหนี้อยู่, หนี้เก่าและยังประนอมอยู่
- Code:
```python
df['อายุ_ปี'] = (pd.Timestamp.now() - pd.to_datetime(df['วันที่ซื้อ Port'])).dt.days / 365.25
filtered_df = df[
    (df['อายุ_ปี'] > 10) &
    (df['สถานะการประนอมหนี้'] == 'TDR')
]
result = filtered_df.shape[0]
```

---

## Filter by Purchase Year / Acquisition Year (ปีที่ซื้อ Port)

CRITICAL DISAMBIGUATION:
- `ปี` and `เดือน` columns = REPORTING PERIOD only (when data was extracted from source system). NOT purchase date.
- For any query about the year a portfolio was purchased/acquired → use `วันที่ซื้อ Port` column.
- NEVER use `ปี == 2025` to mean "purchased in 2025" — that filters by reporting period, not purchase date.

### Count debtors purchased in a specific year
- User may say: ซื้อมาในปี, purchased in year, ซื้อในปี, ปีที่ซื้อ, รับโอนในปี, รับโอนปี, ซื้อ port ปี, เข้ามาในปี, ซื้อพอร์ตปี, ซื้อปี, ปีที่รับโอน, ซื้อมาตั้งแต่ปี
- Column: `วันที่ซื้อ Port` (datetime) — extract year with `.dt.year`
- Code:
```python
df['_purchase_year'] = pd.to_datetime(df['วันที่ซื้อ Port']).dt.year
filtered_df = df[df['_purchase_year'] == 2025]
result = filtered_df['รหัสลูกหนี้'].nunique()
result_df = filtered_df
```

### List debtors by purchase year (all years)
- User may say: แบ่งตามปีที่ซื้อ, กี่รายต่อปีที่ซื้อ, ซื้อมากี่ปีแล้วแต่ละปี, purchase year breakdown
- Code:
```python
df['_purchase_year'] = pd.to_datetime(df['วันที่ซื้อ Port']).dt.year
result = df.groupby('_purchase_year')['รหัสลูกหนี้'].nunique().reset_index()
result.columns = ['ปีที่ซื้อ', 'จำนวนลูกหนี้']
```

---

## TDR Analysis

### TDR debtors only (ยอมปรับโครงสร้างหนี้ / อยู่ระหว่างการประนอมหนี้)
- User may say: TDR, ประนอมหนี้, ที่ยอมปรับโครงสร้าง, ที่ตกลงประนอม, ยินยอมปรับโครงสร้าง, ปรับปรุงโครงสร้างหนี้, ยอมเซ็น, ตกลงแล้ว, สมัครใจปรับ, เจรจาสำเร็จ, ลูกหนี้ร่วมมือ, อยู่ระหว่างการประนอมหนี้, กำลังประนอมหนี้, อยู่ระหว่างปรับโครงสร้าง, อยู่ในกระบวนการประนอม, กำลังปรับ, อยู่ระหว่างเจรจา
- CRITICAL: 'สถานะการประนอมหนี้' contains ONLY English codes 'TDR' or 'Non-TDR' — NEVER use str.contains or Thai text here
- CRITICAL: "อยู่ระหว่างการประนอมหนี้" means TDR status — do NOT use รหัสชื่อกลุ่มการดำเนินงาน for this
- Code: `df[df['สถานะการประนอมหนี้'] == 'TDR']`
- To COUNT them: `result = len(df[df['สถานะการประนอมหนี้'] == 'TDR'])`

### Non-TDR debtors (ไม่ยอมปรับโครงสร้าง)
- User may say: Non-TDR, ไม่ยอมประนอม, ไม่ยินยอม, ปฏิเสธการปรับโครงสร้าง, ไม่ยอมปรับโครงสร้าง, ไม่ร่วมมือ, ดื้อ, ไม่ยอมเจรจา, ปฏิเสธ, ไม่ตกลง, หัวแข็ง
- CRITICAL: use == 'Non-TDR' exactly — NEVER str.contains with Thai text on this column
- Code: `df[df['สถานะการประนอมหนี้'] == 'Non-TDR']`

---

## Collection Performance

### Debtors with zero payment (ไม่เคยจ่ายเลย) — outstanding table
- User may say: ยังไม่จ่าย, ไม่มีการรับชำระ, zero payment, ไม่ได้รับเงิน, ไม่เคยจ่าย, ไม่จ่ายเลย, ไม่มีเงินเข้า, no payment, ยังไม่ชำระ, ไม่มีประวัติจ่าย, เก็บไม่ได้เลย
- CRITICAL: In NPL outstanding table, cash columns have YTD suffix — exact names:
  - `เงินรับประเภท CASH สะสมในเดือน YTD`
  - `เงินรับประเภท LGO1 สะสมในเดือน YTD`
- Code: `df[(df['เงินรับประเภท CASH สะสมในเดือน YTD'] == 0) & (df['เงินรับประเภท LGO1 สะสมในเดือน YTD'] == 0)]`

### Debtors who have paid something (มีผลเรียกเก็บ) — outstanding table
- User may say: มีการชำระ, ได้รับเงิน, debtors who paid, จ่ายแล้ว, มีผลเรียกเก็บ, มีเงินรับ, เก็บได้แล้ว, มีการจ่ายเงินมาแล้ว, จ่ายเงินมาบ้าง, เริ่มชำระแล้ว, ส่งเงินมาแล้ว, มีประวัติจ่าย, เก็บได้บางส่วน, ชำระบางส่วน
- IMPORTANT: "ผลเรียกเก็บ" = CASH + LGO1 combined. Use YTD columns in outstanding table.
- Code (debtors with ANY payment):
```python
result = df[(df['เงินรับประเภท CASH สะสมในเดือน YTD'] > 0) | (df['เงินรับประเภท LGO1 สะสมในเดือน YTD'] > 0)]
```
- Code (count only): `result = ((df['เงินรับประเภท CASH สะสมในเดือน YTD'] > 0) | (df['เงินรับประเภท LGO1 สะสมในเดือน YTD'] > 0)).sum()`

### Total cash collected YTD — outstanding table
- User may say: รับชำระรวม, total collected, เงินรับรวม, เก็บได้เท่าไหร่, เก็บได้รวมเท่าไหร่, ยอดรับชำระ, เงินเข้ารวม, เก็บเงินได้เท่าไหร่, cash รวม
- Code: `result = df['เงินรับประเภท CASH สะสมในเดือน YTD'].sum()`

### Total recovery YTD (cash + LGO1) — outstanding table
- User may say: เงินรับทั้งหมด, total recovery, รับชำระทุกช่องทาง, ผลเรียกเก็บรวม, ยอดเรียกเก็บได้, เก็บได้ทั้งหมด, ยอดเก็บรวม, รับเงินรวมทุกประเภท, รับมารวมทั้งสิ้น
- Code: `result = df['เงินรับประเภท CASH สะสมในเดือน YTD'].sum() + df['เงินรับประเภท LGO1 สะสมในเดือน YTD'].sum()`

---

## Group Summaries

### Debt total by collection group
- User may say: หนี้แต่ละกลุ่ม, debt by group, สรุปตามกลุ่ม, ยอดหนี้แยกกลุ่ม, แต่ละกลุ่มมีหนี้เท่าไหร่, กลุ่มไหนหนี้เยอะ, แยกตามกลุ่มดำเนินงาน
- Code: `df.groupby('รหัสชื่อกลุ่มการดำเนินงาน')['ภาระหนี้คงเหลือ'].sum()`

### Count of debtors by group
- User may say: จำนวนลูกหนี้แต่ละกลุ่ม, count by group, กี่คนในแต่ละกลุ่ม, แต่ละกลุ่มมีกี่คน, กลุ่มไหนมีคนเยอะสุด
- Code: `df.groupby('รหัสชื่อกลุ่มการดำเนินงาน').size()`

### Summary table by group (count + total debt + avg debt)
- User may say: สรุปภาพรวมแต่ละกลุ่ม, group summary, overview by group, ภาพรวมทุกกลุ่ม, สรุปทุกกลุ่ม, ขอสรุปแต่ละกลุ่ม
- Code:
```python
result = df.groupby('รหัสชื่อกลุ่มการดำเนินงาน').agg(
    จำนวนลูกหนี้=('รหัสลูกหนี้', 'count'),
    ภาระหนี้รวม=('ภาระหนี้คงเหลือ', 'sum'),
    ภาระหนี้เฉลี่ย=('ภาระหนี้คงเหลือ', 'mean'),
    มูลค่าหลักประกันรวม=('มูลค่าหลักประกันตามสัดส่วน (รวมสังหา)', 'sum')
).reset_index()
```

---

## Priority / Best Candidates for Collection

- User may say: ลูกหนี้ที่ควรติดตามก่อน, priority debtors, best to collect, น่าจะเก็บได้, ลูกหนี้ที่คุ้มค่า, ควรโฟกัสที่ไหน, ลูกหนี้ที่น่าสนใจ, เก็บง่ายที่สุด, ROI ดีที่สุด, คุ้มที่สุด, ลูกหนี้เป้าหมาย, ลูกหนี้ดาวเด่น, target debtors, quick win
- Logic: Secured Loan + coverage ratio >= 1 + large debt = highest ROI for collection effort
```python
df['coverage_ratio'] = df['มูลค่าหลักประกันตามสัดส่วน (รวมสังหา)'] / df['ภาระหนี้คงเหลือ'].replace(0, float('nan'))
result = df[
    (df['สถานะหลักประกัน'] == 'Secured Loan') &
    (df['coverage_ratio'] >= 1.0)
].nlargest(10, 'ภาระหนี้คงเหลือ')
```

---

## Portfolio Exposure Analysis

### Total outstanding debt (entire portfolio)
- User may say: หนี้รวมทั้งหมด, total portfolio debt, ยอดหนี้รวม, portfolio size, มูลค่าพอร์ตทั้งหมด, หนี้ทั้งพอร์ต, รวมทั้งหมดเท่าไหร่, grand total, ยอดรวม, ภาระหนี้ทั้งสิ้น
- Code: `result = df['ภาระหนี้คงเหลือ'].sum()`

### Total collateral value
- User may say: มูลค่าหลักประกันรวม, total collateral, ราคาทรัพย์รวม, ทรัพย์รวมทั้งหมด, มูลค่าทรัพย์สินรวม, ทรัพย์ทั้งพอร์ตราคาเท่าไหร่
- Code: `result = df['มูลค่าหลักประกันตามสัดส่วน (รวมสังหา)'].sum()`

### Portfolio-level coverage ratio
- User may say: coverage ratio ภาพรวม, อัตราหลักประกันรวม, portfolio coverage, สัดส่วนทรัพย์ต่อหนี้ทั้งพอร์ต, ทรัพย์คุ้มหนี้แค่ไหน, coverage ทั้งพอร์ต
- Code: `result = df['มูลค่าหลักประกันตามสัดส่วน (รวมสังหา)'].sum() / df['ภาระหนี้คงเหลือ'].sum()`

### Secured vs Clean Loan breakdown
- User may say: แบ่งประเภทสินเชื่อ, secured vs clean, สัดส่วนหลักประกัน, มีหลักประกันกับไม่มีสัดส่วนเท่าไหร่, เปรียบเทียบ secured กับ clean, กี่คนมีทรัพย์กี่คนไม่มี
- Code: `result = df.groupby('สถานะหลักประกัน').agg(จำนวน=('รหัสลูกหนี้','count'), ภาระหนี้=('ภาระหนี้คงเหลือ','sum')).reset_index()`

---

## Difficult / Hard-to-collect Debtors

### Debtors that are hard to manage / difficult to collect
- User may say: ลูกหนี้ที่จัดการยาก, ยากต่อการติดตาม, เก็บหนี้ยาก, hard to collect, difficult debtors, ลูกหนี้ปัญหา, ลูกหนี้ที่เก็บยาก, ลูกหนี้ไม่ร่วมมือ, ลูกหนี้ดื้อ, ลูกหนี้น่าเป็นห่วง, เก็บยาก, ปัญหา, ไม่ยอมจ่าย
- Logic: "hard to manage" = Non-TDR + Clean Loan (no collateral, no cooperation)
- Code:
```python
hard = df[
    (df['สถานะการประนอมหนี้'] == 'Non-TDR') &
    (df['สถานะหลักประกัน'] == 'Clean Loan')
]
result = hard
```

### Top N departments with most difficult debtors (count only)
- User may say: ฝ่ายงานที่มีลูกหนี้จัดการยาก top 5, ฝ่ายไหนมีปัญหามากสุด, แผนกไหนเก็บยากสุด, ทีมไหนมีลูกหนี้ดื้อเยอะ, ฝ่ายไหนน่าเป็นห่วงสุด
- IMPORTANT: Use .size().reset_index(name='นับลูกหนี้') — do NOT use named agg for the count column
- Code:
```python
hard = df[
    (df['สถานะการประนอมหนี้'] == 'Non-TDR') &
    (df['สถานะหลักประกัน'] == 'Clean Loan')
]
result = hard.groupby('ชื่อฝ่ายงาน').size().reset_index(name='นับลูกหนี้').sort_values('นับลูกหนี้', ascending=False).head(5)
```

### Top N departments — count + debt totals combined
- User may say: ขอทั้งจำนวนและยอดหนี้, รวมยอดหนี้ด้วย, ขอตัวเลขจำนวนลูกหนี้จริงและภาระหนี้, ขอครบทุกตัวเลข
- CRITICAL: Do ONE groupby with ALL required metrics — NEVER do two separate groupbys and try to map/join on different top-N lists (they won't match and produce NaN)
- Code:
```python
hard = df[
    (df['สถานะการประนอมหนี้'] == 'Non-TDR') &
    (df['สถานะหลักประกัน'] == 'Clean Loan')
]
grp = hard.groupby('ชื่อฝ่ายงาน')
result = pd.DataFrame({
    'นับลูกหนี้': grp['รหัสลูกหนี้'].count(),
    'ภาระหนี้รวม': grp['ภาระหนี้คงเหลือ'].sum(),
    'เงินต้นรวม': grp['เงินต้นคงเหลือ'].sum(),
}).reset_index().sort_values('นับลูกหนี้', ascending=False).head(5)
```

---

## Collection Table Queries (df_coll)

IMPORTANT: The collection table (df_coll) is separate from outstanding (df).
Use df_coll for any question about "ผลเรียกเก็บ", "เก็บได้", "Cash", "LGO1", "Total Actual NPL" by group/team/officer.
Period filter for df_coll uses FULL month names: 'March', 'December' (NOT 'Mar', 'Dec').

### ผลเรียกเก็บ by geographic work group (กลุ่มงาน)
- User may say: ผลเรียกเก็บกลุ่มกรุงเทพกลาง, เก็บได้เท่าไหร่กลุ่ม X, report ผลเรียกเก็บกลุ่ม X,
               ทีม X เก็บได้กี่บาท, ผลงานกลุ่ม X, กลุ่มงาน X เก็บได้เท่าไหร่, ผลเรียกเก็บของ X
- CRITICAL: "กลุ่มกรุงเทพกลาง" / "ทีมเชียงใหม่" / "กลุ่มขอนแก่น" → `กลุ่มงาน` column in df_coll
  Do NOT use `รหัสชื่อการดำเนินงาน` — that column is operation type (01-07), not geographic group.
- Two naming conventions exist simultaneously → always use str.contains, never ==
- Code (report for one group):
```python
df_coll = df_coll[(df_coll['ปี'] == 2026) & (df_coll['เดือน'] == 'March')]
grp = df_coll[df_coll['กลุ่มงาน'].str.contains('กรุงเทพกลาง', na=False)]
result = grp[['รหัสลูกหนี้', 'ชื่อลูกหนี้', 'กลุ่มงาน', 'รหัสชื่อการดำเนินงาน',
              'Cash Non TDR', 'Cash TDR', 'LGO1', 'Total Actual NPL']]
```
- Code (summary total for one group):
```python
df_coll = df_coll[(df_coll['ปี'] == 2026) & (df_coll['เดือน'] == 'March')]
grp = df_coll[df_coll['กลุ่มงาน'].str.contains('กรุงเทพกลาง', na=False)]
result = grp[['Cash Non TDR', 'Cash TDR', 'LGO1', 'Total Actual NPL']].sum().to_frame('ยอดรวม')
```

### ผลเรียกเก็บ across all groups (ranking)
- User may say: กลุ่มงานไหนเก็บได้มากสุด, ranking ผลเรียกเก็บ, เปรียบเทียบผลเรียกเก็บแต่ละทีม,
               แต่ละกลุ่มเก็บได้เท่าไหร่, สรุปผลเรียกเก็บแยกกลุ่ม
- Code:
```python
df_coll = df_coll[(df_coll['ปี'] == 2026) & (df_coll['เดือน'] == 'March')]
result = df_coll.groupby('กลุ่มงาน').agg(
    จำนวนลูกหนี้=('รหัสลูกหนี้', 'nunique'),
    Cash_Non_TDR=('Cash Non TDR', 'sum'),
    Cash_TDR=('Cash TDR', 'sum'),
    LGO1=('LGO1', 'sum'),
    Total_Actual_NPL=('Total Actual NPL', 'sum'),
).sort_values('Total_Actual_NPL', ascending=False).reset_index()
```

### ผลเรียกเก็บ by case officer (รหัสพนักงาน / ชื่อพนักงาน)
- User may say: พนักงานคนไหนเก็บได้มากสุด, ผลงานพนักงาน, officer X เก็บได้เท่าไหร่,
               ผลเรียกเก็บแยกตามพนักงาน, ranking พนักงาน, เจ้าหน้าที่ไหนทำได้ดีสุด
- Code:
```python
df_coll = df_coll[(df_coll['ปี'] == 2026) & (df_coll['เดือน'] == 'March')]
result = df_coll.groupby(['รหัสพนักงาน', 'ชื่อพนักงาน'])['Total Actual NPL'].sum()\
               .sort_values(ascending=False).reset_index()
```

---

## Organizational Breakdown

### Debt or debtors by work group
- User may say: แยกตามกลุ่มงาน, by team, by work group, กลุ่มงานไหนมีหนี้มากสุด, ทีมไหนดูแลหนี้เยอะสุด, กลุ่มงาน, แต่ละทีม
- Code: `df.groupby('ชื่อกลุ่มงาน')['ภาระหนี้คงเหลือ'].sum().sort_values(ascending=False)`

### Debt or debtors by department
- User may say: แยกตามฝ่าย, by department, ฝ่ายไหนดูแลหนี้มากสุด, แต่ละฝ่าย, แยกตามฝ่ายงาน, แผนกไหน, ฝ่าย, department ไหน
- Code: `df.groupby('ชื่อฝ่ายงาน')['ภาระหนี้คงเหลือ'].sum().sort_values(ascending=False)`

### Debt or debtors by portfolio batch
- User may say: แยกตาม port, by portfolio, พอร์ตไหนมีหนี้มาก, แต่ละพอร์ต, port ไหน, portfolio batch, รหัสพอร์ต
- Code: `df.groupby('รหัส Port')['ภาระหนี้คงเหลือ'].sum().sort_values(ascending=False)`

---

## Geographic Breakdown — CRITICAL PATTERN

### "จังหวัดไหน/โซนไหน/พื้นที่ไหน" = GROUP BY, not top-N individual rows
- User may say: จังหวัดไหนมีหนี้มาก, โซนไหนมีลูกหนี้เยอะ, พื้นที่ไหนมีความเสี่ยงสูง, แต่ละจังหวัด, province breakdown, ภูมิภาคไหน
- CRITICAL: These questions need groupby aggregation — NEVER return top-N individual debtor rows.
- Code:
```python
result = df.groupby('จังหวัด').agg(
    จำนวนลูกหนี้=('รหัสลูกหนี้', 'count'),
    ภาระหนี้รวม=('ภาระหนี้คงเหลือ', 'sum'),
    ภาระหนี้เฉลี่ย=('ภาระหนี้คงเหลือ', 'mean'),
).reset_index().sort_values('ภาระหนี้รวม', ascending=False)
```

---

## List Unique Column Values / Enumerate Data Types

SCOPE: This section covers listing unique VALUES within a specific DATA COLUMN (e.g. what collateral types exist, what operation groups exist).
DISAMBIGUATION: If the user asks "มีตารางอะไรบ้าง / มีข้อมูลอะไรบ้าง / what tables do you have / what data is available" — that is a meta-question about the SYSTEM, NOT a data enumeration query. Do NOT run pandas code for that. Answer from system knowledge: NPL module has 3 tables — outstanding (ลูกหนี้คงค้าง), outstandingcol (รายการหลักประกัน), collection (ผลเรียกเก็บ).

CRITICAL PATTERN — "ประเภทอะไรบ้าง / มีประเภทใดบ้าง / มีกี่ประเภท / list all types / มีค่าอะไรบ้างใน column X" queries.
NEVER assign `.unique()` directly to result — it returns an ArrowStringArray that cannot be rendered.
Always use `value_counts()` (with counts) or `pd.Series(col.dropna().unique(), name='col')` (just values).

### ประเภทหลักประกันมีอะไรบ้าง — outstandingcol table
- User may say: มีประเภทหลักประกันอะไรบ้าง, หลักประกันแบ่งเป็นกี่ประเภท, ประเภทหลักประกันมีอะไร, list collateral types, ประเภทของหลักประกัน
- Table: **outstandingcol** (df)
- Code (with counts):
```python
result = df['ประเภทหลักประกัน'].dropna().value_counts().reset_index()
result.columns = ['ประเภทหลักประกัน', 'จำนวน']
```
- Code (just list, no counts):
```python
result = pd.Series(df['ประเภทหลักประกัน'].dropna().unique(), name='ประเภทหลักประกัน')
```

### ประเภทย่อยหลักประกันมีอะไรบ้าง — outstandingcol table
- User may say: มีประเภทย่อยอะไรบ้าง, ประเภทย่อยหลักประกัน, sub-type หลักประกัน, ประเภทย่อยมีกี่แบบ
- Table: **outstandingcol** (df)
- Code:
```python
result = df['ประเภทย่อยหลักประกัน'].dropna().value_counts().reset_index()
result.columns = ['ประเภทย่อยหลักประกัน', 'จำนวน']
```

### สถานะหลักประกัน (per-collateral item) — outstandingcol table
- User may say: สถานะหลักประกันมีอะไรบ้าง, สถานะของทรัพย์หลักประกัน, collateral status types, ทรัพย์มีสถานะอะไรบ้าง
- Table: **outstandingcol** (df) — this is the per-item status (e.g. ใช้ค้ำประกัน, ปลอดจำนอง etc.)
- NOTE: Do NOT confuse with 'สถานะหลักประกัน' in outstanding table which holds 'Secured Loan'/'Clean Loan'
- Code:
```python
result = df['สถานะหลักประกัน'].dropna().value_counts().reset_index()
result.columns = ['สถานะหลักประกัน', 'จำนวน']
```

### กลุ่มการดำเนินงานมีอะไรบ้าง — outstanding table
- User may say: มีกลุ่มการดำเนินงานอะไรบ้าง, แบ่งกลุ่มอย่างไร, collection groups คืออะไร, กลุ่มมีกี่กลุ่ม, ประเภทกลุ่มดำเนินงาน
- Table: **outstanding** (df)
- Code:
```python
result = df['รหัสชื่อกลุ่มการดำเนินงาน'].dropna().value_counts().reset_index()
result.columns = ['กลุ่มการดำเนินงาน', 'จำนวนลูกหนี้']
```
