# Guia para configurar em outro servidor e subir commit

Entregue este guia para outra IA (ou pessoa) configurar o mesmo stack em um servidor novo e subir o código no GitHub.

---

## Objetivo

Montar o stack Valheim (LinuxGSM + BepInEx + OdinEye + Dashboard + Discord Bot + Admin Powers + WebMap) em um servidor Linux limpo e subir os arquivos para `https://github.com/lourenc00/Valheim-Dashboard-Admin`.

---

## Passo 1: Criar usuário e instalar dependências

```bash
sudo adduser vhserver
su - vhserver
```

```bash
sudo apt update && sudo apt install python3 python3-pip python3-venv mono-mcs git tmux ufw -y
```

---

## Passo 2: Instalar LinuxGSM + Valheim

```bash
wget -O linuxgsm.sh https://linuxgsm.sh
chmod +x linuxgsm.sh
./linuxgsm.sh vhserver
./vhserver install
```

Durante a instalação:
- Server Name: `NOME_DO_SERVER`
- Password: `SUA_SENHA`
- Steam user: deixar vazio (anônimo)

---

## Passo 3: Instalar BepInEx

```bash
cd /home/vhserver/serverfiles
wget https://valheim.thunderstore.io/package/download/denikson/BepInExPack_Valheim/5.4.2202/
unzip 5.4.2202
rm 5.4.2202
```

---

## Passo 4: Instalar OdinEye

Baixar `OdinEye.dll` da Thunderstore e colocar em:

```
/home/vhserver/serverfiles/BepInEx/plugins/OdinEye.dll
```

---

## Passo 5: Clonar o repo e copiar arquivos

```bash
cd /home/vhserver
git clone git@github.com:lourenc00/Valheim-Dashboard-Admin.git
cd Valheim-Dashboard-Admin
```

Este repo já contém: `valheim-dashboard.py`, `valheim-discord.py`, `Plugin.cs`, `build.sh`.

---

## Passo 6: Subir commit com as modificações do servidor

O outro servidor pode ter configurações diferentes (caminhos de arquivos, IPs, etc.). Para subir as alterações:

```bash
cd /home/vhserver/Valheim-Dashboard-Admin

# Copiar os arquivos do servidor atual para o repositório
cp /home/vhserver/valheim-dashboard.py ./
cp /home/vhserver/valheim-discord.py ./
# Se tiver o plugin Admin Powers compilado ou o Plugin.cs modificado:
cp /home/vhserver/serverfiles/BepInEx/plugins/AdminPowers.dll ./  # opcional

# ANTES de commitar: remover dados sensíveis do valheim-discord.py
# Substituir token, senhas, IPs por placeholders ou variáveis de ambiente

# Adicionar, commitar e enviar
git add -A
git config user.email "lourenc00@users.noreply.github.com"
git config user.name "lourenc00"
git commit -m "Adapt configs for new server"
git push origin main
```

---

## O que a IA precisa saber para adaptar cada arquivo

### `valheim-discord.py`

Substituir valores hardcoded antes de commit:

| O quê | Substituir por |
|-------|---------------|
| Token do bot | `os.environ["DISCORD_TOKEN"]` |
| Domínio/IP | `os.environ.get("SERVER_DOMAIN", "SEU_IP")` |
| Senha do servidor | `os.environ.get("SERVER_PASSWORD", "SUA_SENHA")` |
| Guild ID | variável ou fixo do servidor |
| Channel ID | (definido via /setchannel) |

Variáveis de ambiente necessárias na execução:
```bash
export DISCORD_TOKEN="token_do_bot"
```

### `valheim-dashboard.py`

Geralmente não tem dados sensíveis. Verificar se a URL da OdinEye está correta:
```python
ODINEYE_URL = "http://localhost:4000"
```

### `Plugin.cs`

Não tem dados sensíveis. Pode commitar como está.

---

## Checklist final para a IA

- [ ] LinuxGSM + Valheim instalado e funcionando
- [ ] BepInEx instalado em `/home/vhserver/serverfiles/`
- [ ] OdinEye.dll em `BepInEx/plugins/`
- [ ] Valheim rodando com `start_server_bepinex.sh` (NÃO com `./vhserver start`)
- [ ] Repositório clonado
- [ ] Arquivos copiados para o repo
- [ ] Dados sensíveis removidos/substituídos
- [ ] Commit feito com `git config user.name` e `user.email` configurados
- [ ] `git push origin main` bem-sucedido
- [ ] Dashboard testado: `python3 valheim-dashboard.py`
- [ ] Discord Bot testado: `DISCORD_TOKEN=xxx python3 valheim-discord.py`

---

## Comandos de teste rápido

```bash
# Ver se o servidor está rodando
curl http://localhost:4000/status

# Testar OdinEye
curl http://localhost:4000/players

# Testar Dashboard
curl http://localhost:8080/

# Testar Admin Powers (se compilado)
curl http://localhost:8091/admin

# Ver log do servidor
tail -f /home/vhserver/log/console/vhserver-console.log
```
