"""Window selection shared by window tools, waits and expectations."""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pc_control.core.errors import ErrorCode, ToolError
from pc_control.platform.base import WindowInfo


class WindowQuery(BaseModel):
    """Criteria to select windows. All given fields must match (AND)."""

    model_config = ConfigDict(extra="forbid")

    hwnd: Annotated[int | None, Field(description="Exact window handle.")] = None
    title: Annotated[str | None, Field(description="Exact title (case-insensitive).")] = None
    title_contains: Annotated[str | None, Field(description="Substring of the title (case-insensitive).")] = None
    title_regex: Annotated[str | None, Field(description="Python regex searched in the title.")] = None
    process: Annotated[str | None, Field(description="Process executable name, e.g. 'notepad.exe'.")] = None
    pid: int | None = None
    class_name: str | None = None

    @model_validator(mode="after")
    def _check(self) -> WindowQuery:
        if not any(v is not None for v in self.model_dump().values()):
            raise ValueError("window query needs at least one criterion")
        if self.title_regex is not None:
            try:
                re.compile(self.title_regex)
            except re.error as e:
                raise ValueError(f"invalid title_regex: {e}") from e
        return self

    def matches(self, w: WindowInfo) -> bool:
        if self.hwnd is not None and w.hwnd != self.hwnd:
            return False
        if self.title is not None and w.title.casefold() != self.title.casefold():
            return False
        if self.title_contains is not None and self.title_contains.casefold() not in w.title.casefold():
            return False
        if self.title_regex is not None and not re.search(self.title_regex, w.title):
            return False
        if self.process is not None and w.process.casefold() != self.process.casefold():
            return False
        if self.pid is not None and w.pid != self.pid:
            return False
        return not (self.class_name is not None and w.class_name != self.class_name)

    def describe(self) -> str:
        return ", ".join(f"{k}={v!r}" for k, v in self.model_dump(exclude_none=True).items())


def filter_windows(windows: list[WindowInfo], query: WindowQuery) -> list[WindowInfo]:
    return [w for w in windows if query.matches(w)]


def resolve_one(windows: list[WindowInfo], query: WindowQuery) -> WindowInfo:
    """Resolve a query to exactly one window, preferring the topmost when several match
    and the query is not ambiguous by construction (hwnd)."""
    found = filter_windows(windows, query)
    if not found:
        raise ToolError(
            ErrorCode.WINDOW_NOT_FOUND,
            f"No window matches {query.describe()}.",
            suggestions=["Call window_list to see open windows.", "Use window_wait if the window is still opening."],
        )
    if len(found) > 1:
        titles = {w.title for w in found}
        if len(titles) > 1:
            raise ToolError(
                ErrorCode.AMBIGUOUS_MATCH,
                f"{len(found)} windows match {query.describe()}.",
                suggestions=["Pass hwnd to pick one of the candidates."],
                details={"candidates": [w.brief() for w in found[:10]]},
            )
    return min(found, key=lambda w: w.z_order)
