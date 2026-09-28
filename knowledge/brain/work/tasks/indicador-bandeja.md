---
title: Indicador na bandeja
type: task
created: 2026-09-28
last_updated: 2026-09-28
status: archived
related: ["[[Modelo de Segurança]]"]
sources: ["2026-09-28_sessao-mcp-pc-control"]
aliases: ["tray icon"]
tags: [pendencia]
knowledge_refs: ["products/mcp-pc-control/features/seguranca"]
priority: p2
---

# Indicador na bandeja

Mostrar um ícone na bandeja do Windows enquanto o agente controla o PC, com opção de parar e retomar. Hoje o kill switch só emite um bipe. Registrado como pendência em `docs/adr/0001-fundacao.md`.

Pendência relacionada: devolver erros estruturados também quando o SDK rejeita parâmetros de tipo inválido.

## Resolução

Concluído na Fase 6 (2026-09-28): ícone na bandeja com menu parar/retomar e ícone de alerta quando a
automação está parada; erros de validação passaram a sair no envelope estruturado. Ver `docs/adr/0002-fases-4-a-6.md`.
