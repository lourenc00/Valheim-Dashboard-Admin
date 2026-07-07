#!/usr/bin/env python3
import json, os, re, subprocess, time, asyncio, threading
from datetime import datetime, timezone, timedelta

import discord
from discord.ext import commands

TOKEN = os.environ["DISCORD_TOKEN"]
LOG_FILE = "/home/vhserver/log/console/vhserver-console.log"
STATE_FILE = "/home/vhserver/valheim-discord-state.json"
ODINEYE_URL = "http://localhost:4000"

join_pattern = re.compile(r"Got character ZDOID from (.+?) : \d+:\d+")
leave_pattern = re.compile(r"Closing socket \d+ \((.+?)\)")
day_pattern = re.compile(r"Day\s+(\d+)")
join_cooldown = {}  # player -> last_join_time
online_players = set()  # players currently connected
recent_leaves = {}  # player -> time of last closing socket
death_cooldown = {}  # player -> time of last death notification

EVENTS = {
    "The forest is moving":           {"emoji":"\U0001f333","name":"A Floresta Está se Movendo","biome":"Black Forest","desc":"Grey dwarfs estão atacando!","tip":"Use tochas/fogo contra grey dwarfs, fique longe de brutes e shaman."},
    "The ground is shaking":          {"emoji":"\U0001f30d","name":"O Chão Está Tremendo","biome":"Mountain / Meadows","desc":"Trolls estão vindo!","tip":"Flechas de fogo. Nunca lute corpo a corpo com troll. Role para desviar."},
    "A foul smell from the swamp":    {"emoji":"\U0001f9a0","name":"Cheiro Pútrido do Pântano","biome":"Swamp","desc":"Skeletons e Surtlings estão atacando!","tip":"Armas de esmagamento. Poção de resistência ao veneno se estiver no pântano."},
    "You are being hunted":           {"emoji":"\U0001f43a","name":"Você Está Sendo Caçado","biome":"Mountains / Plains","desc":"Lobos estão caçando você!","tip":"Fique perto de uma construção. Use arco. Não lute contra matilha despreparado."},
    "A cold wind blows from the mountains": {"emoji":"\U0001f32c","name":"Vento Frio das Montanhas","biome":"Mountain","desc":"Drakes estão atacando!","tip":"Arco com flechas de obsidiana. Poção de resistência ao gelo."},
    "What's that buzzing?":           {"emoji":"\U0001f41d","name":"O Que é Esse Zumbido?","biome":"Plains","desc":"Deathsquitos à vista!","tip":"Escudo e arco. Um golpe de deathsquito pode matar. Use armadura de plains."},
    "The horde is attacking":         {"emoji":"\U0001f479","name":"A Horda Está Atacando!","biome":"Plains","desc":"Fulings estão atacando o local!","tip":"Armadura de plains/black metal. Poção de resistência ao fogo para shamans."},
    "The horde is attacking!":        {"emoji":"\U0001f479","name":"A Horda Está Atacando!","biome":"Plains","desc":"Fulings estão atacando o local!","tip":"Armadura de plains/black metal. Poção de resistência ao fogo para shamans."},
    "They sought the bones of their kin, and found a feast": {"emoji":"\U0001faa4","name":"Busca pelos Ossos","biome":"Swamp","desc":"Surpresa de skeletons!","tip":"Esmagamento ou gelo. Cuidado com arqueiros."},
    "There is a smell of sulfur in the air": {"emoji":"\U0001f4a8","name":"Cheiro de Enxofre","biome":"Swamp / Plains","desc":"Surtlings estão surgindo!","tip":"Armas de gelo são super efetivas contra surtlings."},
    "Seek protection of the elder":   {"emoji":"\U0001fabe","name":"Proteção do Ancião","biome":"Black Forest","desc":"Evento pacífico dos greydwarfs.","tip":"Apenas espere. Sem ameaça real."},
    "The air is filled with foul fumes": {"emoji":"\U0001f987","name":"Ar Envenenado","biome":"Swamp / Mountain","desc":"Morcegos estão vindo!","tip":"Flechas de fogo. Eles são fracos, mas muitos."},
    "Something is stirring":          {"emoji":"\U0001f577","name":"Algo Está se Movendo","biome":"Mistlands","desc":"Seekers ou ticks estão atacando!","tip":"Armadura de carapace. Dano perfurante ou de gelo."},
    "Watch your step":                {"emoji":"\U0001f30a","name":"Cuidado Por Onde Anda","biome":"Mistlands","desc":"Growths (tar) estão atacando!","tip":"Fogo queima o tar. Não deixe eles te prenderem."},
    "There is a strange smell from the dungeon": {"emoji":"\U0001fa78","name":"Cheiro Estranho da Dungeon","biome":"Black Forest","desc":"Trolls ou greydwarfs da dungeon.","tip":"Fogo e flechas."},
}
EVENT_START_PATTERNS = {re.compile(re.escape(msg), re.IGNORECASE): info for msg, info in EVENTS.items()}
EVENT_END_PATTERN = re.compile(r"(Raid is over|The raid is over|RandomEvent stopped)", re.IGNORECASE)
FUSO_BR = timezone(timedelta(hours=-3))

