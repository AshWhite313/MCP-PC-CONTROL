---
title: PathGuard antecipado
type: decision
created: 2026-10-01
last_updated: 2026-10-01
status: active
related: ["[[Navegador]]", "[[Arquivos, Clipboard e Processos]]", "[[Modelo de Segurança]]"]
sources: ["2026-09-28_adr-0002-fases-4-a-6", "2026-10-01_sessao-mcp-pc-control-parte-2"]
aliases: ["PathGuard", "pastas permitidas"]
tags: [adr, seguranca]
decision_date: 2026-09-28
impact: medium
---

# PathGuard antecipado

A validação de caminhos (`security/path_guard.py`) entrou na Fase 4, antes das tools de arquivos.

## Contexto

Downloads e uploads do [[Navegador]] precisam de pastas permitidas. O resto da Fase 3 estava fora do escopo.

## Decisão

Trazer só a parte de validação: raízes permitidas, padrões protegidos, resolução de links e junções antes da comparação, rejeição de caminhos de rede, de dispositivo e de fluxos alternativos (ADS). Pastas conhecidas são resolvidas por `platform/folders.py`, sem depender dos serviços de sistema da Fase 3.

## Consequências

O mesmo `PathGuard` serviu depois às tools de [[Arquivos, Clipboard e Processos]].
