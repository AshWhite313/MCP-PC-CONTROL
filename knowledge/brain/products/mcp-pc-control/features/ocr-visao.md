---
title: OCR e Visão
type: product
created: 2026-09-28
last_updated: 2026-09-28
status: active
related: ["[[MCP-PC-CONTROL]]", "[[UI Automation Tools]]", "[[Modelo de Segurança]]"]
sources: ["2026-09-28_sessao-mcp-pc-control"]
aliases: ["screen_ocr", "screen_find_text", "anotação", "set-of-marks", "zonas de privacidade", "Fase 5"]
tags: [ocr, visao, fase-5]
---

# OCR e Visão

Recursos da Fase 5 do [[MCP-PC-CONTROL]] para apps que não expõem controles acessíveis.

## Tools e recursos

- `screen_ocr`: lê texto da tela (janela ou região) com OCR; retorna caixas de texto com posição.
- `screen_find_text`: localiza texto na tela, tentando primeiro UI Automation (exato e barato) e caindo para OCR; devolve o centro para clicar e, nos acertos por UIA, uma ref de elemento.
- `screen_capture` ganhou `annotate`: `grid` (linhas de coordenadas), `elements` (numera os controles, com refs) e `ocr` (numera os textos). O modelo aponta para um número em vez de adivinhar pixels (set-of-marks).

## Cascata de localização

Semântica antes de pixels: UI Automation → OCR → visão sobre screenshot anotado → coordenadas. `screen_find_text via=any` implementa os dois primeiros níveis.

## Privacidade

Janelas de processos marcados como sensíveis (`never_capture_processes`, ex.: gerenciadores de senha) são pintadas de preto em toda captura, antes de a imagem sair do servidor. Ver [[Modelo de Segurança]].

## OCR do Windows

Usa a API WinRT `Windows.Media.Ocr`, dependência opcional (`extra ocr`) que também exige pacote de idioma. Sem ela, o servidor funciona e o OCR retorna `BACKEND_UNAVAILABLE`. Nos testes, um backend de OCR simulado deriva o texto da árvore de elementos, de forma determinística.

## See Also

- [[Ciclo Observar-Verificar]]