BOSS_NAMES = {"eikthyr":"Eikthyr","gdking":"The Elder","bonemass":"Bonemass","dragon":"Moder","goblinking":"Yagluth","queen":"The Queen","fader":"Fader"}
BOSS_INFO = {
    "eikthyr":{"n":"Eikthyr","b":"Meadows","f":"Altar místico nos prados","s":"2 Troféus de Cervo","w":"Perfurante (flechas)","e":"Use arco e flechas, esquive dos raios"},
    "gdking":{"n":"The Elder","b":"Black Forest","f":"Altar perto de ruínas na floresta escura","s":"3 Sementes Ancestrais","w":"Fogo","e":"Flechas de fogo, use pilares como cobertura"},
    "bonemass":{"n":"Bonemass","b":"Swamp","f":"Altar de crânio no brejo","s":"10 Ossos Murchos","w":"Esmagamento (maça) - Imune a perfuração/corte","e":"Poção de resistência a veneno OBRIGATÓRIA. Maça de Ferro"},
    "dragon":{"n":"Moder","b":"Mountain","f":"Altar nas montanhas perto de drakes","s":"3 Ovos de Dragão","w":"Fogo, Perfurante","e":"Poção de resistência ao gelo. Arco com flechas de obsidiana"},
    "goblinking":{"n":"Yagluth","b":"Plains","f":"Círculo de pedras nas planícies","s":"5 Totens Fuling","w":"Gelo, Esmagamento","e":"Poção de resistência ao fogo. Use os dedos como cobertura"},
    "queen":{"n":"The Queen","b":"Mistlands","f":"Porta da Rainha (precisa do Quebrador de Selos)","s":"Quebrador de Selos + 3 Troféus de Soldado Buscador","w":"Perfurante, Fogo","e":"Equipamento máximo. Mage ou melee pesado"},
    "fader":{"n":"Fader","b":"Ashlands","f":"Coliseu nas Ashlands - Altar Chama Esmeralda","s":"3 Sinos (forjados com Fragmentos de Sino)","w":"Gelo / Dano Espiritual - Resistente a fogo","e":"Poção de resistência ao fogo OBRIGATÓRIA. Armas de gelo"}
}

last_pos = 0
last_sent = {}
last_status = None
last_bosses = {}
last_day = 0

bot = commands.Bot(
    command_prefix=commands.when_mentioned_or("!"),
    intents=discord.Intents.default(),
    activity=discord.Activity(type=discord.ActivityType.watching, name="Valheim")
)

_extra_state = {}

