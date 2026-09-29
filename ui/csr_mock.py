"""Realistic in-memory mock of ledgermind.csr.service (see docs/CSR_SERVICE_CONTRACT.md).

State lives at module level so it survives Streamlit reruns within one server process.
Demo story: Shiksha Setu Foundation pays scholarships funded by three corporate CSR donors. All data is fictional.

Planted cases in the current cycle (2026-27 · Instalment 1):
  Rohan Deshmukh    unverified bank change            -> ESCALATE   (memory off: RELEASE)
  Vikram Shinde     account shared with Aditya         -> ESCALATE   (memory off: RELEASE)
  Kiran Gowda       last transfer returned, a/c closed -> HOLD       (memory off: RELEASE)
  Nikhil Rao        amount above entitlement           -> HOLD
  Farah Shaikh      dropped out                        -> HOLD
  Ananya Iyer       duplicate payout in same cycle     -> ESCALATE   (memory off: RELEASE)
  Sunita Yadav      father's account, learned as OK    -> RELEASE    (memory off: HOLD)
  Tejas More        first payout to a new scholar      -> HOLD
  Priyanka, Harshal, Shreya, Neha                      -> RELEASE
Konkan Co-op Bank normally credits in 5-7 days: with memory those transfers are IN_TRANSIT, with the naive
3-day SLA they look DELAYED (false alarms).
"""
from __future__ import annotations

import copy
import csv
import datetime as _dt
import io
import math
import statistics
import time

FOUNDATION = "Shiksha Setu Foundation"
NAIVE_SLA = 3
_D = _dt.date.fromisoformat


def _iso(d: _dt.date) -> str:
    return d.isoformat()


def _add(day: str, n: int) -> str:
    return _iso(_D(day) + _dt.timedelta(days=n))


def _days(a: str, b: str) -> int:
    return (_D(b) - _D(a)).days


# --------------------------------------------------------------------------- reference data
DONORS = {
    "D-ACME": dict(name="Acme Components CSR", contact="Ritu Malhotra, CSR Lead · csr@acme-components.example"),
    "D-NIMBUS": dict(name="Nimbus Softech CSR", contact="Kavya S., CSR Head · foundation@nimbus-softech.example"),
    "D-SAHYADRI": dict(name="Sahyadri Steels CSR", contact="Vivek Joshi, CSR Manager · csr@sahyadri-steels.example"),
}
GRANTS = [
    dict(id="GR-A-2501", donor="D-ACME", date="2025-07-15", amount=400000.0, program="Engineering"),
    dict(id="GR-A-2601", donor="D-ACME", date="2026-07-10", amount=350000.0, program="Engineering"),
    dict(id="GR-N-2501", donor="D-NIMBUS", date="2025-08-01", amount=450000.0, program="Engineering"),
    dict(id="GR-N-2502", donor="D-NIMBUS", date="2025-08-01", amount=100000.0, program="General"),
    dict(id="GR-N-2601", donor="D-NIMBUS", date="2026-08-05", amount=300000.0, program="Engineering"),
    dict(id="GR-S-2501", donor="D-SAHYADRI", date="2025-06-30", amount=200000.0, program="Medicine"),
    dict(id="GR-S-2601", donor="D-SAHYADRI", date="2026-06-25", amount=100000.0, program="Medicine"),
    dict(id="GR-S-2602", donor="D-SAHYADRI", date="2026-06-25", amount=100000.0, program="Engineering"),
]
CYCLES = [
    dict(id="2025-26-I1", label="2025-26 · Instalment 1", year="2025-26", scheduled_on="2025-09-20"),
    dict(id="2025-26-I2", label="2025-26 · Instalment 2", year="2025-26", scheduled_on="2026-02-12"),
    dict(id="2026-27-I1", label="2026-27 · Instalment 1", year="2026-27", scheduled_on="2026-09-23"),
]
NEXT_CYCLE = dict(id="2026-27-I2", label="2026-27 · Instalment 2", scheduled_on="2027-02-11")
CUR = CYCLES[-1]["id"]
_CYC = {c["id"]: c for c in CYCLES}

IFSC = {"SBI": "SBIN000", "Canara Bank": "CNRB000", "HDFC Bank": "HDFC000", "Union Bank": "UBIN053",
        "India Post Payments Bank": "IPOS000", "Konkan Co-op Bank": "KKBK0KCB"}
UTR_PREFIX = {"SBI": "SBIN", "Canara Bank": "CNRB", "HDFC Bank": "HDFC", "Union Bank": "UBIN",
              "India Post Payments Bank": "IPOS", "Konkan Co-op Bank": "KKBK"}
# historical credit times (days) per bank, cycled through deterministically
_TRANSIT = {"SBI": [1, 1, 2], "HDFC Bank": [1, 1, 1], "Canara Bank": [2, 2, 3], "Union Bank": [2, 3, 2],
            "India Post Payments Bank": [3, 4, 3], "Konkan Co-op Bank": [5, 6, 7, 6]}
BANK_NOTES = {
    "Konkan Co-op Bank": "Co-operative bank, settles NEFT through its sponsor bank. 5 to 7 days is normal.",
    "India Post Payments Bank": "Credits through the post office network, usually 3 to 4 days.",
    "Union Bank": "Usually 2 to 3 days.",
    "Canara Bank": "Usually 2 to 3 days.",
    "SBI": "Next-day credit is typical.",
    "HDFC Bank": "Next-day credit is typical.",
}

ACCOUNTANTS = {
    "Meera K.": dict(focus="Engineering and medicine, Pune colleges", turnaround=1.4),
    "Arjun P.": dict(focus="Engineering and general, Sangli, Solapur and Marathwada", turnaround=2.1),
    "Lakshmi N.": dict(focus="Medicine and Konkan region colleges", turnaround=1.8),
}

