---
title: Catálogo de Tools
type: product
created: 2026-10-01
last_updated: 2026-10-01
status: active
related: ["[[MCP-PC-CONTROL]]", "[[Modelo de Segurança]]", "[[Roadmap]]"]
sources: ["2026-10-01_sessao-mcp-pc-control-parte-2"]
aliases: ["lista de tools", "75 tools", "tools MCP"]
tags: [tools, referencia]
---

# Catálogo de Tools

Lista completa das 75 tools publicadas pelo [[MCP-PC-CONTROL]] em 2026-10-01, gerada a partir do registro do servidor. Nível é a permissão mínima; risco "destrutiva" pede confirmação humana; alguns riscos sobem conforme os parâmetros (ex.: `window_close` com `mode=force`, sobrescrever em `fs_copy`).

Perfis: `observe` expõe só as de leitura; `desktop` adiciona tela, mouse, teclado, janelas, UI Automation e clipboard; `browser` expõe as de navegador; `full` expõe todas.

## Sistema e sessão (5)

| Tool | Nível | Risco | Perfil |
|---|---|---|---|
| `desktop_state` | observe | leitura | observe |
| `session_status` | observe | leitura | observe |
| `system_info` | observe | leitura | observe |
| `wait_for_any` | observe | leitura | observe |
| `wait_ms` | observe | leitura | observe |

## Tela e visão (7)

| Tool | Nível | Risco | Perfil |
|---|---|---|---|
| `screen_capture` | observe | leitura | observe |
| `screen_diff` | observe | leitura | observe |
| `screen_find_text` | observe | leitura | observe |
| `screen_get_pixel` | observe | leitura | observe |
| `screen_list_monitors` | observe | leitura | observe |
| `screen_ocr` | observe | leitura | observe |
| `screen_wait_change` | observe | leitura | observe |

## Mouse (7)

| Tool | Nível | Risco | Perfil |
|---|---|---|---|
| `mouse_click` | interact | sensível | desktop |
| `mouse_down` | interact | sensível | desktop |
| `mouse_drag` | interact | sensível | desktop |
| `mouse_move` | interact | sensível | desktop |
| `mouse_position` | observe | leitura | observe |
| `mouse_scroll` | interact | sensível | desktop |
| `mouse_up` | interact | sensível | desktop |

## Teclado (6)

| Tool | Nível | Risco | Perfil |
|---|---|---|---|
| `input_release_all` | observe | sensível | observe |
| `keyboard_hotkey` | interact | sensível | desktop |
| `keyboard_key_down` | interact | sensível | desktop |
| `keyboard_key_up` | interact | sensível | desktop |
| `keyboard_press` | interact | sensível | desktop |
| `keyboard_type` | interact | sensível | desktop |

## Janelas (8)

| Tool | Nível | Risco | Perfil |
|---|---|---|---|
| `window_close` | interact | sensível | desktop |
| `window_find` | observe | leitura | observe |
| `window_focus` | interact | sensível | desktop |
| `window_get_active` | observe | leitura | observe |
| `window_list` | observe | leitura | observe |
| `window_move_resize` | interact | sensível | desktop |
| `window_set_state` | interact | sensível | desktop |
| `window_wait` | observe | leitura | observe |

## UI Automation (14)

| Tool | Nível | Risco | Perfil |
|---|---|---|---|
| `ui_click` | interact | sensível | desktop |
| `ui_element_at` | observe | leitura | observe |
| `ui_expand` | interact | sensível | desktop |
| `ui_find` | observe | leitura | observe |
| `ui_focus` | interact | sensível | desktop |
| `ui_get` | observe | leitura | observe |
| `ui_get_text` | observe | leitura | observe |
| `ui_menu_select` | interact | sensível | desktop |
| `ui_scroll_into_view` | interact | sensível | desktop |
| `ui_select` | interact | sensível | desktop |
| `ui_set_value` | interact | sensível | desktop |
| `ui_snapshot` | observe | leitura | observe |
| `ui_toggle` | interact | sensível | desktop |
| `ui_wait` | observe | leitura | observe |

## Navegador (16)

| Tool | Nível | Risco | Perfil |
|---|---|---|---|
| `browser_click` | operate | sensível | browser |
| `browser_close` | operate | sensível | browser |
| `browser_dialog` | operate | sensível | browser |
| `browser_download_wait` | operate | sensível | browser |
| `browser_evaluate` | full | destrutiva | browser |
| `browser_fill` | operate | sensível | browser |
| `browser_get_content` | observe | leitura | browser |
| `browser_navigate` | operate | sensível | browser |
| `browser_open` | operate | sensível | browser |
| `browser_press` | operate | sensível | browser |
| `browser_screenshot` | observe | leitura | browser |
| `browser_select` | operate | sensível | browser |
| `browser_snapshot` | observe | leitura | browser |
| `browser_tabs` | operate | sensível | browser |
| `browser_upload` | operate | sensível | browser |
| `browser_wait` | observe | leitura | browser |

## Arquivos (8)

| Tool | Nível | Risco | Perfil |
|---|---|---|---|
| `fs_copy` | operate | sensível | full |
| `fs_known_folders` | observe | leitura | observe |
| `fs_list` | observe | leitura | observe |
| `fs_mkdir` | operate | sensível | full |
| `fs_move` | operate | sensível | full |
| `fs_read` | observe | leitura | observe |
| `fs_search` | observe | leitura | observe |
| `fs_stat` | observe | leitura | observe |

## Clipboard (3)

| Tool | Nível | Risco | Perfil |
|---|---|---|---|
| `clipboard_clear` | interact | sensível | desktop |
| `clipboard_get` | interact | leitura | desktop |
| `clipboard_set` | interact | sensível | desktop |

## Processos (1)

| Tool | Nível | Risco | Perfil |
|---|---|---|---|
| `process_list` | observe | leitura | observe |

## Fora do catálogo

Shell, iniciar e encerrar processos e excluir arquivos não existem como tools. Ver [[Fase 3 fora do escopo]].

## See Also

- [[Roadmap]]
- [[Modelo de Segurança]]
