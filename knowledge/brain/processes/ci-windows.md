---
title: CI no Windows Real
type: process
created: 2026-09-27
last_updated: 2026-09-28
status: active
related: ["[[Backend Windows]]", "[[MCP-PC-CONTROL]]"]
sources: ["2026-09-28_sessao-mcp-pc-control"]
aliases: ["GitHub Actions", "ci.yml"]
tags: [ci, testes]
---

# CI no Windows Real

Processo de validação do [[MCP-PC-CONTROL]] em `.github/workflows/ci.yml`.

## Etapas

1. Job Linux: `uv sync`, ruff e pytest contra o desktop simulado.
2. Job Windows (`windows-latest`): pytest completo, incluindo `tests/windows/test_smoke.py`, que abre o Bloco de Notas, digita, usa atalhos, manipula a janela e usa UI Automation.

## Observações

- O runner Windows hospedado tem sessão interativa: SendInput, captura de tela e UI Automation funcionam.
- Nos testes, o diálogo nativo de confirmação é substituído por uma função, para não bloquear o CI.
- O CI encontrou dois problemas reais: a restauração de janela minimizada e o editor do Bloco de Notas exposto como `Document`.
- Testes de GUI nunca devem rodar no desktop pessoal do desenvolvedor.

## See Also

- [[Backend Windows]]