# id: name, course, college, year, program, donor, accountant, bank, account, holder, region, phone, instalment
_S = [
    ("S-101", "Rohan Deshmukh", "B.E. Mechanical", "COEP Technological University, Pune", 3, "Engineering", "D-ACME",
     "Meera K.", "SBI", "****4412", "Rohan Deshmukh", "Pune", "+91 98220 41873", 21000),
    ("S-102", "Vikram Shinde", "B.Tech Mechanical", "Walchand College of Engineering, Sangli", 3, "Engineering",
     "D-NIMBUS", "Arjun P.", "SBI", "****3318", "Vikram Shinde", "Sangli", "+91 94227 10562", 21000),
    ("S-103", "Aditya Kulkarni", "B.Tech Computer Science", "Walchand College of Engineering, Sangli", 2,
     "Engineering", "D-NIMBUS", "Arjun P.", "Union Bank", "****7741", "Aditya Kulkarni", "Sangli",
     "+91 97641 22087", 21000),
    ("S-104", "Kiran Gowda", "B.E. Civil", "KLS Gogte Institute of Technology, Belagavi", 4, "Engineering", "D-ACME",
     "Lakshmi N.", "Canara Bank", "****2209", "Kiran Gowda", "Belagavi", "+91 99018 33410", 20000),
    ("S-105", "Nikhil Rao", "B.E. Electronics", "KLE Technological University, Hubballi", 2, "Engineering",
     "D-SAHYADRI", "Lakshmi N.", "Canara Bank", "****6075", "Nikhil Rao", "Hubballi", "+91 96860 51249", 21000),
    ("S-106", "Farah Shaikh", "MBBS", "B.J. Government Medical College, Pune", 2, "Medicine", "D-SAHYADRI",
     "Meera K.", "HDFC Bank", "****1186", "Farah Shaikh", "Pune", "+91 90110 27734", 25000),
    ("S-107", "Ananya Iyer", "B.E. Electrical", "Sinhgad College of Engineering, Pune", 3, "Engineering", "D-NIMBUS",
     "Meera K.", "SBI", "****9253", "Ananya Iyer", "Pune", "+91 98509 66120", 21000),
    ("S-108", "Sunita Yadav", "B.Tech Agricultural Engineering", "Dr. B.S. Konkan Krishi Vidyapeeth, Dapoli", 2,
     "Engineering", "D-ACME", "Arjun P.", "India Post Payments Bank", "****6120", "Ramesh Yadav", "Ratnagiri",
     "+91 94039 71805", 20000),
    ("S-109", "Tejas More", "B.E. Information Technology", "Government College of Engineering, Karad", 1,
     "Engineering", "D-NIMBUS", "Arjun P.", "Canara Bank", "****8812", "Tejas More", "Satara",
     "+91 93705 44218", 20000),
    ("S-110", "Priyanka Naik", "MBBS", "Grant Government Medical College, Mumbai", 3, "Medicine", "D-SAHYADRI",
     "Meera K.", "SBI", "****5107", "Priyanka Naik", "Mumbai", "+91 98193 20477", 25000),
    ("S-111", "Harshal Patil", "B.Tech Chemical", "Institute of Chemical Technology, Mumbai", 3, "Engineering",
     "D-ACME", "Meera K.", "HDFC Bank", "****2764", "Harshal Patil", "Jalgaon", "+91 97300 18856", 22500),
    ("S-112", "Sakshi Sawant", "B.Tech Civil", "Finolex Academy of Management and Technology, Ratnagiri", 2,
     "Engineering", "D-ACME", "Lakshmi N.", "Konkan Co-op Bank", "****0331", "Sakshi Sawant", "Ratnagiri",
     "+91 94221 83390", 20000),
    ("S-113", "Omkar Parab", "B.E. Mechanical", "Rajendra Mane College of Engineering, Ratnagiri", 3, "Engineering",
     "D-NIMBUS", "Lakshmi N.", "Konkan Co-op Bank", "****0457", "Omkar Parab", "Sindhudurg", "+91 95528 40713",
     20000),
    ("S-114", "Rutuja Gawde", "MBBS", "Government Medical College, Ratnagiri", 2, "Medicine", "D-SAHYADRI",
     "Lakshmi N.", "Konkan Co-op Bank", "****0512", "Rutuja Gawde", "Ratnagiri", "+91 90963 11548", 25000),
    ("S-115", "Mohammed Arif Khan", "B.Tech Computer Engineering", "Government College of Engineering, Aurangabad", 4,
     "Engineering", "D-NIMBUS", "Arjun P.", "Union Bank", "****4480", "Mohammed Arif Khan", "Aurangabad",
     "+91 98817 62305", 22500),
    ("S-116", "Divya Hegde", "MBBS", "Karnataka Institute of Medical Sciences, Hubballi", 4, "Medicine", "D-SAHYADRI",
     "Lakshmi N.", "Canara Bank", "****3391", "Divya Hegde", "Hubballi", "+91 97409 25561", 25000),
    ("S-117", "Swapnil Jadhav", "B.E. Electronics and Telecom", "Walchand Institute of Technology, Solapur", 2,
     "Engineering", "D-ACME", "Arjun P.", "SBI", "****6634", "Swapnil Jadhav", "Solapur", "+91 99753 40128", 21000),
    ("S-118", "Neha Kamble", "B.Sc Physics", "Fergusson College, Pune", 2, "General", "D-NIMBUS", "Meera K.",
     "Canara Bank", "****1450", "Neha Kamble", "Pune", "+91 88306 71942", 12500),
    ("S-119", "Ganesh Pawar", "B.Com", "Rajaram College, Kolhapur", 3, "General", "D-NIMBUS", "Arjun P.",
     "HDFC Bank", "****7302", "Ganesh Pawar", "Kolhapur", "+91 96578 03316", 12500),
    ("S-120", "Shreya Joshi", "B.E. Computer Engineering", "Vishwakarma Institute of Technology, Pune", 2,
     "Engineering", "D-NIMBUS", "Meera K.", "HDFC Bank", "****8150", "Shreya Joshi", "Pune", "+91 98905 57261",
     22500),
]

_STUDENTS: dict[str, dict] = {}
_PAYOUTS: dict[str, dict] = {}
_TXNS: dict[str, dict] = {}
_DECISIONS: dict[str, dict] = {}
_MEMS: list[dict] = []
_OBS: list[dict] = []
_STATE = {"sim_date": "2026-09-29", "seq": 0}


def _mem(text, mtype, date, student=None, account=None, bank=None):
    m = dict(id=f"csr-mem-{len(_MEMS) + 1:04d}", text=text, type=mtype, date=date, student=student,
             account=account, bank=bank)
    _MEMS.append(m)
    return m


def _utr(bank: str, n: int) -> str:
    return f"{UTR_PREFIX[bank]}{526 + n % 7}{(n * 7919 + 104729) % 10 ** 9:09d}"


def _add_payout(pid, sid, cycle, amount=None, account=None, bank=None, holder=None, status="PENDING",
                outcome=None, confidence=None, note=""):
    s = _STUDENTS[sid]
    p = dict(id=pid, student_id=sid, cycle=cycle, amount=float(amount or s["instalment"]),
             bank=bank or s["bank"], account=account or s["account"], holder=holder or s["holder"],
             status=status, outcome=outcome, confidence=confidence, request_note=note)
    _PAYOUTS[pid] = p
    return p


def _add_txn(p, sent_on, transit=None, fail=None, note=""):
    """transit: days until credit (None = not yet known); fail: (status, days_after_send, reason)."""
    n = len(_TXNS) + 1
    t = dict(id=f"TXN-{n:04d}", payout_id=p["id"], student_id=p["student_id"], amount=p["amount"], bank=p["bank"],
             account=p["account"], utr=_utr(p["bank"], n), sent_on=sent_on,
             credit_on=_add(sent_on, transit) if transit is not None else None, fail=fail, note=note)
    _TXNS[t["id"]] = t
    return t


