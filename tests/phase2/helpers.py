from __future__ import annotations

RAW_NORMAL = (
    '{"request_type":"ACTION","behavior":"MOVE",'
    '"target":"ZONE_B","speed":"NORMAL"}'
)

PROMPT_VERSION = "phase2_action_proposal_v1"
RUN_TIME = "2026-08-28T10:00:00+09:00"


def model_info():
    # Delayed import keeps adapter-only tests independent of later components.
    from phase2.provenance import ModelInfo

    return ModelInfo(
        provider="local",
        model_name="class-a-fixture",
        runtime="deterministic-fixture",
        runtime_version="P2.0",
        sampling_parameters={"temperature": 0},
        artifact_identifier=None,
    )
