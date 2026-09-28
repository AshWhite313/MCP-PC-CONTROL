---
title: Verificação com expect
type: product
created: 2026-09-27
last_updated: 2026-09-28
status: active
related: ["[[MCP-PC-CONTROL]]", "[[Ciclo Observar-Verificar]]", "[[UI Automation Tools]]"]
sources: ["2026-09-28_sessao-mcp-pc-control"]
aliases: ["expect", "effects", "envelope de resultado"]
tags: [verificacao]
---

# Verificação com expect

Mecanismo que impede o agente de assumir que uma ação funcionou. Toda ação que muda estado pode declarar uma pós-condição, e todo resultado relata os efeitos colaterais observados.

## Envelope de resultado

Cada tool devolve `ok`, `action`, `message`, `target`, `details`, `effects`, `duration_ms` e `audit_id`. Erros trazem `code` estável, `action_performed`, `retryable` e `suggestions`. O campo `action_performed` separa "não aconteceu" de "aconteceu com resultado diferente".

## expect

Parâmetro `expect: {any_of: [condições], timeout_ms}`. Tipos de condição: `window`, `pixel`, `element` e `screen`. A linha de base é capturada antes da ação, então "appears" significa "não existia antes". Se nada for atendido, o erro é `EXPECTATION_NOT_MET` com `action_performed: true`.

## effects

Diferença da lista de janelas antes e depois: janelas abertas (com `is_dialog` e `owner_hwnd`), fechadas, renomeadas, foco alterado e apps que pararam de responder. O cálculo acontece depois da espera do `expect`. A ordem inversa perdia diálogos que abriam durante a espera; o erro foi encontrado por um teste na Fase 1.

## Esperas

`wait_for_any`, `window_wait`, `ui_wait` e `screen_wait_change` usam o mesmo motor, com polling adaptativo de 50 ms a 500 ms e respeito ao kill switch.

## See Also

- [[Ciclo Observar-Verificar]]
