import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from personal_agent_memory.services.memory.diary_preparation import (
    preparation_metadata,
    prepare_diary,
    split_evidence,
)


def source(body, role="user", key="note"):
    return {"id": key, "body": body, "role": role}


def classifier(**kwargs):
    blocks = json.loads(kwargs["user_prompt"])["blocks"]
    return json.dumps(
        {
            "blocks": [
                {"id": b["id"], "kinds": ["thought", "intention"], "disposition": "keep"}
                for b in blocks
            ]
        }
    )


async def run(sources, *, reply_context=None, response=classifier, budget=10000):
    provider = SimpleNamespace(
        summarize=AsyncMock(side_effect=response)
        if callable(response) or isinstance(response, Exception)
        else AsyncMock(return_value=response)
    )
    result = await prepare_diary(
        sources,
        summary_factory=lambda: provider,
        source_max_chars=budget,
        reply_context=reply_context,
    )
    return result, provider


@pytest.mark.anyio
async def test_preserves_caveats_negation_and_preference_verbatim():
    body = "喜歡這個 framework。\n\n出處未確認，Connection 是推定。\n未提交申請。"
    result, provider = await run([source(body)])
    assert body in result["body"]
    assert "試圖實踐" not in result["body"] and "無法提交" not in result["body"]
    report = result["sources"][0]
    assert report["validation"] == "structure_valid"
    assert report["blocks"][0]["kinds"] == ["intention", "thought"]
    assert result["semantic_validation"] == "not_performed"
    assert "text" not in preparation_metadata(result)["sources"][0]["blocks"][0]
    provider.summarize.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "raw",
    [
        "invented diary",
        '{"blocks":[]}',
        '{"blocks":[{"id":"foreign","kinds":[],"disposition":"keep"}]}',
        '{"blocks":[{"id":"b0","kinds":[],"disposition":"invent"}]}',
    ],
)
async def test_invalid_model_plan_falls_back_without_loss(raw):
    result, _ = await run([source("不能當成確切引文。")], response=raw)
    assert "不能當成確切引文。" in result["body"]
    assert result["sources"][0]["validation"] == "fallback_invalid_plan"


@pytest.mark.anyio
async def test_omit_suggestion_cannot_delete_qualifications():
    raw = '{"blocks":[{"id":"b0","kinds":[],"disposition":"omit"}]}'
    result, _ = await run([source("來源未確認。")], response=raw)
    assert "來源未確認。" in result["body"]
    assert result["sources"][0]["blocks"][0]["omit_overridden"]


@pytest.mark.anyio
async def test_budget_and_provider_failure_do_not_truncate():
    item = source("來源未確認。" * 50)
    result, provider = await run([item], budget=1)
    assert item["body"] in result["body"]
    assert result["sources"][0]["validation"] == "fallback_source_budget"
    provider.summarize.assert_not_awaited()
    result, _ = await run([item], response=RuntimeError("no provider"))
    assert result["sources"][0]["validation"] == "fallback_provider_error"


def test_offsets_receipts_and_explicit_role():
    receipt = "已寫入個人MEMORY.md（Preferences）＋ second-brain MCP。"
    item = source("User:\n喜歡框架，但出處未知。\n\nAssistant:\n" + receipt, "mixed")
    blocks, excluded = split_evidence(item)
    assert len(blocks) == 1 and blocks[0].role == "user" and len(excluded) == 1
    for b in blocks:
        assert item["body"][b.start : b.end] == b.text
    quoted = source("User:\nquote\n\nAssistant:\n" + receipt, "user")
    assert split_evidence(quoted)[0][0].text == quoted["body"]