def load_state():
    global last_pos, last_sent, last_status, last_bosses, last_day, _extra_state
    try:
        with open(STATE_FILE) as f:
            s = json.load(f)
        last_pos = s.get("pos", 0)
        last_sent = s.get("sent", {})
        last_status = s.get("last_status")
        last_bosses.update(s.get("bosses", {}))
        last_day = s.get("day", 0)
        _extra_state = {"channels": s.get("channels", {}),
                        "notified_updates": s.get("notified_updates", [])}
    except:
        pass

def save_state():
    try:
        s = dict(_extra_state)
        s.update({
            "pos": last_pos,
            "sent": last_sent,
            "last_status": last_status,
            "bosses": last_bosses,
            "day": last_day,
        })
        with open(STATE_FILE, "w") as f:
            json.dump(s, f)
    except Exception as e:
        print(f"save_state error: {e}")

def get_channel(guild_id):
    global _extra_state
    cid = _extra_state.get("channels", {}).get(str(guild_id))
    if cid:
        return bot.get_channel(int(cid))
    return None

def set_channel(guild_id, channel_id):
    global _extra_state
    _extra_state.setdefault("channels", {})[str(guild_id)] = channel_id
    save_state()

async def send_notify(text):
    global _extra_state
    channels = _extra_state.get("channels", {})
    sent_to = set()
    for gid in channels.values():
        ch = bot.get_channel(int(gid))
        if ch and gid not in sent_to:
            try:
                await ch.send(text)
                sent_to.add(gid)
            except:
                pass

def fetch_json(path):
    import urllib.request
    try:
        req = urllib.request.Request(f"{ODINEYE_URL}{path}")
        r = urllib.request.urlopen(req, timeout=5)
        return json.loads(r.read())
    except:
        return None

def _notify(text):
    fut = asyncio.run_coroutine_threadsafe(send_notify(text), bot.loop)
    try:
        fut.result(timeout=10)
    except:
        pass

last_server_notify = 0.0

def check_log_loop():
    global last_pos, last_sent, last_server_notify
    while True:
        try:
            with open(LOG_FILE, "r", errors="replace") as f:
                f.seek(0, 2)
                size = f.tell()
                if last_pos > size:
                    last_pos = 0
                    save_state()
                initial = (last_pos == 0)
                f.seek(last_pos)
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    ts = line[:19] if len(line) > 19 else ""
                    if not initial:
                        if "Game server connected" in line:
                            k = f"server_start:{ts}"
                            if k not in last_sent and time.time() - last_server_notify > 60:
                                _notify(f"\U0001f7e2 **Servidor online (TENTANDO NAO MORRER)**\n\U0001f517 SEU_DOMINIO:2456\n\U0001f511 `SUA_SENHA`")
                                last_sent[k] = time.time()
                                last_server_notify = time.time()
                    m = join_pattern.search(line)
                    if m:
                        n = m.group(1); k = f"join:{n}:{ts}"
                        if initial:
                            online_players.add(n)
                        elif k not in last_sent:
                            now = time.time()
                            if now - death_cooldown.get(n, 0) > 15:
                                if n in online_players:
                                    death_cooldown[n] = now
                                    _notify(f"\U0001f480 **{n}** morreu")
                                    online_players.discard(n)
                                elif now - recent_leaves.get(n, 0) < 15:
                                    death_cooldown[n] = now
                                    _notify(f"\U0001f480 **{n}** morreu")
                                    online_players.add(n)
                                elif now - join_cooldown.get(n, 0) > 30:
                                    agora = datetime.now(FUSO_BR).strftime("%d/%m/%Y %H:%M:%S")
                                    _notify(f"**{n}** entrou em Valheim às **{agora}**")
                                    online_players.add(n)
                            join_cooldown[n] = now
                            last_sent[k] = time.time()
                        else:
                            online_players.add(n)
                    m = leave_pattern.search(line)
                    if m:
                        n = m.group(1); k = f"leave:{n}:{ts}"
                        if initial:
                            online_players.discard(n)
                        elif k not in last_sent:
                            recent_leaves[n] = time.time()
                            online_players.discard(n)
                            agora = datetime.now(FUSO_BR).strftime("%d/%m/%Y %H:%M:%S")
                            _notify(f"**{n}** saiu de Valheim às **{agora}**")
                            last_sent[k] = time.time()
                    m = day_pattern.search(line)
                    if m:
                        d = m.group(1); k = f"day:{d}:{ts}"
                        if k not in last_sent:
                            if not initial:
                                _notify(f"\U0001f305 **Dia {d}** amanheceu em Valheim!")
                            last_sent[k] = time.time()
                    if not initial:
                        for pat, info in EVENT_START_PATTERNS.items():
                            if pat.search(line):
                                k = f"event:{pat.pattern}:{ts}"
                                if k not in last_sent:
                                    _notify(f"{info['emoji']} **{info['name']}**\n{info['desc']}\n\U0001f7e0 Bioma: {info['biome']}\n\U0001f4a1 {info['tip']}")
                                    last_sent[k] = time.time()
                        if EVENT_END_PATTERN.search(line):
                            k = f"event_end:{ts}"
                            if k not in last_sent:
                                _notify(f"\u2705 **O ataque terminou!** O local está seguro novamente.")
                                last_sent[k] = time.time()
                last_pos = f.tell()
                save_state()
                if len(last_sent) > 1000:
                    cutoff = time.time() - 86400
                    for k in list(last_sent):
                        if last_sent[k] <= cutoff:
                            del last_sent[k]
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"Log error: {e}")
        time.sleep(3)

