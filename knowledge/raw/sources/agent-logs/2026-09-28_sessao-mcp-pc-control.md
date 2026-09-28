# Sessão Claude Code: MCP-PC-CONTROL (2026-09-27 a 2026-09-28)

Registro imutável da sessão de desenvolvimento. Fonte para as páginas em `brain/`.

## Pedido inicial

O usuário pediu o projeto de um servidor MCP de "computer use" para Windows 11: uma IA deve observar,
interpretar, planejar, executar, verificar e corrigir ações no PC (mouse, teclado, janelas, processos,
arquivos, shell, clipboard, UI Automation, navegador), com segurança proporcional, observabilidade,
verificação de ações e arquitetura separando interface MCP e backend por sistema operacional.
Pediu primeiro análise, arquitetura, stack, tools, limitações, riscos, segurança, pastas, roadmap e testes.

## Linha do tempo

1. Plano escrito em `docs/PLANO_ARQUITETURA.md` (commit ff39378). Sete fases de roadmap.
2. O usuário delegou as decisões ("pode fazer da forma que achar melhor"). Escolhas: Python, nível padrão
   `interact`, descrições das tools em inglês, perfil de navegador dedicado.
3. Fases 0 e 1 implementadas (commit 05da41c): pipeline de ações, 29 tools, backend Windows via ctypes,
   backend simulado, 85 testes. CI no Windows real encontrou um bug: restaurar janela minimizada a partir de
   maximizada voltava a maximizar. Corrigido em 8426886.
4. Fase 2 implementada (commit 93d6ef4): 14 tools de UI Automation via comtypes, `screen_diff`,
   `screen_wait_change`, condições de elemento e de tela, confirmação por palavras de alto impacto.
   CI no Windows real passou após aceitar editores do Bloco de Notas expostos como `Document` (80ebee0).
5. Fase 3 (shell, processos, escrita de arquivos, clipboard) foi iniciada, mas a geração foi interrompida
   várias vezes pelo sistema de segurança do assistente. O rascunho não foi publicado. O assistente decidiu
   não reescrever essa parte de outra forma para evitar testar o limite por tentativa e erro. O usuário
   concordou em seguir com a Fase 4.
6. O usuário enviou um modelo de "segundo cérebro" (brain-template) e pediu que o conhecimento da conversa
   fosse guardado nesse formato.

## Fatos técnicos relevantes

- SDK MCP Python 2.x: `FastMCP` virou `mcp.server.mcpserver.MCPServer`; tools retornam `CallToolResult`.
- Testes assíncronos usam o plugin pytest do anyio, porque o pytest-asyncio encerra fixtures em outra task.
- comtypes inicializa COM na thread do primeiro import; a UI Automation roda numa thread MTA dedicada.
- Efeitos colaterais de uma ação são medidos depois da espera do `expect`, senão diálogos tardios somem.
- Enquanto uma confirmação humana está pendente, tools que mudam estado são recusadas.
- Runners Windows do GitHub Actions permitem testes reais de GUI (Bloco de Notas, SendInput, UIA).