def _seed():
    for (sid, name, course, college, year, prog, donor, acct_by, bank, account, holder, region, phone,
         inst) in _S:
        _STUDENTS[sid] = dict(id=sid, name=name, course=course, college=college, year=year, program=prog,
                              donor=donor, accountant=acct_by, bank=bank, account=account, holder=holder,
                              region=region, phone=phone, instalment=float(inst), status="ACTIVE",
                              verified=set(), joined="2025-26-I1")
    _STUDENTS["S-109"]["joined"] = CUR
    _STUDENTS["S-106"]["status"] = "DROPPED_OUT"

    # ---- two past cycles: every student except the new one, all credited except Kiran's February transfer
    k = 0
    for ci, (cyc, sent) in enumerate((("2025-26-I1", "2025-09-22"), ("2025-26-I2", "2026-02-13"))):
        for sid, s in _STUDENTS.items():
            if s["joined"] == CUR:
                continue
            p = _add_payout(f"PAY-{cyc[2:4]}{cyc[-1]}-{sid[2:]}", sid, cyc, status="RELEASED", outcome="RELEASE",
                            confidence=0.9 if ci else 0.8)
            seq = _TRANSIT[s["bank"]]
            k += 1
            if sid == "S-104" and ci == 1:
                _add_txn(p, sent, fail=("RETURNED", 6, "Account closed by the holder"),
                         note="Returned by Canara Bank: account closed")
            else:
                _add_txn(p, sent if sid != "S-108" or ci else "2025-09-25", transit=seq[k % len(seq)])
            s["verified"].add(s["account"])

    # ---- current cycle: already released on 23-26 Sep
    def rel(sid, sent, transit=None, fail=None, note="", pid=None):
        p = _add_payout(pid or f"PAY-{CUR[2:4]}{CUR[-1]}-{sid[2:]}", sid, CUR, status="RELEASED", outcome="RELEASE",
                        confidence=0.95)
        return _add_txn(p, sent, transit=transit, fail=fail, note=note)

    rel("S-103", "2026-09-23", 2)
    rel("S-107", "2026-09-24", 1)
    rel("S-112", "2026-09-24", 6)
    rel("S-113", "2026-09-24", 7)
    rel("S-114", "2026-09-25", 6)
    rel("S-115", "2026-09-23", 9, note="Union Bank shows the transfer as 'pending at beneficiary branch'")
    rel("S-116", "2026-09-25", fail=("FAILED", 1, "Account frozen: KYC pending at branch"),
        note="Failed: account frozen, KYC pending")
    rel("S-117", "2026-09-24", 1)
    rel("S-119", "2026-09-24", 1)

    # ---- current cycle: pending (the planted cases + clean ones)
    cp = lambda sid: f"PAY-{CUR[2:4]}{CUR[-1]}-{sid[2:]}"  # noqa: E731
    _STUDENTS["S-101"].update(bank="HDFC Bank", account="****9087")
    _add_payout(cp("S-101"), "S-101", CUR, bank="HDFC Bank", account="****9087",
                note="Student emailed on 20-Sep: 'Please send this instalment to my new HDFC account.'")
    _STUDENTS["S-102"].update(bank="Union Bank", account="****7741")
    _add_payout(cp("S-102"), "S-102", CUR, bank="Union Bank", account="****7741",
                note="Bank details from the 2026-27 renewal form, submitted through the college coordinator.")
    _add_payout(cp("S-104"), "S-104", CUR, note="Renewal form lists the same Canara Bank account as last year.")
    _add_payout(cp("S-105"), "S-105", CUR, amount=26000,
                note="College asked us to include ₹5,000 of hostel fee arrears with this instalment.")
    _add_payout(cp("S-106"), "S-106", CUR, note="Auto-generated from the 2026-27 schedule.")
    _add_payout(cp("S-107") + "B", "S-107", CUR,
                note="Resubmitted by the college portal after a timeout on 24-Sep.")
    _add_payout(cp("S-108"), "S-108", CUR, note="Paid to the father's IPPB account, as in earlier instalments.")
    _add_payout(cp("S-109"), "S-109", CUR, note="New scholar, first instalment. Onboarded 12-Sep.")
    for sid in ("S-110", "S-111", "S-118", "S-120"):
        _add_payout(cp(sid), sid, CUR, note="Renewal confirmed by the college. Same account as last year.")

    # ---- memories
    _mem("Rohan Deshmukh's two earlier instalments (Sep 2025, Feb 2026) were credited to SBI ****4412, "
         "account holder Rohan Deshmukh.", "world", "2026-02-15", "S-101", "****4412", "SBI")
    _mem("On 20-Sep-2026 an email from rohan.deshmukh.pune@gmail.example asked to switch payouts to HDFC ****9087. "
         "The address differs from the one on his application form. Not yet verified by phone.",
         "experience", "2026-09-20", "S-101", "****9087", "HDFC Bank")
    _mem("Union Bank ****7741 has received two scholarship payouts for Aditya Kulkarni (Sep 2025, Feb 2026). "
         "Bank-returned beneficiary name: ADITYA R KULKARNI.", "world", "2026-02-16", "S-103", "****7741",
         "Union Bank")
    _mem("Vikram Shinde's earlier payouts went to SBI ****3318 in his own name.", "world", "2026-02-14", "S-102",
         "****3318", "SBI")
    _mem("Both Walchand College renewal forms (Vikram Shinde, Aditya Kulkarni) were uploaded by the same college "
         "coordinator on 15-Sep-2026.", "experience", "2026-09-15", "S-102", "****7741", "Union Bank")
    _mem("Kiran Gowda's February 2026 transfer to Canara ****2209 was returned on 19-Feb: account closed by the "
         "holder. No replacement account has been received.", "experience", "2026-02-19", "S-104", "****2209",
         "Canara Bank")
    _mem("Nikhil Rao's annual entitlement is ₹42,000 (two instalments of ₹21,000). Top-ups need the "
         "scholarship committee's approval.", "world", "2025-09-10", "S-105")
    _mem("B.J. Government Medical College wrote on 30-Aug-2026 that Farah Shaikh has discontinued the MBBS course.",
         "world", "2026-08-30", "S-106")
    _mem("Ananya Iyer's 2026-27 Instalment 1 (₹21,000) was released on 24-Sep to SBI ****9253 and credited "
         "on 25-Sep.", "experience", "2026-09-25", "S-107", "****9253", "SBI")
    _mem("The college scholarship portal resubmits requests after a timeout; this produced a duplicate for "
         "another student in Feb 2026, caught before release.", "observation", "2026-02-20")
    _mem("Meera K. confirmed on 24-Sep-2025 that Sunita Yadav's IPPB ****6120 is held by her father, Ramesh Yadav. "
         "The student has no bank account of her own; the college letter confirms it. Approved to pay.",
         "experience", "2025-09-24", "S-108", "****6120", "India Post Payments Bank")
    _mem("Payouts to IPPB ****6120 (holder Ramesh Yadav, father) for Sunita Yadav were credited in Sep 2025 and "
         "Feb 2026 without issue.", "world", "2026-02-17", "S-108", "****6120", "India Post Payments Bank")
    _mem("Tejas More was onboarded on 12-Sep-2026. No transfer has been made to Canara ****8812 yet.",
         "world", "2026-09-12", "S-109", "****8812", "Canara Bank")
    _mem("Konkan Co-op Bank settles NEFT through its sponsor bank: every transfer since Sep 2025 took 5 to 7 days, "
         "all credited. Don't chase before day 8.", "observation", "2026-02-21", bank="Konkan Co-op Bank")
    _mem("India Post Payments Bank usually credits in 3 to 4 days.", "observation", "2026-02-18",
         bank="India Post Payments Bank")
    for sid in ("S-110", "S-111", "S-118", "S-120", "S-117", "S-119", "S-112", "S-113", "S-114", "S-115", "S-116"):
        s = _STUDENTS[sid]
        _mem(f"{s['name']}'s two earlier instalments were credited to {s['bank']} {s['account']} in the student's "
             "own name.", "world", "2026-02-16", sid, s["account"], s["bank"])
    _mem("Divya Hegde's 25-Sep transfer failed: Canara Bank reports the account is frozen pending KYC. "
         "She has been asked to update KYC at the branch.", "experience", "2026-09-26", "S-116", "****3391",
         "Canara Bank")

    for i, (text, n, first, last, status) in enumerate([
        ("Konkan Co-op Bank transfers take 5 to 7 days; treat as in transit until day 8.", 12, "2025-09-28",
         "2026-02-20", "active"),
        ("Sunita Yadav's scholarship goes to her father's IPPB account; this is expected.", 3, "2025-09-24",
         "2026-02-17", "confirmed"),
        ("Bank-change requests by email are verified by call-back to the number on the application form.", 4,
         "2025-10-02", "2026-03-11", "confirmed"),
        ("Walchand College renewals are uploaded in bulk by one coordinator; check each account is unique.", 2,
         "2026-02-10", "2026-09-15", "active"),
        ("The college portal can resubmit a payout after a timeout, creating duplicates.", 2, "2026-02-20",
         "2026-09-24", "active"),
    ], 1):
        _OBS.append(dict(id=f"csr-obs-{i:02d}", text=text, evidence_count=n, first_seen=first, last_seen=last,
                         status=status))
    _OBS_STUDENT.update({"csr-obs-02": {"S-108"}, "csr-obs-04": {"S-102", "S-103"}, "csr-obs-05": {"S-107"},
                         "csr-obs-01": {"S-112", "S-113", "S-114"}, "csr-obs-03": {"S-101"}})


