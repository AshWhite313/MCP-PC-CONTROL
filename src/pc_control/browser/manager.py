"""BrowserManager: Playwright lifecycle, tabs, accessibility-style snapshot with refs, actions.

Refs (``b7``) are assigned by injected JS that tags interactive elements with a ``data-pcref``
attribute. Actions resolve refs with the attribute selector, so Playwright re-queries the live DOM
on every use (a ref survives minor re-renders; it goes stale only when the element is gone).
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pc_control.browser.urlguard import UrlGuard
from pc_control.config import BrowserConfig
from pc_control.core.errors import ErrorCode, ToolError

# JS that tags interactive/labelled elements and returns a flat list in document order.
_SNAPSHOT_JS = r"""
(maxNodes) => {
  let n = 0;
  const out = [];
  const roleFor = (el) => {
    const explicit = el.getAttribute('role');
    if (explicit) return explicit;
    const t = el.tagName.toLowerCase();
    if (t === 'a' && el.hasAttribute('href')) return 'link';
    if (t === 'button') return 'button';
    if (t === 'select') return 'combobox';
    if (t === 'textarea') return 'textbox';
    if (t === 'input') {
      const ty = (el.getAttribute('type') || 'text').toLowerCase();
      return {checkbox:'checkbox', radio:'radio', button:'button', submit:'button', reset:'button',
              range:'slider', search:'searchbox'}[ty] || 'textbox';
    }
    if (/^h[1-6]$/.test(t)) return 'heading';
    return t;
  };
  const nameFor = (el) => {
    const al = el.getAttribute('aria-label'); if (al) return al.trim();
    const lb = el.getAttribute('aria-labelledby');
    if (lb) { const r = lb.split(/\s+/).map(id => (document.getElementById(id)||{}).innerText||'').join(' ').trim();
              if (r) return r; }
    if (el.labels && el.labels.length) return el.labels[0].innerText.trim();
    const ph = el.getAttribute('placeholder'); if (ph) return ph.trim();
    const t = el.tagName.toLowerCase();
    if (t === 'input' && (el.type === 'submit' || el.type === 'button')) return (el.value||'').trim();
    if (['a','button','summary','option'].includes(t) || /^h[1-6]$/.test(t))
      return (el.innerText||'').replace(/\s+/g,' ').trim().slice(0,120);
    const ti = el.getAttribute('title'); if (ti) return ti.trim();
    return '';
  };
  const INTERACTIVE = 'a[href],button,input,select,textarea,summary,[role],[onclick],[tabindex]';
  const interactive = new Set(document.querySelectorAll(INTERACTIVE));
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
  let depthMap = new WeakMap(); depthMap.set(document.body, 0);
  let el = walker.currentNode;
  while (el) {
    const parent = el.parentElement;
    const depth = depthMap.has(el) ? depthMap.get(el) : (depthMap.get(parent) || 0) + 1;
    depthMap.set(el, depth);
    const t = el.tagName.toLowerCase();
    const isHeading = /^h[1-6]$/.test(t);
    if (interactive.has(el) || isHeading) {
      const r = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      const visible = r.width > 0 && r.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
      const nm = nameFor(el);
      const role = roleFor(el);
      if (visible || nm) {
        const ref = 'b' + (++n);
        el.setAttribute('data-pcref', ref);
        const node = {ref, role, name: nm, depth,
          disabled: el.disabled === true || el.getAttribute('aria-disabled') === 'true',
          value: (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT')
                 ? (el.type === 'password' ? null : (el.value || '')) : undefined,
          checked: (el.type === 'checkbox' || el.type === 'radio') ? el.checked
                   : (el.getAttribute('aria-checked') === 'true' ? true : undefined),
          password: el.type === 'password' || undefined,
          visible,
          bbox: visible ? {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)} : null};
        out.push(node);
        if (out.length >= maxNodes) break;
      }
    }
    el = walker.nextNode();
  }
  return out;
}
"""


def resolve_executable(cfg: BrowserConfig) -> str | None:
    """Explicit path, else a Chromium pre-installed under PLAYWRIGHT_BROWSERS_PATH, else None
    (let Playwright/the channel decide)."""
    if cfg.executable_path:
        p = os.path.expanduser(os.path.expandvars(cfg.executable_path))
        if not os.path.exists(p):
            raise ToolError(ErrorCode.BACKEND_UNAVAILABLE, f"Browser executable not found: {p}.")
        return p
    base = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if base and cfg.channel == "chromium":
        for pat in ("chromium-*/chrome-linux/chrome", "chromium-*/chrome-win/chrome.exe",
                    "chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium"):
            hits = sorted(glob.glob(os.path.join(base, pat)))
            if hits:
                return hits[-1]
    return None


@dataclass
class TabRef:
    tab_id: str
    page: Any


@dataclass
class BrowserManager:
    cfg: BrowserConfig
    urls: UrlGuard
    _pw: Any = None
    _browser: Any = None
    _context: Any = None
    _tabs: dict[str, Any] = field(default_factory=dict)
    _counter: int = 0
    _active: str | None = None
    dialog_policy: dict[str, str] = field(default_factory=dict)  # tab_id -> accept|dismiss
    last_dialog: dict | None = None

    @property
    def running(self) -> bool:
        return self._context is not None

    async def open(self, ephemeral: bool) -> dict:
        if self.running:
            return self.info()
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        launch: dict = {"headless": self.cfg.headless}
        exe = resolve_executable(self.cfg)
        if exe:
            launch["executable_path"] = exe
        elif self.cfg.channel != "chromium":
            launch["channel"] = self.cfg.channel
        try:
            if ephemeral:
                self._browser = await self._pw.chromium.launch(**launch)
                self._context = await self._browser.new_context()
            else:
                profile = os.path.expanduser(os.path.expandvars(self.cfg.profile_dir))
                Path(profile).mkdir(parents=True, exist_ok=True)
                self._context = await self._pw.chromium.launch_persistent_context(profile, **launch)
        except Exception as e:
            await self.close()
            raise ToolError(ErrorCode.BACKEND_UNAVAILABLE, f"Could not launch the browser: {e}",
                            suggestions=["Check the browser.channel / executable_path in the policy."]) from None
        self._context.set_default_timeout(self.cfg.default_timeout_ms)
        self._context.on("page", self._register_page)
        existing = self._context.pages
        page = existing[0] if existing else await self._context.new_page()
        self._register_page(page)
        return self.info()

    def _register_page(self, page: Any) -> str:
        for tid, p in self._tabs.items():
            if p is page:
                return tid
        self._counter += 1
        tid = f"t{self._counter}"
        self._tabs[tid] = page
        self._active = self._active or tid
        page.on("dialog", lambda d: self._on_dialog(tid, d))
        page.on("close", lambda: self._tabs.pop(tid, None))
        return tid

    async def _on_dialog(self, tid: str, dialog: Any) -> None:
        self.last_dialog = {"tab": tid, "type": dialog.type, "message": dialog.message}
        action = self.dialog_policy.pop(tid, "dismiss")
        try:
            await (dialog.accept() if action == "accept" else dialog.dismiss())
        except Exception:  # noqa: BLE001 - dialog may already be gone
            pass

    async def close(self) -> None:
        for obj in (self._context, self._browser, self._pw):
            if obj is not None:
                try:
                    await (obj.stop() if obj is self._pw else obj.close())
                except Exception:  # noqa: BLE001
                    pass
        self._pw = self._browser = self._context = self._active = None
        self._tabs.clear()

    def info(self) -> dict:
        return {"tabs": [{"tab_id": t, "url": p.url, "active": t == self._active} for t, p in self._tabs.items()]}

    def require(self) -> None:
        if not self.running:
            raise ToolError(ErrorCode.BACKEND_UNAVAILABLE, "No browser is open.",
                            suggestions=["Call browser_open first."])

    def page(self, tab_id: str | None) -> Any:
        self.require()
        tid = tab_id or self._active
        page = self._tabs.get(tid)
        if page is None:
            raise ToolError(ErrorCode.NOT_FOUND, f"No tab {tid!r}.", suggestions=["Call browser_tabs to list tabs."])
        self._active = tid
        return page

    def tab_id_of(self, page: Any) -> str:
        return self._register_page(page)

    async def snapshot(self, page: Any, max_nodes: int) -> list[dict]:
        try:
            return await page.evaluate(_SNAPSHOT_JS, max_nodes)
        except Exception as e:  # noqa: BLE001
            raise ToolError(ErrorCode.INTERNAL, f"Could not read the page: {e}") from None

    def locator(self, page: Any, ref: str):
        return page.locator(f'[data-pcref="{ref}"]')