def check_bosses_loop():
    global last_bosses, last_status, last_sent, last_server_notify
    while True:
        try:
            now = time.time()
            running = subprocess.run(["pgrep", "-f", "valheim_server.x86_64"], capture_output=True, timeout=5).returncode == 0
            status = "online" if running else "offline"
            if status != last_status:
                if status == "online":
                    if now - last_server_notify > 60:
                        _notify(f"\U0001f7e2 **Servidor online (TENTANDO NAO MORRER)**\n\U0001f517 SEU_DOMINIO:2456\n\U0001f511 `SUA_SENHA`")
                        last_server_notify = now
                elif status == "offline":
                    _notify(f"\U0001f534 **Servidor parou** - TENTANDO NAO MORRER está offline")
                last_status = status
                save_state()

            data = fetch_json("/bossDetails")
            if data and "Bosses" in data:
                cur = {}
                for b in data["Bosses"]:
                    cur[b["Key"]] = b["IsDefeated"]
                    old = last_bosses.get(b["Key"])
                    if old is not None and old != b["IsDefeated"] and b["IsDefeated"]:
                        _notify(f"\U0001f451 **{BOSS_NAMES.get(b['Key'], b['Key'])} foi derrotado!**")
                last_bosses = cur
                save_state()

        except:
            pass
        time.sleep(60)

@bot.event
async def on_ready():
    print(f"Bot conectado como {bot.user}")
    # Popula online_players com quem está no servidor agora
    plist = fetch_json("/players") or []
    for p in plist:
        online_players.add(p.get("Name", ""))
    if plist:
        print(f"Players online: {[p.get('Name','') for p in plist]}")
    threading.Thread(target=check_log_loop, daemon=True).start()
    threading.Thread(target=check_bosses_loop, daemon=True).start()

@bot.tree.command(name="setchannel", description="Define o canal para notificações do Valheim")
@discord.app_commands.default_permissions(administrator=True)
async def setchannel(interaction: discord.Interaction, canal: discord.TextChannel):
    set_channel(interaction.guild_id, canal.id)
    await interaction.response.send_message(f"\u2705 Notificações definidas para {canal.mention}", ephemeral=True)

