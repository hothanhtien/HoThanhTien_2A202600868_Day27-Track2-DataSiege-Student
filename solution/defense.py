"""
Your defense. Implement register(ctx) and a handler per event type.
See ../README.md for the full interface + toolkit reference, and
../RULES.md before you start.
"""
from api import Verdict

# Baseline bounds (data/baselines.json) are calibrated at clean-stream
# mean +/- 3 sigma (docs/TOOLKIT_API.md). A clean value crossing that edge is
# already rare, so firing at a MARGIN fraction of the way to the edge -
# rather than at the raw edge - catches faults sitting closer to normal
# variance without materially raising the false-positive rate. Chosen by
# running the practice phase and diffing against phases/practice_answer_key.json
# (README: "learn freely here"): observed clean values topped out around
# 0.90x the bound, observed fault instances started at 1.48x, so 0.92 sits in
# the gap without hugging either edge.
MARGIN = 0.92


def register(ctx):
    ctx.on("data_batch", check_data_batch)
    ctx.on("contract_checkpoint", check_contract_checkpoint)
    ctx.on("lineage_run", check_lineage_run)
    ctx.on("feature_materialization", check_feature_materialization)
    ctx.on("embedding_batch", check_embedding_batch)


def _range_hit(value, lo, hi):
    """Two-sided bound (mean +/- 3 sigma)."""
    center = (lo + hi) / 2.0
    half = (hi - lo) / 2.0
    return abs(value - center) / half > MARGIN


def _bound_hit(value, bound):
    """One-sided bound (mean + 3 sigma; value can't be anomalously low)."""
    return value / bound > MARGIN


def check_data_batch(payload, ctx):
    r = ctx.tools.batch_profile(payload["batch_id"])
    if "error" in r:
        return Verdict(alert=False, pillar="checks", reason=r["error"])

    b = ctx.baseline
    reasons = []
    if _range_hit(r["row_count"], b["row_count_min"], b["row_count_max"]):
        reasons.append("volume_spike")
    if _bound_hit(r["null_rate"]["customer_id"], b["null_rate_max"]):
        reasons.append("null_spike")
    if _range_hit(r["mean_amount"], b["mean_amount_min"], b["mean_amount_max"]):
        reasons.append("distribution_shift")
    if _bound_hit(r["staleness_min"], b["staleness_min_max"]):
        reasons.append("freshness_lag")

    return Verdict(alert=bool(reasons), pillar="checks", reason=",".join(reasons))


def check_contract_checkpoint(payload, ctx):
    r = ctx.tools.contract_diff(payload["contract_id"], payload["checkpoint_batch_id"])
    if "error" in r:
        return Verdict(alert=False, pillar="contracts", reason=r["error"])

    # schema_hash_mismatch / type_violation come back pre-computed from the
    # harness's exact declared-vs-actual comparison - no thresholding needed.
    reasons = list(r["violations"])

    # SLA freshness is contract-specific (FAULT_PILLARS.md: "schema, type, or
    # SLA violations"), so it's checked against *this* checkpoint's own
    # declared_sla rather than the general population baseline.
    sla_min = payload.get("declared_sla", {}).get("freshness_min")
    if sla_min is not None and r["freshness_delay_min"] > sla_min:
        reasons.append("sla_breach")

    return Verdict(alert=bool(reasons), pillar="contracts", reason=",".join(reasons))


def check_lineage_run(payload, ctx):
    r = ctx.tools.lineage_graph_slice(payload["run_id"])
    if "error" in r:
        return Verdict(alert=False, pillar="lineage", reason=r["error"])

    reasons = []

    # payload["inputs"] is the job's static declared config, not its runtime
    # join set (e.g. a join pulls in an upstream table no static config
    # lists), so diffing against it produces no signal - confirmed by
    # inspecting real practice-phase payloads. Instead, learn each job's
    # normal upstream set online (majority vote across the run) and flag
    # runs whose actual_upstream is missing something the consensus has.
    job = payload.get("job", "")
    upstream_key = tuple(sorted(r.get("actual_upstream", [])))
    hist = ctx.state.setdefault("_upstream_hist", {}).setdefault(job, {})
    if hist:
        consensus = max(hist, key=hist.get)
        if set(upstream_key) < set(consensus):
            reasons.append("missing_upstream")
    hist[upstream_key] = hist.get(upstream_key, 0) + 1

    if payload.get("outputs") and r.get("actual_downstream_count", 0) == 0:
        reasons.append("orphan_output")

    if _bound_hit(r["duration_ms"], ctx.baseline["lineage_duration_ms_max"]):
        reasons.append("runtime_anomaly")

    return Verdict(alert=bool(reasons), pillar="lineage", reason=",".join(reasons))


def check_feature_materialization(payload, ctx):
    r = ctx.tools.feature_drift(payload["feature_view"], payload["batch_id"])
    if "error" in r:
        return Verdict(alert=False, pillar="ai_infra", reason=r["error"])

    # feature_drift already returns mean_shift_sigma as a normalized z-score,
    # so no extra scaling is needed before comparing it to the baseline.
    hit = _bound_hit(r["mean_shift_sigma"], ctx.baseline["feature_mean_shift_sigma_max"])
    return Verdict(alert=hit, pillar="ai_infra", reason="feature_skew" if hit else "")


def check_embedding_batch(payload, ctx):
    r = ctx.tools.embedding_drift(payload["corpus"], payload["chunk_batch_id"])
    if "error" in r:
        return Verdict(alert=False, pillar="ai_infra", reason=r["error"])

    b = ctx.baseline
    reasons = []
    if _bound_hit(r["centroid_shift"], b["embedding_centroid_shift_max"]):
        reasons.append("embedding_drift")
    if _bound_hit(r["avg_doc_age_days"], b["corpus_avg_doc_age_days_max"]):
        reasons.append("corpus_staleness")

    return Verdict(alert=bool(reasons), pillar="ai_infra", reason=",".join(reasons))
