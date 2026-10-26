from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx


class FeishuPush:
    def __init__(self, webhook_url: str, post: Callable[..., Any] | None = None) -> None:
        self.webhook_url = webhook_url.strip()
        self.post = post or httpx.post

    def send(self, content: str) -> str:
        if not self.webhook_url:
            return "skipped"
        try:
            response = self.post(
                self.webhook_url,
                json={"msg_type": "text", "content": {"text": content}},
                timeout=10,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return "failed"
        return "sent"

