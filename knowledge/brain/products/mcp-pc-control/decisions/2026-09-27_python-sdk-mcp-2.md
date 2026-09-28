---
title: Python e SDK MCP 2.x
type: decision
created: 2026-09-27
last_updated: 2026-09-28
status: active
related: ["[[MCP-PC-CONTROL]]", "[[Backend Windows]]"]
sources: ["2026-09-28_sessao-mcp-pc-control"]
aliases: ["escolha da linguagem", "ADR 0001"]
tags: [adr, stack]
decision_date: 2026-09-27
impact: high
---

# Python e SDK MCP 2.x

O projeto usa Python 3.11+ e o SDK MCP oficial na versão 2.x.

## Contexto

O plano comparou Python, C#/.NET, Rust e TypeScript. O usuário delegou a escolha.

## Opções consideradas

- Python: ecossistema amplo (MCP, Playwright, psutil, OpenCV, WinRT) e caminho para Linux e macOS.
- C#/.NET com FlaUI: melhor acesso à UI Automation e binário único, mas acoplado ao Windows.
- Rust e TypeScript: acesso fraco ou verboso à UI Automation.

## Decisão

Python 3.11+. O piso é 3.11 porque `tomllib` e `StrEnum` bastam. C# fica como alternativa para um helper de UI Automation, se o desempenho exigir.

## Consequências

- No SDK 2.x, `FastMCP` virou `mcp.server.mcpserver.MCPServer`. As tools devolvem `CallToolResult` explicitamente.
- Win32 é acessado por ctypes com protótipos explícitos, sem pywin32.
- Testes assíncronos usam o plugin pytest do anyio.

## See Also

- `docs/adr/0001-fundacao.md`
