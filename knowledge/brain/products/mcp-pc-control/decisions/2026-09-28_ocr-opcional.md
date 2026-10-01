---
title: OCR opcional
type: decision
created: 2026-10-01
last_updated: 2026-10-01
status: active
related: ["[[OCR e Visão]]", "[[CI no Windows Real]]"]
sources: ["2026-09-28_adr-0002-fases-4-a-6"]
aliases: ["extra ocr", "WinRT OCR"]
tags: [adr, ocr]
decision_date: 2026-09-28
impact: low
---

# OCR opcional

O OCR do Windows (API WinRT `Windows.Media.Ocr`) é uma dependência opcional, instalada com `uv sync --extra ocr`.

## Contexto

Os bindings WinRT mudaram de pacote (`winsdk` para `winrt-Windows-*`) e o OCR ainda exige pacote de idioma no Windows. Como dependência obrigatória, poderiam quebrar a instalação e o CI.

## Decisão

- Importação preguiçosa, compatível com os dois pacotes.
- Sem bindings, `screen_ocr` retorna `BACKEND_UNAVAILABLE` e sugere UI Automation.
- `screen_find_text` tenta UI Automation antes de OCR.
- Nos testes, um OCR simulado deriva o texto da árvore de elementos, de forma determinística.

## Consequências

O OCR real não é exercitado no CI. O teste de fumaça no Windows aceita sucesso ou indisponibilidade.