_OBS_STUDENT: dict[str, set] = {}
_seed()


# --------------------------------------------------------------------------- helpers
def _sim():
    return _STATE["sim_date"]


def _txn_by_payout(pid):
    for t in _TXNS.values():
        if t["payout_id"] == pid:
            return t
    return None


def _bank_days(bank):
    """Actual credit times of finished transfers for a bank."""
    return [_days(t["sent_on"], t["credit_on"]) for t in _TXNS.values()
            if t["bank"] == bank and t["credit_on"] and not t["fail"] and t["credit_on"] <= _sim()]


def _p90(xs):
    if not xs:
        return None
    xs = sorted(xs)
    return float(xs[min(len(xs) - 1, math.ceil(0.9 * len(xs)) - 1)])


def _learned_sla(bank):
    p = _p90(_bank_days(bank))
    return int(max(2, (p or NAIVE_SLA) + 1))


def _txn_status(t, memory_on=True):
    today = _sim()
    if t["fail"] and _add(t["sent_on"], t["fail"][1]) <= today:
        return t["fail"][0]
    if t["credit_on"] and t["credit_on"] <= today:
        return "CREDITED"
    sla = _learned_sla(t["bank"]) if memory_on else NAIVE_SLA
    return "DELAYED" if _days(t["sent_on"], today) > sla else "IN_TRANSIT"


def _txn_public(t, memory_on=True):
    s = _STUDENTS[t["student_id"]]
    status = _txn_status(t, memory_on)
    sla = _learned_sla(t["bank"]) if memory_on else NAIVE_SLA
    credited = t["credit_on"] if status == "CREDITED" else None
    end = credited or (_add(t["sent_on"], t["fail"][1]) if status in ("FAILED", "RETURNED") else _sim())
    note = t["note"]
    if not note:
        if status == "IN_TRANSIT" and t["bank"] == "Konkan Co-op Bank":
            note = "Normal for Konkan Co-op Bank (5 to 7 days)"
        elif status == "DELAYED" and memory_on:
            note = f"Past the learned {sla}-day window for {t['bank']}; chase the bank"
        elif status == "DELAYED":
            note = f"Past the {NAIVE_SLA}-day SLA"
    return dict(id=t["id"], payout_id=t["payout_id"], student_id=t["student_id"], student_name=s["name"],
                amount=t["amount"], bank=t["bank"], account=t["account"], utr=t["utr"], sent_on=t["sent_on"],
                expected_by=_add(t["sent_on"], sla), credited_on=credited, status=status,
                days_in_transit=_days(t["sent_on"], end), sla_days=sla, note=note)


def _payout_state(p):
    """Money state of a payout: disbursed / in_transit / failed_returned / None (not sent)."""
    if p["status"] != "RELEASED":
        return None
    t = _txn_by_payout(p["id"])
    if not t:
        return "in_transit"
    st = _txn_status(t)
    return {"CREDITED": "disbursed", "FAILED": "failed_returned", "RETURNED": "failed_returned"}.get(st, "in_transit")


def _row(p):
    s = _STUDENTS[p["student_id"]]
    d = _DECISIONS.get(p["id"])
    return dict(id=p["id"], student_id=s["id"], student_name=s["name"], course=s["course"], college=s["college"],
                cycle=p["cycle"], cycle_label=_CYC[p["cycle"]]["label"], amount=p["amount"], bank=p["bank"],
                account=p["account"], accountant=s["accountant"], status=p["status"],
                outcome=d["outcome"] if d else p["outcome"], confidence=d["confidence"] if d else p["confidence"])


def _get(pid):
    if pid not in _PAYOUTS:
        raise KeyError(f"Unknown payout {pid}")
    return _PAYOUTS[pid]


def _paid_this_year(p):
    year = _CYC[p["cycle"]]["year"]
    return sum(q["amount"] for q in _PAYOUTS.values()
               if q["student_id"] == p["student_id"] and q["id"] != p["id"] and q["status"] == "RELEASED"
               and _CYC[q["cycle"]]["year"] == year and _payout_state(q) != "failed_returned")


def _flag(code, sev, msg, hard=False, at_risk=0.0):
    return dict(code=code, severity=sev, message=msg, hard_rule=hard, at_risk=float(at_risk))


