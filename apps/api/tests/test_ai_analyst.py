"""Synthetic, no-network tests for grounded AI behavior and privacy."""

import json
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from app.ai.grounding import GroundingError, validate_answer
from app.ai.provider import OpenAIProvider, ProviderAnswer, ProviderCall, ProviderTurn
from app.ai.tools import FactRegistry, ToolError, tool_schemas, validate_args
from app.models.tables import AiRun, AiToolCall, PlayerCoach
from app.services.jobs import process_next_job
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_phase2_api import OTHER, OWNER, _auth, _upload

pytest_plugins = ("test_phase2_api",)


@dataclass
class FakeProvider:
    provider_name: str = "fake"
    calls: tuple[ProviderCall, ...] = ()
    invalid_first: bool = False
    select_count: int = 0
    answer_count: int = 0

    def select(self, question: str, context: list[str], tools: list[dict]) -> ProviderTurn:
        self.select_count += 1
        assert question
        assert all(tool["parameters"]["additionalProperties"] is False for tool in tools)
        return ProviderTurn(self.calls, (), 11, 7)

    def answer(
        self,
        question: str,
        turn: ProviderTurn,
        tool_results: list[tuple[str, str]],
        evidence: dict,
        feedback: str | None = None,
    ) -> ProviderAnswer:
        self.answer_count += 1
        facts = evidence["facts"]
        if self.invalid_first and self.answer_count == 1:
            return ProviderAnswer(
                {
                    "status": "answered",
                    "sentences": [{"text": "Speed was 99 km/h.", "fact_ids": ["FAKE"], "session_ids": []}],
                }
            )
        if not facts:
            return ProviderAnswer(
                {
                    "status": "insufficient_data",
                    "sentences": [
                        {
                            "text": "There is not enough accepted history to answer this yet.",
                            "fact_ids": [],
                            "session_ids": [],
                        }
                    ],
                },
                5,
                3,
            )
        return ProviderAnswer(
            {
                "status": "answered",
                "sentences": [
                    {
                        "text": "The confirmed metric is available from your session.",
                        "fact_ids": [facts[0]["fact_id"]],
                        "session_ids": [facts[0]["source_session_ids"][0]],
                    }
                ],
            },
            5,
            3,
        )


