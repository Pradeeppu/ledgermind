# LedgerMind: teaching a payments agent to remember

*How we used Hindsight memory to build an accounts payable and CSR scholarship agent that learns from every correction and catches fraud a stateless agent would miss.*

## The problem: finance teams re-learn the same things every week

Every accounts payable (AP) team knows this loop. An invoice arrives with a small freight surcharge, and a clerk investigates. Next week the same vendor sends the same surcharge, and the same clerk investigates again. Knowledge about each vendor lives in people's heads: *Sharma always adds 2% for fuel, Krishna's real account ends in 4417, Metro moved to net-15 in April*. When those people are busy or leave, it's gone.

Automation hasn't solved this. Rule engines only know what someone coded into them. AI chatbots can reason, but they forget everything between sessions. So companies keep paying duplicate invoices, missing slow price creep, and paying fake "new bank account" invoices sent by fraudsters.

The same problem shows up in **CSR scholarships**. Companies fund foundations that pay students ₹40,000–50,000 a year. CSR heads rarely see where the money actually went. And when a student's bank account "changes", nobody can tell whether the change is real or a middleman.

## The idea: an agent whose memory is the product

LedgerMind is a payments agent built on **[Hindsight](https://hindsight.vectorize.io/)**, the agent memory system by Vectorize. For every payment, whether a vendor invoice or a scholarship payout, it does five things:

1. **Checks** the payment itself: a three-way match of invoice, purchase order and goods receipt, or the student's entitlement and eligibility.
2. **Recalls** that payee's history from Hindsight: past payments, the bank accounts that actually received money, earlier exceptions, and the notes the team left.
3. **Reflects** with Hindsight, under a mission ("protect against overpayment and fraud; escalate when evidence is weak"), hard directives ("never pay a changed bank account") and a skeptical disposition.
4. **Decides** Approve / Flag / Escalate, or Release / Hold / Escalate for scholarships. Every decision comes with a confidence score, a plain-language reason, and the memories it cited.
5. **Learns.** Every accept, override or note is retained. Recurring decisions consolidate into rules with evidence counts, and a manager can confirm or retire each one.

## What memory changes

The clearest way to show it is to run the same payment twice, once with memory off and once with it on.

| Situation | Memory off | Memory on |
|---|---|---|
| A vendor asks to be paid into a new account | Approves (amount and PO match) | **Escalates**: "18 paid invoices went to ****4417, this asks for ****9032. Call back on the number on file." |
| A known 2% fuel surcharge | Flags it (a false alarm) | **Approves**, citing 6 earlier approvals and the clerk's own note |
| A student's account changes overnight, with an "urgent" note | Releases | **Escalates** and sends a WhatsApp verification to the student's registered number |
| Two students paid into one account | Releases | **Escalates**: a middleman signal |
| The last transfer to this account bounced | Releases again | **Holds** and asks for new details |
| A slow co-operative bank takes 6 days | "Delayed" alarm every time | Learned timing: only real delays are chased |

## Results

We built a synthetic but realistic ledger: 145 vendor invoices over six months, and 136 scholarship payouts over three cycles. Fraud, duplicates, price creep and bank failures were planted in both. The agent learned online, with a simulated clerk correcting it.

- **Invoices:** 22 of 22 planted risky invoices caught, with **0 false auto-approvals** (a stateless agent made 11). The share of invoices needing a human fell from **100% to 18%**.
- **Scholarship payouts:** on the live cycle, memory decided **12 of 12** correctly vs 6 of 12 without it. That's **0 risky payouts released vs 5**.
- **Transfer tracking:** 1 delay alarm (the real one) instead of 4.

We're also clear about the limit. Overall invoice accuracy only moves from 75% to 78%, because the agent is deliberately cautious with new vendors. The win is **safety**: it never lets a risky payment through, and it asks for less human time every week.

## How we used Hindsight

- **Memory banks** with a mission, a disposition (skepticism 4 of 5) and **directives** for the hard rules.
- **retain** for vendor and student master data, every decision, every human correction with its reason, every transfer outcome, and every WhatsApp reply. Each memory is tagged by payee, and bank for transfers, and timestamped.
- **recall**, tag-scoped to the payee, before every decision.
- **reflect** with a JSON `response_schema`, returning `{outcome, confidence, rationale}` plus the memories it cited.
- **Observations** shown as learned rules with evidence counts, which a manager can confirm or retire.

One design choice mattered more than any other: **hard rules run in code before the model is consulted, and memory can only make a decision stricter, never looser.** A changed bank account is escalated no matter what the model says. A soft exception, like a freight surcharge, is auto-cleared only with at least two prior human approvals **and** Hindsight reflect agreeing with at least 0.85 confidence.

## What's next

Next steps are live ERP connectors (Tally, Zoho Books, SAP B1), OCR intake, real WhatsApp Business delivery, and GST reconciliation.

**Code:** https://github.com/Pradeeppu/ledgermind · Built for the Hindsight Hackathon: *AI Agents That Learn Using Hindsight*. All companies, students and data are fictional.
