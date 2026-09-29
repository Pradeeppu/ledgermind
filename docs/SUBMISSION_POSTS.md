# Submission posts (ready to paste)

## LinkedIn

Same invoice. Without memory, the AI agent pays a fraudster. With memory, it stops them.

For the #HindsightHackathon I built **LedgerMind**, a payments agent that remembers every vendor, every student and every bank, using Hindsight memory by Vectorize.

🔹 A vendor suddenly asks to be paid into a new account → it remembers 18 payments went to the real one, and escalates
🔹 A known 2% fuel surcharge → approved automatically, citing the clerk's past approvals
🔹 CSR scholarships: two students on one bank account, or an account that changes overnight → stopped, with a WhatsApp check sent to the student's registered number
🔹 Every transfer is tracked until it's credited, and it learns which banks are just slow

Results on a synthetic six-month ledger:
✅ 22/22 risky invoices caught, 0 false auto-approvals
✅ Human checks fell from 100% to 18%
✅ Scholarship payouts: 12/12 correct with memory vs 6/12 without

Hard rules run first, and memory can only make a decision stricter, never looser.

Code: https://github.com/Pradeeppu/ledgermind
Demo: <VIDEO_LINK>

#AIAgents #AgentMemory #Hindsight #Vectorize #FinTech #CSR #AccountsPayable

---

## Reddit (r/artificial, r/MachineLearning [Project], r/LocalLLaMA or r/SideProject)

**Title:** I built a payments agent with persistent memory. Without memory it paid a fake bank account; with memory it caught it.

**Body:**

For the Hindsight Hackathon I built LedgerMind, an accounts payable and CSR scholarship agent. It uses Hindsight (Vectorize's agent memory) to remember every payee and learn from every human correction.

What memory changed, on a synthetic 6-month ledger with planted fraud:

- **Fake bank change:** a stateless agent approves it; LedgerMind escalates it, because 18 earlier payments went to a different account.
- **Known surcharges:** auto-approved, citing earlier human approvals (fewer false alarms).
- **Scholarships:** one bank account shared by two students, bounced accounts and duplicate payouts are all stopped. WhatsApp verification goes only to the registered number.
- **Transfer tracking:** it learns each bank's normal crediting time, so a slow co-op bank isn't flagged every time.

Numbers:
- 22/22 risky invoices caught, 0 false auto-approvals (the stateless run made 11)
- Human checks fell from 100% to 18%
- Scholarship payouts: 12/12 correct vs 6/12 without memory

Honest caveat: overall invoice accuracy is only 78% vs 75%, because the agent is cautious with new vendors. The win is safety, not accuracy.

Design: hard rules (bank change, duplicates, prompt injection in invoice text) run in code first. Hindsight recall and reflect can only make a decision stricter. Learned rules show their evidence counts, and a manager can retire them.

Code (MIT): https://github.com/Pradeeppu/ledgermind · Demo video: <VIDEO_LINK>

Happy to answer questions about the memory design.

---

## Feedback (for the hackathon form)

Hindsight made the "agent that learns" part genuinely simple.
- **What worked well:**
  - Tag-scoped `recall` meant one memory bank could serve many payees.
  - `reflect` with a `response_schema` gave us structured decisions that cite memories, which made them auditable.
  - Observations with proof counts mapped naturally onto "learned rules" that a manager can govern.
  - Mission, directives and disposition let us encode a skeptical finance persona without prompt hacks.
- **What would help:**
  - More examples of combining deterministic guardrails with reflect.
  - An easy way to read back which observation influenced a reflect answer.
  - A bulk "reset bank" helper for demos and tests.
  - Clearer guidance on retain latency versus `retain_async` for high-volume pipelines.
- **Overall:** a great hackathon theme. Memory changed our agent's decisions in ways we could measure, not just its chat quality.
