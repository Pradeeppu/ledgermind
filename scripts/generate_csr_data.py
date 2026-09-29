"""Generate the synthetic CSR scholarship dataset (fictional foundation, donors, students, payouts).

Scenario: corporate CSR budgets fund "Shiksha Setu Foundation" (fictional), which pays scholarships in two
instalments a year: engineering Rs.40,000-45,000 a year, medicine Rs.50,000 a year. Three cycles:
  C1 2025-26 instalment 1 (Aug 2025), C2 2025-26 instalment 2 (Jan 2026), C3 2026-27 instalment 1 (Sep 2026).
Each payout carries a hidden `_truth` (what an experienced accountant would decide) and `_txn` (how the bank
transfer will actually behave: days to credit, credited / failed / returned). Both are used only by the
replay (simulated accountant and simulated bank), never shown to the agent.

Run: python scripts/generate_csr_data.py
"""
from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(7)
OUT = Path(__file__).resolve().parents[1] / "data" / "csr"

FOUNDATION = "Shiksha Setu Foundation"
DONORS = [
    dict(id="D1", name="Acme Components CSR", contact="csr@acme-components.example"),
    dict(id="D2", name="Nimbus Softech CSR", contact="csr@nimbus-softech.example"),
    dict(id="D3", name="Sahyadri Steels CSR", contact="csr@sahyadri-steels.example"),
]
GRANTS = [
    dict(id="G1", donor_id="D1", date="2025-07-01", amount=1_200_000, program="Engineering"),
    dict(id="G2", donor_id="D2", date="2025-07-15", amount=1_000_000, program="Medicine"),
    dict(id="G3", donor_id="D3", date="2025-08-01", amount=600_000, program="General"),
    dict(id="G4", donor_id="D1", date="2026-07-01", amount=1_200_000, program="Engineering"),
    dict(id="G5", donor_id="D2", date="2026-07-10", amount=600_000, program="Medicine"),
    dict(id="G6", donor_id="D3", date="2026-08-01", amount=500_000, program="General"),
]
CYCLES = [
    dict(id="C1", label="2025-26 · Instalment 1", scheduled_on="2025-08-20", academic_year="2025-26"),
    dict(id="C2", label="2025-26 · Instalment 2", scheduled_on="2026-01-20", academic_year="2025-26"),
    dict(id="C3", label="2026-27 · Instalment 1", scheduled_on="2026-09-15", academic_year="2026-27"),
]
BANKS = {  # name: (IFSC prefix, min days, max days)
    "State Bank of India": ("SBIN", 1, 2), "HDFC Bank": ("HDFC", 1, 1), "Canara Bank": ("CNRB", 2, 3),
    "Union Bank of India": ("UBIN", 1, 2), "India Post Payments Bank": ("IPOS", 3, 4),
    "Konkan Co-op Bank": ("KKCB", 5, 7),
}
ACCOUNTANTS = {"Engineering South": "Meera K.", "Engineering North": "Farah N.", "Medicine": "Arjun S."}
COLLEGES = {
    "Engineering South": ["Kaveri Institute of Technology", "Tungabhadra College of Engineering"],
    "Engineering North": ["Narmada Institute of Technology", "Yamuna College of Engineering"],
    "Medicine": ["Sahyadri Medical College", "Godavari Institute of Medical Sciences"],
}
FIRST = ["Anjali", "Rahul", "Divya", "Karthik", "Sneha", "Arjun", "Pooja", "Vikram", "Lakshmi", "Rohan", "Kavya", "Suresh",
         "Meghana", "Aditya", "Nandini", "Harish", "Priyanka", "Manoj", "Swathi", "Irfan", "Deepa", "Santosh", "Ayesha",
         "Ganesh", "Bhavana", "Naveen", "Shruti", "Tejas", "Fathima", "Ravi", "Keerthi", "Ajay", "Madhuri", "Sai",
         "Lavanya", "Pradeep", "Asha", "Nikhil", "Revathi", "Imran", "Sowmya", "Varun", "Hema", "Kiran", "Ramya",
         "Abhishek", "Chaitra", "Mohan"]
