---
title: Refs do navegador por JS injetado
type: decision
created: 2026-10-01
last_updated: 2026-10-01
status: active
related: ["[[Navegador]]", "[[MCP-PC-CONTROL]]"]
sources: ["2026-09-28_adr-0002-fases-4-a-6", "2026-10-01_sessao-mcp-pc-control-parte-2"]
aliases: ["data-pcref", "snapshot do navegador"]
tags: [adr, navegador]
decision_date: 2026-09-28
impact: medium
---

# Refs do navegador por JS injetado

O snapshot de página do [[Navegador]] é feito por JavaScript injetado, que marca cada elemento interativo com o atributo `data-pcref` e devolve uma lista com papel, nome, valor e estado.

## Contexto

O Playwright atual removeu `page.accessibility`. A opção `aria_snapshot(ref=True)` não existe na versão instalada.

## Opções consideradas

- `aria_snapshot()` sem refs: mostra a árvore, mas não dá como agir sobre um item.
- Localizadores por papel e nome: ambíguos quando há rótulos repetidos.
- JS injetado com atributo próprio: refs estáveis e curtas.

## Decisão

JS injetado. As ações usam o seletor `[data-pcref="b7"]`, que o Playwright reavalia no DOM ao vivo. Uma ref só fica obsoleta quando o elemento some; nesse caso o erro é `ELEMENT_STALE` e a sugestão é refazer o snapshot.

## Consequências

- O nome acessível é calculado de forma aproximada (aria-label, label, placeholder, texto).
- Cliques por texto ou seletor leem papel e nome ao vivo para aplicar a checagem de palavras de alto impacto.
