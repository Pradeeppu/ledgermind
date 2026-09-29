# LedgerMind: video scripts

Three videos, written scene by scene. Every scene lists its timing, the screen, exactly what to click, the
voice-over (VO) and the on-screen caption.

| Video | Purpose | Length |
|---|---|---|
| **Video 1: Main demo** | The hackathon submission ("Video Link") | 3:00 |
| **Video 2: CSR & scholarships** | Deep dive on the real-world CSR use case | 2:30 |
| **Video 3: Teaser** | LinkedIn and Reddit posts | 0:45 |

**Before recording any of them:**
- Reset the demo with `python scripts/replay.py --reset`.
- Start the app with `python -m streamlit run app.py`.
- Set the browser zoom to 110% and turn off notifications.

Every number below comes from `docs/EVALUATION.md` or the demo data. Don't round them up.

All organisations and people are fictional: Acme Components, Shiksha Setu Foundation, Nimbus Softech, Sahyadri Steels, and every student and vendor.

---

## Video 1: Main demo (3:00)

**Goal:** show that memory changes decisions, in two domains (vendor invoices and scholarship payouts), and that the agent learns.

### Scene 1: The problem (0:00–0:20)
- **Screen:** title card, then **Invoice queue**.
- **Action:** hold still, then slowly move the cursor across the KPI tiles.
- **VO:** "Every week, finance teams re-check the same payment exceptions. Who the vendor is, which bank account is real, why last month's transfer failed: that knowledge lives in one person's head. A normal AI agent forgets all of it between sessions. So money gets paid twice, paid late, or paid to the wrong account. This is LedgerMind, a payments agent that remembers."
- **Caption:** *Finance teams re-check the same exceptions every week. AI agents forget. LedgerMind remembers.*

### Scene 2: Memory off vs on, the fake bank account (0:20–0:50)
- **Screen:** **Memory on vs off**.
- **Action:** click the quick pick **Bank change**, then **Run both**. Point at the left card, the right card, and then the reason.
- **VO:** "Same invoice, same checks, memory off versus memory on. Krishna Electricals: amount matches, PO matches. Without memory, the agent approves it. With memory, it escalates. It remembers eighteen paid invoices went to the account ending 4417, and this one asks for 9032. It tells us to call the vendor back on the number we already have."
- **Caption:** *Memory OFF: Approve → Memory ON: Escalate. 18 paid invoices went to ****4417; this one asks for ****9032.*

### Scene 3: Teaching it (0:50–1:10)
- **Screen:** **Memory on vs off**, then **Review invoice**.
- **Action:**
  1. Click the quick pick **Freight surcharge** and **Run both**. Hold on "Memory removed a false alarm".
  2. Open **Review invoice**, choose **VX-1042 · Vertex IT**, open the **Override** tab, choose **Approve**, and type *Annual licence true-up, approved by Rakesh*.
  3. Click **Save override**.
- **VO:** "It also removes false alarms. Sharma's two percent fuel surcharge was approved six times before, so now it's cleared automatically. And I can teach it. Vertex billed more than usual. I override it with a reason, and that reason goes straight into memory as evidence for next time."
- **Caption:** *Flag → Approve, citing 6 prior approvals · Teaching live: override + reason → retained in memory*

### Scene 4: The CSR scholarship case (1:10–1:50)
- **Screen:** **CSR fund overview**, then **Scholarship payouts**.
- **Action:**
  1. On the overview, hover the Sankey chart "Where the CSR money went".
  2. Go to **Scholarship payouts** and click **Run agent on 12 pending**.
  3. Select **Pooja Shetty** and point at **Escalate** and the reason.
  4. Select **Madhuri Hegde** and point at **Shared account**.
- **VO:** "The same memory works for CSR money. Corporate CSR budgets fund a scholarship foundation, and CSR heads rarely see where the money actually went. Here they can: donor, programme, student, down to the bank transfer. Now the accountant runs this cycle's payouts. Pooja's bank account suddenly changed, with an urgent message. Nobody verified it, so it's escalated. Madhuri's new account already received money for a different student: one account, two students. That's a middleman signal. A system without memory would have released both."
- **Caption:** *Unverified bank change → Escalate · One account, two students → Escalate · Memory OFF released both*

