# ADR 0001 — Decisões da fundação (Fases 0 e 1)

Status: aceito · Data: 2026-09-27

## Linguagem: Python 3.11+

Escolhido pelo ecossistema (SDK MCP oficial, Playwright, psutil, OpenCV, WinRT) e pelo caminho para
backends Linux/macOS. C#/.NET com FlaUI continua como alternativa para um eventual helper de UI Automation
se o desempenho via COM em Python não for suficiente (a interface de backend permite a troca).
O piso é 3.11 (não 3.12) porque `tomllib` e `StrEnum` bastam e amplia a compatibilidade.

## SDK MCP 2.x

O projeto usa `mcp>=2.2,<3`. Na 2.x, `FastMCP` virou `mcp.server.mcpserver.MCPServer`. As tools retornam
`CallToolResult` explicitamente (texto JSON + `structured_content` + imagens), para controle total do envelope.
Somente `server.py` e `mcp_interface/` dependem do SDK.

## Win32 via ctypes, sem pywin32

O backend Windows usa `ctypes` com protótipos explícitos (evita truncar handles de 64 bits) e `mss` para
captura. Menos dependências nativas e controle fino de `SendInput` (Unicode, teclas estendidas, scan codes).

## Posicionamento do cursor: `SetCursorPos` + `SendInput`

Coordenadas absolutas normalizadas (0–65535) do `SendInput` sofrem arredondamento; `SetCursorPos` é exato
em pixels físicos num processo Per-Monitor DPI Aware V2. Botões e roda continuam via `SendInput`.

## Canal de confirmação: diálogo nativo antes de elicitation

A elicitation é respondida pelo cliente MCP, que pode ser automatizado. O diálogo nativo é exibido pelo
próprio servidor no desktop local. Por isso a ordem padrão é `["native_dialog", "elicitation"]`.
Enquanto uma confirmação está pendente, todas as tools que mudam estado são recusadas, para que o agente
não consiga clicar em "Sim" no próprio diálogo.

## Efeitos colaterais medidos após o `expect`

Os `effects` (janelas abertas/fechadas, foco) são calculados depois da espera do `expect`, para incluir
diálogos que aparecem durante a espera — o caso mais comum.

## Testes com anyio, não pytest-asyncio

O cliente MCP em memória usa escopos de cancelamento do anyio, que precisam ser encerrados na mesma task em
que foram abertos; o plugin pytest do anyio garante isso para fixtures assíncronas.

## Pendências registradas

- Erros de validação de parâmetros gerados pelo SDK (tipos errados) retornam texto simples, não o envelope
  estruturado. Avaliar um middleware na Fase 2.
- Indicador visual (ícone de bandeja) ainda não implementado; hoje o kill switch avisa com um bipe.
