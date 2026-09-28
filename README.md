# MCP-PC-CONTROL

Servidor MCP (Model Context Protocol) que permite a um agente de IA **observar e operar um computador
Windows** — mouse, teclado, janelas, tela — com verificação de cada ação e uma camada de segurança
proporcional ao poder da ferramenta.

- Arquitetura completa e roadmap: [`docs/PLANO_ARQUITETURA.md`](docs/PLANO_ARQUITETURA.md)
- Decisões de arquitetura: [`docs/adr/`](docs/adr/)

## Status

| Fase | Conteúdo | Situação |
|---|---|---|
| 0 | Fundação: pipeline de ações, envelope de resultado, erros, política, auditoria, kill switch, confirmação humana | ✅ |
| 1 | MVP "ver e agir": sistema, tela, mouse, teclado, janelas (29 tools) | ✅ testado no Windows real (CI) |
| 2 | UI Automation, esperas e verificação (16 tools) | ✅ testado no Windows real (CI) |
| 3 | Processos, arquivos, shell, clipboard | fora do escopo por ora (ver `docs/adr/`) |
| 4 | Navegador via Playwright (16 tools) | ✅ testado com Chromium real (CI) |
| 5–6 | OCR, visão, hardening | planejadas |

Total: 61 tools.

## Instalação

Requisitos: Windows 10/11, Python 3.11+ e [uv](https://docs.astral.sh/uv/).

```powershell
git clone https://github.com/AshWhite313/MCP-PC-CONTROL
cd MCP-PC-CONTROL
uv sync
uv run playwright install chromium   # baixa o navegador usado pelas tools browser_*
```

### Claude Desktop

Em `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "pc-control": {
      "command": "uv",
      "args": ["--directory", "C:\\caminho\\para\\MCP-PC-CONTROL", "run", "mcp-pc-control",
               "--policy", "config\\policy.default.toml"]
    }
  }
}
```

### Claude Code

```powershell
claude mcp add pc-control -- uv --directory C:\caminho\para\MCP-PC-CONTROL run mcp-pc-control
```

### Opções de linha de comando

| Opção | Descrição |
|---|---|
| `--policy ARQ.toml` | Arquivo de política (veja `config/policy.default.toml`) |
| `--level observe\|interact\|operate\|full` | Sobrescreve o nível de permissão |
| `--profile observe\|desktop\|full` | Sobrescreve o conjunto de tools exposto |
| `--backend fake` | Desktop simulado em memória (demonstração/testes, qualquer SO) |
| `--verify-audit ARQ.jsonl` | Verifica a cadeia de hashes de um log de auditoria |

## Tools disponíveis (fase 1)

| Módulo | Tools |
|---|---|
| Sistema | `system_info`, `desktop_state`, `session_status`, `wait_ms`, `wait_for_any` |
| Tela | `screen_list_monitors`, `screen_capture`, `screen_get_pixel` |
| Mouse | `mouse_move`, `mouse_click`, `mouse_down`, `mouse_up`, `mouse_drag`, `mouse_scroll`, `mouse_position` |
| Teclado | `keyboard_type`, `keyboard_press`, `keyboard_hotkey`, `keyboard_key_down`, `keyboard_key_up`, `input_release_all` |
| Janelas | `window_list`, `window_get_active`, `window_find`, `window_focus`, `window_set_state`, `window_move_resize`, `window_close`, `window_wait` |

Recursos para o agente:

- **Resultado estruturado** em toda tool: `ok`, mensagem, alvo, `effects` (janelas/diálogos que abriram ou
  fecharam, mudança de foco), `duration_ms`, `audit_id`; erros com `code` estável, `action_performed` e
  `suggestions`.
- **`expect`**: pós-condição verificada pelo servidor após a ação, sem corrida (a linha de base é capturada antes).
- **`space={"capture_id": ...}`**: clicar em coordenadas lidas de um screenshot reduzido; o servidor converte.
- Resources `pc://policy` e `pc://audit/recent`; prompt `computer_use_playbook`.

## Segurança

- **Níveis de permissão** (`observe` < `interact` < `operate` < `full`); padrão `interact`.
- **Confirmação humana** para ações destrutivas (ex.: `window_close` com `mode="force"`), por um diálogo
  nativo do próprio servidor ou por *elicitation* do cliente MCP. O modelo não tem como se autoaprovar:
  não existe parâmetro de confirmação, e ações de input ficam bloqueadas enquanto uma confirmação está pendente.
- **Kill switch**: `Ctrl+Alt+Shift+F12` (configurável) interrompe toda a automação e solta teclas/botões;
  pressione de novo para retomar. Não há tool que o desative.
- **Auditoria** em JSON Lines com encadeamento por hash (`--verify-audit`); o texto digitado não é registrado
  por padrão; padrões sensíveis (cartão, CPF, chaves de API) são redigidos.
- Janelas de processos elevados (administrador), UAC e tela de bloqueio **não** são automatizadas: o servidor
  retorna `ELEVATED_TARGET` / `SECURE_DESKTOP` para que o agente peça ajuda ao usuário.
- Screenshots e textos lidos da tela são enviados ao provedor do modelo configurado no seu cliente MCP.

## Desenvolvimento

```bash
uv sync
uv run ruff check src tests
uv run pytest                 # no Linux/macOS roda contra o desktop simulado
```

Os testes em `tests/windows/` abrem o Bloco de Notas, movem o mouse e digitam: rode-os apenas em uma VM ou
no CI, nunca no desktop que você está usando.
