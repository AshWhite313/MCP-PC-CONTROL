---
title: Fase 3 fora do escopo
type: decision
created: 2026-09-28
last_updated: 2026-09-28
status: active
related: ["[[MCP-PC-CONTROL]]", "[[Modelo de Segurança]]", "[[Fase 4 Navegador]]"]
sources: ["2026-09-28_sessao-mcp-pc-control"]
aliases: ["Fase 3", "shell e processos"]
tags: [adr, escopo]
decision_date: 2026-09-28
impact: medium
---

# Fase 3 fora do escopo

A Fase 3 do roadmap (processos, arquivos, shell, clipboard e interação com o humano) não foi entregue nesta sessão.

## Contexto

Durante a implementação, a geração do assistente foi interrompida várias vezes pelo seu sistema de segurança na parte que dava ao agente acesso a shell, controle de processos e escrita de arquivos. O rascunho não foi publicado.

## Decisão

O assistente não reescreveu essa parte de outra forma, porque isso significaria testar o limite por tentativa e erro. O usuário aceitou seguir com a [[Fase 4 Navegador]], que não depende da Fase 3.

## Atualização (modelo simples)

A pedido do usuário, um recorte de baixo risco da Fase 3 foi entregue depois das Fases 4 a 6: arquivos
(listar, buscar, ler texto, propriedades, criar pasta, copiar e mover, sem exclusão e com confirmação para
sobrescrever), clipboard de texto (respeitando o marcador de conteúdo privado dos gerenciadores de senha) e
lista de processos somente leitura. Shell e encerrar ou iniciar processos continuam fora.

## Consequências

- A especificação da Fase 3 continua em `docs/PLANO_ARQUITETURA.md` e pode ser implementada fora desta sessão.
- O fluxo "baixar relatório e mover para a pasta Relatórios" passou a ser coberto de ponta a ponta com o modelo simples.

## See Also

- [[Modelo de Segurança]]
