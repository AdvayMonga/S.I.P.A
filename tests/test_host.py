from mcp import types

from bot.host import _to_content


def test_all_text_returns_string() -> None:
    blocks = [
        types.TextContent(type="text", text="he"),
        types.TextContent(type="text", text="llo"),
    ]
    assert _to_content(blocks) == "hello"


def test_empty_is_empty_string() -> None:
    assert _to_content([]) == ""


def test_image_yields_anthropic_blocks() -> None:
    blocks = [
        types.TextContent(type="text", text="see:"),
        types.ImageContent(type="image", data="QkFTRTY0", mimeType="image/png"),
    ]
    assert _to_content(blocks) == [
        {"type": "text", "text": "see:"},
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": "QkFTRTY0"},
        },
    ]
