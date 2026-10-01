---
title: Arquivos, Clipboard e Processos
type: product
created: 2026-10-01
last_updated: 2026-10-01
status: active
related: ["[[MCP-PC-CONTROL]]", "[[Fase 3 fora do escopo]]", "[[Modelo de Segurança]]", "[[Navegador]]"]
sources: ["2026-10-01_sessao-mcp-pc-control-parte-2"]
aliases: ["Fase 3 modelo simples", "fs_*", "clipboard_*", "process_list"]
tags: [fase-3, arquivos]
---

# Arquivos, Clipboard e Processos

Recorte de baixo risco da Fase 3 do [[MCP-PC-CONTROL]], entregue em 2026-09-28 a pedido do usuário. As capacidades de shell e de iniciar ou encerrar processos ficaram de fora, ver [[Fase 3 fora do escopo]].

## Arquivos (8 tools)

`fs_known_folders`, `fs_list`, `fs_search`, `fs_stat`, `fs_read`, `fs_mkdir`, `fs_copy`, `fs_move`.

- Todo caminho passa pelo `PathGuard`: só pastas permitidas (padrão: Downloads, Documentos, Área de Trabalho e `~/AgentWorkspace`), padrões protegidos bloqueados (`.ssh`, `.aws`, `*.kdbx`, `.env`, perfis de navegador, credenciais do Windows), links simbólicos que saem da área permitida recusados.
- `known:Downloads` e similares seguem a pasta real, inclusive redirecionada pelo OneDrive.
- `fs_read` lê texto com detecção de codificação e recusa binários; o conteúdo é marcado como não confiável.
- Não existe exclusão. Substituir arquivo existente em `fs_copy`/`fs_move` pede confirmação humana.
- Criar, copiar e mover exigem nível `operate`.

## Clipboard (3 tools)

`clipboard_get`, `clipboard_set`, `clipboard_clear`. Somente texto. Conteúdo que um gerenciador de senhas marcou como privado (`ExcludeClipboardContentFromMonitorProcessing`) nunca é lido. O texto definido não vai para o log.

## Processos (1 tool)

`process_list`, somente leitura via psutil: pid, nome, memória, CPU e se o processo tem janelas.

## Fluxo coberto

Baixar relatório no [[Navegador]], criar a pasta Relatórios, mover o arquivo e lê-lo, testado de ponta a ponta.

## See Also

- [[Catálogo de Tools]]
