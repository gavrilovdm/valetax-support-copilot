# Knowledge base: gaps, overlaps and contradictions

The brief says to use the four pages "as they are, including gaps, overlaps and inconsistencies".
This is the catalogue. Each gap has the behaviour the co-pilot must show and the eval cases that check
it (`gap` field in [`data/eval/tickets.jsonl`](../data/eval/tickets.jsonl)).

Snapshot: `data/kb/kb.json` (version in the file). Section ids below are the ones the model cites.

| Id | What the KB says | Problem | Required behaviour |
|---|---|---|---|
| G1 | `withdraw.steps`: "Enter your account details and amount to **deposit**", "Start Trading!" | The withdraw page repeats the deposit steps; there are no real withdrawal steps | Do not present these as withdrawal instructions; use the FAQ facts that are about withdrawals, otherwise say the steps are not documented (`coverage: partial`) |
| G2 | No section mentions fees, payment methods, a minimum withdrawal or withdrawal processing time | Questions about them are common and the answer is unknown | Abstain on that part; never state a fee, method or processing time |
| G3 | `faq.i-have-not-received-my-funds…`: "Should you not receive your funds within 24 hours, contact support" | This is an escalation hint, not an SLA | Never say "withdrawals take 24 hours"; may say "if not received within 24 hours, support will investigate" with the citation |
| G4 | `faq.how-long-does-it-take-for-deposited-funds…`: "Deposits are instant! … within 60 minutes" | "Instant" and "60 minutes" in one answer | Quote the 60-minute figure (the concrete one), never promise "instant" |
| G5 | `faq.what-is-the-minimum-deposit-amount`: "starts from 8 USD, depending on the account type"; the account-type table is a link outside the KB | Per-account minimums are unknown | Say "from 8 USD depending on account type"; never name a minimum for a specific account type |
| G6 | `faq.how-do-i-sign-up…`: "Opening a live account allows you to begin trading immediately" vs `faq.how-long-does-it-take-to-open-an-account`: "verification … within 48 hours" and `faq.why-was-my-withdrawal-request-rejected`: rejection if not verified | Can I trade before verification? The KB contradicts itself | Do not resolve the contradiction; cite both or route to a human for a definitive answer |
| G7 | `faq.what-leverage-settings-should-i-select`: "depends on your strategy … up to 1:2000" | The KB itself answers a question the co-pilot must decline (leverage suggestion) | State the cap with a citation if asked what is available; decline to suggest a setting |
| G8 | The deposit and withdraw pages share an identical 9-item FAQ | Two ids for the same text would make citations ambiguous | Ingest keeps one section per identical Q+A, listing both pages (`kb.py`) |
| G9 | `verify.steps` has no document list and no timing; the documents (POI + POA ≤ 6 months) are on the open-account page | Verification questions need the other page | Cite `faq.do-i-need-to-provide-any-documents-to-open-an-account` for documents; outcome questions go to compliance |

Minor: typos in the source ("in in queue", "insifficient margin") are kept verbatim so that quoted
evidence matches the page; drafts paraphrase.
