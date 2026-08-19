"""Slack chat_id normalization.

Slack's API wants a bare channel id (`C…`). Targets are normally exactly that,
but a persisted Inbox binding written by an older build can still carry a
team-qualified `"{team_id}/{channel}"` form, so outbound sends normalize through
`split` before hitting the API.

Encoding note: the reply-target grammar is colon-delimited
(`platform:chat_id[:thread]`, see base.parse_target), which is why the legacy
qualified form joined team+channel with a colon-free `/`.
"""

from __future__ import annotations

from typing import Optional


def split(chat_id: str) -> tuple[Optional[str], str]:
    """`'T…/C…' -> ('T…', 'C…')`; a bare `'C…' -> (None, 'C…')`.

    Only the first `/` splits (channel ids never contain one), so this is
    lossless both ways.
    """
    if chat_id and "/" in chat_id:
        team, _, channel = chat_id.partition("/")
        return (team or None), channel
    return None, chat_id
