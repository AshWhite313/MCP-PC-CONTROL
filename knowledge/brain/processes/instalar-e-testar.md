---
title: Instalar e Testar
type: process
created: 2026-10-01
last_updated: 2026-10-01
status: active
related: ["[[MCP-PC-CONTROL]]", "[[Hardening]]", "[[CI no Windows Real]]"]
sources: ["2026-10-01_sessao-mcp-pc-control-parte-2"]
aliases: ["instalação", "como usar", "Claude Desktop", "Claude Code"]
tags: [processo, instalacao]
---

# Instalar e Testar

Como o usuário instala o [[MCP-PC-CONTROL]] no próprio Windows e conecta um cliente MCP.

## Passos

1. Requisitos: Windows 10 ou 11, Python 3.11+, uv.
2. `git clone https://github.com/AshWhite313/MCP-PC-CONTROL` e `git checkout claude/vigilant-bardeen-s6z4af`.
3. `uv sync` e `uv run playwright install chromium`.
4. Opcional, para OCR: `uv sync --extra ocr` e um pacote de idioma do Windows.
5. `uv run mcp-pc-control --check` para o diagnóstico. Ver [[Hardening]].
6. Claude Desktop: em `%APPDATA%\Claude\claude_desktop_config.json`, servidor com `command: uv` e `args: ["--directory", "<pasta>", "run", "mcp-pc-control", "--policy", "config\\policy.default.toml"]`.
7. Claude Code: `claude mcp add pc-control -- uv --directory <pasta> run mcp-pc-control`.

## Recomendações

- Testar primeiro numa VM ou numa conta separada do Windows.
- Rodar como usuário comum, não administrador.
- Começar com `--level observe` e subir para `interact` e `operate` conforme a confiança.
- Para parar: `Ctrl+Alt+Shift+F12` ou o menu do ícone na bandeja.
- A política (`config/policy.default.toml`) controla nível, perfil, pastas permitidas, navegador, privacidade e auditoria.
- `mcp-pc-control --verify-audit <arquivo>` confere a integridade do log de auditoria.

## See Also

- [[CI no Windows Real]]
