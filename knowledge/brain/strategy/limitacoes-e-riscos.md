---
title: Limitações e Riscos
type: concept
created: 2026-10-01
last_updated: 2026-10-01
status: active
related: ["[[MCP-PC-CONTROL]]", "[[Modelo de Segurança]]", "[[Backend Windows]]", "[[Roadmap]]"]
sources: ["2026-09-27_plano-arquitetura"]
aliases: ["limitações técnicas", "riscos", "threat model"]
tags: [riscos, limitacoes]
---

# Limitações e Riscos

Limitações técnicas e riscos do [[MCP-PC-CONTROL]], resumidos das seções 7 a 9 do plano de arquitetura.

## Limitações técnicas

- A cobertura de UI Automation varia: boa em Win32, WinForms, WPF, UWP, Office e Chromium; parcial em Qt e Electron; nula em jogos, canvas e controles desenhados à mão (só OCR e visão).
- Sessões remotas (Citrix, RDP aninhado) chegam só como pixels.
- UIPI impede enviar input a janelas de processos elevados; o servidor retorna `ELEVATED_TARGET`.
- UAC, Ctrl+Alt+Del e tela de bloqueio ficam na área de trabalho segura, inacessível por projeto (`SECURE_DESKTOP`).
- RDP minimizado deixa de renderizar a sessão.
- Janelas minimizadas não são capturadas; conteúdo com DRM aparece preto.
- O Windows restringe `SetForegroundWindow`; o foco é sempre verificado.
- Alguns apps ignoram texto Unicode sintético; há modo por layout de teclado.
- Input sintético é identificável; o projeto não tenta mascarar isso.
- Não existe sinal universal de "interface pronta"; por isso o `expect`.
- Desde o Chrome 136, não é possível conectar ao perfil pessoal por depuração remota; daí o perfil dedicado.
- CAPTCHA e detecção de bots ficam fora de escopo e voltam para o usuário.

## Ameaças consideradas

Erro do modelo, injeção de prompt via conteúdo de tela, web ou arquivos (risco principal), cliente MCP comprometido, exposição de dados sensíveis em capturas, execução descontrolada e escalada de privilégio. A premissa é que o modelo não é fronteira de segurança.

## Riscos do projeto

| Risco | Mitigação |
|---|---|
| Injeção de prompt levando a ação destrutiva | Confirmação humana fora do alcance do modelo; conteúdo marcado como não confiável |
| Ação destrutiva por erro | Sem exclusão nas tools; confirmação para sobrescrever; auditoria |
| Vazamento de dados por screenshot | Zonas de privacidade; captura por janela ou região |
| UI Automation instável | Thread dedicada, timeouts, re-resolução de refs |
| Testes de GUI instáveis | Desktop simulado + Windows real no CI |
| Muitas tools confundindo o modelo | Perfis de tools |

## See Also

- [[Modelo de Segurança]]
