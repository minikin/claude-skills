# Claim-check brief

The brief `/humanize` hands to a fresh Agent on `model: "opus"` when asked for a full review. It
fills the `{...}` slots and sends the text below the `---` line. `humanize.py` only finds names that
do not exist. This reader checks whether what the prose says about the code is true.

---

You are checking the facts in prose written about a code base. Read these files in full: {FILES}.
The code base is {ROOT}.

List every claim a reader could check against the code: what a function, file or module does, how
a request or value flows, what a change or patch does, what a test exercises, counts and limits,
and why an alternative fails. Verify each claim by reading the code it concerns. Read only what a
claim needs. Do not run builds, test suites, Docker or any paid tool. Reading files and grep are
enough.

The script already reported these names that do not occur in the code base, start from them:
{SCRIPT_FACTS}

Write {OUT}. Open with the files checked, the code base and the date ({DATE}). Then a table: claim
(quoted or tightly paraphrased, with file and line), verdict (confirmed, wrong, unverifiable),
evidence with file and line. Then each wrong or unverifiable claim in two or three sentences: what
the prose says, what the code shows. A claim stated loosely but correctly is confirmed. Do not
judge style or whether the text sounds generated. Plain English, no em dashes. Your last message is
the count of confirmed, wrong and unverifiable claims and each wrong claim in one line.
