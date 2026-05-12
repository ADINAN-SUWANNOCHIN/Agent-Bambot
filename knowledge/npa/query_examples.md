# NPA Query Examples & Intent Mapping

NPA = Non-Performing Asset. Each row in the outstanding table is ONE property/asset.
Key column: `รหัสตลาด` (unique asset ID). There is NO debtor (ลูกหนี้) concept in NPA.
There is NO outstandingcol table — the outstanding table IS the asset-level table.

---

## Asset Counts & Filters

### Count total NPA assets
- User may say: มีทรัพย์กี่รายการ, จำนวนทรัพย์ทั้งหมด, total assets, ทรัพย์ NPA ทั้งหมด
- Code: `result = len(df)`

### Assets with more than N pieces (จำนวนชิ้นทรัพย์)
- User may say: มีหลักประกันมากกว่า 3 ชิ้น, ทรัพย์ที่มีหลายชิ้น, มากกว่า N ชิ้น, assets with multiple pieces
- CRITICAL: Use `จำนวนชิ้นทรัพย์` column directly — it is pre-computed per row.
- Code:
```python
result_df = df[df['จำนวนชิ้นทรัพย์'] > 3].head(10)
result = len(df[df['จำนวนชิ้นทรัพย์'] > 3])
```

### Province/location of assets (จังหวัดไหน)
- User may say: มีทรัพย์ที่จังหวัดอะไรบ้าง, ทรัพย์อยู่จังหวัดไหน, province list, อยู่แถวไหน, กระจายตามจังหวัด
- CRITICAL: Use `จังหวัด` column directly — it exists in NPA outstanding table.
- Code (list all provinces):
```python
result = df['จังหวัด'].dropna().value_counts().reset_index()
result.columns = ['จังหวัด', 'จำนวนทรัพย์']
```
- Code (filter by specific province):
```python
result_df = df[df['จังหวัด'] == 'กรุงเทพมหานคร']
result = len(result_df)
```

### Filter by asset type (ประเภททรัพย์)
- User may say: ที่ดิน, บ้าน, คอนโด, โรงงาน, อาคาร, ห้องชุด, ที่ดินพร้อมสิ่งปลูกสร้าง
- Code: `df[df['ประเภททรัพย์'].str.contains('ที่ดิน', na=False)]`

### Filter by asset grade (เกรดทรัพย์)
- User may say: ทรัพย์เกรด A, ทรัพย์ดี, ทรัพย์คุณภาพสูง, เกรด D, ทรัพย์ด้อยคุณภาพ
- Code: `df[df['เกรดทรัพย์'].fillna('') == 'A']`

### Filter by asset status (สถานะทรัพย์)
- User may say: ทรัพย์ที่ยังไม่ขาย, ทรัพย์ที่ขายแล้ว, สถานะทรัพย์
- Code: `df[df['สถานะทรัพย์'] == 'ยังไม่ได้ขาย']`  ← use exact value from schema

---

## Valuation & Pricing

### Top assets by appraisal value
- User may say: ทรัพย์ราคาสูงสุด, ราคาประเมินมากสุด, ทรัพย์มูลค่าสูง, expensive assets
- Code: `df.nlargest(10, 'ราคาประเมิน')`

### Top assets by asking price
- User may say: ราคาตั้งขายสูงสุด, asking price สูง
- Code: `df.nlargest(10, 'ราคาตั้งขาย')`

### Assets with margin > X% (appraisal vs cost)
- User may say: ทรัพย์ที่กำไรดี, margin สูง, ราคาประเมินเกินต้นทุน, คุ้มค่าการขาย
- Code:
```python
df['margin_pct'] = (df['ราคาประเมิน'] - df['ต้นทุนรวม']) / df['ต้นทุนรวม'].replace(0, float('nan')) * 100
result = df[df['margin_pct'] > 20].sort_values('margin_pct', ascending=False)
```

### Total portfolio appraisal value
- User may say: มูลค่ารวมทั้งพอร์ต, ราคาประเมินรวม, portfolio value
- Code: `result = df['ราคาประเมิน'].sum()`

