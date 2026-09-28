---
title: Confirmação por diálogo nativo
type: decision
created: 2026-09-27
last_updated: 2026-09-28
status: active
related: ["[[Modelo de Segurança]]", "[[MCP-PC-CONTROL]]"]
sources: ["2026-09-28_sessao-mcp-pc-control"]
aliases: ["confirmation broker", "canal de confirmação"]
tags: [adr, seguranca]
decision_date: 2026-09-27
impact: high
---

# Confirmação por diálogo nativo

Ações destrutivas são confirmadas primeiro por um diálogo exibido pelo próprio servidor e só depois por elicitation do cliente MCP.

## Contexto

A elicitation é respondida pelo cliente MCP, que pode ser automatizado. Um diálogo local só pode ser respondido por quem está diante do computador.

## Decisão

- Ordem padrão dos canais: `native_dialog`, depois `elicitation`. Sem canal disponível, a ação é negada com `CONFIRMATION_REQUIRED`.
- Tempo esgotado conta como rejeição.
- Enquanto uma confirmação está pendente, todas as tools que mudam estado são recusadas. Sem isso, o agente poderia clicar em "Sim" no próprio diálogo. A brecha foi percebida durante a implementação da Fase 0 e fechada com teste.
- Tools podem adiar a confirmação para depois de inspecionar o alvo; o runner impede qualquer efeito antes dela.

## See Also

- [[Modelo de Segurança]]
