# LedgerMind: Idea Submission

**Project name:** LedgerMind
**Tagline:** An AI Accounts Payable agent that remembers every vendor, learns from every correction, and catches fraud that a system without memory would miss.
**Category:** Operations & Support: Accounts Payable Agent
**Team:** [Your team name]

---

## Short description (about 50 words)

LedgerMind reviews vendor invoices against purchase orders and delivery records, then recommends Approve, Flag or Escalate. Before each decision it recalls that vendor's full history from Hindsight memory. Every human correction is stored, so the agent clears more repeat exceptions on its own each week and still escalates risky cases such as bank-detail changes and duplicate invoices.

---

## Problem

Accounts Payable (AP) teams keep re-investigating the same invoice exceptions. The knowledge of how each vendor behaves, and how past exceptions were settled, lives only in the heads of experienced clerks. Rule-based ERP tools can't adapt without someone editing the rules, and AI chatbots forget everything between sessions. Companies lose time as a result, overpay through duplicate invoices and slow price creep, and stay exposed to vendor-impersonation fraud, where an attacker sends an invoice with "new bank details".

| Pain point | Impact |
|---|---|
| The same exceptions are re-checked by hand every week | Hours lost, slow invoice cycle, late-payment penalties |
| Knowledge walks out when experienced staff leave | Errors and long onboarding for new clerks |
| Fake bank-detail changes | Direct financial loss that often can't be recovered |
| Duplicate and re-numbered invoices | Double payment |
| Small price increases over months | Margin erosion that nobody notices |
| Decisions aren't explained | Audit findings and compliance risk |

---

## Solution

LedgerMind is an AP agent with persistent memory built on **Hindsight** (by Vectorize). For each incoming invoice it:

1. **Matches** the invoice against the Purchase Order and Goods Receipt Note (three-way match) and computes the variances.
2. **Recalls** the vendor's history from Hindsight: past invoices, payment terms, bank account, earlier exceptions and how humans resolved them.
3. **Runs risk checks** for bank-account changes, near-duplicate invoices, price creep, freight or tax overage, and payment-term mismatch.
4. **Reflects** under a fixed mission and set of hard rules, then returns **Approve / Flag / Escalate** with a confidence score, a plain-language reason and the past cases it relied on.
5. **Learns**: when a clerk accepts, overrides or adds a note, that feedback is retained. Hindsight then consolidates the feedback into learned vendor rules with evidence counts.

**Before and after memory:**

| Situation | Without memory | With LedgerMind |
|---|---|---|
| Sharma Logistics bills ₹750 extra freight | "Amount exceeds PO. Review." | "2.1% freight overage matches an approved pattern (12 prior approvals). Auto-approved." |
| Krishna Electricals sends a new bank account | Passes, because amount and PO match | "ESCALATE: 14 invoices over 6 months went to account ending 4417; this one uses 9032. Verify by phone." |
| BrightPack re-sends BP-2291 as BP-2291A | Treated as a new invoice | "Likely duplicate of BP-2291 (same PO, amount and items; paid 11-Jul). Flagged." |
| Apex Steel rod price rises from ₹512 to ₹540 over 5 months | Each invoice matches its own PO | "Unit price up 5.5% since March, above the 3% contract band. Flagged." |

---

## How we use Hindsight

Memory is the core of the product. Without it, LedgerMind is just a rule engine.

- **Retain:** every invoice summary, decision and human correction, tagged by vendor, invoice, PO and date.
- **Recall:** all four retrieval strategies are used:
  - semantic, for similar past exceptions ("freight" vs "shipping");
  - keyword, for exact invoice, PO and account numbers;
  - graph, for links from vendor to PO to approver;
  - temporal, for duplicates within days and price trends over months.
- **Reflect:** produces the final decision under the memory bank's **mission** ("protect against overpayment and fraud, escalate when evidence is weak"), **directives** (never auto-approve a bank-detail change; always cite memories) and **disposition** (high skepticism).
- **Observations:** consolidated vendor rules, such as "Sharma freight overage ≤3% is routinely approved (12 cases)". These appear in a "What I've Learned" panel, where managers can confirm or retire each rule.

**Safety:** hard rules (bank change, high value, exact duplicate, prompt-injection text inside an invoice) run in code before the LLM. Neither the model nor a learned rule can override them.

---

## Key features

- Vendor memory profile: terms, bank-account history, habits and exception timeline
- Memory-aware three-way match
- Explained decisions with cited past cases
- One-click feedback loop (Accept / Override with reason / Add note)
- Fraud and risk detection: bank change, duplicates, price creep, overages
- "What I've Learned" panel of learned rules with evidence
- Learning-curve dashboard showing the human-intervention rate falling week by week
- **Memory OFF vs ON** side-by-side comparison of the same invoice
- "Ask the agent", for questions like "Why did we pay Apex above PO in July?"

---

## Tech stack

- **Memory:** Hindsight Cloud (self-hosted Docker as backup)
- **LLM:** Groq, running `gpt-oss-120b` as primary and `qwen3-32b` as fallback, with JSON-schema validation and retries
- **Backend:** Python, FastAPI, SQLAlchemy (SQLite for the demo, PostgreSQL in production)
- **Frontend:** Streamlit (or React + Tailwind)
- **Data:** synthetic but realistic set of 10 Indian vendors and about 180 invoices over 6 months, with planted patterns (fraud, duplicates, price creep, recurring overages)

---

## What makes it different

| | Remembers vendors | Learns from corrections | Explains decisions | Catches new fraud |
|---|---|---|---|---|
| Manual review | Only in people's heads | Slowly | Rarely | Depends on the clerk |
| ERP rules / RPA | Static data | No | Rule ID only | Only if pre-coded |
| Stateless chatbot | No | No | Without history | No baseline |
| **LedgerMind** | **Yes, per vendor** | **Yes, every correction** | **Yes, cites cases** | **Yes, against a learned baseline** |

---

## Impact and success metrics

Targets, measured on a 6-month replay of the synthetic data:

- Human-intervention rate falls from **≥60% in week 1 to ≤15% by week 8**
- **100%** of planted frauds and duplicates caught, with **0** false auto-approvals on risky invoices
- **100%** of decisions carry a rationale and memory references (audit-ready)
- Memory ON beats Memory OFF by **30+ percentage points** in decision accuracy

**Target users:** AP teams at small and mid-size companies (200–5,000 invoices a month) on Tally, Zoho Books, SAP Business One or NetSuite. These teams feel the pain most but can't afford enterprise AP suites.

**Future:** live ERP connectors, OCR for scanned invoices, email-inbox intake, and payment scheduling that learns early-payment discounts.

---

## Demo plan (3 minutes)

1. **Problem:** Priya, an AP clerk handling 400 invoices a week.
2. **Memory OFF:** the Sharma freight invoice gets a generic "review" message, and the Krishna fake bank change passes.
3. **Teach:** Priya approves the Sharma freight with a note, and the note is retained live.
4. **Memory ON:** the next Sharma invoice is auto-approved, citing her note.
5. **Wow moment:** the Krishna invoice is **escalated** with bank-account evidence.
6. **It learned:** the learned-rules panel, plus the learning curve dropping from 62% to 11%.
