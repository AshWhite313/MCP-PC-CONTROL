# Brain Index

Last rebuilt: 2026-09-28

> This index is auto-generated. Do not edit manually.
> Run `/brain rebuild-index` to regenerate.

## Knowledge

### concepts (1)

- **Ciclo Observar-Verificar** (also: Observar → Interpretar → Planejar → Executar → Verificar → Corrigir, computer use loop) - Princípio central do [[MCP-PC-CONTROL]]: um agente opera o computador em ciclos de observar, interpretar, planejar, executar, verificar e corrigir. - `concepts/ciclo-observar-verificar.md`

### processes (1)

- **CI no Windows Real** (also: GitHub Actions, ci.yml) - Processo de validação do [[MCP-PC-CONTROL]] em `.github/workflows/ci.yml`. - `processes/ci-windows.md`

### products (7)

- **Confirmação por diálogo nativo** (also: confirmation broker, canal de confirmação) - Ações destrutivas são confirmadas primeiro por um diálogo exibido pelo próprio servidor e só depois por elicitation do cliente MCP. - `products/mcp-pc-control/decisions/2026-09-27_confirmacao-nativa.md`
- **Fase 3 fora do escopo** (also: Fase 3, shell e processos) - A Fase 3 do roadmap (processos, arquivos, shell, clipboard e interação com o humano) não foi entregue nesta sessão. - `products/mcp-pc-control/decisions/2026-09-28_fase-3-fora-do-escopo.md`
- **MCP-PC-CONTROL** (also: pc-control, mcp-pc-control, MCP de controle do PC) - Servidor MCP local que permite a um agente de IA observar e operar um computador Windows 11. O repositório é `AshWhite313/MCP-PC-CONTROL`, branch de desenvolvimento `claude/vigilant-bardeen-s6z4af`. - `products/mcp-pc-control/overview.md`
- **Modelo de Segurança** (also: segurança, política, kill switch, auditoria) - Conjunto de controles do [[MCP-PC-CONTROL]]. A premissa é que o modelo não é uma fronteira de segurança: toda decisão é tomada pelo servidor, com base em política configurada pelo usuário. - `products/mcp-pc-control/features/seguranca.md`
- **Python e SDK MCP 2.x** (also: escolha da linguagem, ADR 0001) - O projeto usa Python 3.11+ e o SDK MCP oficial na versão 2.x. - `products/mcp-pc-control/decisions/2026-09-27_python-sdk-mcp-2.md`
- **UI Automation Tools** (also: ui_*, UIA tools, Fase 2) - Conjunto de 14 tools que encontram e acionam controles pelo nome, sem coordenadas. Entrou na Fase 2 de [[MCP-PC-CONTROL]]. - `products/mcp-pc-control/features/ui-automation.md`
- **Verificação com expect** (also: expect, effects, envelope de resultado) - Mecanismo que impede o agente de assumir que uma ação funcionou. Toda ação que muda estado pode declarar uma pós-condição, e todo resultado relata os efeitos colaterais observados. - `products/mcp-pc-control/features/verificacao-expect.md`

### systems (1)

- **Backend Windows** (also: platform/windows, backend Win32) - Implementação dos contratos de plataforma do [[MCP-PC-CONTROL]] para Windows 10 e 11, em `src/pc_control/platform/windows/`. - `systems/backend-windows.md`

## Work

### work/milestones (1)

- **Fase 4 Navegador** (also: browser_*, Playwright) - Próxima fase acordada com o usuário em 2026-09-28. - `work/milestones/fase-4-navegador.md`

### work/tasks (1)

- **Indicador na bandeja** (also: tray icon) - Mostrar um ícone na bandeja do Windows enquanto o agente controla o PC, com opção de parar e retomar. Hoje o kill switch só emite um bipe. Registrado como pendência em `docs/adr/0001-fundacao.md`. - `work/tasks/indicador-bandeja.md`