@bot.tree.command(name="status", description="Mostra o status do servidor Valheim")
async def status(interaction: discord.Interaction):
    running = subprocess.run(["pgrep", "-f", "valheim_server.x86_64"], capture_output=True, timeout=5).returncode == 0
    players = fetch_json("/players") or []
    wd = fetch_json("/worldDetails") or {}
    embed = discord.Embed(
        title="TENTANDO NAO MORRER",
        color=0x00ff00 if running else 0xff0000,
        description="Online" if running else "Offline"
    )
    if running:
        embed.add_field(name="Jogadores", value=str(len(players)), inline=True)
        embed.add_field(name="Dia", value=str(wd.get("DayNumber", "?")), inline=True)
        embed.add_field(name="Acesso", value="SEU_DOMINIO:2456", inline=False)
        if players:
            embed.add_field(name="\u200b", value="\n".join(f"• {p['Name']}" for p in players[:10]), inline=False)
    embed.set_footer(text="Valheim Bot")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="bosses", description="Mostra o progresso dos bosses")
async def bosses(interaction: discord.Interaction):
    data = fetch_json("/bossDetails")
    if not data or "Bosses" not in data:
        await interaction.response.send_message("Não foi possível obter dados dos bosses.", ephemeral=True)
        return
    BOSS_ORDER = ["eikthyr","gdking","bonemass","dragon","goblinking","queen","fader"]
    defeated_map = {b["Key"]: b["IsDefeated"] for b in data["Bosses"]}
    next_boss = None
    for key in BOSS_ORDER:
        if not defeated_map.get(key):
            next_boss = BOSS_INFO.get(key, {}).get("n", key)
            break
    lines = ["\U0001f3f0 **Progresso dos Bosses**\n"]
    for key in BOSS_ORDER:
        b_info = next((b for b in data["Bosses"] if b["Key"] == key), None)
        if not b_info:
            continue
        info = BOSS_INFO.get(key, {})
        emoji = "\u2705" if b_info["IsDefeated"] else "\u274C"
        lines.append(f"{emoji} {info.get('n', key)} ({info.get('b','?')})")
        lines.append(f"\U0001fa84 {info.get('s','?')}")
        lines.append(f"\u2694\ufe0f {info.get('w','?')}\n")
    if next_boss:
        lines.append(f"\U0001f3af **Próximo boss: {next_boss}**")
    msg = "\n".join(lines).strip()
    if len(msg) > 1900:
        await interaction.response.send_message(msg[:1900])
    else:
        await interaction.response.send_message(msg)

@bot.tree.command(name="players", description="Lista os jogadores online")
async def players(interaction: discord.Interaction):
    plist = fetch_json("/players") or []
    if not plist:
        await interaction.response.send_message("Nenhum jogador online no momento.")
        return
    lines = [f"\U0001f465 **Jogadores online ({len(plist)})**\n"]
    for p in plist:
        h = p.get("Health", 0); mh = p.get("MaxHealth", 0)
        s = p.get("Stamina", 0); ms = p.get("MaxStamina", 0)
        hp_pct = int(h / mh * 100) if mh > 0 else 0
        st_pct = int(s / ms * 100) if ms > 0 else 0
        lines.append(f"**{p.get('Name','?')}**")
        lines.append(f"\U00002764 HP {h}/{mh} ({hp_pct}%)")
        lines.append(f"\U000026a1 Stamina {s}/{ms} ({st_pct}%)")
    await interaction.response.send_message("\n".join(lines))

@bot.tree.command(name="map", description="Link do mapa do servidor")
async def mapcmd(interaction: discord.Interaction):
    await interaction.response.send_message("\U0001f5fa **WebMap**: <http://SEU_DOMINIO:3000>")

