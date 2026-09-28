---
title: Modelo de Segurança
type: product
created: 2026-09-27
last_updated: 2026-09-28
status: active
related: ["[[MCP-PC-CONTROL]]", "[[Confirmação por diálogo nativo]]", "[[Fase 3 fora do escopo]]"]
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

## Pendências

- Indicador visual na bandeja ainda não existe; o kill switch avisa com bipe.
- Zonas de privacidade em capturas estão planejadas para a Fase 5.

## See Also

- [[Fase 3 fora do escopo]]
