# Phase 2 — scale up

At ~10,000 tickets/month (≈14/hour) throughput is not the problem: one worker process handles it.
What breaks first as Valetax grows is **the knowledge**: more pages, internal SOPs that contradict
public pages, more languages and products, and quality that drifts silently when any of them
changes. So Phase 2 is mostly about keeping the KB, the evals and the feedback loop healthy;
infrastructure follows volume. Each item has a trigger: build it when the trigger fires, not before.

## 1. Retrieval instead of full context

| | Trigger | Design |
|---|---|---|
| Today | KB ≈ 2K tokens | Whole KB in a cached prefix (ADR-001) |
| Next | KB > ~30–50K tokens, **or** eval shows citation accuracy dropping as the KB grows | Hybrid retrieval: BM25 + embeddings fused with Reciprocal Rank Fusion; filter by the predicted category; top 6–10 sections into the prompt. Section ids and the validator stay as they are. |

Why the threshold: monthly LLM cost on Sonnet 5.5 (80% cache hits, measured tokens):

| KB size → | 2K tokens (today) | 50K tokens | 300K tokens |
|---|---|---|---|
| 10k tickets | $86 | $364 | $1,814 |
| 50k tickets | $429 | $1,821 | $9,071 |
| 100k tickets | $858 | $3,642 | $18,142 |

Full context stays cheap up to tens of thousands of tokens thanks to caching, but at hundreds of
thousands it costs real money and long contexts dilute attention ("lost in the middle"). With
retrieval the prompt stays ~3–5K tokens whatever the KB size (≈ the left column).

The seam already exists: the pipeline only calls `KnowledgeBase.render()` and validates citations
against `KnowledgeBase.get()`. Retrieval replaces `render()` with `render(selected_sections)`. I did
not add a `KnowledgeSource` interface now — with one implementation it would be ceremony.

Retrieval brings its own eval: recall@k / MRR of the right section per labelled ticket, gated in CI,
so a re-index or an embedding-model change cannot silently lower answer quality.

## 2. The KB and SOPs as a product

- **Sources and precedence.** Internal SOPs > public help pages > macros. Each document has an owner,
  a version and a review date. When two sources disagree (like G6 today), ingest flags the conflict
  for the owner instead of letting the model pick.
- **Ingest pipeline.** Same contract as `kb ingest`: stable section ids, content hash, dedup — plus
  change detection: a changed section re-runs the eval cases that cite it before it goes live.
- **Gap list from production.** Every `unanswered` item and every abstain is logged with the ticket
  category; the top gaps per week go to the KB owner. The co-pilot's abstains are a to-do list for
  the help centre.

## 3. Integration and runtime

```
helpdesk webhook ──► queue (SQS / Redis) ──► worker(s) ──► internal note + tags + queue in helpdesk
                                               │
                                               └──► audit log (append-only) ──► metrics
```

- Idempotent by ticket id + KB version + prompt version: a redelivered webhook does not create a
  second draft. A failed LLM call leaves the ticket untouched in its normal queue (already the
  behaviour: escalate, never drop).
- Drafts are **internal notes**, never customer-visible, until the assist-mode go/no-go.
- Rate limits and provider outages: SDK retries with backoff, server-side refusal fallback; if the
  provider is down the helpdesk simply works as it does today.
- Latency budget: drafts are needed before an agent opens the ticket (minutes), not in 300 ms —
  so no streaming UI, and the Batch API stays for offline re-runs only (ADR-011).

## 4. Feedback loop and quality monitoring

- For every draft: was it sent as-is, edited (edit distance) or discarded; did the agent change
  the queue? These are the business-case inputs, now measured.
- Weekly: sample 50 drafts across languages, run the judge + gap-specific assertions, and have a
  senior agent review 10. Alert if hard-rule violations > 0, or the accept rate drops a few points
  week on week.
- Agent-edited replies become new eval cases (after redaction): the eval set grows from real
  traffic and the synthetic set becomes the regression floor.
- Any change of prompt, model or KB runs the eval in CI and posts the diff of metrics on the PR.

## 5. Model strategy as volume grows

The eval says Sonnet 5.5 now. Revisit when: (a) volume makes token cost a visible share of value
— from the table above that needs ~100k+ tickets/month with a large KB; then measure Haiku again
on the categories where it was clean (simple FAQ answers) and route only those to it; (b) a new
model version ships — run the same eval before switching; (c) refusals or latency become a problem
on a provider — the port in `llm.py` makes a second provider a new class, not a rewrite.

## 6. Governance (regulated environment)

- Audit log per ticket: model, prompt version, KB version, flags, validator findings, route — and
  the agent's final action. Retained per Valetax's record-keeping policy.
- PII: redaction before the LLM (done); data-processing terms with the LLM provider (zero/30-day
  retention as allowed); no training on customer data.
- Change control: prompt and KB changes go through PR + eval gate, with an owner sign-off for
  hard-rule wording.
