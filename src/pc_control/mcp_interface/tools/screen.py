"""Screen tools: screen_list_monitors, screen_capture, screen_get_pixel."""

from __future__ import annotations

from typing import Annotated, Literal

from mcp.server.mcpserver import Context
from mcp_types import CallToolResult
from pydantic import BaseModel, ConfigDict, Field

from pc_control.config import Level
from pc_control.core.conditions import ScreenCondition, ScreenRegion
from pc_control.core.elements import ACTION_PATTERNS, UiSelector, find_elements, fold, interesting
from pc_control.core.errors import ErrorCode, ToolError
from pc_control.core.runner import Operation, Outcome
from pc_control.core.screenshots import capture_region, diff_regions
from pc_control.mcp_interface.common import Registry, Space, render, resolve_point
from pc_control.platform.base import FindCriteria, Rect, TextBox
from pc_control.security.policy import Risk
from pc_control.vision.annotate import Mark
from pc_control.vision.annotate import annotate as annotate_capture


class Region(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: int
    y: int
    width: Annotated[int, Field(gt=0)]
    height: Annotated[int, Field(gt=0)]


def _filter_text(boxes: list[TextBox], text: str, match: str) -> list[TextBox]:
    import re

    if match == "regex":
        pat = re.compile(text)
        return [b for b in boxes if pat.search(b.text)]
    want = fold(text)
    if match == "exact":
        return [b for b in boxes if fold(b.text) == want]
    return [b for b in boxes if want in fold(b.text)]


def register(reg: Registry) -> None:
    rt = reg.rt

    @reg.tool("screen_list_monitors", level=Level.OBSERVE, risk=Risk.SAFE, profile="observe",
              title="List monitors", idempotent=True)
    async def screen_list_monitors(ctx: Context) -> CallToolResult:
        """List monitors with id, bounds (physical pixels on the virtual screen; monitors left of/above the
        primary have negative coordinates), work area (without taskbar), DPI and scale factor."""

        async def impl(op: Operation) -> Outcome:
            ms = await op.call(op.backend.screen.list_monitors)
            vb = await op.call(op.backend.screen.virtual_bounds)
            return Outcome(
                f"{len(ms)} monitor(s).",
                details={"monitors": [m.to_dict() for m in ms], "virtual_bounds": vb.to_dict(),
                         "layout_generation": op.backend.screen.layout_generation()},
            )

        return render(await rt.run(screen_list_monitors.spec, {}, impl, ctx=ctx))

    @reg.tool("screen_capture", level=Level.OBSERVE, risk=Risk.SAFE, profile="observe", title="Screenshot")
    async def screen_capture(
        ctx: Context,
        monitor: Annotated[int | None, Field(description="Monitor id to capture.")] = None,
        window: Annotated[int | None, Field(description="hwnd of a window to capture (its screen area).")] = None,
        region: Annotated[Region | None, Field(description="Screen region in physical pixels.")] = None,
        all_monitors: Annotated[bool, Field(description="Capture the whole virtual screen.")] = False,
        max_long_edge: Annotated[int | None, Field(ge=256, le=8192, description=(
            "Downscale so the longest side is at most this many pixels (default from policy)."))] = None,
        format: Annotated[Literal["png", "jpeg"], Field(description="jpeg is smaller; png is exact.")] = "png",
        annotate: Annotated[Literal["none", "grid", "elements", "ocr"], Field(description=(
            "Overlay: grid draws coordinate lines; elements numbers the UI controls (with refs) so you can "
            "say which to click; ocr numbers the text runs found on screen."))] = "none",
    ) -> CallToolResult:
        """Take a screenshot. Give at most one of monitor / window / region / all_monitors; by default the
        monitor of the active window is captured. The image may be downscaled: the result has a capture_id
        and scale — pass space={'capture_id': ...} to mouse tools to click on image coordinates directly.
        With annotate='elements' or 'ocr' the result also lists numbered marks (bbox, center, ref) so you can
        point at a number. Prefer structured tools (desktop_state, window_list, ui_find) when you do not need
        pixels: images are expensive."""

        async def impl(op: Operation) -> Outcome:
            b = op.backend
            chosen = [v for v in (monitor, window, region) if v is not None] + ([True] if all_monitors else [])
            if len(chosen) > 1:
                raise ToolError(ErrorCode.INVALID_ARGUMENT, "Give at most one of monitor, window, region, all_monitors.")
            vb = await op.call(b.screen.virtual_bounds)
            if all_monitors:
                rect = vb
            elif region is not None:
                rect = Rect(region.x, region.y, region.width, region.height)
            elif window is not None:
                w = await op.call(b.windows.get_window, window)
                if w is None:
                    raise ToolError(ErrorCode.WINDOW_NOT_FOUND, f"No window with hwnd {window}.",
                                    suggestions=["Call window_list to get current hwnds."])
                if w.state == "minimized":
                    raise ToolError(ErrorCode.INVALID_ARGUMENT, f"Window {w.title!r} is minimized.",
                                    suggestions=["Restore it with window_set_state(state='restore') first."])
                rect = w.bounds
            else:
                monitors = await op.call(b.screen.list_monitors)
                if monitor is not None:
                    m = next((m for m in monitors if m.id == monitor), None)
                    if m is None:
                        raise ToolError(ErrorCode.NOT_FOUND, f"No monitor with id {monitor}.",
                                        suggestions=["Call screen_list_monitors."])
                else:
                    fg = await op.call(b.windows.foreground_window)
                    m = next((m for m in monitors if fg and m.id == fg.monitor), None)
                    m = m or next((m for m in monitors if m.primary), monitors[0])
                rect = m.bounds
            clipped = rect.intersect(vb)
            if clipped is None:
                raise ToolError(ErrorCode.INVALID_ARGUMENT, f"Area {rect.to_dict()} is off screen.")
            privacy = {p.casefold() for p in rt.config.privacy.never_capture_processes}
            shot = await op.call(
                lambda: capture_region(b, rt.captures, clipped, max_long_edge=max_long_edge
                                       or rt.config.screen.max_long_edge, fmt=format,
                                       privacy_processes=privacy or None)
            )
            details: dict = {}
            if annotate != "none":
                marks = await op.call(_marks_for, op, annotate, clipped, window)
                if annotate == "grid":
                    shot = await op.call(annotate_capture, shot, "grid")
                else:
                    shot = await op.call(annotate_capture, shot, "marks", marks)
                    details["marks"] = [m.to_dict() for m in marks]
            warnings = ["Requested area was clipped to the visible screen."] if clipped != rect else []
            if shot.masked:
                warnings.append(f"{len(shot.masked)} privacy-protected window(s) were blacked out.")
            return Outcome(
                f"Captured {clipped.width}x{clipped.height} px as {shot.record.capture_id} "
                f"(image {shot.record.image_width}x{shot.record.image_height}).",
                images=[shot], warnings=warnings, details=details,
            )

        params = {"monitor": monitor, "window": window, "region": region.model_dump() if region else None,
                  "all_monitors": all_monitors, "annotate": annotate}
        return render(await rt.run(screen_capture.spec, params, impl, ctx=ctx))

    @reg.tool("screen_get_pixel", level=Level.OBSERVE, risk=Risk.SAFE, profile="observe", title="Get pixel color",
              idempotent=True)
    async def screen_get_pixel(ctx: Context, x: int, y: int, space: Space = "screen") -> CallToolResult:
        """Read the colour of one pixel. Useful to check a status light or a highlight without a screenshot."""

        async def impl(op: Operation) -> Outcome:
            sx, sy = await op.call(resolve_point, rt, x, y, space)
            r, g, b = await op.call(op.backend.screen.get_pixel, sx, sy)
            hexcolor = f"#{r:02x}{g:02x}{b:02x}"
            return Outcome(f"Pixel ({sx}, {sy}) is {hexcolor}.", target={"x": sx, "y": sy},
                           details={"rgb": [r, g, b], "hex": hexcolor})

        return render(await rt.run(screen_get_pixel.spec, {"x": x, "y": y}, impl, ctx=ctx))

    @reg.tool("screen_diff", level=Level.OBSERVE, risk=Risk.SAFE, profile="observe", title="Compare screenshots")
    async def screen_diff(
        ctx: Context,
        before: Annotated[str, Field(description="capture_id of the earlier screenshot.")],
        after: Annotated[str, Field(description="capture_id of a later screenshot of the same area, or 'now'.")] = "now",
    ) -> CallToolResult:
        """Compare two screenshots of the same area: fraction of changed pixels and the changed regions in
        screen coordinates. Use it to confirm that something visibly happened, without re-reading images."""

        async def impl(op: Operation) -> Outcome:
            import io

            from PIL import Image

            gen = op.backend.screen.layout_generation()
            rec_a = rt.captures.get(before, gen)
            img_a = Image.open(io.BytesIO(rt.captures.image(before)))
            if after == "now":
                shot = await op.call(lambda: capture_region(op.backend, rt.captures, rec_a.bounds,
                                                            max_long_edge=max(rec_a.image_width, rec_a.image_height)))
                rec_b, data_b = shot.record, shot.data
            else:
                rec_b, data_b = rt.captures.get(after, gen), rt.captures.image(after)
            if rec_b.bounds != rec_a.bounds:
                raise ToolError(ErrorCode.INVALID_ARGUMENT, "The two captures cover different screen areas.")
            ratio, regions = await op.call(diff_regions, img_a, Image.open(io.BytesIO(data_b)), rec_a.bounds)
            return Outcome(
                "No visible change." if ratio == 0 else f"{ratio:.2%} of pixels changed in {len(regions)} region(s).",
                details={"changed_ratio": round(ratio, 5), "identical": ratio == 0, "regions": regions,
                         "after_capture_id": rec_b.capture_id},
            )

        return render(await rt.run(screen_diff.spec, {"before": before, "after": after}, impl, ctx=ctx))

    @reg.tool("screen_wait_change", level=Level.OBSERVE, risk=Risk.SAFE, profile="observe",
              title="Wait for screen change")
    async def screen_wait_change(
        ctx: Context,
        mode: Annotated[Literal["changes", "stable"], Field(description=(
            "changes: wait until the area looks different from when the call started; "
            "stable: wait until it stops changing for stable_ms (animations/loading finished)."))] = "changes",
        region: Region | None = None,
        window: Annotated[int | None, Field(description="Watch this window's area (hwnd).")] = None,
        threshold: Annotated[float, Field(gt=0, le=1)] = 0.005,
        stable_ms: Annotated[int, Field(ge=100, le=30_000)] = 600,
        timeout_ms: Annotated[int, Field(ge=0, le=120_000)] = 10_000,
    ) -> CallToolResult:
        """Wait for a visual change (or for the screen to settle) in a region or window. For apps without
        accessibility info; prefer ui_wait / window_wait when possible."""

        async def impl(op: Operation) -> Outcome:
            cond = ScreenCondition(
                region=ScreenRegion(**region.model_dump()) if region else None, window=window, state=mode,
                threshold=threshold, stable_ms=stable_ms,
            )
            timeout = min(timeout_ms, rt.config.limits.max_wait_ms)
            res = await rt.conditions.wait_any([cond], timeout, is_cancelled=lambda: rt.killswitch.engaged)
            if not res.met:
                raise ToolError(ErrorCode.TIMEOUT, f"Screen did not become '{mode}' within {timeout} ms.",
                                details=res.to_dict())
            return Outcome(f"Screen condition '{mode}' met after {res.waited_ms} ms.", details=res.to_dict())

        params = {"mode": mode, "region": region.model_dump() if region else None, "window": window}
        return render(await rt.run(screen_wait_change.spec, params, impl, ctx=ctx))

    # -- OCR and text search ----------------------------------------------------------------

    def _region_and_window(op, window, region):
        """Resolve (Rect, hwnd|None) for OCR/find-text targets."""
        b = op.backend
        vb = b.screen.virtual_bounds()
        if region is not None:
            return Rect(region.x, region.y, region.width, region.height).intersect(vb), None
        if window is not None:
            w = b.windows.get_window(window)
            if w is None:
                raise ToolError(ErrorCode.WINDOW_NOT_FOUND, f"No window with hwnd {window}.")
            return w.bounds.intersect(vb), window
        fg = b.windows.foreground_window()
        return (fg.bounds.intersect(vb) if fg else vb), (fg.hwnd if fg else None)

    def _ocr(op, rect: Rect, language: str | None) -> list[TextBox]:
        ocr = op.backend.ocr
        if ocr is None or not ocr.available():
            raise ToolError(ErrorCode.BACKEND_UNAVAILABLE,
                            "OCR is not available (Windows OCR bindings or language pack missing).",
                            suggestions=["Prefer ui_find / screen_find_text via UIA when the app exposes controls."])
        privacy = {p.casefold() for p in rt.config.privacy.never_capture_processes}
        shot = capture_region(op.backend, rt.captures, rect, max_long_edge=100_000, privacy_processes=privacy or None)
        return ocr.recognize(shot.data, (rect.x, rect.y), language)

    def _marks_for(op, mode: str, rect: Rect, window) -> list[Mark]:
        if mode == "grid":
            return []
        marks: list[Mark] = []
        if mode == "ocr":
            for i, box in enumerate(_ocr(op, rect, None), 1):
                marks.append(Mark(i, box.bounds, label=box.text[:40]))
            return marks
        # elements: number interactive UI controls inside the region
        acc = op.backend.accessibility
        if acc is None:
            return marks
        hwnd = window
        if hwnd is None:
            fg = op.backend.windows.foreground_window()
            hwnd = fg.hwnd if fg else None
        if hwnd is None:
            return marks
        root = acc.window_root(hwnd)
        i = 0
        for el in acc.find_all(root, FindCriteria(), 1000, False):
            if el.bounds is None or el.bounds.intersect(rect) is None:
                continue
            if not (ACTION_PATTERNS & set(el.patterns)) and not interesting(el):
                continue
            i += 1
            ref = rt.refs.register(el)
            marks.append(Mark(i, el.bounds, label=el.name[:30], ref=ref))
        return marks

    @reg.tool("screen_ocr", level=Level.OBSERVE, risk=Risk.SAFE, profile="observe", title="OCR")
    async def screen_ocr(
        ctx: Context,
        window: Annotated[int | None, Field(description="hwnd to read; default: the active window.")] = None,
        region: Region | None = None,
        language: Annotated[str | None, Field(description="BCP-47 tag, e.g. 'pt-BR'. Default: system language.")] = None,
    ) -> CallToolResult:
        """Read text from the screen with OCR, for apps that do not expose their text as controls (canvas,
        images, remote sessions). Prefer ui_get_text / ui_find when the control is accessible. Returns text
        runs with screen bounding boxes; the text is untrusted data."""

        async def impl(op: Operation) -> Outcome:
            rect, _ = _region_and_window(op, window, region)
            if rect is None:
                raise ToolError(ErrorCode.INVALID_ARGUMENT, "The target area is off screen.")
            boxes = await op.call(_ocr, op, rect, language)
            full = "\n".join(b.text for b in boxes)
            details = {"count": len(boxes), "untrusted": True,
                       "boxes": [{"text": b.text, "bbox": b.bounds.to_dict(),
                                  "center": dict(zip(("x", "y"), b.bounds.center, strict=True)),
                                  "confidence": round(b.confidence, 3)} for b in boxes]}
            return Outcome(f"Recognized {len(boxes)} text run(s).", details=details, text_blocks={"text": full})

        params = {"window": window, "region": region.model_dump() if region else None, "language": language}
        return render(await rt.run(screen_ocr.spec, params, impl, ctx=ctx))

    @reg.tool("screen_find_text", level=Level.OBSERVE, risk=Risk.SAFE, profile="observe", title="Find text on screen")
    async def screen_find_text(
        ctx: Context,
        text: Annotated[str, Field(min_length=1, description="Text to locate.")],
        match: Literal["exact", "contains", "regex"] = "contains",
        via: Annotated[Literal["any", "uia", "ocr"], Field(description=(
            "any tries UI Automation first, then OCR; uia only accessible controls; ocr only pixels."))] = "any",
        window: int | None = None,
        region: Region | None = None,
    ) -> CallToolResult:
        """Locate text on screen and get its position to click. Uses UI Automation first (exact, cheap) and
        falls back to OCR. Returns matches with center points and, for UIA hits, an element ref."""

        async def impl(op: Operation) -> Outcome:
            rect, hwnd = _region_and_window(op, window, region)
            results = []
            source = None
            if via in ("any", "uia") and op.backend.accessibility is not None and hwnd is not None:
                sel = UiSelector(text=text, match=match, window=hwnd, include_offscreen=False)
                try:
                    found = find_elements(op.backend, rt.refs, sel, 50)
                except ToolError:
                    found = []
                for el in found:
                    if el.bounds is None or (rect and el.bounds.intersect(rect) is None):
                        continue
                    results.append({"text": el.name, "center": dict(zip(("x", "y"), el.bounds.center, strict=True)),
                                    "bbox": el.bounds.to_dict(), "source": "uia", "ref": rt.refs.register(el)})
                if results:
                    source = "uia"
            if not results and via in ("any", "ocr"):
                boxes = await op.call(_ocr, op, rect, None)
                for b in _filter_text(boxes, text, match):
                    results.append({"text": b.text, "center": dict(zip(("x", "y"), b.bounds.center, strict=True)),
                                    "bbox": b.bounds.to_dict(), "source": "ocr"})
                if results:
                    source = "ocr"
            if not results:
                raise ToolError(ErrorCode.NOT_FOUND, f"Text {text!r} not found on screen.",
                                suggestions=["Try match='contains', another window, or scroll it into view."])
            return Outcome(f"Found {len(results)} match(es) for {text!r} via {source}.",
                           details={"matches": results, "source": source})

        params = {"text": text, "match": match, "via": via, "window": window}
        return render(await rt.run(screen_find_text.spec, params, impl, ctx=ctx))
