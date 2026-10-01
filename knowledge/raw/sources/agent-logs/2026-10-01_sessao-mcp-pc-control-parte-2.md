# Sessão Claude Code: MCP-PC-CONTROL, parte 2 (2026-09-28 a 2026-10-01)

Continuação de `2026-09-28_sessao-mcp-pc-control`. Registro imutável.

## Linha do tempo

1. Brain criado no formato do brain-template enviado pelo usuário (commit b451811).
2. Fase 4, navegador (commits 495a211, 5aa4d7e): 16 tools `browser_*` com Playwright.
   - `page.accessibility` foi removido do Playwright atual e `aria_snapshot(ref=True)` não existe na versão
     usada. Solução: JS injetado marca elementos interativos com `data-pcref` (refs b1, b2...).
   - O ambiente de desenvolvimento tem Chromium pré-instalado em `/opt/pw-browsers`, de build diferente do
     esperado pelo Playwright instalado; foi preciso apontar `executable_path`.
   - Primeiro CI falhou porque `playwright` não estava declarado em `pyproject.toml` (fora instalado à mão
     no venv). Corrigido declarando a dependência; CI passou a rodar `playwright install chromium`.
   - Teste revelou que clique por texto/seletor não passava pela checagem de palavras de alto impacto (só
     por ref). Corrigido lendo papel e nome do elemento ao vivo.
   - Peças pequenas da Fase 3 foram trazidas por serem necessárias e seguras: `PathGuard` (validação de
     caminho), `FilesystemConfig`, código `PATH_NOT_ALLOWED`, confirmação adiada (`deferred_confirmation`) e
     um resolvedor de pastas conhecidas próprio (`platform/folders.py`).
3. Fase 5, OCR e visão (commit 9047d1a): `screen_ocr`, `screen_find_text`, anotação de capturas
   (`grid`, `elements`, `ocr`), zonas de privacidade. OCR do Windows via WinRT como extra opcional; OCR
   simulado nos testes deriva o texto da árvore de elementos.
4. O modelo da sessão foi trocado pelo usuário para claude-opus-5-5 durante a Fase 6.
5. Fase 6, hardening (commit 60af9ef): extensão MCP converte erros de validação do SDK para o envelope
   padrão; ícone na bandeja com parar/retomar; `--check` e `--version`; encerramento limpo.
6. Modelo simples da Fase 3, a pedido do usuário (commit 1f6e710): 8 tools de arquivos, 3 de clipboard,
   `process_list`. Sem shell, sem iniciar ou encerrar processos, sem exclusão de arquivos.
7. Estado final: 75 tools, 141 testes no Linux, CI verde no Windows real. O rascunho original da Fase 3
   ficou apenas num `git stash` local do contêiner temporário, nunca publicado.

## Pedidos e preferências do usuário

- Delegou as decisões técnicas ("pode fazer da forma que achar melhor, eu confio em você").
- Vai testar depois, no próprio PC.
- Pediu para guardar o conhecimento no formato do brain-template e perguntou se o brain estava completo.
- Pediu que a Fase 3 fosse entregue ao menos como modelo simples.
- Comunicação em português do Brasil.

## Fatos técnicos

- Extensões MCP (`mcp.server.extension.Extension`) podem interceptar `tools/call`; usado para erros.
- O runner do GitHub Actions Windows roda como administrador; `--check` aponta isso como alerta.
- Bandeja e hotkey compartilham uma janela oculta com loop de mensagens (`platform/windows/tray.py`).
- Clipboard: conteúdo com o formato `ExcludeClipboardContentFromMonitorProcessing` nunca é lido.