### Total portfolio cost basis
- User may say: ต้นทุนรวมทั้งพอร์ต, total cost
- Code: `result = df['ต้นทุนรวม'].sum()`

---

## Geographic / Zone Analysis — CRITICAL PATTERN

### Which province/zone has the highest appraisal price?
- User may say: จังหวัดไหนราคาสูงสุด, โซนไหนแพงสุด, พื้นที่ไหนมีราคาดี, province ranking, ราคาเฉลี่ยแต่ละจังหวัด, จังหวัดที่มีมูลค่าสูง, ทรัพย์แถวไหนแพง
- CRITICAL: "โซนไหน/จังหวัดไหน/พื้นที่ไหน" = GROUP BY province — DO NOT return top-N individual assets.
- Always groupby จังหวัด (or อำเภอ/เขต if asked for district-level) and aggregate.
- Include avg price per area (ราคาต่อตารางวา) when area column exists.
- Code:
```python
filtered_df = df[df['ประเภททรัพย์'].str.contains('ที่ดิน', na=False)].copy()
filtered_df['ราคาต่อตรว'] = filtered_df['ราคาประเมิน'] / filtered_df['พื้นที่ (ตรว.)'].replace(0, float('nan'))
result = filtered_df.groupby('จังหวัด').agg(
    จำนวนทรัพย์=('รหัสตลาด', 'count'),
    ราคาประเมินเฉลี่ย=('ราคาประเมิน', 'mean'),
    ราคาต่อตรวเฉลี่ย=('ราคาต่อตรว', 'mean'),
    ราคาประเมินรวม=('ราคาประเมิน', 'sum'),
).reset_index().sort_values('ราคาต่อตรวเฉลี่ย', ascending=False)
```

### Which district/อำเภอ has highest price?
- User may say: อำเภอไหน, เขตไหน, district ไหน, ย่านไหน, ทำเลไหน
- Same pattern but groupby อำเภอ or เขต instead of จังหวัด:
```python
result = df.groupby(['จังหวัด', 'อำเภอ']).agg(
    จำนวนทรัพย์=('รหัสตลาด', 'count'),
    ราคาประเมินเฉลี่ย=('ราคาประเมิน', 'mean'),
).reset_index().sort_values('ราคาประเมินเฉลี่ย', ascending=False).head(10)
```

---

## Holding Period

### Assets held longer than N years
- User may say: ถือครองมานานกว่า 3 ปี, holding period เกิน, ทรัพย์เก่า, ค้างอยู่นาน, ถือมานานแล้ว
- IMPORTANT: Use `ระยะเวลาถือครอง NPA (ปี)` directly — do NOT compute from ปี/เดือน
- Code:
```python
result = df[df['ระยะเวลาถือครอง NPA (ปี)'] > 3]
```

### Average holding period
- User may say: ถือครองเฉลี่ยกี่ปี, average holding, ระยะเวลาเฉลี่ย
- Code: `result = df['ระยะเวลาถือครอง NPA (ปี)'].mean()`

### Top N assets with longest holding period
- User may say: ทรัพย์ที่ถือครองนานสุด, ค้างนานสุด, อยู่นานที่สุด
- Code: `result = df.nlargest(10, 'ระยะเวลาถือครอง NPA (ปี)')`

---

## Organizational Breakdown

### Assets by department/team
- User may say: ทรัพย์แต่ละฝ่าย, แยกตามฝ่าย, by department, ฝ่ายไหนดูแลทรัพย์เยอะสุด
- Code: `df.groupby('ชื่อฝ่ายงาน').agg(จำนวนทรัพย์=('รหัสตลาด', 'count'), ราคาประเมินรวม=('ราคาประเมิน', 'sum')).reset_index().sort_values('จำนวนทรัพย์', ascending=False)`

### Assets by property type summary
- User may say: แยกตามประเภทอสังหา, สรุปตามประเภท, breakdown by type
- Code: `result = df.groupby('ประเภททรัพย์').agg(จำนวน=('รหัสตลาด','count'), ราคาประเมินรวม=('ราคาประเมิน','sum')).reset_index()`

