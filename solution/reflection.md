# Reflection

**Which fault types were hardest to catch, and why?**

`missing_upstream` (lineage). The event payload declares `inputs` (the job's
static config), and my first instinct was to diff that against
`lineage_graph_slice`'s `actual_upstream`. It never fired: on the practice
stream, `inputs` only ever listed `raw.orders`, but a clean run's
`actual_upstream` was `["raw.orders", "raw.customers"]` — the join with
`customers` isn't in the static declaration at all, faulty or not. So the
declared field is a red herring, not ground truth to diff against. I switched
to learning each job's normal upstream set online — a majority vote over
`actual_upstream` values seen so far for that job — and flagging any run
whose set is a strict subset of the learned consensus. That only works
because clean runs dominate the stream early enough to establish the
consensus before a fault shows up; a stream that front-loads that fault type
would beat it. I only found this by running the practice phase, logging my
own handler's tool responses to a scratch file, and inspecting them —
`docs/TOOLKIT_API.md` doesn't document payload shape beyond the id fields
used to call each tool.

The second-hardest category was tuning where to alert on the magnitude
checks (checks + ai_infra pillars, all baseline-bound fields). The bounds are
mean ± 3σ, so alerting only past the raw edge is safe but under-catches
subtle instances; alerting too far below it (I first tried 0.65× the bound)
produced a 27.6% false-positive rate, almost entirely from `runtime_anomaly`
on clean lineage runs whose duration naturally sits ~75-90% of the way to
the bound. Diffing per-field ratios (value / bound) against
`practice_answer_key.json`'s tiers showed a clean gap on this stream — clean
values topped out ~0.90×, every fault instance (including "subtle"-tier
ones) started at ~1.48× — so I settled on a single MARGIN = 0.92 across all
magnitude checks rather than hand-tuning one per field.

**What would you change about your cost/coverage tradeoff, if you had another pass?**

Right now every handler makes exactly one metered call per event — the
minimum needed to get any signal at all, since payloads carry no numeric
data on their own. On the public stream (160 events) that still overran the
fixed 220-credit budget by ~9% (240 spent), because the budget doesn't scale
with stream length the way practice's 120-event stream did. I accepted the
overage rather than skipping calls: the scoring formula caps the cost
penalty at -20 points but has no cap on the TPR loss from silently skipping
events, so under this formula it's essentially always better to spend the
budget than to fly blind on some fraction of the stream. If I revisited
this, I'd add a per-event-type running variance check (e.g. via the online
upstream/duration history already being collected) so that once a job or
batch source has produced enough consecutive boring reads, cheaper
non-metered heuristics could deprioritize (not skip) further metered calls
on it — spending the saved budget on pillars that show more volatility
instead of spreading it evenly. I didn't build that here because it adds
real complexity for a gain that's capped at 20% of the score, while a wrong
call on the TPR/FPR side is uncapped.
