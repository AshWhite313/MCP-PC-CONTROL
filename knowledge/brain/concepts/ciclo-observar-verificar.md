---
title: Ciclo Observar-Verificar
type: concept
created: 2026-09-27
last_updated: 2026-09-28
status: active
related: ["[[MCP-PC-CONTROL]]", "[[Verificação com expect]]"]
sources: ["2026-09-28_sessao-mcp-pc-control"]
aliases: ["Observar → Interpretar → Planejar → Executar → Verificar → Corrigir", "computer use loop"]
tags: [conceito]
---

# Ciclo Observar-Verificar

Princípio central do [[MCP-PC-CONTROL]]: um agente opera o computador em ciclos de observar, interpretar, planejar, executar, verificar e corrigir.

## Definição

O modelo interpreta, planeja e corrige. O servidor fornece percepção confiável, ação precisa e verificação determinística. Nenhuma ação é considerada concluída só porque foi enviada.

## Como se manifesta

- Observar: `desktop_state`, `window_list`, `ui_snapshot`; screenshot só quando necessário.
- Localizar: primeiro semântica (UI Automation), depois OCR, depois visão sobre screenshot anotado, e coordenadas por último.
- Executar: tools pequenas e específicas.
- Verificar: `expect`, `effects` e as tools de espera, ver [[Verificação com expect]].
- Corrigir: erros com código estável, `action_performed` e sugestões.

O prompt MCP `computer_use_playbook` ensina esse ciclo ao agente.

## See Also

- [[UI Automation Tools]]