@bot.tree.command(name="rank", description="Ranking de tempo de jogo")
async def rank(interaction: discord.Interaction):
    try:
        with open("/home/vhserver/valheim-dashboard-data.json") as f:
            data = json.load(f)
    except:
        data = {}
    pt = data.get("playtimes", {})
    if not pt:
        await interaction.response.send_message("Nenhum dado de tempo de jogo disponível ainda.")
        return
    sorted_players = sorted(pt.items(), key=lambda x: x[1], reverse=True)
    lines = ["\U0001f3c6 **Ranking de Tempo de Jogo**\n"]
    medals = ["\U0001f947","\U0001f948","\U0001f949"]
    for i, (name, secs) in enumerate(sorted_players[:10]):
        h, r = divmod(int(secs), 3600)
        m = int(r // 60)
        medal = medals[i] if i < 3 else f"{i+1}."
        lines.append(f"{medal} **{name}** — {h}h {m}min")
    await interaction.response.send_message("\n".join(lines))

VHSERVER_SCRIPT = "/home/vhserver/vhserver"
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

@bot.tree.command(name="update", description="Verifica ou aplica atualizações do servidor")
@discord.app_commands.describe(acao="'check' para verificar, 'apply' para atualizar")
@discord.app_commands.choices(acao=[
    discord.app_commands.Choice(name="check", value="check"),
    discord.app_commands.Choice(name="apply", value="apply"),
])
async def update(interaction: discord.Interaction, acao: str):
    if acao == "apply":
        if not interaction.permissions.administrator:
            await interaction.response.send_message("Apenas administradores podem aplicar atualizações.", ephemeral=True)
            return
        await interaction.response.defer()
        pid = subprocess.run(["pgrep", "-f", "valheim_server.x86_64"], capture_output=True, timeout=5).returncode
        if pid == 0:
            subprocess.run(["pkill", "-9", "-f", "valheim_server.x86_64"], timeout=5)
            await interaction.followup.send("\U0001f504 Servidor parado. Atualizando...")
        else:
            await interaction.followup.send("\U0001f504 Atualizando...")
        subprocess.run(["bash", VHSERVER_SCRIPT, "update"], timeout=300)
        subprocess.run(["bash", VHSERVER_SCRIPT, "start"], timeout=30)
        await interaction.followup.send("\u2705 **Servidor atualizado e reiniciado!**\n\U0001f517 SEU_DOMINIO:2456\n\U0001f511 `SUA_SENHA`")
        return

    await interaction.response.defer()
    r = subprocess.run(["bash", VHSERVER_SCRIPT, "check-update"], capture_output=True, text=True, timeout=120)
    out = ANSI_RE.sub("", r.stdout + r.stderr)
    builds = [l.strip() for l in out.split("\n") if "build:" in l.lower()]
    local = None; remote = None
    for l in builds:
        if "local" in l.lower(): local = l.split()[-1]
        if "remote" in l.lower(): remote = l.split()[-1]
    if builds:
        await interaction.followup.send("\n".join(builds))
    if local and remote and local != remote:
        await interaction.followup.send("\U0001f514 **Atualização disponível!** Use `/update apply` para aplicar (só admin).")
    else:
        await interaction.followup.send("\u2705 **Servidor atualizado!**")

@bot.tree.command(name="ajuda", description="Mostra os comandos disponíveis")
async def ajuda(interaction: discord.Interaction):
    embed = discord.Embed(title="Comandos do Valheim Bot", color=0x2ecc71)
    embed.add_field(name="/status", value="Status do servidor e jogadores online", inline=False)
    embed.add_field(name="/players", value="Jogadores online com HP/Stamina", inline=False)
    embed.add_field(name="/bosses", value="Progresso dos bosses derrotados", inline=False)
    embed.add_field(name="/rank", value="Ranking de tempo de jogo", inline=False)
    embed.add_field(name="/map", value="Link do mapa do servidor", inline=False)
    embed.add_field(name="/update", value="Verifica (check) ou aplica (apply) atualizações", inline=False)
    embed.add_field(name="/setchannel #canal", value="Define o canal de notificações (só admin)", inline=False)
    embed.add_field(name="/ajuda", value="Mostra esta mensagem", inline=False)
    await interaction.response.send_message(embed=embed)

if __name__ == "__main__":
    load_state()
    bot.run(TOKEN)