LAST = ["Nair", "Reddy", "Sharma", "Patil", "Iyer", "Khan", "Das", "Kulkarni", "Gowda", "Menon", "Rao", "Pillai",
        "Joshi", "Shetty", "Yadav", "Hegde", "Naidu", "Verma"]


def entitlement(program: str, year: int) -> int:
    if program == "Medicine":
        return 50_000
    return {1: 40_000, 2: 40_000, 3: 42_000, 4: 45_000}[year]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    students, payouts, verifications = [], [], []
    regions = ["Engineering South"] * 15 + ["Engineering North"] * 15 + ["Medicine"] * 18
    bank_names = list(BANKS)
    for i, region in enumerate(regions, 1):
        sid = f"S{i:02d}"
        first, last = FIRST[i - 1], LAST[(i * 7) % len(LAST)]
        program = "Medicine" if region == "Medicine" else "Engineering"
        joined = "C2" if i in (41, 42, 43) else ("C3" if i in (44, 45, 46) else "C1")
        bank = "Konkan Co-op Bank" if i in (3, 23, 26, 38, 47) else bank_names[i % 5]
        acct = f"{random.randint(1000, 9999)}"
        students.append(dict(
            id=sid, name=f"{first} {last}", program=program, region=region, accountant=ACCOUNTANTS[region],
            course="MBBS" if program == "Medicine" else random.choice(["B.Tech CSE", "B.Tech ECE", "B.Tech Mechanical", "B.Tech Civil"]),
            college=random.choice(COLLEGES[region]), year_2025=random.choice([1, 2, 3]) if joined == "C1" else 1,
            joined=joined, status="active", phone=f"+91 9{random.randint(100, 999)} {random.randint(10000, 99999)}",
            bank=bank, ifsc=f"{BANKS[bank][0]}0{random.randint(100000, 999999)}", account=acct,
            holder=f"{first} {last}"))
    S = {s["id"]: s for s in students}
    # planted master-data quirks
    S["S12"]["holder"] = "Ramachandra " + S["S12"]["name"].split()[1]           # account held by father (learned OK)
    S["S40"]["status"] = "discontinued"                                     # dropped out in Aug 2026
    S["S40"]["status_note"] = "Discontinued the course in August 2026 (college letter on file)"

    def truth_txn(bank: str, result="CREDITED", reason="", days=None):
        lo, hi = BANKS[bank][1:]
        return dict(days=days if days is not None else random.randint(lo, hi), result=result, reason=reason)

    n = 0
    for c in CYCLES:
        base = date.fromisoformat(c["scheduled_on"])
        for s in students:
            order = ["C1", "C2", "C3"]
            if order.index(c["id"]) < order.index(s["joined"]):
                continue
            year = s["year_2025"] + (1 if c["id"] == "C3" else 0)
            if year > 4:
                continue
            ent = entitlement(s["program"], min(year, 4))
            n += 1
            p = dict(id=f"P{n:04d}", student_id=s["id"], cycle=c["id"], scheduled_on=str(base + timedelta(days=(n % 4))),
                     amount=ent // 2, year=year, annual_entitlement=ent, bank=s["bank"], ifsc=s["ifsc"],
                     account=f"****{s['account']}", holder=s["holder"], request_note="", live=False,
                     _truth=dict(outcome="RELEASE", note="Within entitlement; account on record.", verify=False),
                     _txn=truth_txn(s["bank"]))
            first_payout = c["id"] == s["joined"]
            if first_payout:
                p["_truth"] = dict(outcome="RELEASE", verify=True,
                                   note="First payout: account verified by Rs.1 penny-drop test before release.")
            if s["id"] == "S12":
                p["_truth"]["note"] = ("Account is in the father's name (Ramachandra); verified with the college ID and a "
                                       "letter from the parent. OK to release.")
            payouts.append(p)

    P = {(p["student_id"], p["cycle"]): p for p in payouts}
    # ---- history quirks ----
    P[("S05", "C2")]["_txn"] = dict(days=2, result="FAILED", reason="Account closed at beneficiary bank")
    P[("S05", "C2")]["_truth"]["note"] = "Transfer failed: account closed. Asked the student for updated bank details."

    # ---- C3: which payouts are live (pending for the demo) vs processed in the replay ----
    live = {"S07", "S09", "S33", "S05", "S14", "S40", "S12", "S44", "S23", "S02", "S36"}
    for p in payouts:
        if p["cycle"] == "C3":
            p["live"] = p["student_id"] in live
            if not p["live"]:
                p["scheduled_on"] = str(date(2026, 9, 16) + timedelta(days=int(p["id"][1:]) % 3))
            else:
                p["scheduled_on"] = "2026-09-22"

    def c3(sid):
        return P[(sid, "C3")]

    # unverified bank change with urgency language -> ESCALATE
    c3("S07").update(bank="HDFC Bank", ifsc="HDFC0417731", account="****5520",
                     request_note="Please send the scholarship to my new account, the old one is not working. Urgent, fees due tomorrow.")
    c3("S07")["_truth"] = dict(outcome="ESCALATE", verify=False,
                               note="Unverified bank change with urgency. Call the student on the number on file before paying.")
    # bank change already verified by the accountant -> RELEASE
    c3("S09").update(bank="Canara Bank", ifsc="CNRB0005521", account="****8830",
                     request_note="Changed bank after moving to the college hostel. New passbook attached.")
    verifications.append(dict(student_id="S09", account="****8830", bank="Canara Bank", user="Meera K.", date="2026-09-10",
                              reason="Called the student on the registered number and checked the new passbook."))
    c3("S09")["_truth"] = dict(outcome="RELEASE", verify=False, note="New account already verified on 10 Sep.")
    # two students on one account -> ESCALATE
    shared = S["S21"]
    c3("S33").update(bank=shared["bank"], ifsc=shared["ifsc"], account=f"****{shared['account']}",
                     holder=S["S33"]["name"], request_note="Updated bank details submitted through the college office.")
    c3("S33")["_truth"] = dict(outcome="ESCALATE", verify=False,
                               note=f"Same account as {shared['name']} (S21). Possible middleman; verify both students.")
    # previous transfer to this account failed -> HOLD
    c3("S05")["_truth"] = dict(outcome="HOLD", verify=False, note="Last transfer bounced (account closed). Need new bank details.")
    # amount above entitlement -> HOLD
    c3("S14")["amount"] = c3("S14")["annual_entitlement"] + 5_000
    c3("S14")["_truth"] = dict(outcome="HOLD", verify=False, note="Amount exceeds the annual entitlement. Correct the instalment.")
    # discontinued student -> HOLD
    c3("S40")["_truth"] = dict(outcome="HOLD", verify=False, note="Student discontinued in Aug 2026. Stop payment.")
    # new student, first payout -> HOLD until verified
    c3("S44")["_truth"] = dict(outcome="HOLD", verify=False, note="First payout; run the penny-drop test first.")
    # duplicate payout for S15 in C3 (the original is processed in the replay)
    dup = dict(c3("S15"))
    dup.update(id="P9001", live=True, scheduled_on="2026-09-22", request_note="Re-uploaded from the college batch file.",
               _truth=dict(outcome="ESCALATE", verify=False, note="Duplicate of this cycle's payout already released."))
    payouts.append(dup)

    # ---- C3 processed batch: bank-side incidents for the tracker ----
    c3("S18")["_txn"] = dict(days=9, result="CREDITED", reason="Held by the bank for a KYC refresh")
    c3("S27")["_txn"] = dict(days=2, result="RETURNED", reason="Beneficiary name mismatch at the receiving bank")
    c3("S31")["_txn"] = dict(days=1, result="FAILED", reason="Invalid IFSC code")
    for sid in ("S03", "S26", "S38"):
        c3(sid)["_txn"] = dict(days=6, result="CREDITED", reason="")
    for sid in ("S45", "S46"):  # new students in C3 processed in the replay (verified, then released)
        pass

    payouts.sort(key=lambda p: (p["scheduled_on"], p["id"]))
    for name, rows in [("foundation", {"name": FOUNDATION, "sim_start": "2026-09-22"}), ("donors", DONORS),
                       ("grants", GRANTS), ("cycles", CYCLES), ("students", students), ("payouts", payouts),
                       ("verifications", verifications)]:
        (OUT / f"{name}.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    live_n = sum(p["live"] for p in payouts)
    print(f"students={len(students)} payouts={len(payouts)} live={live_n} grants={len(GRANTS)}")


if __name__ == "__main__":
    main()
