# Question Examples & Test Cases

Test reference sheet. Each case documents the question, expected behavior, and any fix history.
Module defaults to **NPL** unless marked `[NPA]`.

---

## 1. NPL Collection — กลุ่มงาน Queries

These queries must route to the **collection table (df_coll)**, not outstanding.

| # | Question | Expected Table | Key Columns | Notes |
|---|----------|---------------|-------------|-------|
| 1.1 | ขอรายงาน NPL ผลเรียกเก็บของลูกหนี้กลุ่มกรุงเทพกลาง | collection | กลุ่มงาน, Total Actual NPL | Fixed: was routing to outstanding+outstandingcol |
| 1.2 | กลุ่มกรุงเทพกลางเก็บได้รวมเท่าไหร่เดือนมีนาคม | collection | กลุ่มงาน, Total Actual NPL | เดือน = 'March' (full name, not 'Mar') |
| 1.3 | กลุ่มงานไหนเก็บได้มากสุดเดือนนี้ | collection | กลุ่มงาน, Total Actual NPL | Ranking all groups |
| 1.4 | พนักงานคนไหนเก็บได้มากที่สุด | collection | รหัสพนักงาน, ชื่อพนักงาน, Total Actual NPL | Officer ranking |
| 1.5 | ลูกหนี้ที่มี LGO1 มีกี่ราย | collection | LGO1 | LGO1 > 0 (negatives are reversals) |
| 1.6 | ผลเรียกเก็บแยกตามกลุ่มงานทั้งหมด | collection | กลุ่มงาน, Cash Non TDR, Cash TDR, LGO1 | groupby กลุ่มงาน |

**Critical disambiguation:**
- `กลุ่มงาน` = geographic team (กรุงเทพกลาง, เชียงใหม่, ขอนแก่น) — in df_coll
- `รหัสชื่อการดำเนินงาน` = operation type (01 ประนอมหนี้, 03 ดำเนินคดี) — in df_coll
- `ชื่อกลุ่มงาน` = org team in **outstanding only** — does NOT exist in collection table

---

## 2. Month Format — Period Filter Edge Cases

Two formats exist in the same dataset. Wrong format returns 0 rows silently.

| Table | เดือน format | Example | Wrong (returns 0 rows) |
|-------|------------|---------|------------------------|
| outstanding / outstandingcol | Abbreviated | `'Mar'`, `'Dec'` | `'March'`, `'มีนาคม'` |
| collection | Full English | `'March'`, `'December'` | `'Mar'`, `'Dec'` |

| # | Question | Table | Correct Filter |
|---|----------|-------|----------------|
| 2.1 | ลูกหนี้ค้างชำระเดือนมีนาคม 2566 | outstanding | `ปี == 2026` & `เดือน == 'Mar'` |
| 2.2 | ผลเรียกเก็บเดือนมีนาคม 2566 | collection | `ปี == 2026` & `เดือน == 'March'` |
| 2.3 | ยอดหนี้ ธ.ค. 2568 | outstanding | `ปี == 2025` & `เดือน == 'Dec'` |
| 2.4 | เก็บได้เดือนธันวาคมที่แล้ว | collection | `ปี == 2025` & `เดือน == 'December'` |

---

## 3. Follow-up Chain Queries

These test the LLM-based follow-up classifier. Q2 must narrow Q1's result, not re-query the whole table.

### 3A — All columns follow-up (ขอข้อมูลเพิ่มเติม / อยากได้ทุก column)

| Turn | Question | Expected Behavior |
|------|----------|-------------------|
| Q1 | ขอรายงาน NPL ผลเรียกเก็บของลูกหนี้กลุ่มกรุงเทพกลาง | collection → 284 rows, 7 columns |
| Q2 | ขอข้อมูลเพิ่มเติม อยากได้ทุก column | collection → same 284 rows, all columns |

