---
title: Hardening
type: product
created: 2026-10-01
last_updated: 2026-10-01
status: active
related: ["[[MCP-PC-CONTROL]]", "[[Modelo de Segurança]]", "[[Instalar e Testar]]", "[[Indicador na bandeja]]"]
sources: ["2026-10-01_sessao-mcp-pc-control-parte-2", "2026-09-28_adr-0002-fases-4-a-6"]
aliases: ["Fase 6", "bandeja", "tray", "--check", "erros estruturados"]
tags: [fase-6, robustez]
---

# Hardening

Conjunto de melhorias de robustez da Fase 6 do [[MCP-PC-CONTROL]], entregue em 2026-09-28.

## Erros de parâmetros estruturados

O SDK MCP valida os argumentos antes de o código da tool rodar e, sem tratamento, devolvia texto livre. Uma extensão MCP (`mcp_interface/structured_errors.py`) intercepta `tools/call` e converte esses erros para o envelope padrão: `INVALID_ARGUMENT` com a lista de campos, ou `NOT_FOUND` para tool desconhecida. O erro também entra no log de auditoria.

## Ícone na bandeja

`platform/windows/tray.py` mantém uma janela oculta com loop de mensagens que serve à bandeja e ao atalho do kill switch.

- Ícone normal: uma IA pode controlar o PC. Ícone de alerta: automação parada.
- Clique direito abre menu com "Parar automação" ou "Retomar automação".
- Um aviso aparece quando o servidor inicia.
- Resolve a pendência [[Indicador na bandeja]].

## Diagnóstico

`mcp-pc-control --check` imprime o estado de: versão, política, backend, elevação, DPI, monitores, janelas, UI Automation, OCR, canal de confirmação, navegador, pastas permitidas, log de auditoria e atalho do kill switch. `--version` mostra a versão. Ver [[Instalar e Testar]].

## Encerramento limpo

Ao fechar o servidor, teclas e botões pressionados são soltos, o navegador é fechado e o ícone sai da bandeja.

## Validação

Testes de diagnóstico no backend simulado; no Windows real do CI, a bandeja é criada, alterna com o kill switch e encerra, e `--check` roda.

## See Also

- [[Modelo de Segurança]]
