"""Windows OCR via the WinRT Windows.Media.Ocr API.

Optional: the WinRT bindings are imported lazily and work under either the modern ``winrt-Windows-*``
packages (import root ``winrt``) or the older ``winsdk`` package (import root ``winsdk``). When neither
is installed the backend reports itself unavailable and screen_ocr returns a clear
BACKEND_UNAVAILABLE instead of failing to import. OCR also needs the language pack installed in Windows.
Install with: ``uv pip install 'mcp-pc-control[ocr]'``.
"""

from __future__ import annotations

import asyncio
import importlib
import threading

from pc_control.platform.base import Rect, TextBox


class _Ns:
    """Resolves WinRT namespaces under whichever package root is installed."""

    def __init__(self, root: str) -> None:
        self.root = root

    def mod(self, dotted: str):
        return importlib.import_module(f"{self.root}.windows.{dotted}")


def _namespace() -> _Ns | None:
    for root in ("winrt", "winsdk"):
        try:
            importlib.import_module(f"{root}.windows.media.ocr")
            return _Ns(root)
        except Exception:  # noqa: BLE001 - try the next root
            continue
    return None


class WindowsOcr:
    def __init__(self) -> None:
        self._checked = False
        self._ok = False
        self._ns: _Ns | None = None
        self._lock = threading.Lock()

    def _engine_cls(self):
        self._ns = self._ns or _namespace()
        return None if self._ns is None else self._ns.mod("media.ocr").OcrEngine

    def available(self) -> bool:
        with self._lock:
            if not self._checked:
                self._checked = True
                try:
                    engine_cls = self._engine_cls()
                    self._ok = engine_cls is not None and \
                        engine_cls.try_create_from_user_profile_languages() is not None
                except Exception:  # noqa: BLE001
                    self._ok = False
            return self._ok

    def languages(self) -> list[str]:
        try:
            engine_cls = self._engine_cls()
            return [lang.language_tag for lang in engine_cls.available_recognizer_languages] if engine_cls else []
        except Exception:  # noqa: BLE001
            return []

    def recognize(self, png: bytes, origin: tuple[int, int], language: str | None) -> list[TextBox]:
        if self._engine_cls() is None:
            return []
        return asyncio.run(self._recognize_async(png, origin, language))

    async def _recognize_async(self, png, origin, language) -> list[TextBox]:
        ns = self._ns
        OcrEngine = ns.mod("media.ocr").OcrEngine
        BitmapDecoder = ns.mod("graphics.imaging").BitmapDecoder
        DataWriter = ns.mod("storage.streams").DataWriter
        InMemoryRandomAccessStream = ns.mod("storage.streams").InMemoryRandomAccessStream
        Language = ns.mod("globalization").Language

        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream.get_output_stream_at(0))
        writer.write_bytes(list(png))
        await writer.store_async()
        await writer.flush_async()
        stream.seek(0)
        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()

        engine = None
        if language:
            try:
                engine = OcrEngine.try_create_from_language(Language(language))
            except Exception:  # noqa: BLE001
                engine = None
        engine = engine or OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            return []
        result = await engine.recognize_async(bitmap)
        ox, oy = origin
        boxes: list[TextBox] = []
        for line in result.lines:
            words = list(line.words)
            if not words:
                continue
            x0 = min(w.bounding_rect.x for w in words)
            y0 = min(w.bounding_rect.y for w in words)
            x1 = max(w.bounding_rect.x + w.bounding_rect.width for w in words)
            y1 = max(w.bounding_rect.y + w.bounding_rect.height for w in words)
            boxes.append(TextBox(text=line.text,
                                 bounds=Rect(round(ox + x0), round(oy + y0), round(x1 - x0), round(y1 - y0))))
        return boxes
