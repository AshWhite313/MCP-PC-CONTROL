---
title: MCP-PC-CONTROL
type: product
created: 2026-09-27
last_updated: 2026-09-28
status: active
related: ["[[Ciclo Observar-Verificar]]", "[[Backend Windows]]", "[[UI Automation Tools]]", "[[Verificação com expect]]", "[[Modelo de Segurança]]"]
sources: ["2026-09-28_sessao-mcp-pc-control"]
aliases: ["pc-control", "mcp-pc-control", "MCP de controle do PC"]
tags: [mcp, computer-use, windows]
---

# MCP-PC-CONTROL

Servidor MCP local que permite a um agente de IA observar e operar um computador Windows 11. O repositório é `AshWhite313/MCP-PC-CONTROL`, branch de desenvolvimento `claude/vigilant-bardeen-s6z4af`.

## Objetivo

O agente deve executar o [[Ciclo Observar-Verificar]]: perceber o estado do PC, agir, verificar o resultado e corrigir. O modelo planeja; o servidor percebe, age, espera, verifica e aplica a segurança.

## Arquitetura

Quatro camadas em `src/pc_control/`:

- `mcp_interface/`: registro das tools, schemas, renderização do envelope de resultado.
- `core/`: pipeline de ações (`ActionRunner`), erros, condições de espera, refs de elementos, coordenadas.
- `security/`: níveis, política, confirmação humana, auditoria, redação, kill switch, limites.
- `platform/`: contratos (`base.py`) e backends `windows/` e `fake/` (desktop simulado para testes).

Linux e macOS estão previstos como backends futuros.

## Estado

| Fase | Conteúdo | Situação |
|---|---|---|
| 0 | Fundação | concluída |
| 1 | Tela, mouse, teclado, janelas (29 tools) | concluída, testada no Windows real |
| 2 | [[UI Automation Tools]], comparação de tela (16 tools) | concluída, testada no Windows real |
| 3 | Processos, arquivos, shell, clipboard | fora do escopo desta sessão, ver [[Fase 3 fora do escopo]] |
| 4 | Navegador | pendente, ver [[Fase 4 Navegador]] |
| 5 | OCR e visão | pendente |

Total publicado: 45 tools, 105 testes no desktop simulado e testes de fumaça no Windows real via CI.

## Stack

Python 3.11+, SDK MCP 2.x (ver [[Python e SDK MCP 2.x]]), ctypes para Win32, mss para captura, comtypes para UI Automation, Pillow, pydantic, uv, ruff, pytest com anyio.

## Documentos

- `docs/PLANO_ARQUITETURA.md`: plano completo (tools, riscos, segurança, roadmap, testes).
- `docs/adr/0001-fundacao.md`: decisões da fundação.
- `README.md`: instalação no Claude Desktop e no Claude Code.

## Open Questions

- Desempenho da UI Automation em árvores grandes (Excel, páginas web) ainda não foi medido.
- Suporte a múltiplos monitores com DPI diferente não foi testado em hardware real.

## See Also

- [[Modelo de Segurança]]
- [[Verificação com expect]]
- [[CI no Windows Real]]
