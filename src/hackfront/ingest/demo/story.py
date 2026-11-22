"""Brightcart: one controlled, SIMULATED story about an online store, told across 3 repos, 1 Jira project and 3 Slack channels.

Everything is invented (people, customers, numbers). It is replayed through the real clients, adapters and mappers, so the
graph, blame, triage and memory are produced by production code, not typed in. Plain language on purpose: every constraint
below can be explained to a product manager. See docs/story.md.

The story, in time order (stage 0 is everything up to 3 April):
  1. Nov 2025  "Try a failed payment up to 10 times so fewer customers see an error" (SHOP-101).      -> a decision that will die
  2. Jan 2026  Security audit: customers must be signed out after 15 idle minutes (SHOP-377).         -> a compliance rule
  3. Feb 2026  Support begs to revert; security refuses; staying signed in while active is the fix.    -> a refinement
  4. 2 Mar 2026  Payment-provider outage: 214 customers charged 2-6 times for one order (SHOP-412).
                 Decision: try a payment at most 3 times, and give every payment a unique ID (#218).
  5. Mar 2026  Follow-ups: payment ID required (#233), card numbers never printed (#229), 8 second checkout (SHOP-455),
               reliability team reviews any change to payment attempts (#240).
  6. Apr 2026  Nightly refunds get the same limit (#247); the checkout page follows (#96).            -> refines the decision
 Later arrivals, applied with apply_stage(n) so the graph can be watched growing:
  stage 1 (14 Apr)  Support asks for more attempts: a new ticket and a new Slack thread join the existing incident cluster.
  stage 2 (20 Apr)  A coding agent opens #301 "raise attempts from 3 to 8". It undoes step 4 and skips the review rule.
  stage 3 (22 Apr)  People fix failed checkouts a different way (#310), close #301, and mark SHOP-470 done.
  stage 4 (24 Apr)  Two days later SHOP-412 is edited: the root cause was revised, so the belief behind the decision shifts.
 Plus one question nobody can answer (why is the maximum order $2,000?) and a few noise records.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

from . import data as d
from .data import adf, diff, iso, sha, t, ts

OWNER = "brightcart"
JIRA_SITE = "https://brightcart.atlassian.net"
SLACK_WS = "brightcart"
JIRA_PROJECTS = [{"key": "SHOP", "name": "Brightcart Shop"}]
CHANNEL_NAMES = {"C7CHK": "checkout-incidents", "C8SEC": "security-reviews", "C9PRD": "product-and-eng"}
USERS = {"U_PRIYA": "priya", "U_DANIEL": "daniel", "U_MEI": "mei", "U_LEO": "leo", "U_SAM": "sam", "U_KAI": "kai"}


def gh_user(login: str, uid: int, kind: str = "User") -> dict:
    return {"login": login, "id": uid, "type": kind, "html_url": f"https://github.com/{login}"}


PRIYA, DANIEL, MEI = gh_user("priya-k", 1001), gh_user("daniel-p", 1002), gh_user("mei-s", 1003)
LEO, SAM, KAI = gh_user("leo-m", 1004), gh_user("sam-r", 1005), gh_user("kai-t", 1006)
AGENT = gh_user("pr-agent", 2001, "Bot")

# Who is who across tools. DECLARED by the workspace admin (handles differ per tool); the graph never guesses identity.
PEOPLE = {
    "priya": {"name": "Priya K.", "role": "Payments engineer", "github": "priya-k", "jira": "priya-k", "slack": "priya"},
    "daniel": {"name": "Daniel P.", "role": "Engineering manager", "github": "daniel-p", "jira": "daniel-p", "slack": "daniel"},
    "mei": {"name": "Mei S.", "role": "Security lead", "github": "mei-s", "jira": "mei-s", "slack": "mei"},
    "leo": {"name": "Leo M.", "role": "Customer support lead", "github": "leo-m", "jira": "leo-m", "slack": "leo"},
    "sam": {"name": "Sam R.", "role": "Reliability engineer", "github": "sam-r", "jira": "sam-r", "slack": "sam"},
    "kai": {"name": "Kai T.", "role": "Storefront engineer", "github": "kai-t", "jira": "kai-t", "slack": "kai"},
    "pr-agent": {"name": "pr-agent", "role": "AI coding agent", "github": "pr-agent"},
}


def permalink(channel: str, slack_ts: str) -> str:
    return f"https://{SLACK_WS}.slack.com/archives/{channel}/p{slack_ts.replace('.', '')}"


# ---------------------------------------------------------------- repositories
class Repo:
    """Keeps each file's current text so every commit's patch is a real diff and blame replays exactly."""

    def __init__(self, name: str):
        self.name, self.full = name, f"{OWNER}/{name}"
        self.api = f"https://api.github.com/repos/{self.full}"
        self.gh = f"https://github.com/{self.full}"
        self.files: dict[str, str] = {}
        self.commits: list[dict] = []  # oldest first while building
        self.pulls: list[dict] = []
        self.pr_commits: dict[int, list] = {}
        self.pr_files: dict[int, list] = {}
        self.reviews: dict[int, list] = {}
        self.review_comments: dict[int, list] = {}
        self.issue_comments: dict[int, list] = {}
        self._id = 0

    def next_id(self) -> int:
        self._id += 1
        return sum(map(ord, self.full)) * 1000 + self._id

    def commit(self, label: str, message: str, when: str, author: dict, **changes: str) -> dict:
        files = []
        for path, new in changes.items():
            files.append((path, diff(self.files.get(path, ""), new)))
            self.files[path] = new
        h, date = sha(f"{self.full}:{label}"), iso(t(when))
        person = {"name": author["login"], "email": f"{author['login']}@brightcart.example", "date": date}
        adds, dels = sum(p.count("\n+") for _, p in files), sum(p.count("\n-") for _, p in files)
        parents = [self.commits[-1]["sha"]] if self.commits else []
        c = {"sha": h, "url": f"{self.api}/commits/{h}", "html_url": f"{self.gh}/commit/{h}",
             "commit": {"message": message, "author": person, "committer": person}, "author": author, "committer": author,
             "parents": [{"sha": p, "url": f"{self.api}/commits/{p}", "html_url": f"{self.gh}/commit/{p}"} for p in parents],
             "stats": {"additions": adds, "deletions": dels, "total": adds + dels},
             "files": [{"filename": f, "status": "added" if p.startswith("@@ -0,0 ") else "modified",
                        "additions": p.count("\n+"), "deletions": p.count("\n-"), "changes": p.count("\n+") + p.count("\n-"),
                        "patch": p} for f, p in files]}
        self.commits.append(c)
        return c

    def pr(self, number: int, title: str, body: str, when: str, author: dict, commits=(), state="closed", merged=True,
           files=None, base=None) -> dict:
        head = commits[-1] if commits else None
        p = {"number": number, "id": 9000 + number, "url": f"{self.api}/pulls/{number}", "html_url": f"{self.gh}/pull/{number}",
             "state": state, "title": title, "body": body, "user": author, "created_at": iso(t(when)), "updated_at": iso(t(when)),
             "merged": merged, "merge_commit_sha": head["sha"] if (merged and head) else None,
             "head": {"ref": f"feature/pr-{number}", "sha": head["sha"] if head else sha(f"{self.full}:head:{number}")},
             "base": {"ref": "main", "sha": (base or self.commits[-1])["sha"]}, "additions": 5, "deletions": 2}
        self.pulls = [x for x in self.pulls if x["number"] != number] + [p]
        self.pr_commits[number] = list(commits)
        if files is not None:
            self.pr_files[number] = [{"filename": f, "status": "modified"} for f in files]
        return p

    def review(self, n: int, author: dict, state: str, body: str, when: str, commit: dict) -> None:
        i = self.next_id()
        self.reviews.setdefault(n, []).append({
            "id": i, "html_url": f"{self.gh}/pull/{n}#pullrequestreview-{i}", "user": author, "state": state, "body": body,
            "submitted_at": iso(t(when)), "commit_id": commit["sha"]})

    def inline(self, n: int, author: dict, body: str, path: str, line: int, when: str, commit: dict) -> None:
        i = self.next_id()
        self.review_comments.setdefault(n, []).append({
            "id": i, "url": f"{self.api}/pulls/comments/{i}", "html_url": f"{self.gh}/pull/{n}#discussion_r{i}", "user": author,
            "body": body, "path": path, "line": line, "diff_hunk": commit["files"][0]["patch"], "commit_id": commit["sha"],
            "created_at": iso(t(when)), "updated_at": iso(t(when))})

    def comment(self, n: int, author: dict, body: str, when: str) -> None:
        i = self.next_id()
        self.issue_comments.setdefault(n, []).append({
            "id": i, "url": f"{self.api}/issues/comments/{i}", "html_url": f"{self.gh}/pull/{n}#issuecomment-{i}", "body": body,
            "user": author, "created_at": iso(t(when)), "updated_at": iso(t(when))})

    def namespace(self) -> SimpleNamespace:
        return SimpleNamespace(COMMITS=list(reversed(self.commits)), PULLS=list(reversed(self.pulls)), PR_COMMITS=self.pr_commits,
                               PR_FILES=self.pr_files, PR_REVIEWS=self.reviews, PR_REVIEW_COMMENTS=self.review_comments,
                               PR_ISSUE_COMMENTS=self.issue_comments)


# ---------------------------------------------------------------- Slack ids (needed inside PR and Jira text)
def thread_ts(when: str, n: int = 100) -> str:
    return ts(t(when), n)


T_OLD = thread_ts("2025-11-18T11:00:00Z")        # the decision that later dies
T_MAXORDER = thread_ts("2026-02-12T10:00:00Z")   # the question nobody can answer
T_AUDIT = thread_ts("2026-01-22T14:00:00Z")
T_PUSHBACK = thread_ts("2026-02-05T13:20:00Z")
T_INCIDENT = thread_ts("2026-03-02T15:00:00Z")
T_REVIEW = thread_ts("2026-03-05T10:00:00Z")
T_CARDS = thread_ts("2026-03-08T09:30:00Z")
T_REFUNDS = thread_ts("2026-04-01T15:00:00Z")
T_RAISE = thread_ts("2026-04-14T09:10:00Z")
T_DEPLOY = thread_ts("2026-03-20T16:00:00Z")
T_ONCALL = thread_ts("2026-04-06T08:30:00Z")

# ---------------------------------------------------------------- payments
pay = Repo("payments")
PREAD0 = "# payments\n\nCard payments are sent by charge_card in src/payments/charge.py.\n"
PREAD1 = PREAD0 + "\nSee docs/payment-ids.md for how repeats are recognised.\n"
PCI0 = "name: ci\non: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: pytest\n"
PCI1 = PCI0 + "      - run: ruff check .\n"
CHARGE0 = '''MAX_PAYMENT_ATTEMPTS = 10


class PaymentFailed(Exception):
    pass


def charge_card(order_id, amount, send):
    for _ in range(MAX_PAYMENT_ATTEMPTS):
        result = send(order_id, amount)
        if result.ok:
            return result
    raise PaymentFailed(order_id)
'''
CHARGE_CAP = CHARGE0.replace("MAX_PAYMENT_ATTEMPTS = 10", "MAX_PAYMENT_ATTEMPTS = 3")
CHARGE1 = CHARGE_CAP.replace(
    "    for _ in range(MAX_PAYMENT_ATTEMPTS):\n        result = send(order_id, amount)\n",
    "    payment_id = f\"{order_id}-payment\"  # the same ID on every attempt, so the provider never charges an order twice\n"
    "    for _ in range(MAX_PAYMENT_ATTEMPTS):\n        result = send(order_id, amount, payment_id)\n")
CHARGE2 = CHARGE1.replace("MAX_PAYMENT_ATTEMPTS = 3\n", "from .retry_later import retry_later\n\nMAX_PAYMENT_ATTEMPTS = 3\n").replace(
    "    raise PaymentFailed(order_id)\n", "    retry_later(order_id)  # park the order and try again from the queue, never in a tight loop\n    raise PaymentFailed(order_id)\n")
LATER0 = "def retry_later(order_id):\n    # puts the order on a queue; a worker tries it again after a pause, still with the same payment ID\n    print(\"queued\", order_id)\n"
PAPI0 = "from .charge import charge_card\n\n\ndef create_payment(order_id, amount, send):\n    return charge_card(order_id, amount, send)\n"
PAPI1 = PAPI0.replace("def create_payment(order_id, amount, send):\n", "def create_payment(order_id, amount, send):\n    if not order_id:\n        raise ValueError(\"every payment needs an order ID\")\n")
LOG1 = ('def last4(card_number):\n    return "*" * 12 + card_number[-4:]\n\n\n'
        'def log_payment(logger, payment):\n    logger.info("payment for card %s", last4(payment["card_number"]))\n')
NIGHT0 = ("MAX_REFUND_ATTEMPTS = 10\n\n\ndef send_refunds(refunds, send):\n    for refund in refunds:\n"
          "        for _ in range(MAX_REFUND_ATTEMPTS):\n            if send(refund).ok:\n                break\n")
NIGHT1 = NIGHT0.replace("MAX_REFUND_ATTEMPTS = 10", "MAX_REFUND_ATTEMPTS = 3  # same limit as card payments (SHOP-412)")
CHARGE_PY = "src/payments/charge.py"

p_init = pay.commit("init", "Add project scaffolding", "2025-11-10T09:00:00Z", DANIEL,
                    **{"requirements.txt": d.REQ0, "README.md": PREAD0, ".github/workflows/ci.yml": PCI0})
p_charge = pay.commit("charge", "Add card payments that try again when the provider fails (SHOP-101)\n\nTry up to 10 times.",
                      "2025-11-20T10:00:00Z", PRIYA, **{CHARGE_PY: CHARGE0})
p_api = pay.commit("api", "Add payment entrypoint", "2025-12-03T10:00:00Z", PRIYA, **{"src/payments/api.py": PAPI0})
p_night0 = pay.commit("night0", "Add nightly refund job (SHOP-460)", "2025-12-20T10:00:00Z", SAM, **{"src/refunds/nightly.py": NIGHT0})
p_bump = pay.commit("bump", "Update the requests library\n\nAutomated security update.", "2026-01-05T06:00:00Z", DANIEL, **{"requirements.txt": d.REQ1})
p_lint = pay.commit("lint", "Run the code checker on every change", "2026-02-02T09:00:00Z", SAM, **{".github/workflows/ci.yml": PCI1})
p_cap = pay.commit("cap", "Try a card payment at most 3 times instead of 10\n\nSHOP-412: repeated attempts charged customers twice.",
                   "2026-03-03T17:12:00Z", PRIYA, **{CHARGE_PY: CHARGE_CAP})
p_id = pay.commit("id", "Give every payment a unique payment ID (#218)\n\nThe ID is reused on every attempt, so a repeat is recognised and not charged again.",
                  "2026-03-04T08:55:00Z", PRIYA, **{CHARGE_PY: CHARGE1})
p_cards = pay.commit("cards", "Show only the last 4 digits of card numbers in records (#229)", "2026-03-09T11:00:00Z", MEI, **{"src/payments/logging.py": LOG1})
p_needid = pay.commit("needid", "Refuse payments that have no order ID (#233)", "2026-03-10T14:00:00Z", PRIYA, **{"src/payments/api.py": PAPI1})
p_owners = pay.commit("owners", "Reliability team reviews changes to payment attempts (#240)\n\nSHOP-415 process rule.", "2026-03-11T09:00:00Z", DANIEL,
                      **{".github/CODEOWNERS": "src/payments/charge.py @brightcart/reliability\nsrc/checkout/ @brightcart/reliability\n"})
p_doc = pay.commit("doc", "Link the payment ID doc from the README", "2026-03-12T12:00:00Z", DANIEL, **{"README.md": PREAD1})
p_refund = pay.commit("refund", "Use the same 3 attempt limit for nightly refunds (#247)\n\nFollows #218, see SHOP-460.", "2026-04-02T10:00:00Z", PRIYA,
                      **{"src/refunds/nightly.py": NIGHT1})

pay.pr(142, "Add card payments with automatic retries", "Implements SHOP-101. Try again when the payment provider fails so fewer customers see an error.",
       "2025-11-19T16:00:00Z", PRIYA, [p_charge], base=p_init)
pay.pr(160, "Add nightly refund job", "Nightly refunds for SHOP-460. Tries each refund up to 10 times.", "2025-12-19T15:00:00Z", SAM, [p_night0], base=p_api)
pay.pr(188, "Update the requests library", "Automated security update. No change in behaviour.", "2026-01-05T05:00:00Z", DANIEL, [p_bump], base=p_night0)
pay.pr(
    218, "Try a payment at most 3 times and give every payment a unique ID",
    f"Fixes SHOP-412. Replaces the try-up-to-10-times policy from {permalink('C9PRD', T_OLD)}. We decided to try a card payment at most 3 times instead of 10 "
    "because repeated attempts charged 214 customers twice during the outage. Alternative rejected: a setting that lets teams raise the limit, since checkout "
    f"needs to finish within 8 seconds (SHOP-455) so more than 3 attempts would not help. Decision thread: {permalink('C7CHK', T_INCIDENT)}. "
    "Trade-off: a few customers see an error sooner and their order is retried later.",
    "2026-03-04T09:30:00Z", PRIYA, [p_cap, p_id], base=p_lint)
pay.pr(229, "Show only the last 4 digits of card numbers in records",
       f"Rule from the security review: full card numbers must never appear in our records, always show only the last 4 digits. {permalink('C8SEC', T_CARDS)}",
       "2026-03-09T10:00:00Z", MEI, [p_cards], base=p_id)
pay.pr(233, "Every payment must have a unique payment ID",
       "Rule from the SHOP-415 review: every payment must carry a unique payment ID, and we now refuse to charge an order that has none. "
       "Never try a payment again without the same ID. Always reuse the same ID for every attempt of one order. Follows #218. Closes SHOP-430.",
       "2026-03-10T13:00:00Z", PRIYA, [p_needid], base=p_cards)
pay.pr(240, "Reliability team reviews changes to payment attempts",
       "Rule from SHOP-415: every change to how many times we try a payment, or how long checkout waits, must be reviewed by the reliability team "
       f"and checked against the 8 second limit (SHOP-455). Never merge such a change without both. {permalink('C7CHK', T_REVIEW)}",
       "2026-03-11T08:00:00Z", DANIEL, [p_owners], base=p_needid)
pay.pr(247, "Use the same 3 attempt limit for nightly refunds",
       "Follows #218 and SHOP-460. We decided nightly refunds get the same limit of 3 rather than their own policy, because they hit the same "
       f"double-charge problem during SHOP-412. Thread: {permalink('C9PRD', T_REFUNDS)}", "2026-04-02T09:00:00Z", PRIYA, [p_refund], base=p_doc)

pay.review(218, SAM, "CHANGES_REQUESTED", "Please show that 3 attempts still fit inside the 8 second checkout limit (SHOP-455) before this merges.", "2026-03-04T09:40:00Z", p_cap)
pay.comment(218, PRIYA, "Added a short pause between attempts and measured it: 95% of checkouts finish in 7.1 seconds with 3 attempts. Unique payment ID is in too.", "2026-03-04T09:58:00Z")
pay.review(218, DANIEL, "APPROVED", "Approved. Keep the limit at 3 even now that payment IDs exist.", "2026-03-04T10:30:00Z", p_id)
pay.inline(218, DANIEL, "Why not make this a setting? -> No: the 8 second checkout limit makes more than 3 pointless (see SHOP-412).", CHARGE_PY, 1, "2026-03-04T09:50:00Z", p_cap)
pay.review(233, DANIEL, "APPROVED", "Good. The payment ID is the real fix; the limit of 3 is the seatbelt.", "2026-03-10T14:20:00Z", p_needid)
pay.inline(247, SAM, "Same reasoning as #218: do not give refunds a separate, larger limit.", "src/refunds/nightly.py", 1, "2026-04-02T09:40:00Z", p_refund)

# ---------------------------------------------------------------- accounts (sign-in)
acc = Repo("accounts")
SIGN0 = "SIGN_IN_TIMEOUT_MINUTES = 1440\n\n\ndef still_signed_in(minutes_idle):\n    return minutes_idle < SIGN_IN_TIMEOUT_MINUTES\n"
SIGN1 = SIGN0.replace("1440", "15")
SIGN2 = SIGN1.replace("def still_signed_in(minutes_idle):\n    return minutes_idle < SIGN_IN_TIMEOUT_MINUTES\n",
                      "def still_signed_in(minutes_idle, active=False):\n    # customers who are actively shopping are never signed out\n    return active or minutes_idle < SIGN_IN_TIMEOUT_MINUTES\n")
a_init = acc.commit("init", "Add sign-in sessions", "2025-11-12T10:00:00Z", MEI, **{"src/accounts/sign_in.py": SIGN0, "requirements.txt": d.REQ0})
a_ttl = acc.commit("ttl", "Sign customers out after 15 idle minutes\n\nSHOP-377: security audit requirement.", "2026-01-26T16:40:00Z", MEI, **{"src/accounts/sign_in.py": SIGN1})
a_ref = acc.commit("active", "Keep active customers signed in (#201)", "2026-02-10T09:40:00Z", MEI, **{"src/accounts/sign_in.py": SIGN2})
a_bump = acc.commit("bump", "Update the requests library", "2026-03-15T06:00:00Z", DANIEL, **{"requirements.txt": d.REQ1})
acc.pr(61, "Add sign-in sessions", "Customers stay signed in for 24 hours.", "2025-11-12T09:00:00Z", MEI, [a_init], base=a_init)
acc.pr(190, "Sign customers out after 15 idle minutes",
       "Audit SHOP-377: customers must be signed out after 15 idle minutes. We decided to cut the sign-in time from 24 hours to 15 minutes of inactivity "
       f"rather than keep it, because a stolen login on a shared computer was rated high risk. This is a compliance requirement, not optional. {permalink('C8SEC', T_AUDIT)}",
       "2026-01-27T11:00:00Z", MEI, [a_ttl], base=a_init)
acc.pr(201, "Keep active customers signed in",
       f"Follows #190 and SHOP-441. Keep the 15 minute limit but only for idle customers instead of reverting it, as agreed in {permalink('C8SEC', T_PUSHBACK)}. "
       "Customers who are shopping never get signed out; idle ones still are.", "2026-02-10T10:00:00Z", MEI, [a_ref], base=a_ttl)
acc.pr(214, "Update the requests library", "Automated security update. No change in behaviour.", "2026-03-15T05:00:00Z", DANIEL, [a_bump], base=a_ref)
acc.review(190, DANIEL, "APPROVED", "Approved. Compliance item SHOP-377, do not weaken it later.", "2026-01-27T12:00:00Z", a_ttl)

# ---------------------------------------------------------------- storefront (checkout page)
store = Repo("storefront")
WAIT0 = ("export const CHECKOUT_WAIT_SECONDS = 30;\nexport const PAYMENT_TRIES = 5;\n\n"
         "export async function payForOrder(order: Order): Promise<Receipt> {\n  for (let n = 0; n < PAYMENT_TRIES; n++) {\n"
         "    const res = await submitPayment(order, CHECKOUT_WAIT_SECONDS);\n    if (res.ok) return res.receipt;\n  }\n  throw new Error(\"payment failed\");\n}\n")
WAIT1 = WAIT0.replace("CHECKOUT_WAIT_SECONDS = 30;", "CHECKOUT_WAIT_SECONDS = 7; // SHOP-455: checkout must finish within 8 seconds")
WAIT2 = WAIT1.replace("PAYMENT_TRIES = 5;", "PAYMENT_TRIES = 3; // same as the payments service, do not add more on top")
SCI0 = "name: ci\non: [push]\njobs:\n  e2e:\n    runs-on: ubuntu-latest\n    steps:\n      - run: npm test\n"
SCI1 = SCI0.replace("npm test", "npm test -- --retries=2")
s_init = store.commit("init", "Add checkout payment page", "2025-11-15T10:00:00Z", KAI, **{"src/checkout/waiting.ts": WAIT0, ".github/workflows/ci.yml": SCI0})
s_ci = store.commit("ci", "Re-run flaky browser tests twice", "2026-02-25T10:00:00Z", KAI, **{".github/workflows/ci.yml": SCI1})
s_wait = store.commit("wait", "Stop waiting after 7 seconds to stay inside the 8 second limit (#91)", "2026-03-06T10:00:00Z", KAI, **{"src/checkout/waiting.ts": WAIT1})
s_tries = store.commit("tries", "Try a payment at most 3 times on the page too (#96)", "2026-04-03T10:00:00Z", KAI, **{"src/checkout/waiting.ts": WAIT2})
store.pr(70, "Add checkout payment page", "The page waits up to 30 seconds and tries a payment 5 times.", "2025-11-15T09:00:00Z", KAI, [s_init], base=s_init)
store.pr(88, "Re-run flaky browser tests", "Test hygiene. Unrelated to what customers see.", "2026-02-25T09:00:00Z", KAI, [s_ci], base=s_init)
store.pr(91, "Stop waiting after 7 seconds",
         "SHOP-455: checkout needs to finish within 8 seconds, because customers abandon their cart after that. We decided to stop waiting after 7 seconds instead of 30 "
         "so the page answers before payment attempts pile up. Payments side: https://github.com/brightcart/payments/pull/218",
         "2026-03-06T09:00:00Z", KAI, [s_wait], base=s_ci)
store.pr(96, "Try a payment at most 3 times on the page too",
         "Rule for the checkout page: it must never add its own payment attempts on top of the payments service, and must always keep the total inside the 8 second "
         "limit (SHOP-455). Follows #91 and the payments limit of 3 (https://github.com/brightcart/payments/pull/218).",
         "2026-04-03T09:00:00Z", KAI, [s_tries], base=s_wait)
store.review(96, DANIEL, "APPROVED", "Approved. One layer of attempts only, see SHOP-455.", "2026-04-03T11:00:00Z", s_tries)

REPOS = {pay.full: pay.namespace(), acc.full: acc.namespace(), store.full: store.namespace()}
REPO_NAMES = [pay.name, acc.name, store.name]


# ---------------------------------------------------------------- Jira
def issue(n: int, summary: str, description: str, created: str, itype: str, status: str, reporter: str, priority="Medium", updated=None) -> dict:
    key = f"SHOP-{n}"
    return {"id": str(10000 + n), "key": key, "self": f"{JIRA_SITE}/rest/api/3/issue/{key}",
            "fields": {"summary": summary, "description": adf(description), "issuetype": {"name": itype}, "project": {"key": "SHOP"},
                       "status": {"name": status}, "priority": {"name": priority},
                       "reporter": {"accountId": f"acc-{reporter}", "displayName": reporter}, "created": created, "updated": updated or created,
                       "labels": [], "issuelinks": []}}


def jcomment(n: int, cid: int, who: str, text: str, when: str) -> dict:
    return {"id": str(cid), "self": f"{JIRA_SITE}/rest/api/3/issue/{10000 + n}/comment/{cid}",
            "author": {"accountId": f"acc-{who}", "displayName": who}, "body": adf(text), "created": when, "updated": when}


ISSUE_412 = ("Incident 2026-03-02, root cause found: during an 11 minute payment-provider outage 214 customers were charged 2-6 times for one order. "
             "The provider answered 'error' after some payments had already gone through, and we tried each payment up to 10 times without a unique payment ID. "
             "Workaround: refunds issued, automatic retries switched off by hotfix.")
JIRA_ISSUES = {"SHOP": [
    issue(101, "Try failed card payments again", "Customers see an error whenever the payment provider hiccups. Try the payment again so fewer customers are affected.",
          "2025-11-17T10:00:00.000+0000", "Story", "Done", "priya-k"),
    issue(377, "Security audit: customers stay signed in for 24 hours",
          "External security test (Q1) rated 24 hour sign-ins high risk, for example on a shared computer. Requirement: customers must be signed out after 15 idle minutes or less. "
          "Compliance item, not optional.", "2026-01-20T10:00:00.000+0000", "Task", "Done", "mei-s", "High"),
    issue(412, "Customers charged twice during payment outage", ISSUE_412, "2026-03-02T14:20:00.000+0000", "Bug", "Done", "daniel-p", "Highest"),
    issue(415, "Review of the double-charge incident",
          "Review of SHOP-412. Root cause: automatic retries with no unique payment ID. The outage was made worse by a checkout page that waited 30 seconds. Actions: "
          "limit attempts (SHOP-412 fix), require a unique payment ID (SHOP-430), set an 8 second checkout limit (SHOP-455). No test existed for the case where "
          "the provider errors after taking the money.", "2026-03-05T11:00:00.000+0000", "Task", "Done", "daniel-p", "High"),
    issue(430, "Refuse payments without a unique payment ID",
          "Every payment must carry a unique payment ID. Refuse any payment without one; never try again without the same ID; always reuse it for every attempt. "
          "From the SHOP-415 review.", "2026-03-06T10:00:00.000+0000", "Task", "Done", "priya-k"),
    issue(441, "Support: customers signed out in the middle of checkout", "Since the 15 minute sign-out (SHOP-377) support sees customers losing their cart. Can we go back to the old time?",
          "2026-02-04T09:00:00.000+0000", "Bug", "Done", "leo-m"),
    issue(455, "Set a checkout time limit",
          "Checkout has to finish within 8 seconds. Customers abandon the cart after that. Waiting for the page, payment attempts and the retry queue all spend from this limit.",
          "2026-03-05T12:00:00.000+0000", "Task", "Done", "daniel-p"),
    issue(460, "Nightly refunds try each refund too many times", "Nightly refunds try each refund up to 10 times on any error. Align this with card payments.",
          "2025-12-18T10:00:00.000+0000", "Task", "Done", "sam-r"),
    issue(390, "Keep libraries up to date", "Keep the requests library current in every service.", "2026-01-03T10:00:00.000+0000", "Task", "Done", "daniel-p", "Low"),
    issue(395, "Flaky browser tests on the storefront", "Browser tests fail roughly one run in ten. Investigate.", "2026-02-20T10:00:00.000+0000", "Bug", "Done", "kai-t", "Low"),
    issue(480, "Update the on-call rota", "Update the on-call rota for Q2.", "2026-04-05T10:00:00.000+0000", "Task", "To Do", "sam-r", "Low"),
]}
JIRA_COMMENTS = {
    "SHOP-412": [jcomment(412, 30001, "priya-k", f"Root cause and the decision on attempts are in {permalink('C7CHK', T_INCIDENT)}. Fix in {pay.gh}/pull/218.", "2026-03-04T09:45:00.000+0000"),
                 jcomment(412, 30002, "sam-r", "Hotfix deployed at 15:42 UTC, automatic retries switched off until the fix lands.", "2026-03-02T15:50:00.000+0000")],
    "SHOP-415": [jcomment(415, 30010, "daniel-p", f"Review thread: {permalink('C7CHK', T_REVIEW)}. Actions are tracked in SHOP-430 and SHOP-455.", "2026-03-05T12:30:00.000+0000")],
    "SHOP-441": [jcomment(441, 30030, "mei-s", f"Not reverting, SHOP-377 is a compliance item. Keeping active customers signed in instead: {acc.gh}/pull/201.", "2026-02-05T14:00:00.000+0000")],
}


# ---------------------------------------------------------------- Slack
def msg(ts_: str, who: str, text: str, **extra) -> dict:
    return {"type": "message", "user": who, "ts": ts_, "text": text, **extra}


def thread(root_ts: str, who: str, text: str, replies: list[tuple[str, str, str]]) -> list[dict]:
    out = [msg(root_ts, who, text, thread_ts=root_ts, reply_count=len(replies))]
    out += [msg(ts(t(when), 200 + i), w, txt, thread_ts=root_ts) for i, (when, w, txt) in enumerate(replies)]
    return out


SLACK_THREADS = {
    "C7CHK": {
        T_INCIDENT: thread(T_INCIDENT, "U_DANIEL", "Incident: customers charged twice. 214 customers were charged 2-6 times for one order. Refunds are in progress (SHOP-412). How do we make sure this never happens again?", [
            ("2026-03-02T15:05:00Z", "U_SAM", "The payment provider was down for 11 minutes. Some payments had already gone through, so every new attempt charged the customer again. Hotfix is live."),
            ("2026-03-02T15:12:00Z", "U_PRIYA", "Root cause: we tried each payment up to 10 times with no unique payment ID. Proposal: give every payment a unique ID so repeats are recognised, and try at most 3 times with a short pause. "
             "3 attempts cover 99% of short provider hiccups in last quarter's data; beyond that we fail fast and retry the order later from a queue."),
            ("2026-03-02T15:20:00Z", "U_DANIEL", "Agreed. Priya owns it. Keep the limit at 3 even after payment IDs land: checkout needs to finish within 8 seconds or customers leave, and 10 attempts blew through that anyway. "
             "Nobody raises it without new data.")]),
        T_REVIEW: thread(T_REVIEW, "U_DANIEL", "Review of SHOP-412 is in SHOP-415. Actions: limit attempts (https://github.com/brightcart/payments/pull/218), "
                         "unique payment ID (SHOP-430), 8 second checkout limit (SHOP-455).", [
            ("2026-03-05T10:20:00Z", "U_LEO", "Support impact: 61 tickets, all refunded within 24 hours. Customer emails went out."),
            ("2026-03-05T10:40:00Z", "U_DANIEL", "Lesson: no test covered the case where the provider errors after taking the money. Added to the checklist."),
            ("2026-03-05T10:55:00Z", "U_DANIEL", "Process change from SHOP-415: any change to payment attempts, checkout wait time or the 8 second limit must get a reliability team review "
             "and a check against SHOP-455. Never merge one without both.")]),
    },
    "C8SEC": {
        T_AUDIT: thread(T_AUDIT, "U_MEI", "Security audit review: the external test flagged 24 hour sign-ins (SHOP-377). Proposal: sign customers out after 15 idle minutes.", [
            ("2026-01-22T14:15:00Z", "U_DANIEL", "Compliance requires it, so we do it. Mei owns the change.")]),
        T_PUSHBACK: thread(T_PUSHBACK, "U_LEO", f"Lots of tickets about customers losing their cart since {acc.gh}/pull/190 (SHOP-441). Can we undo the 15 minute sign-out?", [
            ("2026-02-05T13:45:00Z", "U_MEI", "Can't revert, SHOP-377 is a compliance item. We will keep active customers signed in so only idle ones are signed out.")]),
        T_CARDS: thread(T_CARDS, "U_MEI", "Reminder from the review: full card numbers must never appear in our records. Always show only the last 4 digits.", [
            ("2026-03-08T09:45:00Z", "U_PRIYA", "Will do, I will mask them in the payment log.")]),
    },
    "C9PRD": {
        T_OLD: thread(T_OLD, "U_PRIYA", "Payments: we decided to try a failed payment up to 10 times so fewer customers see an error rather than fail the checkout (SHOP-101). Any objections?", [
            ("2025-11-18T11:30:00Z", "U_SAM", "Fine for now, we can tune it later.")]),
        T_MAXORDER: thread(T_MAXORDER, "U_LEO", "Anyone know why the maximum order is $2,000?", [
            ("2026-02-12T10:09:00Z", "U_PRIYA", "No idea, it predates me. Not written down anywhere I can find.")]),
        T_REFUNDS: thread(T_REFUNDS, "U_SAM", "Nightly refunds still try 10 times (SHOP-460). Same double-charge problem as SHOP-412?", [
            ("2026-04-01T15:20:00Z", "U_PRIYA", f"Yes. Same limit as card payments, see {permalink('C7CHK', T_INCIDENT)}. I will open a PR.")]),
        T_DEPLOY: thread(T_DEPLOY, "U_SAM", "Deploy window moved to Thursday 14:00 UTC.", []),
        T_ONCALL: thread(T_ONCALL, "U_SAM", "On-call handoff notes are in the wiki (SHOP-480).", []),
    },
}

WORKSPACE = {
    "name": "Brightcart (simulated)",
    "demo": True,
    "github": {"owner": OWNER, "repos": list(REPO_NAMES)},
    "jira": {"site": JIRA_SITE, "projects": ["SHOP"]},
    "slack": {"workspace": SLACK_WS, "channels": list(SLACK_THREADS), "channel_names": dict(CHANNEL_NAMES), "users": dict(USERS)},
}


# ---------------------------------------------------------------- later arrivals (stages 1-4)
def _set_issue(n: int, **fields) -> None:
    key = f"SHOP-{n}"
    JIRA_ISSUES["SHOP"] = [issue(n, **fields) if i["key"] == key else i for i in JIRA_ISSUES["SHOP"]]


def _stage1() -> None:  # a new ticket and a new Slack thread join the incident cluster
    JIRA_ISSUES["SHOP"].append(issue(
        470, "Failed checkouts up 3% week over week",
        "The share of customers who see 'payment failed' is up 3% week over week since we limited payment attempts (SHOP-412). Support asks for more attempts. "
        "Proposal: raise the limit.", "2026-04-14T09:00:00.000+0000", "Bug", "In Progress", "leo-m", "High"))
    JIRA_COMMENTS["SHOP-470"] = [jcomment(470, 30020, "daniel-p", f"Before changing the limit read {permalink('C7CHK', T_INCIDENT)}. The limit was the SHOP-412 fix.", "2026-04-14T10:00:00.000+0000")]
    SLACK_THREADS["C7CHK"][T_RAISE] = thread(T_RAISE, "U_LEO", "Failed checkouts are up since we limited payment attempts. Can we raise the limit? SHOP-470", [
        ("2026-04-14T09:25:00Z", "U_PRIYA", f"Please read the decision first: {permalink('C7CHK', T_INCIDENT)}. The limit protects customers from being charged twice; fix the failures at the source instead."),
        ("2026-04-14T09:40:00Z", "U_DANIEL", "Not raising it without the 8 second numbers from SHOP-455.")])


def _stage2() -> None:  # a coding agent opens a PR that undoes the decision and skips the review rule
    pay.pr(301, "Raise payment attempts from 3 to 8 to reduce failed checkouts",
           "Failed checkouts are up 3% (SHOP-470). Raising MAX_PAYMENT_ATTEMPTS from 3 to 8 in src/payments/charge.py should recover short provider hiccups. "
           "Tests pass. Opened by pr-agent from the SHOP-470 description.", "2026-04-20T08:00:00Z", AGENT, [], state="open", merged=False,
           files=[CHARGE_PY], base=p_refund)
    pay.comment(301, SAM, "Tests are green. Waiting for a reliability review.", "2026-04-20T09:00:00Z")


def _stage3() -> None:  # people fix it a different way, close the agent PR, mark the ticket done
    c = pay.commit("later", "Retry failed payments later from a queue instead of raising the limit (SHOP-470)\n\nKeeps the limit of 3 from #218.",
                   "2026-04-22T10:00:00Z", PRIYA, **{CHARGE_PY: CHARGE2, "src/payments/retry_later.py": LATER0})
    pay.pr(310, "Retry failed payments later from a queue",
           "Resolves SHOP-470 without raising the limit. We decided to park a failed order on a queue and try it again after a pause instead of adding attempts "
           "now, because more attempts while the payment provider is struggling make things worse for customers (SHOP-412). Keeps the limit of 3 from #218; the reliability team approved. Closes #301.",
           "2026-04-22T09:00:00Z", PRIYA, [c], base=p_refund)
    pay.review(310, SAM, "APPROVED", "Reliability review done. Limit stays at 3, the queue handles the rest.", "2026-04-22T09:40:00Z", c)
    pay.pr(301, "Raise payment attempts from 3 to 8 to reduce failed checkouts",
           "Failed checkouts are up 3% (SHOP-470). Raising MAX_PAYMENT_ATTEMPTS from 3 to 8 in src/payments/charge.py should recover short provider hiccups. "
           "Closed without merging: it undoes #218 and skipped the review rule from #240.", "2026-04-20T08:00:00Z", AGENT, [], state="closed", merged=False,
           files=[CHARGE_PY], base=p_refund)
    _set_issue(470, summary="Failed checkouts up 3% week over week",
               description="The share of customers who see 'payment failed' is up 3% week over week since we limited payment attempts (SHOP-412). Resolved on 22 April by "
                           "retrying failed payments later from a queue (https://github.com/brightcart/payments/pull/310). The limit of 3 stays.",
               created="2026-04-14T09:00:00.000+0000", itype="Bug", status="Done", reporter="leo-m", priority="High", updated="2026-04-22T11:00:00.000+0000")


def _stage4() -> None:  # two days later the incident ticket is corrected: the belief behind the decision shifts
    _set_issue(412, summary="Customers charged twice during payment outage",
               description="Update 24 April: root cause revised. The double charges happened because the provider confirmed some payments late, and a unique payment ID "
                           "alone would have prevented every one of them. The limit of 3 attempts only reduces load during an outage; it is a safety net, not the fix. "
                           + ISSUE_412,
               created="2026-03-02T14:20:00.000+0000", itype="Bug", status="Done", reporter="daniel-p", priority="Highest", updated="2026-04-24T08:00:00.000+0000")


_STAGES = {1: _stage1, 2: _stage2, 3: _stage3, 4: _stage4}
STAGE = 0


def apply_stage(n: int) -> int:
    """Add the arrivals of every stage up to n (once). The transports read these structures on each call."""
    global STAGE
    while STAGE < n and STAGE + 1 in _STAGES:
        STAGE += 1
        _STAGES[STAGE]()
    REPOS.update({pay.full: pay.namespace(), acc.full: acc.namespace(), store.full: store.namespace()})
    return STAGE


apply_stage(int(os.environ.get("HACKFRONT_STORY_STAGE", "0") or 0))