Expected Q2 code pattern:
```python
df_coll = df_coll[(df_coll['ปี'] == 2026) & (df_coll['เดือน'] == 'March')]
result = df_coll[df_coll['รหัสลูกหนี้'].isin(_prev_ids)]
```

### 3B — Period refinement (เอาแค่ของเดือนล่าสุด)

| Turn | Question | Expected Behavior |
|------|----------|-------------------|
| Q1 | ขอข้อมูลเพิ่มเติมของลูกหนี้กลุ่มนี้ เอาทุก column | outstanding → 413 rows, 36 columns |
| Q2 | เอาแค่ของเดือนล่าสุด | outstanding → same 413 IDs filtered to latest period only |

Expected Q2 code pattern:
```python
df = df[(df['ปี'] == 2026) & (df['เดือน'] == 'Mar')]
result = df[df['รหัสลูกหนี้'].isin(_prev_ids)]
```

### 3C — Follow-up that should NOT inherit (new independent query)

| Turn | Question | Expected Behavior |
|------|----------|-------------------|
| Q1 | ขอรายงาน NPL ผลเรียกเก็บกลุ่มกรุงเทพกลาง | collection → 284 rows |
| Q2 | ขอลูกหนี้ที่มียอดหนี้เกิน 10 ล้านทั้งหมด | outstanding → ALL debtors > 10M, NOT filtered to 284 |

Q2 contains no continuation signals → classifier should say `new` → `_prev_ids` NOT injected.

### 3D — Display N rows follow-up

| Turn | Question | Expected Behavior |
|------|----------|-------------------|
| Q1 | ลูกหนี้ที่มีหนี้มากที่สุด top 20 | outstanding → top 20 rows |
| Q2 | แสดง 5 รายแรก | outstanding → same table, show first 5 rows (uses `_DISPLAY_ONLY_PAT` fast path) |

---

## 4. Report Export (ขอรายงาน)

These should produce a downloadable Excel file and show the download button.

| # | Question | Expected Output |
|---|----------|----------------|
| 4.1 | ขอรายงาน NPL ผลเรียกเก็บกลุ่มกรุงเทพกลาง | Excel file, collection rows, download button appears |
| 4.2 | export ลูกหนี้ TDR ทั้งหมดเป็น Excel | Excel file, outstanding TDR rows |
| 4.3 | ดาวน์โหลดรายชื่อลูกหนี้ที่ไม่มีหลักประกัน | Excel file, outstanding Clean Loan rows |
| 4.4 | ขอออกรายงาน NPA ทรัพย์ที่ถือครองเกิน 3 ปี | `[NPA]` Excel file, outstanding holding > 3 years |

---

## 5. Excel Upload — Account List Queries

Upload a file containing a list of account numbers, then query about those accounts.

### Setup
1. Upload Excel/CSV with a column named `รหัสลูกหนี้` (NPL) or `รหัสตลาด` (NPA)
2. Click 📎 to open upload row → select file
3. Status shows: "Loaded N rows from filename — join key: รหัสลูกหนี้"

### Pattern A — Filter portfolio to uploaded accounts

| # | Question after upload | Expected Behavior |
|---|----------------------|-------------------|
| 5.1 | ขอข้อมูลของรหัสในไฟล์นี้ | outstanding filtered to uploaded IDs |
| 5.2 | ลูกหนี้ในไฟล์นี้มียอดหนี้รวมเท่าไหร่ | sum of ภาระหนี้คงเหลือ for uploaded IDs |
| 5.3 | ใครในไฟล์นี้เป็น TDR บ้าง | outstanding filtered to uploaded IDs + สถานะการประนอมหนี้ == 'TDR' |

Expected code pattern (Pattern A):
```python
ids = df_user['รหัสลูกหนี้'].dropna().unique()
result = df[df['รหัสลูกหนี้'].isin(ids)]
```

### Pattern B — Enrich uploaded file with all portfolio columns

