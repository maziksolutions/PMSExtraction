import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.extractor import (
    _explain_zero_extraction,
    _extract_reason_from_raw_text,
    ExtractionResult,
    _parse_json_records,
)

@pytest.mark.asyncio
async def test_explain_zero_extraction_with_mocked_claude():
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text='Page contains an exploded diagram without part callouts or bill of materials table.')]

    with patch("app.core.config.settings.ANTHROPIC_API_KEY", "mock-key"), \
         patch("app.services.extractor.is_claude_vision_billing_tripped", return_value=False), \
         patch("anthropic.AsyncAnthropic") as mock_anthropic:
        
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_msg)
        mock_anthropic.return_value = mock_client

        reason = await _explain_zero_extraction(
            image_bytes=b"fake-image-bytes",
            filename="Test_PV_Manual.pdf",
            page_no=58,
            extraction_type="spare",
        )

        assert "diagram" in reason.lower()
        assert "bill of materials" in reason.lower()


@pytest.mark.asyncio
async def test_explain_zero_extraction_fallback_openai():
    mock_choice = MagicMock()
    mock_choice.message.content = "Page outlines operating procedures with no maintenance intervals."
    mock_res = MagicMock(choices=[mock_choice])

    with patch("app.core.config.settings.ANTHROPIC_API_KEY", ""), \
         patch("app.core.config.settings.OPENAI_API_KEY", "mock-openai-key"), \
         patch("openai.AsyncOpenAI") as mock_openai:

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_res)
        mock_openai.return_value = mock_client

        reason = await _explain_zero_extraction(
            text_content="General operating instructions chunk...",
            filename="Test_Manual.pdf",
            page_no=12,
            extraction_type="job",
        )

        assert "operating procedures" in reason.lower()


@pytest.mark.asyncio
async def test_explain_zero_extraction_default_when_no_keys():
    with patch("app.core.config.settings.ANTHROPIC_API_KEY", ""), \
         patch("app.core.config.settings.OPENAI_API_KEY", ""):

        reason = await _explain_zero_extraction(
            filename="Test_Manual.pdf",
            page_no=5,
            extraction_type="component",
        )

        assert "No structured component" in reason


def test_extract_reason_from_prompt_json():
    # Model returns JSON with no_extraction_reason
    raw_json = '{"records": [], "no_extraction_reason": "Page 98 contains dimensional schematics with no spare parts list."}'
    records = _parse_json_records(raw_json, "manual.pdf", "spare")
    assert records == []

    reason = _extract_reason_from_raw_text(raw_json)
    assert reason == "Page 98 contains dimensional schematics with no spare parts list."

    res_obj = ExtractionResult([], reason=reason)
    assert len(res_obj) == 0
    assert bool(res_obj) is False
    assert res_obj.no_extraction_reason == reason