def _player(client: TestClient) -> str:
    response = client.post("/v1/players", headers=_auth(), json={"display_name": "Synthetic Player"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_tool_contracts_are_closed_and_bounded() -> None:
    for tool in tool_schemas():
        assert set(tool["parameters"]["required"]) == set(tool["parameters"]["properties"])
        assert tool["strict"] is True
    with pytest.raises(ToolError, match="unknown_tool"):
        validate_args("run_sql", "{}")
    with pytest.raises(ToolError, match="invalid_tool_arguments"):
        validate_args("get_last_speed_exceedance", '{"threshold_kmh":"30","player_id":"another"}')
    with pytest.raises(ToolError, match="invalid_tool_arguments"):
        validate_args(
            "get_latest_session_comparison",
            '{"metric_key":"maximum_velocity_kmh","session_type":"training","previous_count":20}',
        )


def test_responses_provider_preserves_tool_chain_and_disables_storage() -> None:
    provider = OpenAIProvider(key="synthetic-test-key", model="gpt-6-luna", timeout_seconds=5, max_tool_calls=3)
    call = SimpleNamespace(type="function_call", call_id="call_1", name="get_personal_records", arguments="{}")
    response = SimpleNamespace(output=(call,), usage=SimpleNamespace(input_tokens=12, output_tokens=4))
    final = SimpleNamespace(
        output_text=json.dumps(
            {
                "status": "insufficient_data",
                "sentences": [{"text": "No accepted history is available.", "fact_ids": [], "session_ids": []}],
            }
        ),
        usage=SimpleNamespace(input_tokens=16, output_tokens=6),
    )
    create = Mock(side_effect=(response, final))
    provider.client.responses.create = create
    turn = provider.select("What is my record?", [], [])
    answer = provider.answer("What is my record?", turn, [("call_1", '{"items":[]}')], {"facts": []})
    assert turn.calls[0].name == "get_personal_records"
    assert turn.input_tokens == 12 and answer.output_tokens == 6
    assert create.call_args_list[0].kwargs["store"] is False
    assert create.call_args_list[0].kwargs["max_tool_calls"] == 3
    second = create.call_args_list[1].kwargs
    assert second["store"] is False
    assert second["input"][0]["content"] == turn.input_prompt
    assert second["input"][1] is call
    assert second["input"][2] == {"type": "function_call_output", "call_id": "call_1", "output": '{"items":[]}'}
    assert answer.payload["status"] == "insufficient_data"


def test_grounding_rejects_fabricated_numbers_and_citations() -> None:
    registry = FactRegistry(4)
    with pytest.raises(GroundingError, match="model_authored_number"):
        validate_answer(
            {"status": "answered", "sentences": [{"text": "You ran 99 km/h.", "fact_ids": [], "session_ids": []}]},
            registry,
        )
    with pytest.raises(GroundingError, match="unknown_fact_id"):
        validate_answer(
            {
                "status": "answered",
                "sentences": [{"text": "Your speed is available.", "fact_ids": ["FAKE"], "session_ids": []}],
            },
            registry,
        )
    with pytest.raises(GroundingError, match="medical_claim"):
        validate_answer(
            {
                "status": "insufficient_data",
                "sentences": [{"text": "You have an injury risk.", "fact_ids": [], "session_ids": []}],
            },
            registry,
        )
    with pytest.raises(GroundingError, match="unsupported_change_claim"):
        validate_answer(
            {
                "status": "insufficient_data",
                "sentences": [{"text": "Your speed increased.", "fact_ids": [], "session_ids": []}],
            },
            registry,
        )


def test_chat_uses_fake_provider_audits_and_is_idempotent(phase2) -> None:
    client, database, _, _ = phase2
    player_id = _player(client)
    fake = FakeProvider(
        calls=(
            ProviderCall(
                "call_rec", "get_personal_records", '{"metric_key":"maximum_velocity_kmh","session_type":null}'
            ),
        )
    )
    client.app.state.ai_provider = fake
    thread = client.post(f"/v1/players/{player_id}/chats", headers=_auth(), json={"title": "Speed history"})
    assert thread.status_code == 201, thread.text
    thread_id = thread.json()["id"]
    route = f"/v1/players/{player_id}/chats/{thread_id}/messages"
    request_id = str(uuid4())
    first = client.post(route, headers=_auth(), json={"question": "What is my top speed?", "request_id": request_id})
    assert first.status_code == 200, first.text
    assert first.json()["answer"]["status"] == "insufficient_data"
    assert first.json()["analytics_rule_version"] == "analytics_v1"
    assert first.json()["facts"] == []
    again = client.post(route, headers=_auth(), json={"question": "What is my top speed?", "request_id": request_id})
    assert again.status_code == 200
    assert again.json()["run_id"] == first.json()["run_id"]
    assert fake.select_count == 1
    conflict = client.post(route, headers=_auth(), json={"question": "A different question", "request_id": request_id})
    assert conflict.status_code == 409
    messages = client.get(route, headers=_auth()).json()["items"]
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert client.get(route, headers=_auth("other")).status_code == 404
    with database.user_transaction(OWNER) as session:
        run = session.get(AiRun, UUID(first.json()["run_id"]))
        assert run is not None and run.provider == "fake" and run.input_tokens == 16 and run.output_tokens == 10
        calls = session.scalars(select(AiToolCall).where(AiToolCall.ai_run_id == run.id)).all()
        assert len(calls) == 1 and calls[0].status == "ok" and calls[0].result_hash


def test_daily_quota_blocks_new_runs_without_billing(phase2) -> None:
    client, _, _, settings = phase2
    settings.ai_daily_run_limit = 1
    player_id = _player(client)
    fake = FakeProvider()
    client.app.state.ai_provider = fake
    thread_id = client.post(f"/v1/players/{player_id}/chats", headers=_auth(), json={}).json()["id"]
    route = f"/v1/players/{player_id}/chats/{thread_id}/messages"
    first = client.post(route, headers=_auth(), json={"question": "Speed?", "request_id": str(uuid4())})
    assert first.status_code == 200
    second = client.post(route, headers=_auth(), json={"question": "Distance?", "request_id": str(uuid4())})
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "ai_quota_exceeded"
    assert fake.select_count == 1
    assert len(client.get(route, headers=_auth()).json()["items"]) == 2


def test_invalid_answer_retries_then_falls_back(phase2) -> None:
    client, _, _, _ = phase2
    player_id = _player(client)
    fake = FakeProvider(invalid_first=True)
    client.app.state.ai_provider = fake
    thread_id = client.post(f"/v1/players/{player_id}/chats", headers=_auth(), json={}).json()["id"]
    response = client.post(
        f"/v1/players/{player_id}/chats/{thread_id}/messages",
        headers=_auth(),
        json={"question": "How has my speed changed?", "request_id": str(uuid4())},
    )
    assert response.status_code == 200, response.text
    assert response.json()["answer"]["status"] == "insufficient_data"
    assert fake.answer_count == 2


def test_repeated_invalid_answer_returns_unavailable(phase2) -> None:
    client, database, _, _ = phase2
    player_id = _player(client)

    class AlwaysInvalid(FakeProvider):
        def answer(self, *args, **kwargs) -> ProviderAnswer:
            self.answer_count += 1
            return ProviderAnswer(
                {"status": "answered", "sentences": [{"text": "Speed was 99 km/h.", "fact_ids": [], "session_ids": []}]}
            )

    fake = AlwaysInvalid()
    client.app.state.ai_provider = fake
    thread_id = client.post(f"/v1/players/{player_id}/chats", headers=_auth(), json={}).json()["id"]
    response = client.post(
        f"/v1/players/{player_id}/chats/{thread_id}/messages",
        headers=_auth(),
        json={"question": "My speed?", "request_id": str(uuid4())},
    )
    assert response.status_code == 200, response.text
    assert response.json()["answer"]["status"] == "unavailable"
    assert fake.answer_count == 2
    with database.user_transaction(OWNER) as session:
        run = session.get(AiRun, UUID(response.json()["run_id"]))
        assert run is not None and run.error_code == "model_authored_number"


def test_unknown_tool_is_rejected_and_audited(phase2) -> None:
    client, database, _, _ = phase2
    player_id = _player(client)
    client.app.state.ai_provider = FakeProvider(
        calls=(ProviderCall("bad", "run_sql", json.dumps({"query": "SELECT *"})),)
    )
    thread_id = client.post(f"/v1/players/{player_id}/chats", headers=_auth(), json={}).json()["id"]
    response = client.post(
        f"/v1/players/{player_id}/chats/{thread_id}/messages",
        headers=_auth(),
        json={"question": "Show all athletes", "request_id": str(uuid4())},
    )
    assert response.status_code == 200, response.text
    assert response.json()["facts"] == []
    with database.user_transaction(OWNER) as session:
        call = session.scalar(select(AiToolCall).where(AiToolCall.ai_run_id == UUID(response.json()["run_id"])))
        assert call is not None and call.status == "rejected"
        assert call.result_json == {"error": "unknown_tool"}
        assert "query" not in call.arguments_json


def test_confirmed_speed_is_grounded_and_old_answer_becomes_stale(phase2, synthetic_pdf: bytes) -> None:
    client, database, storage, settings = phase2
    player_id = _player(client)
    upload = _upload(client, synthetic_pdf)["upload_id"]
    assert process_next_job(database, storage, settings)
    row_id = client.get(f"/v1/report-uploads/{upload}", headers=_auth()).json()["candidate_rows"][0]["id"]
    link = client.post(
        f"/v1/report-uploads/{upload}/links",
        headers=_auth(),
        json={"player_id": player_id, "source_athlete_row_id": row_id, "session_type": "training"},
    )
    assert link.status_code == 200, link.text
    session_id = link.json()["session_id"]

    def confirm(label: str) -> None:
        url = f"/v1/report-uploads/{upload}/chart-reviews"
        proposed = client.post(
            url,
            headers=_auth(),
            json={"source_athlete_row_id": row_id, "metric_key": "maximum_velocity_kmh", "raw_label": label},
        )
        assert proposed.status_code == 201, proposed.text
        response = client.post(
            f"{url}/{proposed.json()['id']}/confirm",
            headers=_auth(),
            json={"source_athlete_row_id": row_id, "raw_label": label},
        )
        assert response.status_code == 200 and response.json()["status"] == "confirmed"

    confirm("30.4")
    fake = FakeProvider(
        calls=(
            ProviderCall("speed", "get_personal_records", '{"metric_key":"maximum_velocity_kmh","session_type":null}'),
        )
    )
    client.app.state.ai_provider = fake
    thread_id = client.post(f"/v1/players/{player_id}/chats", headers=_auth(), json={}).json()["id"]
    route = f"/v1/players/{player_id}/chats/{thread_id}/messages"
    answer = client.post(
        route, headers=_auth(), json={"question": "What is my highest speed?", "request_id": str(uuid4())}
    )
    assert answer.status_code == 200, answer.text
    with database.user_transaction(OWNER) as debug_session:
        debug_run = debug_session.get(AiRun, UUID(answer.json()["run_id"]))
        assert debug_run is not None
        error_code = debug_run.error_code
    assert answer.json()["answer"]["status"] == "answered", error_code
    assert answer.json()["facts"][0]["raw_value"] == "30.400"
    assert answer.json()["facts"][0]["source_session_ids"] == [session_id]
    assert answer.json()["stale"] is False
    assert client.get(route, headers=_auth("other")).status_code == 404
    session_analysis = client.post(
        f"/v1/players/{player_id}/sessions/{session_id}/analysis",
        headers=_auth(),
        json={"request_id": str(uuid4())},
    )
    assert session_analysis.status_code == 200, session_analysis.text
    assert any(fact["metric_key"] == "maximum_velocity_kmh" for fact in session_analysis.json()["facts"])
    assert (
        client.get(f"/v1/players/{player_id}/sessions/{session_id}/analysis", headers=_auth("other")).status_code == 404
    )
    confirm("30.9")
    saved = client.get(route, headers=_auth()).json()["items"][-1]["analysis"]
    assert saved["stale"] is True
    assert saved["facts"][0]["raw_value"] == "30.400"
    old_session_analysis = client.get(f"/v1/players/{player_id}/sessions/{session_id}/analysis", headers=_auth())
    assert old_session_analysis.status_code == 200 and old_session_analysis.json()["stale"] is True
    refreshed = client.post(
        route, headers=_auth(), json={"question": "What is my highest speed?", "request_id": str(uuid4())}
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["facts"][0]["raw_value"] == "30.900"
    assert refreshed.json()["stale"] is False


def test_coach_chat_is_creator_private_and_revocation_takes_effect(phase2) -> None:
    client, database, _, _ = phase2
    player_id = _player(client)
    with database.user_transaction(OWNER) as session:
        session.add(PlayerCoach(player_id=UUID(player_id), coach_user_id=OTHER))
    coach_thread = client.post(f"/v1/players/{player_id}/chats", headers=_auth("other"), json={})
    assert coach_thread.status_code == 201, coach_thread.text
    thread_id = coach_thread.json()["id"]
    assert client.get(f"/v1/players/{player_id}/chats", headers=_auth()).json()["items"] == []
    assert client.get(f"/v1/players/{player_id}/chats/{thread_id}/messages", headers=_auth()).status_code == 404
    with database.user_transaction(OWNER) as session:
        grant = session.get(PlayerCoach, (UUID(player_id), OTHER))
        assert grant is not None
        from datetime import UTC, datetime

        grant.revoked_at = datetime.now(UTC)
    assert client.get(f"/v1/players/{player_id}/chats", headers=_auth("other")).status_code == 404
