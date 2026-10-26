import httpx

from app.services.feishu import FeishuPush


class FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad response", request=None, response=None)


def test_feishu_push_sends_text_payload():
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()

    status = FeishuPush("https://feishu.example/hook", post=post).send("# Digest")

    assert status == "sent"
    assert calls[0][0] == "https://feishu.example/hook"
    assert calls[0][1]["json"] == {
        "msg_type": "text",
        "content": {"text": "# Digest"},
    }
    assert calls[0][1]["timeout"] == 10


def test_feishu_push_skips_when_webhook_is_not_configured():
    status = FeishuPush("", post=lambda *_args, **_kwargs: None).send("Digest")

    assert status == "skipped"


def test_feishu_push_returns_failed_on_http_error():
    status = FeishuPush(
        "https://feishu.example/hook",
        post=lambda *_args, **_kwargs: FakeResponse(500),
    ).send("Digest")

    assert status == "failed"

