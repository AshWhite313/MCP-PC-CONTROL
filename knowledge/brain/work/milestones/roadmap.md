---
title: Roadmap
type: milestone
created: 2026-10-01
last_updated: 2026-10-01
status: active
related: ["[[MCP-PC-CONTROL]]", "[[Catálogo de Tools]]", "[[Fase 3 fora do escopo]]", "[[Fase 4 Navegador]]"]
sources: ["2026-09-27_plano-arquitetura", "2026-10-01_sessao-mcp-pc-control-parte-2"]
aliases: ["fases", "plano de fases"]
tags: [roadmap]
knowledge_refs: ["products/mcp-pc-control/overview"]
priority: p1
---

# Roadmap

Fases definidas no plano de arquitetura (`docs/PLANO_ARQUITETURA.md`, seção 11) e seu estado em 2026-10-01.

| Fase | Escopo planejado | Estado | Commit |
|---|---|---|---|
| 0 | Fundação: pipeline, envelope, erros, política, auditoria, kill switch | concluída | 05da41c |
| 1 | Tela, mouse, teclado, janelas | concluída | 05da41c, 8426886 |
| 2 | [[UI Automation Tools]], esperas, verificação | concluída | 93d6ef4, 80ebee0 |
| 3 | Processos, arquivos, shell, clipboard, humano | parcial: [[Arquivos, Clipboard e Processos]] | 1f6e710 |
| 4 | [[Navegador]] | concluída | 495a211, 5aa4d7e |
| 5 | [[OCR e Visão]], zonas de privacidade | concluída | 9047d1a |
| 6 | [[Hardening]]: erros estruturados, bandeja, diagnóstico | concluída | 60af9ef |
| 7 | Futuro: backends Linux e macOS, adaptadores Office, HTTP autenticado | não iniciada | |

## Pendências conhecidas

- Fase 3 restante: shell, iniciar e encerrar processos, excluir arquivos, `human_ask` e `human_handoff`. Ver [[Fase 3 fora do escopo]].
- `screen_find_image` (busca por imagem) planejada como opcional na Fase 5 e não feita.
- Pausar automaticamente quando o usuário mexe no mouse ou teclado: não feito.
- Teste em múltiplos monitores com DPI diferente e com um cliente MCP real ainda não realizados.
- Avaliação ponta a ponta com agente real (cenários do enunciado) não executada.
- Empacotamento como executável único não feito; instalação é via `uv`.

## See Also

- [[Limitações e Riscos]]
