# Valheim Dashboard Admin

Conjunto de ferramentas para administração de servidor Valheim rodando em Linux com BepInEx e `-crossplay`. Contém:

- **Dashboard Web** — painel com status, players online, ranking por tempo de jogo, proxy para Admin Powers
- **Discord Bot** — notificações em tempo real (entrada/saída/morte/boss/eventos) + 8 comandos slash
- **Admin Powers Plugin** — plugin BepInEx (porta 8091) com GodMode, HitKill, Invisível, NoStamina

Tudo roda **server-side** — nenhum mod necessário nos clients.

---

## Índice

- [0. Servidor Valheim (LinuxGSM)](#0-instalação-do-servidor-valheim-linuxgsm)
- [0.B BepInEx](#0b-bepinex-para-plugins-server-side)
- [0.C OdinEye](#0c-odineye-api-de-status)
- [0.D Python 3](#0d-python-3-para-dashboard-e-discord-bot)
- [0.E Mono Compiler](#0e-mono-compiler-para-build-do-admin-powers)
- [1. Dashboard Web](#1-dashboard-web-valheim-dashboardpy)
- [2. Discord Bot](#2-discord-bot-valheim-discordpy)
- [3. Admin Powers Plugin](#3-admin-powers-plugin-plugincs)
- [4. WebMap](#4-webmap)
- [Port Map](#port-map)

---

## 0. Instalação do Servidor Valheim (LinuxGSM)

### 0.1 Criar usuário dedicado
```bash
sudo adduser vhserver
sudo passwd vhserver  # defina uma senha
su - vhserver
```

### 0.2 Instalar LinuxGSM
```bash
# Como usuário vhserver
wget -O linuxgsm.sh https://linuxgsm.sh
chmod +x linuxgsm.sh
./linuxgsm.sh vhserver
```

### 0.3 Instalar o Valheim Server
```bash
./vhserver install
```
Durante a instalação, o LinuxGSM pergunta:
- `Server Name`: nome do servidor (ex: "Meu Servidor")
- `Server Password`: senha do servidor
- `Steam user`: deixe em branco (anônimo)

A instalação baixa o Valheim dedicado (~2GB) via SteamCMD para:
```
/home/vhserver/serverfiles/
```

### 0.4 Configurar o servidor

Editar `/home/vhserver/lgsm/config-lgsm/vhserver/vhserver.cfg`:

```ini
# Configurações básicas
servername="TENTANDO NAO MORRER"
serverpassword="SUA_SENHA"
port="2456"
world="Valheim-com-amigos"
maxplayers="10"

# Parâmetros extras do servidor
# Se quiser crossplay (jogar com Xbox/Windows Store), adicione:
# -crossplay
# Se quiser senha administrativa:
# -savedir /home/vhserver/serverfiles/saves
```

### 0.5 Comandos LinuxGSM úteis

| Comando | Descrição |
|---------|-----------|
| `./vhserver start` | Inicia o servidor |
| `./vhserver stop` | Para o servidor |
| `./vhserver restart` | Reinicia |
| `./vhserver monitor` | Monitora e reinicia se cair |
| `./vhserver console` | Abre o console interativo |
| `./vhserver details` | Mostra informações do servidor |
| `./vhserver update` | Atualiza o Valheim |
| `./vhserver update-lgsm` | Atualiza o LinuxGSM |
| `./vhserver backup` | Faz backup do mundo |
| `./vhserver debug` | Inicia em modo debug |

### 0.6 Systemd Service (recomendado)

Para o servidor iniciar automaticamente com o sistema:

```bash
# Como root ou com sudo
sudo ./vhserver install-systemd
sudo systemctl enable vhserver
sudo systemctl start vhserver
```

Verificar status:
```bash
systemctl status vhserver
```

### 0.7 Firewall

```bash
sudo ufw allow 2456/udp
sudo ufw allow 2457/udp  # necessário para -crossplay
sudo ufw enable
```

### 0.8 Verificar instalação

```bash
# O servidor pode levar alguns minutos para iniciar
# Acompanhe o log:
tail -f /home/vhserver/log/console/vhserver-console.log

# Quando estiver pronto, deve aparecer:
# "Game server connected"
# "Game Server ID: ..."
```

### 0.9 Testar conexão

- **IP do servidor**: `http://SEU_IP:2456`
- **No jogo**: Abra o Valheim → **Join Game** → **IP connect** → digite `SEU_IP:2456` e a senha

---

## 0.B BepInEx (para plugins server-side)

BepInEx é necessário para carregar plugins como OdinEye, Admin Powers e WebMap no servidor.

### Instalação
```bash
cd /home/vhserver/serverfiles/

# Baixar BepInEx Pack para Valheim
wget https://valheim.thunderstore.io/package/download/denikson/BepInExPack_Valheim/5.4.2202/
unzip 5.4.2202
rm 5.4.2202
```

### Estrutura esperada
```
serverfiles/
├── BepInEx/
│   ├── core/
│   │   └── 0Harmony.dll
│   ├── plugins/
│   │   └── (coloque os .dll dos plugins aqui)
│   ├── config/
│   │   └── (configurações dos plugins)
│   └── patchers/
├── valheim_server.x86_64
├── start_server_bepinex.sh    ← script gerado pelo BepInEx
└── linux64/
    └── lib_bepinex.so
```

### Script de inicialização

O BepInEx gera `start_server_bepinex.sh` com o comando correto para iniciar o servidor carregando os plugins. Edite-o se necessário:

```bash
#!/bin/bash
export LD_LIBRARY_PATH=./linux64:$LD_LIBRARY_PATH
export SteamAppId=892970

./valheim_server.x86_64 \
  -name "TENTANDO NAO MORRER" \
  -port 2456 \
  -world "Valheim-com-amigos" \
  -password "SUA_SENHA" \
  -crossplay \
  -public 1 \
  -savedir "/home/vhserver/serverfiles/saves"
```

**Importante**: O servidor DEVE ser iniciado com `start_server_bepinex.sh`, NÃO com o comando `./vhserver start` do LinuxGSM, para que os plugins carreguem.

### Iniciar com tmux
```bash
tmux new-session -d -s vhserver './start_bepinex.sh'
```

Para anexar ao tmux e ver o console:
```bash
tmux attach -t vhserver
# Para sair do tmux sem matar: Ctrl+B, D
```

---

## 0.C OdinEye (API de status)

OdinEye expõe uma API HTTP com informações do servidor Valheim (players, bosses, dia, etc.) na porta **4000**.

### Instalação
```bash
# Baixar OdinEye da Thunderstore
# Link: https://thunderstore.io/c/valheim/p/Guiraud_Olivier/OdinEye/
# Ou via dotnet (se tiver):
# dotnet tool install -g Thunderstore.CLI
# thunderstore download Guiraud_Olivier/OdinEye

# Copiar para os plugins do BepInEx
cp OdinEye.dll /home/vhserver/serverfiles/BepInEx/plugins/
```

### Verificar
```bash
# Após iniciar o servidor com start_server_bepinex.sh:
curl http://localhost:4000/status
# Deve retornar JSON com informações do servidor
```

### Endpoints da OdinEye
| Rota | Descrição |
|------|-----------|
| `/status` | Status geral do servidor |
| `/players` | Lista de jogadores online |
| `/bossDetails` | Status de derrota dos bosses |
| `/info` | Informações do servidor (nome, versão, dia) |

---

## 0.D Python 3 (para Dashboard e Discord Bot)

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv

# Opcional: criar virtualenv
python3 -m venv /home/vhserver/venv
source /home/vhserver/venv/bin/activate
pip install flask requests discord.py
```

---

## 0.E Mono Compiler (para build do Admin Powers)

```bash
sudo apt install mono-mcs
```

Este compilador é usado apenas para compilar o plugin `AdminPowers.dll` a partir do `Plugin.cs`. Não é necessário no servidor se você já tiver a DLL pré-compilada.

---

## 1. Dashboard Web (`valheim-dashboard.py`)

Servidor web Flask na porta **8080**. Mostra status do servidor, players online, ranking, e faz proxy para o Admin Powers.

### Instalação

```bash
# Criar venv e instalar dependências
python3 -m venv /home/vhserver/venv
source /home/vhserver/venv/bin/activate
pip install flask requests

# Copiar o script
cp valheim-dashboard.py /home/vhserver/
```

### Execução Manual
```bash
source /home/vhserver/venv/bin/activate
python3 /home/vhserver/valheim-dashboard.py
```

### Systemd Service (opcional)

Criar `/etc/systemd/system/valheim-dashboard.service`:

```ini
[Unit]
Description=Valheim Dashboard
After=network.target

[Service]
Type=simple
User=vhserver
WorkingDirectory=/home/vhserver
ExecStart=/home/vhserver/venv/bin/python3 /home/vhserver/valheim-dashboard.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable valheim-dashboard
sudo systemctl start valheim-dashboard
```

### Funcionalidades
- **Status do servidor** — online/offline, mapa, dia, versão (via OdinEye)
- **Players online** — cards com HP, Stamina, bioma, ZDOID
- **Admin Powers** — proxy para `http://localhost:8091/admin`
- **Ranking** — tempo de jogo acumulado por jogador, persistido em `valheim-dashboard-data.json`
- **Auto-detecção de ausência** — jogador marcado como away após 5 min sem heartbeat

### Endpoints da API
| Rota | Descrição |
|------|-----------|
| `/` | Dashboard HTML |
| `/api/player-sessions` | Sessões ativas (nome, HP, stamina, bioma, status) |
| `/api/playtimes` | Tempo de jogo acumulado por jogador |
| `/api/rank` | Ranking ordenado por tempo (decrescente) |
| `/admin` | Proxy reverso para Admin Powers (porta 8091) |

### Arquivo de Dados
`valheim-dashboard-data.json` — criado automaticamente na mesma pasta do script. Contém:
- `playtimes`: dicionário `{jogador: segundos_total}`
- `sessions`: dicionário `{jogador: {login, last_heartbeat}}`

---

## 2. Discord Bot (`valheim-discord.py`)

Bot Python que monitora o servidor Valheim via OdinEye + log do console e envia notificações para o Discord.

### Pré-requisitos no Discord

1. Acesse https://discord.com/developers/applications
2. Crie uma **New Application**
3. Vá em **Bot** → **Add Bot**
4. Em **Token**, clique em **Reset Token** e copie o token gerado
5. Ative as **Intents**: `MESSAGE CONTENT INTENT`, `SERVER MEMBERS INTENT`
6. Vá em **OAuth2** → **URL Generator**
   - Scopes: `bot`, `applications.commands`
   - Permissions: `Send Messages`, `Embed Links`, `Read Message History`
   - Copie a URL gerada e abra no navegador para adicionar o bot ao servidor

### Instalação

```bash
# Instalar dependências
pip install discord.py

# Copiar o script
cp valheim-discord.py /home/vhserver/

# Configurar token via variável de ambiente
export DISCORD_TOKEN="seu_token_aqui"
```

### Variáveis de Ambiente

| Variável | Obrigatório | Descrição |
|----------|-------------|-----------|
| `DISCORD_TOKEN` | Sim | Token do bot Discord |

### Configuração Interna

No topo do script, ajuste se necessário:

```python
LOG_FILE = "/home/vhserver/log/console/vhserver-console.log"  # Caminho do log do Valheim
STATE_FILE = "/home/vhserver/valheim-discord-state.json"       # Estado persistente do bot
ODINEYE_URL = "http://localhost:4000"                          # URL da OdinEye
```

E nas mensagens de notificação, substitua o domínio e senha:

```python
# Ocorre em 3 lugares no código (notificações de server online /status /update apply)
# Substitua SEU_DOMINIO e SUA_SENHA pelos valores do seu servidor
```

### Slash Commands

Os comandos são registrados como **guild commands** (instântaneos, sem cache de 1h).  
Na primeira execução, o bot registra os comandos no servidor configurado (guild ID fixo no código).

| Comando | Descrição | Requer Admin |
|---------|-----------|:---:|
| `/status` | Mostra se o servidor está online, IP e senha | |
| `/players` | Lista jogadores online com HP e Stamina | |
| `/bosses` | Progresso dos bosses + próximo não derrotado | |
| `/rank` | Ranking de tempo de jogo | |
| `/map` | Link do WebMap interativo | |
| `/update check` | Verifica se há atualização disponível | |
| `/update apply` | Aplica atualização (mata server, atualiza, reinicia) | ✅ |
| `/setchannel #canal` | Define o canal para notificações | ✅ |
| `/ajuda` | Lista todos os comandos | |

### Notificações Automáticas

O bot monitora o log do servidor em tempo real e envia para o canal configurado:

| Evento | Gatilho | Cooldown |
|--------|---------|:--------:|
| 🟢 Servidor online | `Game server connected` no log ou processo detectado | 60s |
| 🔴 Servidor offline | Processo não encontrado via `pgrep` | — |
| 🚪 Entrada | `Got character ZDOID from <nome>` (jogador não estava online) | 30s |
| 🚪 Saída | `Closing socket (<nome>)` | — |
| 💀 Morte | `Got character ZDOID` de jogador já online | 15s |
| 👹 Boss derrotado | OdinEye `/bossDetails` indica derrota | 1 vez |
| ⚔️ Evento/raid | Linhas no log como `The forest is moving` | 1 vez |
| 🌅 Dia | `Day N` no log do servidor | 1 vez por dia |

### Detecção de Morte (server-side)

Como o Valheim com `-crossplay` não loga mortes, a detecção funciona por heurística:

1. O bot mantém um conjunto `online_players` com quem está conectado
2. Quando um novo `Got character ZDOID` aparece para um jogador já em `online_players`, é considerado uma morte (respawn)
3. O jogador é removido de `online_players` após a morte
4. Um cooldown de 15s evita duplicatas quando o servidor gera 2 ZDOIDs no mesmo respawn
5. O próximo ZDOID (dentro de 15s) ainda notifica como morte, mas após 30s sem ZDOID vira "entrou"

### Estado Persistente

Arquivo `valheim-discord-state.json` — salvo automaticamente. Contém:

- `pos`: posição no arquivo de log (para retomar leitura)
- `sent`: dicionário de notificações já enviadas (evita duplicatas)
- `channels`: guild → canal de notificações
- `bosses`: status dos bosses
- `day`: último dia notificado
- `last_status`: online/offline
- `notified_updates`: versões já notificadas

### Execução como Systemd Service

Criar `/etc/systemd/system/valheim-discord.service`:

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
RestartSec=5
Environment=DISCORD_TOKEN=seu_token_aqui

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable valheim-discord
sudo systemctl start valheim-discord
```

### Arquitetura Interna

```
┌─────────────────────────────────────────────┐
│           check_log_loop (thread)            │
│  A cada 3s: lê novas linhas do log           │
│  → ZDOID → join/morte                        │
│  → Closing socket → saída                    │
│  → Eventos/raid → notificação com dica       │
│  → Game server connected → server online     │
│  → Day N → amanhecer                         │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│         check_bosses_loop (thread)           │
│  A cada 60s: consulta OdinEye                │
│  → /bossDetails → boss derrotado?            │
│  → pgrep valheim_server → status online/off  │
│  → /info → dia atual                         │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│          Bot Discord (main thread)           │
│  bot.run(TOKEN) → processa slash commands    │
│  → /status, /players, /bosses, /rank, etc.  │
└─────────────────────────────────────────────┘
```

---

## 3. Admin Powers Plugin (`Plugin.cs`)

Plugin BepInEx que intercepta chamadas do servidor Valheim via Harmony e expõe poderes administrativos via HTTP.

### Como funciona

O plugin usa **Harmony Transpilers** para modificar o comportamento do servidor em tempo real:

- **`RPC_Damage`**: intercepta toda chamada de dano. Se godmode ativo, zera o dano. Se hitkill ativo, define dano = vida do alvo.
- **`HaveStamina`**: sempre retorna `true` se nostamina ativo.
- **`UseStamina`**: não consome stamina se nostamina ativo.
- **`InGhostMode`**: sempre retorna `true` se invisible ativo.

Os estados (godmode, hitkill, etc.) são armazenados por player usando ZDOs (ZNet Data Objects) no `ZDOMan.instance.m_objectsByID`, garantindo que persistem enquanto o servidor está rodando.

### Build

```bash
# Pré-requisitos
sudo apt install mono-mcs

# Buscar as DLLs de referência (copiar do diretório do servidor Valheim)
cp /home/vhserver/serverfiles/BepInEx/core/0Harmony.dll .
cp /home/vhserver/serverfiles/valheim_server_Data/Managed/*.dll .

# Compilar
chmod +x build.sh
./build.sh
```

O `build.sh` faz:

```bash
#!/bin/bash
mcs -target:library \
    -nostdlib \
    -r:mscorlib.dll \
    -r:System.dll \
    -r:System.Core.dll \
    -r:System.Net.dll \
    -r:0Harmony.dll \
    -r:assembly_valheim.dll \
    -out:out/AdminPowers.dll \
    Plugin.cs
```

### Instalação

```bash
# Copiar a DLL compilada para os plugins do BepInEx
cp out/AdminPowers.dll /home/vhserver/serverfiles/BepInEx/plugins/
```

### Endpoints HTTP (porta 8091)

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/admin` | Página HTML com status dos toggles + formulário para ativar/desativar |
| `POST` | `/admin/toggle/{poder}` | Ativa/desativa um poder. Body: `{"player": "NomeDoJogador"}` |
| `GET` | `/admin/players` | Lista jogadores conectados (nome, ZDOID, HP) |

### Poderes

| Poder | Efeito | Funciona server-side? |
|-------|--------|:---------------------:|
| `godmode` | Jogador não recebe dano | ✅ |
| `hitkill` | Jogador mata qualquer criatura com 1 golpe | ✅ |
| `invisible` | Mobs ignoram o jogador (ghost mode) | ✅ |
| `nostamina` | Stamina nunca acaba | ✅ |
| `nohunger` | Fome nunca diminui | ❌ (ver abaixo) |

### Limitações

- **NoHunger**: Impossível server-side com `-crossplay`. A lógica de fome (`UpdateFood`) roda exclusivamente no client. O servidor não tem acesso ao sistema de food decay. O patch existe no código mas não funciona.
- **Skills**: Impossível server-side com `-crossplay`. Os dados de skill ficam no PlayFab (nuvem), não há arquivos `.fch` no servidor. `ZDO.GetByteArray("skills")` retorna `null`.

### Uso via Dashboard

O dashboard web (porta 8080) faz proxy para `/admin` do plugin. Acesse:

```
http://seu-servidor:8080/admin
```

---

## 4. WebMap

Mapa interativo do mundo Valheim.

### Instalação

```bash
# Baixar o plugin WebMap
# https://thunderstore.io/c/valheim/p/ASharpPen/Valheim.WebMap/

# Copiar para BepInEx/plugins/
cp Valheim.WebMap.dll /home/vhserver/serverfiles/BepInEx/plugins/

# Configurar (opcional)
# Arquivo: serverfiles/BepInEx/config/com.github.h0tw1r3.valheim.webmap.cfg
# Porta padrão: 8888 → recomendo mudar para 3000
```

### Configuração
```ini
[General]
Port=3000
```

### Acesso
```
http://seu-servidor:3000
```

---

## Port Map

| Porta | Serviço | Descrição |
|-------|---------|-----------|
| 2456 | Valheim | Porta principal do jogo (UDP) |
| 2457 | Valheim | Porta crossplay/P2P (UDP) |
| 3000 | WebMap | Mapa interativo via navegador |
| 4000 | OdinEye | API REST de status do servidor |
| 8080 | Dashboard | Painel web administrativo |
| 8091 | Admin Powers | API HTTP dos poderes administrativos |

### Firewall (UFW)
```bash
sudo ufw allow 2456/udp
sudo ufw allow 2457/udp
sudo ufw allow 3000/tcp
sudo ufw allow 4000/tcp
sudo ufw allow 8080/tcp
sudo ufw allow 8091/tcp
```

---

## Dependências Resumidas

### Dashboard
- Python 3.8+
- `flask`, `requests`

### Discord Bot
- Python 3.8+
- `discord.py`
- OdinEye rodando (porta 4000)

### Admin Powers
- BepInEx 5.4.2202+
- Mono C# compiler (`mcs`)
- `0Harmony.dll` (BepInEx)
- Unity BCL (`mscorlib.dll`, `System.dll`, `System.Core.dll`, `System.Net.dll`)
- `assembly_valheim.dll`

### WebMap
- BepInEx 5.4.2202+
- Plugin `Valheim.WebMap.dll`

---

## Estrutura de Arquivos (produção)

```
/home/vhserver/
├── serverfiles/
│   ├── BepInEx/
│   │   ├── core/
│   │   │   └── 0Harmony.dll
│   │   ├── plugins/
│   │   │   ├── AdminPowers.dll    ← compilado do Plugin.cs
│   │   │   ├── OdinEye.dll
│   │   │   └── Valheim.WebMap.dll
│   │   └── config/
│   │       └── com.github.h0tw1r3.valheim.webmap.cfg
│   ├── valheim_server.x86_64
│   └── start_bepinex.sh
├── log/
│   └── console/
│       └── vhserver-console.log
├── valheim-dashboard.py
├── valheim-discord.py
├── valheim-dashboard-data.json   ← criado automaticamente
├── valheim-discord-state.json    ← criado automaticamente
└── venv/
    └── ...                        ← virtualenv Python
```

---

## Licença

MIT