def _inr(x):
    x = int(round(x))
    t = str(x)
    if len(t) > 3:
        head, tail = t[:-3], t[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        t = ",".join(parts) + "," + tail
    return "₹" + t


def _history(sid, exclude=None):
    """Earlier transfers for a student, oldest first."""
    ts = [t for t in _TXNS.values() if t["student_id"] == sid and t["payout_id"] != exclude]
    return sorted(ts, key=lambda t: t["sent_on"])


def _recall(p):
    s = _STUDENTS[p["student_id"]]
    out = [m for m in _MEMS if m["student"] == s["id"]]
    out += [m for m in _MEMS if m["student"] not in (None, s["id"]) and m["account"] == p["account"]]
    out += [m for m in _MEMS if m["student"] is None and m["bank"] in (p["bank"], None)
            and ("portal" in m["text"] and p["id"].endswith("B") or m["bank"] == p["bank"])]
    seen, res = set(), []
    for m in sorted(out, key=lambda m: m["date"], reverse=True):
        if m["id"] not in seen:
            seen.add(m["id"])
            res.append(dict(id=m["id"], text=m["text"], type=m["type"], date=m["date"]))
    return res[:6]


def _decide_logic(p, memory_on):
    s = _STUDENTS[p["student_id"]]
    inst = s["instalment"]
    annual = inst * 2
    flags, learned = [], []
    amt = p["amount"]

    # ---- checks a stateless system can do from the payout request and the student master
    if s["status"] != "ACTIVE":
        flags.append(_flag("STUDENT_NOT_ACTIVE", "high", f"{s['name']} is marked {s['status'].replace('_', ' ').lower()} "
                           "in the student register. Scholarships stop when a student leaves the course.", True, amt))
    paid = _paid_this_year(p) if memory_on else 0.0
    if amt > inst + 0.5:
        flags.append(_flag("ABOVE_ENTITLEMENT", "medium", f"Requested {_inr(amt)} but one instalment is {_inr(inst)} "
                           f"(annual entitlement {_inr(annual)}). The extra {_inr(amt - inst)} needs committee "
                           "approval.", True, amt - inst))
    if s["joined"] == p["cycle"] and p["account"] not in s["verified"]:
        flags.append(_flag("FIRST_PAYOUT", "medium", f"First payout to a new scholar. {p['bank']} {p['account']} "
                           "hasn't been verified by penny-drop or call-back yet.", False, amt))
    if p["holder"] != s["name"]:
        if memory_on and p["account"] in s["verified"]:
            learned.append("Meera K. confirmed in Sep 2025 that this IPPB account belongs to the student's father, "
                           "and two payouts to it were credited. Account holder mismatch accepted.")
        else:
            flags.append(_flag("HOLDER_MISMATCH", "medium", f"Account holder '{p['holder']}' is not the student "
                               f"({s['name']}).", False, amt))

    # ---- checks that need memory: history of this student, this account and this cycle
    if memory_on:
        hist = _history(s["id"], exclude=p["id"])
        prev_accounts = [t["account"] for t in hist]
        if prev_accounts and p["account"] not in prev_accounts and p["account"] not in s["verified"]:
            last = hist[-1]
            flags.append(_flag("BANK_CHANGE_UNVERIFIED", "high", f"Account changed from {last['bank']} "
                               f"{last['account']} (used for {len(hist)} earlier payouts) to {p['bank']} "
                               f"{p['account']}. The change hasn't been verified.", True, amt))
        elif p["account"] in s["verified"] and p["account"] not in prev_accounts and prev_accounts:
            learned.append(f"The new account {p['bank']} {p['account']} was verified by an accountant.")
        others = sorted({_STUDENTS[t["student_id"]]["name"] for t in _TXNS.values()
                         if t["account"] == p["account"] and t["student_id"] != s["id"]})
        others += sorted({_STUDENTS[q["student_id"]]["name"] for q in _PAYOUTS.values()
                          if q["account"] == p["account"] and q["student_id"] != s["id"]
                          and q["status"] != "RELEASED"} - set(others))
        if others:
            flags.append(_flag("SHARED_ACCOUNT", "high", f"{p['bank']} {p['account']} already receives payouts for "
                               f"{', '.join(others)}. One account can't be paid for two scholars.", True, amt))
        acct_txns = sorted([t for t in _TXNS.values() if t["account"] == p["account"] and t["payout_id"] != p["id"]],
                           key=lambda t: t["sent_on"])
        if acct_txns and _txn_status(acct_txns[-1]) in ("FAILED", "RETURNED"):
            lt = acct_txns[-1]
            if p["account"] in s["verified"] and s.get("verified_on", "") > lt["sent_on"]:
                learned.append("The account was re-verified after the failed transfer.")
            else:
                flags.append(_flag("PREVIOUS_TRANSFER_FAILED", "high", f"The last transfer to {p['bank']} "
                                   f"{p['account']} ({lt['sent_on']}) was {_txn_status(lt).lower()}: "
                                   f"{lt['fail'][2].lower()}. Get a working account before sending again.", False,
                                   amt))
        dup = [q for q in _PAYOUTS.values() if q["student_id"] == s["id"] and q["cycle"] == p["cycle"]
               and q["id"] != p["id"] and q["status"] == "RELEASED"]
        if dup:
            q = dup[0]
            t = _txn_by_payout(q["id"])
            flags.append(_flag("DUPLICATE_PAYOUT", "high", f"{s['name']} was already paid {_inr(q['amount'])} for "
                               f"{_CYC[p['cycle']]['label']} ({q['id']}, UTR {t['utr'] if t else 'pending'}).",
                               True, amt))
        if paid + amt > annual + 0.5 and not dup:
            flags.append(_flag("ANNUAL_LIMIT", "medium", f"This would take {_CYC[p['cycle']]['year']} payouts to "
                               f"{_inr(paid + amt)}, above the {_inr(annual)} entitlement.", True, paid + amt - annual))
        if p["bank"] == "Konkan Co-op Bank":
            learned.append("Konkan Co-op Bank takes 5 to 7 days to credit, so the tracker will wait until day 8 "
                           "before chasing.")

    codes = {f["code"] for f in flags}
    if codes & {"BANK_CHANGE_UNVERIFIED", "SHARED_ACCOUNT", "DUPLICATE_PAYOUT"}:
        outcome = "ESCALATE"
    elif flags:
        outcome = "HOLD"
    else:
        outcome = "RELEASE"

    # ---- rationale + confidence
    first = s["name"].split()[0]
    if outcome == "RELEASE":
        if not memory_on:
            conf = 0.74
            rat = (f"The request matches {first}'s record: active scholar, {_inr(amt)} is within the {_inr(inst)} "
                   "instalment, and the account is the one on file. No history is available to compare against, "
                   "so this relies on the request alone.")
        else:
            n = len(_history(s["id"], exclude=p["id"]))
            conf = 0.96 if not learned else 0.93
            rat = (f"Safe to release. {first} is an active scholar, {_inr(amt)} matches the instalment, and "
                   f"{p['bank']} {p['account']} is the verified account"
                   + (f" that received {n} earlier payouts." if n else ".")
                   + (" " + learned[0] if learned else ""))
    elif outcome == "ESCALATE":
        conf = 0.94
        top = next(f for c in ("SHARED_ACCOUNT", "DUPLICATE_PAYOUT", "BANK_CHANGE_UNVERIFIED") for f in flags
                   if f["code"] == c)
        rat = {"SHARED_ACCOUNT": f"Escalate. The account on {first}'s renewal form belongs to another scholar. "
                                 "That pattern (one coordinator, one account, two students) is how scholarship money "
                                 "gets diverted. Confirm with both students directly before paying anyone.",
               "DUPLICATE_PAYOUT": f"Escalate. {first} has already been paid for this cycle and the money was "
                                   "credited. This request looks like a portal resubmission; releasing it would pay "
                                   "the instalment twice.",
               "BANK_CHANGE_UNVERIFIED": f"Escalate. The bank account changed by email, days before the payout, and "
                                         "nobody has verified it. Call {0} on the number from the application form "
                                         "or run a penny-drop before releasing.".format(first)}[top["code"]]
    else:
        conf = 0.88 if memory_on else 0.8
        top = flags[0]
        rat = {"STUDENT_NOT_ACTIVE": f"Hold. The college has told us {first} left the course, so no further "
                                     "instalments are due. Close the scholarship and return the balance to the pool.",
               "ABOVE_ENTITLEMENT": f"Hold. {_inr(amt)} is above {first}'s {_inr(inst)} instalment. Release the "
                                    "standard amount, or get committee approval for the top-up.",
               "FIRST_PAYOUT": f"Hold. This is {first}'s first payout and the account is unverified. A penny-drop or "
                               "call-back clears it.",
               "HOLDER_MISMATCH": f"Hold. The account holder isn't {first}. Confirm who holds the account and why "
                                  "before paying.",
               "PREVIOUS_TRANSFER_FAILED": f"Hold. The last transfer to this account bounced because the account "
                                           f"is closed. Ask {first} for a working account instead of sending again.",
               }.get(top["code"], "Hold for review.")
    return outcome, conf, rat, flags, learned


_STATUS_FOR = {"RELEASE": "RELEASED", "HOLD": "ON_HOLD", "ESCALATE": "ESCALATED"}


def _release(p):
    p["status"] = "RELEASED"
    if not _txn_by_payout(p["id"]):
        seq = _TRANSIT[p["bank"]]
        _add_txn(p, _sim(), transit=int(statistics.median(seq)))


# --------------------------------------------------------------------------- contract: overview
def _money_by(key_fn):
    agg: dict = {}
    for p in _PAYOUTS.values():
        st = _payout_state(p)
        if not st:
            continue
        a = agg.setdefault(key_fn(p), dict(disbursed=0.0, in_transit=0.0, failed_returned=0.0))
        a[st] += p["amount"]
    return agg


def overview():
    received_by_prog: dict = {}
    received_by_donor: dict = {}
    for g in GRANTS:
        received_by_prog[g["program"]] = received_by_prog.get(g["program"], 0.0) + g["amount"]
        received_by_donor[g["donor"]] = received_by_donor.get(g["donor"], 0.0) + g["amount"]
    by_prog = _money_by(lambda p: _STUDENTS[p["student_id"]]["program"])
    by_donor = _money_by(lambda p: _STUDENTS[p["student_id"]]["donor"])
    zero = dict(disbursed=0.0, in_transit=0.0, failed_returned=0.0)

    donors = []
    for did, d in DONORS.items():
        m = by_donor.get(did, zero)
        rec = received_by_donor.get(did, 0.0)
        funded = {p["student_id"] for p in _PAYOUTS.values() if _payout_state(p) and
                  _STUDENTS[p["student_id"]]["donor"] == did}
        donors.append(dict(id=did, name=d["name"], received=rec, disbursed=m["disbursed"], in_transit=m["in_transit"],
                           left=rec - m["disbursed"] - m["in_transit"], students_funded=len(funded),
                           grants=sum(1 for g in GRANTS if g["donor"] == did)))

    pend = [p for p in _PAYOUTS.values() if p["cycle"] == CUR and p["status"] in ("PENDING", "ON_HOLD", "ESCALATED")]
    programs = []
    for prog in ("Engineering", "Medicine", "General"):
        m = by_prog.get(prog, zero)
        rec = received_by_prog.get(prog, 0.0)
        active = [s for s in _STUDENTS.values() if s["program"] == prog and s["status"] == "ACTIVE"]
        need = sum(s["instalment"] for s in active) + sum(
            min(p["amount"], _STUDENTS[p["student_id"]]["instalment"]) for p in pend
            if _STUDENTS[p["student_id"]]["program"] == prog and _STUDENTS[p["student_id"]]["status"] == "ACTIVE")
        programs.append(dict(program=prog, received=rec, disbursed=m["disbursed"], in_transit=m["in_transit"],
                             failed_returned=m["failed_returned"], left=rec - m["disbursed"] - m["in_transit"],
                             students=len({s["id"] for s in _STUDENTS.values() if s["program"] == prog}),
                             next_cycle_need=need))

    rec = sum(received_by_prog.values())
    dis = sum(p["disbursed"] for p in programs)
    tra = sum(p["in_transit"] for p in programs)
    fr = sum(p["failed_returned"] for p in programs)
    cur = [p for p in _PAYOUTS.values() if p["cycle"] == CUR]
    cnt = lambda st: sum(1 for p in cur if p["status"] == st)  # noqa: E731
    cycle = dict(id=CUR, label=_CYC[CUR]["label"], scheduled_on=_CYC[CUR]["scheduled_on"], payouts=len(cur),
                 released=cnt("RELEASED"), pending=cnt("PENDING"), on_hold=cnt("ON_HOLD"), escalated=cnt("ESCALATED"),
                 amount_released=sum(p["amount"] for p in cur if p["status"] == "RELEASED"),
                 amount_pending=sum(p["amount"] for p in cur if p["status"] != "RELEASED"))

    flow = []
    for g_don in DONORS:
        for prog in ("Engineering", "Medicine", "General"):
            v = sum(g["amount"] for g in GRANTS if g["donor"] == g_don and g["program"] == prog)
            if v:
                flow.append(dict(source=DONORS[g_don]["name"], target=prog, value=v))
    for pr in programs:
        for label, v in (("Credited to students", pr["disbursed"]), ("In transit", pr["in_transit"]),
                         ("Failed or returned", pr["failed_returned"]),
                         ("Not yet spent", pr["left"] - pr["failed_returned"])):
            if v > 0:
                flow.append(dict(source=pr["program"], target=label, value=v))

    return dict(sim_date=_sim(), foundation=FOUNDATION,
                totals=dict(received=rec, disbursed=dis, in_transit=tra, failed_returned=fr, left=rec - dis - tra,
                            committed_pending=sum(p["amount"] for p in pend),
                            utilisation_pct=round((dis + tra) / rec * 100, 1) if rec else 0.0,
                            students_active=sum(1 for s in _STUDENTS.values() if s["status"] == "ACTIVE"),
                            students_funded=len({p["student_id"] for p in _PAYOUTS.values() if _payout_state(p)})),
                donors=donors, programs=programs, cycle=cycle, flow=flow)


def _allocations(donor_id=None):
    out = []
    for p in sorted(_PAYOUTS.values(), key=lambda p: (p["cycle"], p["student_id"])):
        s = _STUDENTS[p["student_id"]]
        if donor_id and s["donor"] != donor_id or p["status"] != "RELEASED":
            continue
        t = _txn_by_payout(p["id"])
        out.append(dict(student_id=s["id"], student_name=s["name"], course=s["course"], college=s["college"],
                        cycle=_CYC[p["cycle"]]["label"], amount=p["amount"], sent_on=t["sent_on"] if t else None,
                        status=_txn_status(t) if t else "IN_TRANSIT", utr=t["utr"] if t else None,
                        _donor=s["donor"], _credited=t["credit_on"] if t and _txn_status(t) == "CREDITED" else None))
    return out


def donor_trail(donor_id):
    if donor_id not in DONORS:
        raise KeyError(f"Unknown donor {donor_id}")
    d = next(x for x in overview()["donors"] if x["id"] == donor_id)
    allocs = [{k: v for k, v in a.items() if not k.startswith("_")} for a in _allocations(donor_id)]
    return dict(donor=dict(id=donor_id, name=DONORS[donor_id]["name"], contact=DONORS[donor_id]["contact"]),
                grants=[{k: g[k] for k in ("id", "date", "amount", "program")} for g in GRANTS if g["donor"] == donor_id],
                allocations=allocs,
                summary={k: d[k] for k in ("received", "disbursed", "in_transit", "left", "students_funded")})


def utilisation_report_csv(donor_id=None):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["foundation", "donor", "student_id", "student_name", "course", "college", "cycle", "amount_inr",
                "sent_on", "credited_on", "status", "utr"])
    for a in _allocations(donor_id):
        w.writerow([FOUNDATION, DONORS[a["_donor"]]["name"], a["student_id"], a["student_name"], a["course"],
                    a["college"], a["cycle"], f"{a['amount']:.2f}", a["sent_on"] or "", a["_credited"] or "",
                    a["status"], a["utr"] or ""])
    return buf.getvalue()


