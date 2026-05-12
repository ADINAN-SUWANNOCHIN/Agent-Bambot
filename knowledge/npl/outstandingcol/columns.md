# Column Dictionary — NPL Outstandingcol Table

STRUCTURAL WARNING: One row = ONE COLLATERAL ITEM, not one debtor.
A debtor with 5 collateral pieces = 5 rows, each with the same รหัสลูกหนี้.

---

## CRITICAL STRUCTURAL RULES

1. **NEVER use `len(df)` for debtor counts** — that counts collateral rows, not people.
2. **ALWAYS use `.drop_duplicates('รหัสลูกหนี้')` or `['รหัสลูกหนี้'].nunique()`** for unique debtors.
3. Join key to outstanding table: `รหัสลูกหนี้`

```python
# Correct debtor count pattern:
filtered = df[df['some_condition']]
result_df = filtered.drop_duplicates('รหัสลูกหนี้')
result = len(result_df)   # unique debtor count
```

---

## จำนวนทรัพย์หลักประกัน — PRE-COMPUTED PIECE COUNT

- **Exact column name:** `จำนวนทรัพย์หลักประกัน`
- **English:** collateral piece count per debtor
- **CRITICAL:** Pre-computed total for the debtor — the SAME value is REPEATED on every row for that debtor.
- **NEVER `.sum()` or `.mean()` this column** — multiplies the count by row count.
- **Use for filtering only:** `df[df['จำนวนทรัพย์หลักประกัน'] > N]`
- **Correct pattern for "debtors with > N pieces":**
```python
filtered = df[df['จำนวนทรัพย์หลักประกัน'] > 3]
result_df = filtered.drop_duplicates('รหัสลูกหนี้')
result = len(result_df)
```

---

## Province / Location — CRITICAL PREFIX

- **Province:** `ที่อยู่ทรัพย์ - จังหวัด` (NOT plain `จังหวัด` — that column does not exist here)
- **District:** `ที่อยู่ทรัพย์ - อำเภอ`
- **Sub-district:** `ที่อยู่ทรัพย์ - ตำบล`
- **Project name:** `ที่อยู่ทรัพย์ - ชื่อโครงการ`

```python
# Province breakdown:
result = df.groupby('ที่อยู่ทรัพย์ - จังหวัด').size().reset_index(name='จำนวนหลักประกัน')
# Unique debtors per province:
result = df.drop_duplicates('รหัสลูกหนี้').groupby('ที่อยู่ทรัพย์ - จังหวัด').size()
```

---

## Land Area Columns

| Column | Unit | Note |
|--------|------|------|
| `ไร่` | Rai | 1 ไร่ = 400 ตรว. = 1,600 ตรม. |
| `งาน` | Ngan | 1 งาน = 100 ตรว. = 400 ตรม. |
| `วา` | Wah | linear (2 meters) |
| `พื้นที่ (ตรว.)` | Square Wah | pre-computed total area |
| `พื้นที่ (ตรม.)` | Square meters | pre-computed total area |

**Normalize to ตรว.:**
```python
df['พื้นที่_ตรว'] = df['ไร่'].fillna(0)*400 + df['งาน'].fillna(0)*100 + df['วา'].fillna(0)
```

---

## เลขที่เอกสารสิทธิ์

- **Exact column name:** `เลขที่เอกสารสิทธิ์`
- **English:** title deed number, land title document number
- **Aliases:** เลขโฉนด, โฉนด, เลขที่โฉนด, title deed, เอกสารสิทธิ์, document number
- **Type:** numeric (int64)

---

## มูลค่าหลักประกัน / มูลค่าหลักประกันตามสัดส่วน

- `มูลค่าหลักประกัน` — raw appraisal value of this individual collateral piece
- `มูลค่าหลักประกันตามสัดส่วน` — proportionally allocated value (when one collateral is shared across multiple loans)
- `%สัดส่วนใน` — proportion allocated to this debtor (float, e.g. 100.0 = 100%)

---

## Other Key Columns

| Column | Note |
|--------|------|
| `รหัสลูกหนี้` | Debtor ID — join key, NOT unique per row |
| `ชื่อลูกหนี้` | Debtor name |
| `รหัส Port` | Portfolio code |
| `วันที่ซื้อ Port` | Portfolio purchase date |
| `เลขที่ Client Number` | Client number (= รหัสลูกหนี้ usually) |
| `รหัสชื่อกลุ่มการดำเนินงาน` | Collection group (same as outstanding table) |
| `ประเภทหลักประกัน` | Collateral type (ที่ดินเปล่า, บ้าน, เครื่องจักร, etc.) |
| `ประเภทหลักประกัน TFRS` | TFRS 9 classification |
| `ประเภทหลักประกันย่อย` | Sub-type (โฉนดที่ดิน, นส.3, etc.) |
| `เกรดทรัพย์` | Asset grade A/B/C/D — may have nulls |
| `สถานะหลักประกัน` | Secured Loan / Clean Loan |
| `ช่วงมูลค่าหลักประกันคงเหลือ` | Value range bucket |
| `ช่วงเงินต้นคงเหลือ` | Principal range bucket |
| `ช่วงระยะเวลาถือครอง NPL` | Holding period range |
| `ปี` / `เดือน` | Snapshot period — เดือน = 'Mar' or 'Dec' (abbreviations, same as outstanding) |