### Scene 5: Tracking every transfer (1:50–2:10)
- **Screen:** **Transaction tracker**.
- **Action:**
  1. Turn **Use learned bank timings (memory)** off, then on again.
  2. Point at the callout about false alarms.
  3. Click **Advance bank clock +1 day** and point at the updates.
- **VO:** "Every transfer is tracked until it's credited. The agent has learned that Konkan Co-op Bank normally takes about six days. So those transfers aren't flagged as delayed, and only the one that's really stuck gets chased. Failed and returned transfers go back to the pool and show up on the student's record."
- **Caption:** *Learned bank timings: slow bank ≠ delayed · only real delays get chased*

### Scene 6: It actually learns (2:10–2:35)
- **Screen:** **Learning curve**, then back to **Scholarship payouts**.
- **Action:** hover the first and last points of the chart, then hold on the KPIs.
- **VO:** "Does it learn? Across six months of invoices, the share needing a human fell from a hundred percent to eighteen. It caught all twenty-two planted risky invoices, with zero false auto-approvals. On this cycle's scholarship payouts, memory got twelve out of twelve right; without memory, six. Overall invoice accuracy is only a little higher, because it's careful with new vendors. The win is safety."
- **Caption:** *Invoices: human 100% → 18% · 22/22 risky caught · 0 false auto-approvals · Payouts: 12/12 with memory vs 6/12 without*

### Scene 7: Under the hood (2:35–2:50)
- **Screen:** **Settings** (the Memory bank tab).
- **Action:** hover **Mission**, the **Directives** list and **Disposition**.
- **VO:** "Under the hood it's Hindsight. Every decision, correction and transfer result is retained with tags. Before each payment, it recalls that payee's history, and reflect makes the call, guided by a mission, hard directives and a skeptical disposition. Hard rules run in code first, and memory can only make a decision stricter."
- **Caption:** *Hindsight: retain → recall → reflect → observations · mission · directives · disposition*

### Scene 8: Close (2:50–3:00)
- **Screen:** end card.
- **VO:** "LedgerMind remembers every vendor, every student and every bank, so less money goes to the wrong place. The code is on GitHub. Thanks for watching."
- **Caption:** *LedgerMind · built on Hindsight by Vectorize · github.com/Pradeeppu/ledgermind*

---

## Video 2: CSR & scholarships deep dive (2:30)

**Goal:** tell the CSR story end to end, from the CSR head's question to the accountant's work to the bank's confirmation.

### Scene 1: The CSR head's question (0:00–0:20)
- **Screen:** sidebar **Signed in as → Kavya S. · CSR Head, Nimbus Softech**, then **CSR fund overview**.
- **Action:** switch the user, then hold on the KPI tiles.
- **VO:** "I'm Kavya. I head CSR at Nimbus Softech, and we fund medical scholarships through a foundation. Every year I sign the cheque, and every year I ask the same thing: where did the money go, and did it actually reach the students?"
- **Caption:** *CSR heads fund scholarships but rarely see where the money lands*

### Scene 2: Where the money went (0:20–0:45)
- **Screen:** **CSR fund overview**.
- **Action:**
  1. Hover the Sankey chart from donor to programme to outcome.
  2. Hover the programme table and the next-cycle shortfall note, if one is shown.
  3. Open the **Nimbus Softech CSR** donor card and scroll the list of students funded.
  4. Click **Download utilisation report**.
- **VO:** "Now I can see it. Money in from each donor, how much reached students, how much is in transit, what bounced and came back, and what's left for next cycle. For my company, here's every student we funded, the amount, the date, and the bank reference. One click gives me the utilisation report for our CSR filing."
- **Caption:** *Donor → programme → student → bank reference · one-click utilisation report*

### Scene 3: The accountant's cycle (0:45–1:05)
- **Screen:** switch the user to **Meera K. · Foundation Accountant**, then **Scholarship payouts**.
- **Action:** click **Run agent on 12 pending** and hold on the result KPIs.
- **VO:** "I'm Meera, one of the foundation's accountants. Engineering students get forty to forty-five thousand rupees a year, and medical students fifty thousand, paid in two instalments. I let LedgerMind check this cycle's payouts. Clean ones go straight to the bank. The rest are held or escalated, each with a reason."
- **Caption:** *Engineering ₹40–45k/yr · Medicine ₹50k/yr · clean payouts released, risky ones held*