@pytest.mark.anyio
async def test_no_content_skips_model_and_unrelated_context_is_not_sent():
    result, provider = await run([source("已寫入 second-brain MCP。", "assistant")])
    assert not result["body"]
    provider.summarize.assert_not_awaited()
    child = {**source("好，就這樣做。"), "reply_to_ids": ["parent"]}
    parent = source("建議 A。", "assistant", "parent")
    unrelated = source("unrelated secret", "user", "other")
    result, provider = await run([child], reply_context=[parent, unrelated])
    prompt = provider.summarize.call_args.kwargs["user_prompt"]
    assert "建議 A。" in prompt and "unrelated secret" not in prompt
    assert "建議 A。" not in result["body"]
    assert result["sources"][0]["reply_context_ids"] == ["parent"]


def test_trailing_save_request_excluded_without_removing_qualification():
    item = source("喜歡這個框架。Connection 是推定。幫我寫到 memory system。")
    blocks, excluded = split_evidence(item)
    assert blocks[0].text == "喜歡這個框架。Connection 是推定。"
    assert item["body"][excluded[0]["start"] : excluded[0]["end"]] == "幫我寫到 memory system。"


@pytest.mark.anyio
async def test_work_report_is_shortened_but_original_evidence_remains():
    item = {
        **source("User:\n修好職缺匯入。\n\nAssistant:\n已修好，未提交申請。", "mixed"),
        "ingest_reason": "task_completed",
    }
    responses = iter(
        [
            json.dumps(
                {
                    "presentation": "work_report",
                    "blocks": [
                        {"id": "b0", "kinds": ["intention"], "disposition": "keep"},
                        {"id": "b1", "kinds": ["event"], "disposition": "keep"},
                    ],
                }
            ),
            json.dumps({"summary": "修復職缺匯入，尚未提交申請。", "block_ids": ["b0", "b1"]}),
            json.dumps({"supported": True, "preserves_scope": True}),
        ]
    )
    result, provider = await run([item], response=lambda **_: next(responses))
    assert result["body"] == "修復職缺匯入，尚未提交申請。"
    assert result["semantic_validation"] == "model_review_only"
    assert result["sources"][0]["compression"]["status"] == "model_reviewed"
    assert result["sources"][0]["blocks"][1]["text"] == "已修好，未提交申請。"
    assert provider.summarize.await_count == 3


@pytest.mark.anyio
@pytest.mark.parametrize(
    "candidate,review,expected",
    [
        (
            {"summary": "已提交申請。", "block_ids": ["b0"]},
            {"supported": False, "preserves_scope": False},
            "fallback_review_rejected",
        ),
        ({"summary": "已修好。", "block_ids": ["foreign"]}, None, "fallback_invalid_summary"),
        ({"summary": "完成" * 200, "block_ids": ["b0"]}, None, "fallback_invalid_summary"),
        (
            {"summary": "已修好。", "block_ids": ["b0"]},
            {"supported": "true", "preserves_scope": "true"},
            "fallback_invalid_summary",
        ),
    ],
)
async def test_bad_work_summary_falls_back(candidate, review, expected):
    item = {**source("已修好，尚未提交申請。", "assistant"), "ingest_reason": "task_completed"}
    responses = iter(
        [
            json.dumps(
                {
                    "presentation": "work_report",
                    "blocks": [{"id": "b0", "kinds": ["event"], "disposition": "keep"}],
                }
            ),
            json.dumps(candidate),
            json.dumps(review),
        ]
    )
    result, _ = await run([item], response=lambda **_: next(responses))
    assert item["body"] in result["body"]
    assert result["sources"][0]["compression"]["status"] == expected


@pytest.mark.anyio
async def test_personal_ingest_reason_blocks_accidental_work_compression():
    item = {**source("喜歡框架，但出處未知。"), "ingest_reason": "user_preference"}
    response = json.dumps(
        {
            "presentation": "work_report",
            "blocks": [{"id": "b0", "kinds": ["thought"], "disposition": "keep"}],
        }
    )
    result, provider = await run([item], response=response)
    assert item["body"] in result["body"]
    assert result["sources"][0]["compression"]["status"] == "not_requested"
    provider.summarize.assert_awaited_once()


