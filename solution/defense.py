"""
Your defense. Implement register(ctx) and a handler per event type.
See ../README.md for the full interface + toolkit reference, and
../RULES.md before you start.
"""
from api import Verdict


def register(ctx):
    ctx.on("data_batch", check_data_batch)
    ctx.on("contract_checkpoint", check_contract_checkpoint)
    ctx.on("lineage_run", check_lineage_run)
    ctx.on("feature_materialization", check_feature_materialization)
    ctx.on("embedding_batch", check_embedding_batch)


def check_data_batch(payload, ctx):
    # TODO: call ctx.tools.batch_profile(payload["batch_id"]) and compare
    # against ctx.baseline's row_count/null_rate/mean_amount/staleness bounds.
    return Verdict(alert=False, pillar="checks")


def check_contract_checkpoint(payload, ctx):
    # TODO: ctx.tools.contract_diff(payload["contract_id"], payload["checkpoint_batch_id"])
    return Verdict(alert=False, pillar="contracts")


def check_lineage_run(payload, ctx):
    # TODO: ctx.tools.lineage_graph_slice(payload["run_id"])
    return Verdict(alert=False, pillar="lineage")


def check_feature_materialization(payload, ctx):
    # TODO: ctx.tools.feature_drift(payload["feature_view"], payload["batch_id"])
    return Verdict(alert=False, pillar="ai_infra")


def check_embedding_batch(payload, ctx):
    # TODO: ctx.tools.embedding_drift(payload["corpus"], payload["chunk_batch_id"])
    return Verdict(alert=False, pillar="ai_infra")
