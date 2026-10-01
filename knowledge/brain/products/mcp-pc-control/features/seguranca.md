---
title: Modelo de Segurança
type: product
created: 2026-09-27
last_updated: 2026-10-01
status: active
related: ["[[MCP-PC-CONTROL]]", "[[Confirmação por diálogo nativo]]", "[[Fase 3 fora do escopo]]", "[[Limitações e Riscos]]"]
sources: ["2026-09-28_sessao-mcp-pc-control"]
aliases: ["segurança", "política", "kill switch", "auditoria"]
tags: [seguranca]
---

# Modelo de Segurança

Conjunto de controles do [[MCP-PC-CONTROL]]. A premissa é que o modelo não é uma fronteira de segurança: toda decisão é tomada pelo servidor, com base em política configurada pelo usuário.

## Controles implementados

- Níveis `observe`, `interact`, `operate` e `full`. Padrão `interact`.
- Política em TOML (`config/policy.default.toml`); chaves desconhecidas são rejeitadas.
- Confirmação humana para ações destrutivas, ver [[Confirmação por diálogo nativo]]. Não existe parâmetro de confirmação que o modelo possa preencher.
- Clique em elemento com rótulo de alto impacto ("excluir", "pagar", "enviar", "transferir" e outros) pede confirmação, também por coordenadas.
- Kill switch global (`Ctrl+Alt+Shift+F12`): interrompe tudo e solta teclas e botões. Nenhuma tool o libera.
- Auditoria em JSON Lines encadeada por hash, verificável com `--verify-audit`. Texto digitado é registrado só pelo tamanho.
- Redação de cartão, CPF e chaves de API em resultados e logs.
- Limite de ações por minuto e ações de input serializadas.
- Janelas elevadas (UIPI), UAC e tela de bloqueio não são automatizadas: erros `ELEVATED_TARGET` e `SECURE_DESKTOP`.
- Processos protegidos nunca são encerrados por `window_close` forçado.

- Ícone na bandeja com parar/retomar, ver [[Hardening]].
- Zonas de privacidade: janelas de apps sensíveis ficam pretas em toda captura, ver [[OCR e Visão]].
- `PathGuard` limita arquivos, downloads e uploads a pastas permitidas, ver [[PathGuard antecipado]].
- Guarda de URL e perfil dedicado no [[Navegador]]; `browser_evaluate` desligado por padrão.
- Clipboard nunca lê conteúdo marcado como privado por gerenciadores de senha.
- Erros de parâmetros também saem estruturados e auditados.

## Pendências

- Pausar automaticamente quando o usuário usa mouse ou teclado ainda não existe.

## See Also

- [[Fase 3 fora do escopo]]
