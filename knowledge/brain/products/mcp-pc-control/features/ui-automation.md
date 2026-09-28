---
title: UI Automation Tools
type: product
created: 2026-09-28
last_updated: 2026-09-28
status: active
related: ["[[MCP-PC-CONTROL]]", "[[Backend Windows]]", "[[Verificação com expect]]"]
sources: ["2026-09-28_sessao-mcp-pc-control"]
aliases: ["ui_*", "UIA tools", "Fase 2"]
tags: [uia, fase-2]
---

# UI Automation Tools

Conjunto de 14 tools que encontram e acionam controles pelo nome, sem coordenadas. Entrou na Fase 2 de [[MCP-PC-CONTROL]].

## Tools

`ui_snapshot`, `ui_find`, `ui_get`, `ui_element_at`, `ui_get_text`, `ui_click`, `ui_set_value`, `ui_select`, `ui_toggle`, `ui_expand`, `ui_scroll_into_view`, `ui_focus`, `ui_menu_select`, `ui_wait`.

## Referências de elementos

Cada elemento recebe uma ref curta (`e14`). A ref guarda o handle do backend e um localizador (nome, tipo, AutomationId, classe, janela). Quando a interface se redesenha, o servidor reencontra o elemento pelo localizador e informa `re_resolved: true`.

## Comportamento

- `ui_snapshot` devolve a árvore em texto compacto, uma linha por elemento, como bloco de texto separado do JSON.
- `ui_click` tenta Invoke, Toggle, SelectionItem, ExpandCollapse e ação padrão legada, depois clique real no ponto clicável. O resultado informa `method_used` e `fallbacks_tried`.
- `ui_set_value` define o valor e relê para confirmar; em falha, foca, seleciona tudo e digita.
- Seletores ambíguos são recusados com `AMBIGUOUS_MATCH` e a lista de candidatos com refs.
- A comparação de nomes ignora maiúsculas, acentos, `&` de atalho e reticências finais.
- Campos de senha nunca são lidos nem registrados.

## Validação

No Bloco de Notas do runner Windows do CI: snapshot, preenchimento verificado, leitura de texto, menu até o diálogo "Sobre" e clique em OK pelo nome.

## See Also

- [[Backend Windows]]
- [[Modelo de Segurança]]