| # | Question after upload | Expected Behavior |
|---|----------------------|-------------------|
| 5.4 | อยากได้ทุก column ของรหัสในไฟล์นี้ | df_user merged with df on รหัสลูกหนี้ — all columns |
| 5.5 | ขอข้อมูลเพิ่มเติม อยากได้ทุก column | same as 5.4 |

Expected code pattern (Pattern B):
```python
result = df_user.merge(df, on='รหัสลูกหนี้', how='left')
```

---

## 6. NPA-Specific Queries

### 6A — Org hierarchy scope (fixed bug)

`ชื่อกลุ่มงาน` exists **only** in NPA outstanding. It does NOT exist in NPA collection.

| # | Module | Question | Table | Correct Column |
|---|--------|----------|-------|----------------|
| 6.1 | NPA | ทรัพย์ที่ดูแลโดยกลุ่มงาน X มีกี่รายการ | outstanding | `ชื่อกลุ่มงาน` |
| 6.2 | NPA | ผลเรียกเก็บของทรัพย์ในจังหวัด X | collection | `จังหวัด` (NOT `ชื่อกลุ่มงาน`) |
| 6.3 | NPA | ผลเรียกเก็บแยกตามเขต | collection | `เขต` |

### 6B — Standard NPA queries

| # | Question | Expected |
|---|----------|----------|
| 6.4 | ทรัพย์ที่ถือครองเกิน 5 ปีมีกี่รายการ | `ระยะเวลาถือครอง NPA (ปี)` > 5 |
| 6.5 | ทรัพย์ที่ดินในกรุงเทพมีกี่รายการ | `ประเภททรัพย์`.contains('ที่ดิน') + `จังหวัด` == 'กรุงเทพ...' |
| 6.6 | ทรัพย์เกรด A ราคาประเมินรวมเท่าไหร่ | `เกรดทรัพย์` == 'A', sum ราคาประเมิน |
| 6.7 | ต้นทุนต่อราคาประเมินเฉลี่ยของทรัพย์ที่ดิน | `ต้นทุนต่อราคาประเมิน` mean, filter ที่ดิน |

---

## 7. Cross-Period / Trend Queries

These must NOT apply the default period filter (they compare across periods).

| # | Question | Expected Behavior |
|---|----------|-------------------|
| 7.1 | เปรียบเทียบยอดหนี้รวม Q4 2568 กับ มี.ค. 2569 | No period filter; groupby ปี+เดือน |
| 7.2 | แนวโน้มผลเรียกเก็บย้อนหลัง 3 เดือน | collection; no period filter; groupby ปี+เดือน |
| 7.3 | YoY เปรียบเทียบมีนาคม 2568 กับมีนาคม 2569 | two separate period filters joined/compared |

---

## 8. Common Traps — Queries That Previously Failed

| # | Question | Old Wrong Behavior | Fixed Behavior |
|---|----------|--------------------|---------------|
| 8.1 | ขอรายงาน NPL ผลเรียกเก็บกลุ่มกรุงเทพกลาง | routed to outstanding, used `ชื่อกลุ่มงาน`, 0 rows | routes to collection, uses `กลุ่มงาน`, 284 rows |
| 8.2 | Q2: ขอข้อมูลเพิ่มเติม อยากได้ทุก column (after collection query) | re-routed to outstanding, 1,578 rows | stays on collection, 284 rows, all columns |
| 8.3 | Q2: เอาแค่ของเดือนล่าสุด (after outstanding query) | ignored _prev_ids, returned 88,373 rows | uses _prev_ids, returns 413 rows filtered to latest period |
| 8.4 | ผลเรียกเก็บเดือนมีนาคม (collection table) | used `'Mar'`, 0 rows | uses `'March'`, correct rows |
| 8.5 | NPA: ผลเรียกเก็บของกลุ่มงาน X | used `ชื่อกลุ่มงาน` in collection (column doesn't exist), error | uses `จังหวัด`/`เขต` in collection table |
| 8.6 | any query after Grand Total rows in Excel | `ปี` dtype became str, int filter returned 0 rows | Grand Total rows stripped at load time |