### Scene 4: What memory caught (1:05–1:40)
- **Screen:** **Scholarship payouts** review panel.
- **Action:** select each payout and point at the decision card:
  1. **Pooja Shetty:** Escalate, bank change with urgency language.
  2. **Madhuri Hegde:** Escalate, shared account.
  3. **Nandini Hegde:** Escalate, duplicate payout.
  4. **Sneha Verma:** Hold, the last transfer bounced (account closed).
  5. **Suresh Joshi:** Release. Point at "Learned from Meera K.": the account is in a parent's name, which was approved before.
- **VO:** "Pooja's account changed overnight, with an urgent note. Escalated, and I'm told to call Pooja on the number we have. Madhuri's new account already received money for another student. Nandini was already paid this cycle, so this would pay twice. Sneha's last transfer bounced because the account was closed, so we don't resend it. And Suresh's account is in a parent's name. I approved that twice before, so LedgerMind now releases it and shows me my own note."
- **Caption:** *Bank change · shared account · duplicate · bounced account → stopped · parent's account → learned OK*

### Scene 5: Verify and release (1:40–1:55)
- **Screen:** **Scholarship payouts**.
- **Action:**
  1. Select **Kiran Sharma**. The decision is Hold, first payout.
  2. Open the **Verify account** tab, type *Rs.1 penny-drop succeeded, name matches*, and save.
  3. Click **Run again**. The decision changes to Release.
- **VO:** "Kiran is new, so the first payout waits for a one-rupee penny-drop test. It passes, I mark the account verified, and on the next run it's released. That verification is now part of Kiran's memory."
- **Caption:** *Verify once → released → remembered*

### Scene 6: Tracking to the last rupee (1:55–2:15)
- **Screen:** **Transaction tracker**.
- **Action:**
  1. Point at the status KPIs.
  2. Turn **Use learned bank timings** off, then on.
  3. Click **Advance bank clock +1 day** and point at the credited updates.
  4. Open a transfer's timeline.
- **VO:** "Then every transfer is tracked until it's credited. The co-op bank always takes about six days, and memory knows that, so it isn't raised as a false alarm. The transfer that's genuinely stuck is flagged to chase. Here's one transfer's full journey: released, sent, credited."
- **Caption:** *Learned bank timings · real delays flagged · full journey per transfer*

### Scene 7: The team view and close (2:15–2:30)
- **Screen:** **Accountant workload**, then the end card.
- **Action:** hover each accountant's card, then click **Open their queue** for Meera.
- **VO:** "And the finance lead sees each accountant's queue, holds, turnaround and failed transfers to chase. For CSR, that means every rupee is traceable from donor to student."
- **Caption:** *Every rupee traceable, from donor to student · LedgerMind on Hindsight*

---

## Video 3: 45-second teaser (for LinkedIn and Reddit)

| Time | Screen | VO | Caption |
|---|---|---|---|
| 0:00–0:07 | **Memory on vs off**, Krishna result already showing | "Same invoice. Without memory, the agent pays a fake bank account." | *Memory OFF: Approve* |
| 0:07–0:15 | Point at the right card | "With memory, it remembers eighteen payments to the real account, and stops it." | *Memory ON: Escalate* |
| 0:15–0:27 | **Scholarship payouts**: Pooja, then Madhuri | "It does the same for CSR scholarships. A student's account changes overnight, or two students share one account. Stopped before the money leaves." | *Unverified change · one account, two students* |
| 0:27–0:37 | **Learning curve** | "And it learns from every correction. Human checks drop from a hundred percent to eighteen, with zero false approvals." | *100% → 18% · 0 false auto-approvals* |
| 0:37–0:45 | End card | "LedgerMind. Built on Hindsight. Link in the comments." | *github.com/Pradeeppu/ledgermind* |

---

## Recording tips
- **Voice:** record it separately and lay it over the screen recording. That's easier than talking and clicking at the same time. `python scripts/make_video.py` can also render Video 1 automatically, with a neural voice and captions.
- **Order matters:** each run changes the data. Reset with `python scripts/replay.py --reset` before every full take.
- **Draft label:** if Hindsight isn't connected, the sidebar shows "Local memory (offline)". Say so in the description, or connect Hindsight first.
- **Sharing:** export at 1080p. Upload Videos 1 and 2 to YouTube (unlisted) and use Video 3 natively on LinkedIn.