# --------------------------------------------------------------------------- contract: payouts
def list_payouts(status=None, accountant=None, cycle=None):
    rows = [_row(p) for p in _PAYOUTS.values()
            if (not status or p["status"] == status) and (not cycle or p["cycle"] == cycle)
            and (not accountant or _STUDENTS[p["student_id"]]["accountant"] == accountant)]
    return sorted(rows, key=lambda r: (r["cycle"] != CUR, r["status"] != "PENDING", r["cycle"], r["student_name"]))


def get_payout(payout_id):
    p = _get(payout_id)
    s = _STUDENTS[p["student_id"]]
    return _row(p) | dict(year=_CYC[p["cycle"]]["year"], annual_entitlement=s["instalment"] * 2,
                          paid_this_year=_paid_this_year(p), ifsc=IFSC[p["bank"]] + p["account"][-4:].rjust(4, "0"),
                          account_holder=p["holder"], request_note=p["request_note"],
                          scheduled_on=_CYC[p["cycle"]]["scheduled_on"])


def decide_payout(payout_id, memory_on=True):
    p = _get(payout_id)
    t0 = time.time()
    time.sleep(0.2)
    outcome, conf, rat, flags, learned = _decide_logic(p, memory_on)
    d = dict(payout_id=payout_id, outcome=outcome, confidence=round(conf, 2), rationale=rat,
             memory_mode="on" if memory_on else "off", risk_flags=flags,
             memories=_recall(p) if memory_on else [], learned_from=learned if memory_on else [],
             decided_at=_dt.datetime.now().isoformat(timespec="seconds"), model="mock-llm",
             latency_ms=int((time.time() - t0) * 1000))
    if memory_on:
        _DECISIONS[payout_id] = d
        if p["status"] == "PENDING":
            if outcome == "RELEASE" and conf >= 0.85:
                _release(p)
            elif outcome != "RELEASE":
                p["status"] = _STATUS_FOR[outcome]
    return copy.deepcopy(d)


