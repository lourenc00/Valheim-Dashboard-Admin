# Valheim Dashboard Admin

Conjunto de ferramentas para administração de servidor Valheim (Linux, BepInEx, `-crossplay`), contendo:

- **Dashboard Web** — painel com status, players, rank por tempo de jogo, proxy para Admin Powers
- **Discord Bot** — notificações de entrada/saída/morte/boss/eventos + 8 comandos slash
- **Admin Powers Plugin** — plugin BepInEx (porta 8091) com GodMode, HitKill, Invisível, NoStamina, NoHunger

Tudo roda **server-side** — nenhum mod necessário nos clients.

---

## Dashboard (`valheim-dashboard.py`)

Servidor web Flask na porta **8080**.

### Funcionalidades
- **Status do servidor** — online/offline, mapa, dia, versão
- **Players online** — cards com HP, Stamina, bioma
- **Admin Powers** — proxy para o endpoint `/admin` no plugin (porta 8091)
- **Ranking** — tempo de jogo acumulado por jogador (persistido em `valheim-dashboard-data.json`)
- **Proxy WebMap** — link para o mapa interativo web

### Endpoints
| Rota | Descrição |
|------|-----------|
| `/` | Dashboard HTML |
| `/api/player-sessions` | Sessões ativas dos jogadores |
| `/api/playtimes` | Tempo de jogo acumulado |
| `/api/rank` | Ranking ordenado por tempo |
| `/admin` | Proxy para Admin Powers (porta 8091) |

### Persistência
Sessões e playtimes são salvos em `valheim-dashboard-data.json`. Um jogador é marcado como ausente após 5 minutos sem heartbeat.

---

## Discord Bot (`valheim-discord.py`)

Bot Python (discord.py) conectado ao servidor Valheim via **OdinEye** (porta 4000) + monitoramento do log do servidor.

### Slash Commands (registrados como guild commands)

| Comando | Descrição |
|---------|-----------|
| `/status` | Mostra se o servidor está online, IP, senha |
| `/players` | Lista jogadores online com HP e Stamina |
| `/bosses` | Progresso dos bosses + próximo não derrotado |
| `/rank` | Ranking de tempo de jogo |
| `/map` | Link do WebMap interativo |
| `/update check` | Verifica se há atualização disponível |
| `/update apply` | (Admin) Aplica atualização — mata server, atualiza, reinicia |
| `/setchannel #canal` | (Admin) Define canal de notificações |
| `/ajuda` | Lista todos os comandos |

### Notificações Automáticas
- **Entrada** — quando um jogador conecta (cooldown de 30s entre notificações do mesmo player)
- **Saída** — quando um jogador desconecta ("Closing socket")
- **Morte** — detectada via novo ZDOID de jogador já online; cooldown de 15s por player
- **Boss derrotado** — lido da OdinEye `/bossDetails`; notifica uma vez por boss
- **Eventos** — raids como "A Floresta Está se Movendo", "O Chão Está Tremendo", etc. (com bioma, descrição e dica)
- **Servidor online/offline** — monitora o processo via `pgrep` e a linha "Game server connected" no log
- **Dia** — notifica ao amanhecer

### Arquitetura
- Thread `check_log_loop` — lê o log do servidor (`vhserver-console.log`) em tempo real, detecta ZDOID, Closing Socket, eventos
- Thread `check_bosses_loop` — consulta OdinEye a cada 60s para bosses, status, dia
- Estado persistido em `valheim-discord-state.json` (posição do log, notificações enviadas, bosses, etc.)
- Fuso horário: Brazil/Linhares (UTC-3)

### Configuração
```python
TOKEN = os.environ["DISCORD_TOKEN"]  # Token do bot Discord
```
Variáveis de ambiente necessárias:
- `DISCORD_TOKEN` — token do bot Discord

### Systemd Service
```ini
[Unit]
Description=Valheim Discord Bot
After=network.target

[Service]
Type=simple
User=vhserver
WorkingDirectory=/home/vhserver
ExecStart=/usr/bin/python3 /home/vhserver/valheim-discord.py
Restart=always
Environment=DISCORD_TOKEN=seu_token_aqui

[Install]
WantedBy=multi-user.target
```

---

## Admin Powers Plugin (`Plugin.cs`)

Plugin BepInEx (Harmony) que expõe poderes administrativos via HTTP na porta **8091**. Compila com `-nostdlib` + Unity BCL.

### Endpoints
| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/admin` | HTML com status dos toggles + formulário |
| POST | `/admin/toggle/{poder}` | Ativa/desativa um poder |
| GET | `/admin/players` | Lista jogadores no servidor |

### Poderes
| Poder | Patch | Efeito |
|-------|-------|--------|
| `godmode` | `RPC_Damage` | Anula todo dano recebido |
| `hitkill` | `RPC_Damage` | Dano causa morte instantânea no alvo |
| `invisible` | `InGhostMode` | Jogador fica invisível para mobs |
| `nostamina` | `HaveStamina` + `UseStamina` | Stamina nunca acaba |
| `nohunger` | [impossível server-side] | Sempre retorna `false` em `HaveFood` |

### Build
```bash
chmod +x build.sh
./build.sh
```
Requer:
- `mcs` (Mono C# compiler)
- `0Harmony.dll` (BepInEx)
- Unity BCL (`mscorlib.dll`, `System.dll`, etc.)

Gera `AdminPowers.dll` em `out/`.

### Como funciona
- Usa **Harmony Transpiler** no `RPC_Damage` para interceptar dano
- Estados (godmode, hitkill, etc.) são armazenados em `ZDOMan.instance.m_objectsByID` como ZDO bools por player
- Servidor HTTP escuta em `*:8091` via `HttpListener`
- Compatível com `-crossplay` — tudo roda server-side

---

## Port Map

| Porta | Serviço |
|-------|---------|
| 2456 | Valheim (game) |
| 2457 | Valheim (crossplay/P2P) |
| 3000 | WebMap (valheim-map.world) |
| 4000 | OdinEye (API de status) |
| 8080 | Dashboard Web |
| 8091 | Admin Powers Plugin |

---

## Dependências

### Dashboard
- Python 3 + Flask
- requests

### Discord Bot
- Python 3 + discord.py
- OdinEye rodando no servidor

### Admin Powers
- BepInEx 5.x no servidor Valheim
- Mono C# compiler (mcs) para build
- 0Harmony.dll

---

## Licença

MIT
