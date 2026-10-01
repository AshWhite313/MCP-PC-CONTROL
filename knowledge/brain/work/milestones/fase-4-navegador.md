---
title: Fase 4 Navegador
type: milestone
created: 2026-09-28
last_updated: 2026-10-01
status: archived
related: ["[[MCP-PC-CONTROL]]", "[[Fase 3 fora do escopo]]"]
sources: ["2026-09-28_sessao-mcp-pc-control"]
aliases: ["browser_*", "Playwright"]
tags: [roadmap]
knowledge_refs: ["products/mcp-pc-control/overview"]
priority: p1
---

# Fase 4 Navegador

Próxima fase acordada com o usuário em 2026-09-28.

## Escopo

Tools `browser_*` com Playwright e perfil dedicado do agente: abrir e navegar, abas, snapshot com refs, clicar, preencher, selecionar, esperar, screenshot, downloads para pastas permitidas, diálogos. Política de URLs. Login, 2FA e CAPTCHA ficam com o usuário.

## Situação

Concluída em 2026-09-28: 16 tools browser_* implementadas e testadas com Chromium real no CI.

## Critério de saída (atendido)

Fluxo num site local de testes: abrir, navegar, preencher login (senha não é relida nem registrada),
selecionar opção, clicar, baixar o CSV para pasta permitida (verificado por conteúdo), esperar por texto.
Cliques de alto impacto ("Excluir tudo") pedem confirmação; browser_evaluate é desligado por padrão;
downloads passam pelo PathGuard.

## See Also

- `docs/PLANO_ARQUITETURA.md`, seção 5.2.11
