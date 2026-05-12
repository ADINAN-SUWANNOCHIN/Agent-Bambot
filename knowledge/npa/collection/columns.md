# Column Dictionary — NPA Collection Table

One row = one collection event/payment for an NPA asset.
Key join column: `รหัสตลาด` (links back to NPA outstanding table).

---

## Payment Columns — CRITICAL: Total Actual covers all types

`ผลเรียกเก็บ` for NPA = Full Payment + Installment Payment + Others combined.
**Always use `Total Actual > 0` for "has any payment" queries — never check just one type.**

| Column | Meaning |
|--------|---------|
| `Full Payment` | Full outright purchase payment (ซื้อขาด) |
| `Installment Payment` | Partial/installment payment (ผ่อนชำระ) |
| `Others (ค่าเช่า, ริบเงิน, ดอกเบี้ย)` | Other income: rental income, forfeited deposits, interest |
| `Total Actual` | = Full Payment + Installment Payment + Others — use as the single total |

---

## มีผลเรียกเก็บ (has any payment)

- User may say: มีผลเรียกเก็บ, เก็บได้, มีการชำระ, มีเงินรับ, ขายได้บางส่วน
- Code:
```python
result = df[df['Total Actual'] > 0]
```

## ไม่มีผลเรียกเก็บ (zero payment)

- User may say: เก็บไม่ได้, ไม่มีการชำระ, ไม่มีผลเรียกเก็บ, ยังไม่ขาย
- Code:
```python
result = df[df['Total Actual'] == 0]
```

## ยอดรวมผลเรียกเก็บ

- Code: `result = df['Total Actual'].sum()`

---

## เดือน — CRITICAL: Full English, not abbreviation

- **Values:** `'March'`, `'December'` (full English month names)
- **NOT** `'Mar'` or `'Dec'` — unlike the NPA outstanding table which uses abbreviations
- Filter example: `df[df['เดือน'] == 'March']`

---

## Other Key Columns

| Column | Meaning |
|--------|---------|
| `รหัสตลาด` | Asset ID — join key to NPA outstanding table |
| `รหัสลูกค้า` | Buyer/customer ID (for installment sales) |
| `ชื่อนามสกุล` | Buyer name |
| `ประเภทผลเรียกเก็บ` | Collection type (e.g. ผ่อนชำระ, ซื้อขาด) |
| `ประเภทการขายทรัพย์` | Disposal method |
| `ประเภททรัพย์` | Asset type |
| `จังหวัด` / `เขต` / `ตำบล` | Location of the asset |
| `สายงาน` / `ฝ่ายงาน` / `กลุ่มงาน` | Org hierarchy |
| `รหัสพนักงาน` / `พนักงาน` | Case officer |
| `รหัส Port` | Portfolio code |