def get_payout_decision(payout_id):
    _get(payout_id)
    d = _DECISIONS.get(payout_id)
    return copy.deepcopy(d) if d else None


def payout_feedback(payout_id, action, new_outcome=None, reason="", user="Meera K."):
    p = _get(payout_id)
    s = _STUDENTS[p["student_id"]]
    d = _DECISIONS.get(payout_id)
    if action == "accept":
        if not d:
            return dict(ok=False, retained=False, message="Run the agent before accepting a decision.")
        if d["outcome"] == "RELEASE":
            _release(p)
        else:
            p["status"] = _STATUS_FOR[d["outcome"]]
        _mem(f"{user} accepted {d['outcome']} for {s['name']}'s {_CYC[p['cycle']]['label']} payout."
             + (f" Note: {reason}" if reason else ""), "experience", _sim(), s["id"], p["account"], p["bank"])
        return dict(ok=True, retained=True, message="Decision accepted and retained to memory.")
    if action == "override":
        if new_outcome not in _STATUS_FOR:
            return dict(ok=False, retained=False, message="new_outcome must be RELEASE, HOLD or ESCALATE.")
        if not reason.strip():
            return dict(ok=False, retained=False, message="A reason is required to override.")
        old = d["outcome"] if d else "none"
        if new_outcome == "RELEASE":
            _release(p)
        elif p["status"] != "RELEASED":
            p["status"] = _STATUS_FOR[new_outcome]
        if d:
            d["outcome"] = new_outcome
        _mem(f"{user} overrode {old} to {new_outcome} on {s['name']}'s payout: '{reason}'.", "experience", _sim(),
             s["id"], p["account"], p["bank"])
        return dict(ok=True, retained=True, message=f"Override recorded ({old} to {new_outcome}). The agent will "
                                                    "remember why.")
    if action == "note":
        if not reason.strip():
            return dict(ok=False, retained=False, message="Note is empty.")
        _mem(f"Note by {user} on {s['name']}: {reason}", "experience", _sim(), s["id"], p["account"], p["bank"])
        return dict(ok=True, retained=True, message="Note retained to memory.")
    if action == "verify_account":
        s["verified"].add(p["account"])
        s["verified_on"] = _sim()
        _mem(f"{user} verified {p['bank']} {p['account']} for {s['name']} on {_sim()}"
             + (f": {reason}" if reason else " (call-back / penny-drop).")
             + " It is now the student's verified account.", "experience", _sim(), s["id"], p["account"], p["bank"])
        if p["status"] != "RELEASED":
            p["status"] = "PENDING"
            _DECISIONS.pop(payout_id, None)
        return dict(ok=True, retained=True, message=f"{p['bank']} {p['account']} is now {s['name'].split()[0]}'s "
                                                    "verified account. Run the agent again.")
    return dict(ok=False, retained=False, message=f"Unknown action '{action}'.")


# --------------------------------------------------------------------------- contract: transactions
def list_transactions(status=None, bank=None, memory_on=True):
    out = [_txn_public(t, memory_on) for t in _TXNS.values() if not bank or t["bank"] == bank]
    if status:
        out = [t for t in out if t["status"] == status]
    return sorted(out, key=lambda t: (t["sent_on"], t["id"]), reverse=True)


