---
title: Navegador
type: product
created: 2026-09-28
last_updated: 2026-10-01
status: active
related: ["[[MCP-PC-CONTROL]]", "[[Modelo de Segurança]]", "[[Fase 4 Navegador]]"]
sources: ["2026-09-28_sessao-mcp-pc-control"]
aliases: ["browser_*", "Playwright", "Fase 4"]
tags: [navegador, playwright, fase-4]
---

# Navegador

16 tools de automação de navegador via Playwright, adicionadas na Fase 4 do [[MCP-PC-CONTROL]].

## Tools

`browser_open`, `browser_close`, `browser_tabs`, `browser_navigate`, `browser_snapshot`, `browser_wait`, `browser_click`, `browser_fill`, `browser_select`, `browser_press`, `browser_screenshot`, `browser_get_content`, `browser_download_wait`, `browser_upload`, `browser_dialog`, `browser_evaluate`.

## Design

- **Perfil dedicado do agente**, separado do navegador pessoal do usuário.
- Refs de elementos (`b1`, `b2`) vêm de um snapshot da página feito por JS injetado (ver [[Refs do navegador por JS injetado]]); as ações usam seletores de atributo, que o Playwright reavalia no DOM ao vivo (a ref sobrevive a pequenas mudanças).
- Executável resolvido por config: build do Playwright, canal instalado (Edge/Chrome) ou caminho explícito.

## Segurança

- Guarda de URL (allowlist/denylist por domínio e subdomínios).
- Downloads e uploads passam pelo PathGuard (pastas permitidas). Ver [[Modelo de Segurança]].
- Campos de senha não são relidos nem registrados.
- Cliques com rótulo de alto impacto pedem confirmação; `browser_evaluate` é desligado por padrão e confirmado a cada uso.

## Validação

9 testes contra um site local ("sistema de vendas") com Chromium real no CI (Linux e Windows): login, seleção, clique, download verificado por conteúdo, espera por texto, recusa de confirmação e bloqueio de URL.

## See Also

- [[Verificação com expect]]
