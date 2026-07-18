from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class CommunityService:
    CHANNELS = [
        {"channel_id": "polymers", "name": "Polymers", "description": "Film structures, barrier tradeoffs, and recyclability discussion."},
        {"channel_id": "composites", "name": "Composites", "description": "Layered materials, hybrids, and substitution pathways."},
        {"channel_id": "battery-materials", "name": "Battery Materials", "description": "Adjacent materials intelligence for energy storage packaging and components."},
        {"channel_id": "sourcing", "name": "Sourcing", "description": "Supplier risk, lead time, capacity, and qualification signals."},
        {"channel_id": "compliance", "name": "Compliance", "description": "Regulations, declarations, lab evidence, and audit readiness."},
    ]

    def __init__(self, runtime_dir: Path):
        self.path = runtime_dir / "community_posts.json"

    def _read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write(self, records: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(records, handle, indent=2)

    def ensure_seed(self) -> None:
        if self.path.exists():
            return
        self._write(
            [
                {
                    "post_id": "POST-001",
                    "channel_id": "polymers",
                    "title": "Which mono-material snack pouch candidates are actually evidence-ready?",
                    "body": "Film A11 looks operationally strong, but the real difference seems to be documentation coverage and substitute depth rather than only barrier score.",
                    "author_name": "Demo Analyst",
                    "author_role": "Materials Strategist",
                    "author_reputation": 78,
                    "created_at": "2026-07-15T11:20:00",
                    "updated_at": "2026-07-15T14:00:00",
                    "upvotes": 14,
                    "saves": 6,
                    "comment_count": 2,
                    "pinned": True,
                    "moderation_state": "reviewed",
                    "related_entities": [{"type": "material", "id": "MAT-001", "label": "Film A11"}],
                    "source_refs": ["Film A11 synthetic datasheet", "Migration review summary"],
                    "moderation_note": "Frame claims with source context when possible.",
                    "comments": [
                        {"comment_id": "COM-001", "author": "Compliance Lead", "author_role": "Compliance Lead", "body": "The declaration gap matters more once you compare it against supplier readiness.", "created_at": "2026-07-15T13:05:00"},
                        {"comment_id": "COM-002", "author": "Demo Analyst", "author_role": "Materials Strategist", "body": "Agreed. The chat result looked strong, but Workbench exposed the documentation difference.", "created_at": "2026-07-15T14:00:00"},
                    ],
                },
                {
                    "post_id": "POST-002",
                    "channel_id": "sourcing",
                    "title": "Lead-time drift is making supplier backup logic more important",
                    "body": "The last few quarter snapshots suggest teams should keep substitute pathways closer to the decision surface during sourcing reviews.",
                    "author_name": "Compliance Lead",
                    "author_role": "Compliance Lead",
                    "author_reputation": 83,
                    "created_at": "2026-07-13T09:40:00",
                    "updated_at": "2026-07-13T10:12:00",
                    "upvotes": 11,
                    "saves": 5,
                    "comment_count": 1,
                    "pinned": False,
                    "moderation_state": "reviewed",
                    "related_entities": [{"type": "supplier", "id": "SUP-008", "label": "FiberMint Industrial"}],
                    "source_refs": ["Quarterly supplier snapshot", "Risk trend excerpt"],
                    "moderation_note": "Keep supplier-specific claims tied to a timeframe.",
                    "comments": [
                        {"comment_id": "COM-003", "author": "Demo Analyst", "author_role": "Materials Strategist", "body": "This is where a scenario run becomes useful before the shortlist gets finalized.", "created_at": "2026-07-13T10:12:00"},
                    ],
                },
                {
                    "post_id": "POST-003",
                    "channel_id": "compliance",
                    "title": "Post-consumer content guidance is changing when teams start reformulation",
                    "body": "Instead of waiting for final activation, some teams are using regulation signals to narrow substitutes earlier in the cycle.",
                    "author_name": "Demo Analyst",
                    "author_role": "Materials Strategist",
                    "author_reputation": 78,
                    "created_at": "2026-07-10T16:30:00",
                    "updated_at": "2026-07-10T18:05:00",
                    "upvotes": 17,
                    "saves": 9,
                    "comment_count": 1,
                    "pinned": False,
                    "moderation_state": "reviewed",
                    "related_entities": [{"type": "regulation", "id": "REGU-003", "label": "Post-consumer content mandate"}],
                    "source_refs": ["Regulatory watch note", "Scenario comparison snapshot"],
                    "moderation_note": "Separate confirmed policy language from team interpretation.",
                    "comments": [
                        {"comment_id": "COM-004", "author": "Compliance Lead", "author_role": "Compliance Lead", "body": "This is a good example of why evidence gaps should sit next to regulation detail.", "created_at": "2026-07-10T18:05:00"},
                    ],
                },
            ]
        )

    def list_channels(self) -> list[dict[str, Any]]:
        posts = self._read()
        counts = {item["channel_id"]: 0 for item in self.CHANNELS}
        last_activity = {item["channel_id"]: "" for item in self.CHANNELS}
        for post in posts:
            counts[post["channel_id"]] = counts.get(post["channel_id"], 0) + 1
            last_activity[post["channel_id"]] = max(last_activity.get(post["channel_id"], ""), post.get("updated_at", post.get("created_at", "")))
        return [{**channel, "post_count": counts.get(channel["channel_id"], 0), "last_activity": last_activity.get(channel["channel_id"], "")} for channel in self.CHANNELS]

    def list_posts(
        self,
        channel_id: str | None = None,
        moderation_state: str | None = None,
        related_entity_id: str | None = None,
    ) -> list[dict[str, Any]]:
        posts = self._read()
        if channel_id:
            posts = [item for item in posts if item["channel_id"] == channel_id]
        if moderation_state:
            posts = [item for item in posts if item.get("moderation_state") == moderation_state]
        if related_entity_id:
            posts = [item for item in posts if any(entity.get("id") == related_entity_id for entity in item.get("related_entities", []))]
        return sorted(posts, key=lambda item: (not item.get("pinned", False), item.get("updated_at", item.get("created_at", ""))), reverse=False)

    def get_post(self, post_id: str) -> dict[str, Any] | None:
        return next((item for item in self._read() if item["post_id"] == post_id), None)

    def create_post(self, payload: dict[str, Any], author_name: str, author_role: str = "Explorer", author_reputation: int = 60) -> dict[str, Any]:
        posts = self._read()
        now = datetime.now().isoformat(timespec="seconds")
        record = {
            "post_id": f"POST-{len(posts) + 1:03d}",
            "author_name": author_name,
            "author_role": author_role,
            "author_reputation": author_reputation,
            "created_at": now,
            "updated_at": now,
            "upvotes": 0,
            "saves": 0,
            "comment_count": 0,
            "pinned": False,
            "moderation_state": "pending",
            "related_entities": (
                [{"type": "material", "id": payload["related_material_id"], "label": payload["related_material_id"]}]
                if payload.get("related_material_id")
                else []
            ),
            "source_refs": [payload["source_reference"]] if payload.get("source_reference") else [],
            "moderation_note": "Keep demo posts specific, source-aware, and useful for future readers.",
            "comments": [],
            **payload,
        }
        posts.append(record)
        self._write(posts)
        return record

    def upvote(self, post_id: str) -> dict[str, Any] | None:
        posts = self._read()
        updated = None
        for post in posts:
            if post["post_id"] == post_id:
                post["upvotes"] = int(post.get("upvotes", 0)) + 1
                updated = post
                break
        if updated is None:
            return None
        self._write(posts)
        return updated

    def save_post(self, post_id: str) -> dict[str, Any] | None:
        posts = self._read()
        updated = None
        for post in posts:
            if post["post_id"] == post_id:
                post["saves"] = int(post.get("saves", 0)) + 1
                updated = post
                break
        if updated is None:
            return None
        self._write(posts)
        return updated

    def add_reply(self, post_id: str, body: str, author_name: str, author_role: str = "Explorer") -> dict[str, Any] | None:
        posts = self._read()
        updated = None
        for post in posts:
            if post["post_id"] != post_id:
                continue
            comments = post.setdefault("comments", [])
            comments.append(
                {
                    "comment_id": f"COM-{len(comments) + 1:03d}",
                    "author": author_name,
                    "author_role": author_role,
                    "body": body,
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
            post["comment_count"] = len(comments)
            post["updated_at"] = datetime.now().isoformat(timespec="seconds")
            updated = post
            break
        if updated is None:
            return None
        self._write(posts)
        return updated

    def moderate(self, post_id: str, state_value: str) -> dict[str, Any] | None:
        posts = self._read()
        updated = None
        for post in posts:
            if post["post_id"] != post_id:
                continue
            post["moderation_state"] = state_value
            post["updated_at"] = datetime.now().isoformat(timespec="seconds")
            updated = post
            break
        if updated is None:
            return None
        self._write(posts)
        return updated

    def pin(self, post_id: str) -> dict[str, Any] | None:
        posts = self._read()
        updated = None
        for post in posts:
            if post["post_id"] != post_id:
                continue
            post["pinned"] = not bool(post.get("pinned"))
            post["updated_at"] = datetime.now().isoformat(timespec="seconds")
            updated = post
            break
        if updated is None:
            return None
        self._write(posts)
        return updated