def transaction_timeline(txn_id):
    if txn_id not in _TXNS:
        raise KeyError(f"Unknown transaction {txn_id}")
    t = _TXNS[txn_id]
    pub = _txn_public(t)
    p = _PAYOUTS[t["payout_id"]]
    s = _STUDENTS[t["student_id"]]
    ev = [dict(date=_CYC[p["cycle"]]["scheduled_on"], event="Payout scheduled",
               detail=f"{_CYC[p['cycle']]['label']} · {_inr(t['amount'])} for {s['name']}"),
          dict(date=t["sent_on"], event="Released by accountant", detail=f"Approved by {s['accountant']}"),
          dict(date=t["sent_on"], event="NEFT transfer sent",
               detail=f"UTR {t['utr']} to {t['bank']} {t['account']}")]
    st = pub["status"]
    if st == "CREDITED":
        ev.append(dict(date=pub["credited_on"], event="Credited to student",
                       detail=f"Credited in {pub['days_in_transit']} day(s)"))
    elif st in ("FAILED", "RETURNED"):
        fd = _add(t["sent_on"], t["fail"][1])
        ev.append(dict(date=fd, event="Transfer failed" if st == "FAILED" else "Funds returned",
                       detail=t["fail"][2]))
        if st == "RETURNED":
            ev.append(dict(date=fd, event="Money back in the foundation account",
                           detail=f"{_inr(t['amount'])} available to re-send"))
    else:
        ev.append(dict(date=_sim(), event="Awaiting credit" if st == "IN_TRANSIT" else "Delayed",
                       detail=f"Day {pub['days_in_transit']} · expected by {pub['expected_by']} "
                              f"(learned {pub['sla_days']}-day window for {t['bank']})"))
    return ev


def advance_bank_clock(days=1):
    before = {tid: _txn_status(t) for tid, t in _TXNS.items()}
    _STATE["sim_date"] = _add(_sim(), int(days))
    updates = []
    for tid, t in _TXNS.items():
        after = _txn_status(t)
        if after != before[tid]:
            updates.append(dict(txn_id=tid, student_name=_STUDENTS[t["student_id"]]["name"], **{"from": before[tid]},
                                to=after))
    return dict(sim_date=_sim(), updates=updates)


def bank_insights():
    out = []
    for bank in IFSC:
        ts = [t for t in _TXNS.values() if t["bank"] == bank]
        days = _bank_days(bank)
        sla = _learned_sla(bank)
        avoided = 0
        for t in ts:
            if _txn_status(t) in ("FAILED", "RETURNED"):
                continue
            end = t["credit_on"] if t["credit_on"] and t["credit_on"] <= _sim() else _sim()
            d = _days(t["sent_on"], end)
            if NAIVE_SLA < d <= sla:
                avoided += 1
        out.append(dict(bank=bank, transfers=len(ts), credited=len(days),
                        failed=sum(1 for t in ts if _txn_status(t) in ("FAILED", "RETURNED")),
                        median_days=float(statistics.median(days)) if days else None, p90_days=_p90(days),
                        learned_sla_days=sla, naive_sla_days=NAIVE_SLA, false_delay_alarms_avoided=avoided,
                        note=BANK_NOTES.get(bank, "")))
    return sorted(out, key=lambda b: -b["transfers"])


# --------------------------------------------------------------------------- contract: students + team
def list_students():
    return [dict(id=s["id"], name=s["name"], course=s["course"], college=s["college"], year=s["year"],
                 status=s["status"], accountant=s["accountant"]) for s in _STUDENTS.values()]


def _account_state(s, acct):
    ts = sorted([t for t in _TXNS.values() if t["student_id"] == s["id"] and t["account"] == acct],
                key=lambda t: t["sent_on"])
    if ts and _txn_status(ts[-1]) in ("FAILED", "RETURNED") and not (
            acct in s["verified"] and s.get("verified_on", "") > ts[-1]["sent_on"]):
        return "failed"
    if acct in s["verified"]:
        return "verified"
    if not ts and s["joined"] == CUR:
        return "new"
    return "unverified"


def student_profile(student_id):
    if student_id not in _STUDENTS:
        raise KeyError(f"Unknown student {student_id}")
    s = _STUDENTS[student_id]
    pays = sorted([p for p in _PAYOUTS.values() if p["student_id"] == student_id], key=lambda p: (p["cycle"], p["id"]))
    accts: dict = {}
    for p in pays:
        t = _txn_by_payout(p["id"])
        a = accts.setdefault(p["account"], dict(account=p["account"], bank=p["bank"],
                                                ifsc=IFSC[p["bank"]] + p["account"][-4:], holder=p["holder"],
                                                first_used=None, last_used=None, payouts=0))
        if t:
            a["payouts"] += 1
            a["first_used"] = a["first_used"] or t["sent_on"]
            a["last_used"] = t["sent_on"]
    accounts = [a | dict(state=_account_state(s, a["account"])) for a in accts.values()]
    payouts = []
    for p in pays:
        t = _txn_by_payout(p["id"])
        tp = _txn_public(t) if t else None
        payouts.append(dict(payout_id=p["id"], cycle_label=_CYC[p["cycle"]]["label"], amount=p["amount"],
                            status=p["status"], txn_status=tp["status"] if tp else None,
                            sent_on=tp["sent_on"] if tp else None, credited_on=tp["credited_on"] if tp else None))
    facts = [m["text"] for m in sorted(_MEMS, key=lambda m: m["date"], reverse=True) if m["student"] == student_id]
    obs = [o for o in _OBS if student_id in _OBS_STUDENT.get(o["id"], set())]
    return dict(student=dict(id=s["id"], name=s["name"], course=s["course"], college=s["college"], year=s["year"],
                             status=s["status"], annual_entitlement=s["instalment"] * 2, accountant=s["accountant"],
                             region=s["region"], phone=s["phone"]),
                facts=facts, accounts=accounts, payouts=payouts, observations=copy.deepcopy(obs))


def team_workload():
    out = []
    txns = [_txn_public(t) for t in _TXNS.values()]
    for name, a in ACCOUNTANTS.items():
        mine = [p for p in _PAYOUTS.values() if _STUDENTS[p["student_id"]]["accountant"] == name and p["cycle"] == CUR]
        sids = {sid for sid, s in _STUDENTS.items() if s["accountant"] == name}
        # a failed transfer still needs chasing unless the student has been paid since
        latest: dict = {}
        for t in sorted(txns, key=lambda t: t["sent_on"]):
            if t["student_id"] in sids:
                latest[t["student_id"]] = t
        out.append(dict(accountant=name, focus=a["focus"],
                        pending=sum(1 for p in mine if p["status"] == "PENDING"),
                        on_hold=sum(1 for p in mine if p["status"] == "ON_HOLD"),
                        escalated=sum(1 for p in mine if p["status"] == "ESCALATED"),
                        released=sum(1 for p in mine if p["status"] == "RELEASED"),
                        amount_pending=sum(p["amount"] for p in mine if p["status"] != "RELEASED"),
                        avg_turnaround_days=a["turnaround"],
                        failed_to_chase=sum(1 for t in latest.values() if t["status"] in ("FAILED", "RETURNED")),
                        delayed_to_chase=sum(1 for t in txns if t["student_id"] in sids and t["status"] == "DELAYED")))
    return out


__all__ = ["overview", "donor_trail", "utilisation_report_csv", "list_payouts", "get_payout", "decide_payout",
           "get_payout_decision", "payout_feedback", "list_transactions", "transaction_timeline",
           "advance_bank_clock", "bank_insights", "list_students", "student_profile", "team_workload"]
