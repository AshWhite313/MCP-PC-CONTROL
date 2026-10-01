# Brain Index

Last rebuilt: 2026-10-01

> This index is auto-generated. Do not edit manually.
> Run `/brain rebuild-index` to regenerate.

## Knowledge

### concepts (1)

- **Ciclo Observar-Verificar** (also: Observar → Interpretar → Planejar → Executar → Verificar → Corrigir, computer use loop) - Princípio central do [[MCP-PC-CONTROL]]: um agente opera o computador em ciclos de observar, interpretar, planejar, executar, verificar e corrigir. - `concepts/ciclo-observar-verificar.md`

### events (1)

- **Sessão de desenvolvimento do MCP-PC-CONTROL** (also: conversa, sessão Claude Code, histórico do projeto) - Sessão única de Claude Code em que o [[MCP-PC-CONTROL]] foi planejado e construído, de 2026-09-27 a 2026-10-01. - `events/2026-09-27_sessao-desenvolvimento.md`

### processes (2)

- **CI no Windows Real** (also: GitHub Actions, ci.yml) - Processo de validação do [[MCP-PC-CONTROL]] em `.github/workflows/ci.yml`. - `processes/ci-windows.md`
- **Instalar e Testar** (also: instalação, como usar, Claude Desktop, Claude Code) - Como o usuário instala o [[MCP-PC-CONTROL]] no próprio Windows e conecta um cliente MCP. - `processes/instalar-e-testar.md`

### products (15)