---

## NPA Collection Table Queries

### มีผลเรียกเก็บ (has any payment)
- User may say: เก็บได้, มีผลเรียกเก็บ, มีการชำระ, มีเงินรับ, ขายได้บ้าง, มีรายรับ
- Use `Total Actual > 0` — covers Full Payment + Installment + Others
- Code: `result = df[df['Total Actual'] > 0]`
- WRONG: checking only `Full Payment > 0` misses installment and rental income

### ยอดผลเรียกเก็บรวม (total collected amount)
- User may say: เก็บได้รวมเท่าไหร่, ยอดรวมผลเรียกเก็บ, total collection NPA
- Code: `result = df['Total Actual'].sum()`

### แยกตามประเภทผลเรียกเก็บ (breakdown by payment type)
- User may say: ผ่อนชำระกับซื้อขาดเท่าไหร่, แยกประเภทเงินรับ, full vs installment
- Code:
```python
result = pd.DataFrame({
    'Full Payment': [df['Full Payment'].sum()],
    'Installment Payment': [df['Installment Payment'].sum()],
    'Others': [df['Others (ค่าเช่า, ริบเงิน, ดอกเบี้ย)'].sum()],
    'Total Actual': [df['Total Actual'].sum()],
})
```

### Collection by department/team
- User may say: ฝ่ายไหนเก็บได้เยอะสุด, แยกผลเรียกเก็บตามฝ่าย, team collection performance
- Code:
```python
result = df.groupby('ฝ่ายงาน').agg(
    จำนวนรายการ=('Total Actual', 'count'),
    ผลเรียกเก็บรวม=('Total Actual', 'sum'),
).reset_index().sort_values('ผลเรียกเก็บรวม', ascending=False)
```

---

## CRITICAL: What NPA does NOT have

- NO รหัสลูกหนี้ column — do NOT use it
- NO outstandingcol table — do NOT reference df_col
- NO TDR / Non-TDR status
- NO Secured Loan / Clean Loan concept
- NO กลุ่มการดำเนินงาน (collection groups) — NPA uses different status columns
- DO NOT groupby to count "collateral pieces per debtor" — the table IS already asset-level

---

## List Unique Values / Enumerate Types

CRITICAL PATTERN — "มีอะไรบ้าง / มีประเภทใดบ้าง / list all types" queries.
NEVER assign `.unique()` directly to result — it returns an ArrowStringArray that cannot be rendered.
Always use `value_counts()` (with counts) or `pd.Series(col.dropna().unique(), name='col')` (just values).

### ประเภททรัพย์มีอะไรบ้าง — outstanding table
- User may say: มีประเภทอสังหาอะไรบ้าง, ประเภทของทรัพย์ NPA, asset types, ทรัพย์แบ่งเป็นกี่ประเภท, ประเภทสินทรัพย์มีอะไร
- Code (with counts):
```python
result = df['ประเภททรัพย์'].dropna().value_counts().reset_index()
result.columns = ['ประเภททรัพย์', 'จำนวนทรัพย์']
```

### เกรดทรัพย์มีอะไรบ้าง — outstanding table
- User may say: เกรดทรัพย์มีกี่เกรด, asset grade types, เกรดมีอะไรบ้าง, แบ่งตามเกรด
- Code:
```python
result = df['เกรดทรัพย์'].dropna().value_counts().reset_index()
result.columns = ['เกรดทรัพย์', 'จำนวนทรัพย์']
```

### สถานะทรัพย์มีอะไรบ้าง — outstanding table
- User may say: สถานะทรัพย์มีอะไรบ้าง, asset status types, สถานะของทรัพย์ NPA, ทรัพย์มีสถานะอะไร
- Code:
```python
result = df['สถานะทรัพย์'].dropna().value_counts().reset_index()
result.columns = ['สถานะทรัพย์', 'จำนวนทรัพย์']
```
