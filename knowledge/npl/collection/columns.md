# Column Dictionary — NPL Collection Table

One row = one debtor's monthly collection result.
Key columns and how to use them correctly.

---

## Payment Columns — CRITICAL: ALL THREE COUNT AS ผลเรียกเก็บ

`ผลเรียกเก็บ` (collection result / payment received) = Cash Non TDR + Cash TDR + LGO1 combined.
**Never check only Cash columns and ignore LGO1 — that undercounts.**

| Column | Type | Meaning |
|--------|------|---------|
| `Cash Non TDR` | int | Voluntary cash payment from Non-TDR debtors |
| `Cash TDR` | int | Voluntary cash payment from TDR debtors |
| `LGO1` | int | Court-enforced collection via กรมบังคับคดี (Legal Execution Dept). Can be negative (reversals/adjustments). |
| `Total Actual NPL` | int | = Cash Non TDR + Cash TDR + LGO1. Use this as the single total payment column. |

---

## มีผลเรียกเก็บ (has any payment)

- User may say: มีผลเรียกเก็บ, มีการชำระ, เก็บได้, มีเงินรับ, มีการจ่าย, ชำระแล้ว, จ่ายมาแล้ว, มีประวัติจ่าย
- **Use `Total Actual NPL > 0` — this covers Cash + LGO1 in one column**
- Code:
```python
result = df[df['Total Actual NPL'] > 0]
```
- WRONG: `df[(df['Cash Non TDR'] > 0) | (df['Cash TDR'] > 0)]` — misses LGO1 payments entirely

---

## ไม่มีผลเรียกเก็บ (zero payment)

- User may say: ไม่มีผลเรียกเก็บ, เก็บไม่ได้, ไม่จ่าย, ไม่มีการชำระ, ยังไม่จ่าย
- Code:
```python
result = df[df['Total Actual NPL'] == 0]
```

---

## ยอดรวมผลเรียกเก็บ (total collected amount)

- User may say: ผลเรียกเก็บรวม, เก็บได้รวมเท่าไหร่, ยอดรวมที่เก็บได้, total collection
- Code: `result = df['Total Actual NPL'].sum()`

---

## LGO1 — Court-Enforced Collection

- User may say: LGO1, บังคับคดี, กรมบังคับคดี, court enforcement, ยึดทรัพย์เก็บเงิน
- Column: `LGO1`
- NOTE: LGO1 values can be negative — these are reversals or adjustments, not real payments. Filter with `> 0` when looking for actual collections.
- Code (debtors with LGO1 collection): `df[df['LGO1'] > 0]`
- Code (LGO1 total): `df['LGO1'].sum()`

---

## Other Columns

| Column | Meaning |
|--------|---------|
| `รหัสลูกหนี้` | Debtor ID — join key to outstanding table |
| `ชื่อลูกหนี้` | Debtor name |
| `สถานะการประนอมหนี้` | TDR / Non-TDR status of the debtor |
| `ประเภทธุรกิจ` | Business type of the debtor |
| `ประเภทสินเชื่อ` | Loan type (e.g. Housing Loan) |
| `รหัสชื่อการดำเนินงาน` | Operation sub-group code |
| `สายงาน` / `ฝ่ายงาน` / `กลุ่มงาน` | Org hierarchy (division → dept → team) |
| `รหัสพนักงาน` / `ชื่อพนักงาน` | Case officer responsible |
| `ปี` / `เดือน` | Snapshot period — เดือน values are full English: 'March', 'December' (NOT 'Mar'/'Dec' like outstanding table) |

---

## กลุ่มงาน — Geographic Work Team

CRITICAL DISAMBIGUATION — two columns both called "กลุ่ม", completely different meaning:

| Column | Contains | Example values |
|--------|----------|----------------|
| `กลุ่มงาน` | Geographic / org team | กลุ่มกรุงเทพกลาง 1, ส่วนขอนแก่น 2 |
| `รหัสชื่อการดำเนินงาน` | Operation type (01–07) | 01 กลุ่มประนอมหนี้, 03 กลุ่มดำเนินคดี |

When user says "กลุ่มกรุงเทพกลาง", "ทีมเชียงใหม่", "เขตภาคเหนือ" → always `กลุ่มงาน` column.
When user says "กลุ่มประนอมหนี้", "กลุ่ม 01", "กลุ่มบังคับคดี" → always `รหัสชื่อการดำเนินงาน` column.
NEVER mix these two columns.

`กลุ่มงาน` naming conventions (both exist in the same dataset):
- Old format: "กลุ่มกรุงเทพกลาง 1", "กลุ่มกรุงเทพกลาง 2"
- New format: "ส่วนกรุงเทพกลาง 1", "ส่วนกรุงเทพกลาง 2"
→ Always use `str.contains('กรุงเทพกลาง', na=False)` to capture both naming conventions.

Code (filter collection by work group):
```python
df_coll = df_coll[(df_coll['ปี'] == 2026) & (df_coll['เดือน'] == 'March')]
grp = df_coll[df_coll['กลุ่มงาน'].str.contains('กรุงเทพกลาง', na=False)]
result = grp[['รหัสลูกหนี้', 'ชื่อลูกหนี้', 'กลุ่มงาน',
              'Cash Non TDR', 'Cash TDR', 'LGO1', 'Total Actual NPL']]
```

Code (total collection by group):
```python
df_coll = df_coll[(df_coll['ปี'] == 2026) & (df_coll['เดือน'] == 'March')]
result = df_coll.groupby('กลุ่มงาน')['Total Actual NPL'].sum().sort_values(ascending=False).reset_index()
```

---

## Period Filter — FULL month names only

WRONG: `df_coll[df_coll['เดือน'] == 'Mar']`   ← returns 0 rows silently
RIGHT: `df_coll[df_coll['เดือน'] == 'March']`

The collection table uses full English month names: January, February, March, ..., December.
The outstanding / outstandingcol tables use abbreviated names: Jan, Feb, Mar, ..., Dec.
These are DIFFERENT — always use full names for df_coll.