- **Arquivos, Clipboard e Processos** (also: Fase 3 modelo simples, fs_*, clipboard_*, process_list) - Recorte de baixo risco da Fase 3 do [[MCP-PC-CONTROL]], entregue em 2026-09-28 a pedido do usuário. As capacidades de shell e de iniciar ou encerrar processos ficaram de fora, ver [[Fase 3 fora do escopo]]. - `products/mcp-pc-control/features/arquivos-clipboard-processos.md`
- **Catálogo de Tools** (also: lista de tools, 75 tools, tools MCP) - Lista completa das 75 tools publicadas pelo [[MCP-PC-CONTROL]] em 2026-10-01, gerada a partir do registro do servidor. Nível é a permissão mínima; risco "destrutiva" pede confirmação humana; alguns riscos sobem conforme os parâmetros (ex.: `window_close` com `mode=force`, sobrescrever em `fs_copy`). - `products/mcp-pc-control/catalogo-tools.md`
- **Confirmação por diálogo nativo** (also: confirmation broker, canal de confirmação) - Ações destrutivas são confirmadas primeiro por um diálogo exibido pelo próprio servidor e só depois por elicitation do cliente MCP. - `products/mcp-pc-control/decisions/2026-09-27_confirmacao-nativa.md`
- **Fase 3 fora do escopo** (also: Fase 3, shell e processos) - A Fase 3 do roadmap (processos, arquivos, shell, clipboard e interação com o humano) não foi entregue nesta sessão. - `products/mcp-pc-control/decisions/2026-09-28_fase-3-fora-do-escopo.md`
- **Hardening** (also: Fase 6, bandeja, tray, --check, erros estruturados) - Conjunto de melhorias de robustez da Fase 6 do [[MCP-PC-CONTROL]], entregue em 2026-09-28. - `products/mcp-pc-control/features/hardening.md`
- **MCP-PC-CONTROL** (also: pc-control, mcp-pc-control, MCP de controle do PC) - Servidor MCP local que permite a um agente de IA observar e operar um computador Windows 11. O repositório é `AshWhite313/MCP-PC-CONTROL`, branch de desenvolvimento `claude/vigilant-bardeen-s6z4af`. - `products/mcp-pc-control/overview.md`
- **Modelo de Segurança** (also: segurança, política, kill switch, auditoria) - Conjunto de controles do [[MCP-PC-CONTROL]]. A premissa é que o modelo não é uma fronteira de segurança: toda decisão é tomada pelo servidor, com base em política configurada pelo usuário. - `products/mcp-pc-control/features/seguranca.md`
- **Navegador** (also: browser_*, Playwright, Fase 4) - 16 tools de automação de navegador via Playwright, adicionadas na Fase 4 do [[MCP-PC-CONTROL]]. - `products/mcp-pc-control/features/navegador.md`
- **OCR e Visão** (also: screen_ocr, screen_find_text, anotação, set-of-marks, zonas de privacidade, Fase 5) - Recursos da Fase 5 do [[MCP-PC-CONTROL]] para apps que não expõem controles acessíveis. - `products/mcp-pc-control/features/ocr-visao.md`
- **OCR opcional** (also: extra ocr, WinRT OCR) - O OCR do Windows (API WinRT `Windows.Media.Ocr`) é uma dependência opcional, instalada com `uv sync --extra ocr`. - `products/mcp-pc-control/decisions/2026-09-28_ocr-opcional.md`
- **PathGuard antecipado** (also: PathGuard, pastas permitidas) - A validação de caminhos (`security/path_guard.py`) entrou na Fase 4, antes das tools de arquivos. - `products/mcp-pc-control/decisions/2026-09-28_pathguard-antecipado.md`
- **Python e SDK MCP 2.x** (also: escolha da linguagem, ADR 0001) - O projeto usa Python 3.11+ e o SDK MCP oficial na versão 2.x. - `products/mcp-pc-control/decisions/2026-09-27_python-sdk-mcp-2.md`
- **Refs do navegador por JS injetado** (also: data-pcref, snapshot do navegador) - O snapshot de página do [[Navegador]] é feito por JavaScript injetado, que marca cada elemento interativo com o atributo `data-pcref` e devolve uma lista com papel, nome, valor e estado. - `products/mcp-pc-control/decisions/2026-09-28_refs-navegador.md`
- **UI Automation Tools** (also: ui_*, UIA tools, Fase 2) - Conjunto de 14 tools que encontram e acionam controles pelo nome, sem coordenadas. Entrou na Fase 2 de [[MCP-PC-CONTROL]]. - `products/mcp-pc-control/features/ui-automation.md`
- **Verificação com expect** (also: expect, effects, envelope de resultado) - Mecanismo que impede o agente de assumir que uma ação funcionou. Toda ação que muda estado pode declarar uma pós-condição, e todo resultado relata os efeitos colaterais observados. - `products/mcp-pc-control/features/verificacao-expect.md`

### strategy (1)

- **Limitações e Riscos** (also: limitações técnicas, riscos, threat model) - Limitações técnicas e riscos do [[MCP-PC-CONTROL]], resumidos das seções 7 a 9 do plano de arquitetura. - `strategy/limitacoes-e-riscos.md`

### systems (1)

- **Backend Windows** (also: platform/windows, backend Win32) - Implementação dos contratos de plataforma do [[MCP-PC-CONTROL]] para Windows 10 e 11, em `src/pc_control/platform/windows/`. - `systems/backend-windows.md`

## Work

### work/milestones (2)

- **Fase 4 Navegador** (also: browser_*, Playwright) - Próxima fase acordada com o usuário em 2026-09-28. - `work/milestones/fase-4-navegador.md`
- **Roadmap** (also: fases, plano de fases) - Fases definidas no plano de arquitetura (`docs/PLANO_ARQUITETURA.md`, seção 11) e seu estado em 2026-10-01. - `work/milestones/roadmap.md`

### work/tasks (1)

- **Indicador na bandeja** (also: tray icon) - Mostrar um ícone na bandeja do Windows enquanto o agente controla o PC, com opção de parar e retomar. Hoje o kill switch só emite um bipe. Registrado como pendência em `docs/adr/0001-fundacao.md`. - `work/tasks/indicador-bandeja.md`
