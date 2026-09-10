# Ironwood Insurance — Commission Formula

Applied per folio (billing period). This is the logic behind `commissionsByFolio`
in `index.html` and the "Revenue / commission" metric on the Vidura dashboard's
Reports tab.

## 1. Qualification

A producer must meet **one** of the following for a folio to earn any commission
at all:

- Total premium (all carriers, that folio) **≥ $50,000**, regardless of product
  mix, OR
- Total premium **≥ $20,000** AND **2+ Life policies** sold that folio

If neither is met, commission = **$0** for that folio, no matter how much was
written.

## 2. Tier rate

Once qualified, the tier rate is set by total premium for the folio:

| Total Premium | Rate |
|---|---|
| $20,000+  | 6%  |
| $40,000+  | 7%  |
| $60,000+  | 8%  |
| $80,000+  | 9%  |
| $100,000+ | 10% |

## 3. Applying the rate

- **Farmers / Foremost premium** → full tier rate
- **Everything else** (Brokered, Pacific Specialty, other non-Farmers/Foremost
  carriers) → **half** the tier rate
- **Broker Fee premium** → flat **50%**, gated on qualifying (i.e. $0 if not
  qualified)
- **Accelerator bonus**: if qualified and total premium exceeds $120,000, an
  extra **2%** on the amount over $120,000

## 4. Worked example

A producer writes $65,000 this folio: $50,000 Farmers, $10,000 Brokered,
$5,000 in Broker Fees.

- Qualifies (≥ $50,000)
- Tier rate at $65,000 total = 8%
- Farmers/Foremost commission: $50,000 × 8% = $4,000
- Other (Brokered) commission: $10,000 × 4% (half of 8%) = $400
- Broker Fee commission: $5,000 × 50% = $2,500
- Total premium is under $120,000, so no accelerator
- **Total commission: $6,900**

## Source of truth

This file is documentation, not the calculation itself. The live logic lives in
the Python that updates `commissionsByFolio` in `index.html` each time sales
data changes — keep this doc in sync if the plan ever changes.