@pytest.mark.anyio
async def test_unknown_kind_is_visible_but_not_used_as_a_category():
    raw = json.dumps(
        {
            "presentation": "verbatim",
            "blocks": [{"id": "b0", "kinds": ["thought", "explanation"], "disposition": "keep"}],
        }
    )
    result, _ = await run([source("Connection 是推定。")], response=raw)
    block = result["sources"][0]["blocks"][0]
    assert block["kinds"] == ["thought"]
    assert block["unrecognized_kinds"] == ["explanation"]
    assert "Connection 是推定。" in result["body"]


@pytest.mark.anyio
async def test_work_summary_may_cite_only_result_block():
    item = source("User:\n修好問題。\n\nAssistant:\n已修好，未部署。", "mixed")
    responses = iter(
        [
            json.dumps(
                {
                    "presentation": "work_report",
                    "blocks": [
                        {"id": "b0", "kinds": ["intention"], "disposition": "keep"},
                        {"id": "b1", "kinds": ["event"], "disposition": "keep"},
                    ],
                }
            ),
            json.dumps({"summary": "已修復問題，尚未部署。", "block_ids": ["b1"]}),
            json.dumps({"supported": True, "preserves_scope": True}),
        ]
    )
    result, _ = await run([item], response=lambda **_: next(responses))
    assert result["body"] == "已修復問題，尚未部署。"
    assert len(result["sources"][0]["blocks"]) == 2


@pytest.mark.anyio
async def test_scope_is_kept_even_when_model_omits_it_and_reviewer_agrees():
    item = source(
        "Imported Pinterest job. No application submitted or fit evaluation performed.", "assistant"
    )
    responses = iter(
        [
            json.dumps(
                {
                    "presentation": "work_report",
                    "blocks": [{"id": "b0", "kinds": ["event"], "disposition": "keep"}],
                }
            ),
            json.dumps({"summary": "已匯入 Pinterest 職缺。", "block_ids": ["b0"]}),
            json.dumps({"supported": True, "preserves_scope": True}),
        ]
    )
    result, _ = await run([item], response=lambda **_: next(responses))
    assert result["body"] == (
        "已匯入 Pinterest 職缺。\nNo application submitted or fit evaluation performed."
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "text", ["Job 7838591 imported.", "匯入 job 7838591。", "修改 tools/capture.py 完成。"]
)
async def test_detailed_work_summary_falls_back(text):
    item = source("Imported job 7838591 using tools/capture.py.", "assistant")
    responses = iter(
        [
            json.dumps(
                {
                    "presentation": "work_report",
                    "blocks": [{"id": "b0", "kinds": ["event"], "disposition": "keep"}],
                }
            ),
            json.dumps({"summary": text, "block_ids": ["b0"]}),
        ]
    )
    result, provider = await run([item], response=lambda **_: next(responses))
    assert result["sources"][0]["compression"]["status"] == "fallback_presentation"
    assert item["body"] in result["body"]
    assert provider.summarize.await_count == 2


@pytest.mark.anyio
async def test_long_summary_gets_one_repair_and_program_binds_evidence():
    responses = iter(
        [
            json.dumps(
                {
                    "presentation": "work_report",
                    "blocks": [{"id": "b0", "kinds": ["event"], "disposition": "keep"}],
                }
            ),
            json.dumps({"summary": "技術細節" * 100}),
            json.dumps({"summary": "完成職缺匯入修復。"}),
            json.dumps({"supported": True, "preserves_scope": True}),
        ]
    )
    result, provider = await run(
        [source("已修復職缺匯入。", "assistant")], response=lambda **_: next(responses)
    )
    assert result["body"] == "完成職缺匯入修復。"
    assert result["sources"][0]["compression"]["block_ids"] == ["b0"]
    assert provider.summarize.await_count == 4
