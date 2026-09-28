---
title: Backend Windows
type: system
created: 2026-09-27
last_updated: 2026-09-28
status: active
related: ["[[MCP-PC-CONTROL]]", "[[UI Automation Tools]]", "[[CI no Windows Real]]"]
sources: ["2026-09-28_sessao-mcp-pc-control"]
aliases: ["platform/windows", "backend Win32"]
tags: [windows, win32, uia]
---

# Backend Windows

Implementação dos contratos de plataforma do [[MCP-PC-CONTROL]] para Windows 10 e 11, em `src/pc_control/platform/windows/`.

## Componentes

- `win32.py`: bindings ctypes com protótipos explícitos para não truncar handles de 64 bits.
- `__init__.py`: tela (mss), input (SendInput), janelas (Win32 e DWM), sistema, diálogo de confirmação e hotkey do kill switch.
- `uia.py`: UI Automation via comtypes.
- `keymap.py`: nomes de teclas para virtual-key codes.

## Notas operacionais

- O processo declara Per-Monitor DPI Aware V2. Coordenadas são pixels físicos do virtual screen.
- O cursor é posicionado com `SetCursorPos`, que é exato; botões e roda usam `SendInput`.
- Texto é digitado com `KEYEVENTF_UNICODE`, independente do layout (ABNT2 ou US).
- Limites de janela vêm de `DWMWA_EXTENDED_FRAME_BOUNDS`; janelas "cloaked" são filtradas.
- `SW_RESTORE` numa janela minimizada a partir de maximizada volta a maximizar; o backend restaura duas vezes.
- A UI Automation roda numa thread MTA dedicada, porque o comtypes inicializa COM na thread do primeiro import. Cache requests reduzem chamadas entre processos, e timeouts de conexão e transação evitam travar com apps que não respondem.
- Invoke que expira por diálogo modal é tratado como executado.

## Dependências

mss, comtypes, Pillow. Detecção de ambiente seguro via `OpenInputDesktop`.

## See Also

- [[CI no Windows Real]]
