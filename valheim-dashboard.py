#!/usr/bin/env python3
import http.server
import json
import re
import subprocess
import threading
import time
import urllib.request
import copy
import os
from datetime import datetime, timezone
TZ = timezone.utc
try:
    import zoneinfo
    TZ = zoneinfo.ZoneInfo("America/Sao_Paulo")
except:
    try:
        os.environ["TZ"] = "America/Sao_Paulo"
        time.tzset()
    except:
        pass
SAVE_FILE = "/home/vhserver/valheim-dashboard-data.json"

def load_saved():
    try:
        with open(SAVE_FILE) as f:
            return json.load(f)
    except:
        return {}

def save_saved(obj):
    with open(SAVE_FILE, "w") as f:
        json.dump(obj, f)

LOG_FILE = "/home/vhserver/log/console/vhserver-console.log"
VHSERVER_SCRIPT = "/home/vhserver/vhserver"
DASHBOARD_PORT = 8080
ODINEYE_URL = "http://localhost:4000"
SKILLS_URL = "http://localhost:8090"
ADMIN_POWERS_URL = "http://localhost:8091"

data = {
    "server": {
        "status": "offline",
        "name": "TENTANDO NAO MORRER",
        "players_online": 0,
        "players_max": 10,
        "world": "Valheim-com-amigos",
        "days": 0,
        "uptime": "0s",
        "started_at": "",
        "update": {
            "checked_at": "",
            "available": False,
            "local_build": "",
            "remote_build": "",
            "checking": False
        },
        "game_version": "",
    },
    "recent_events": [],
    "players": {},
    "bosses": [],
    "world_details": {},
    "odineye_players": {},
    "skills_data": [],
    "admin_powers": [],
}

last_read_pos = 0
server_start_time = None
log_dt_pattern = re.compile(r"^(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}):\s")
day_pattern = re.compile(r"Day\s+(\d+)")
join_pattern = re.compile(r"Got character ZDOID from (.+?) : \d+:\d+")
leave_pattern = re.compile(r"Closing socket \d+ \((.+?)\)")
death_pattern = re.compile(r"(.+?) died")

def parse_log_ts(line):
    m = log_dt_pattern.match(line)
    if m:
        try:
            return datetime.strptime(m.group(1), "%m/%d/%Y %H:%M:%S").timestamp()
        except:
            pass
    return time.time()
event_store = []
player_playtimes = {}  # name -> total_seconds
player_sessions = {}   # name -> join_timestamp


def run_cmd(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout, r.stderr
    except:
        return "", ""


def check_update():
    if data["server"]["update"]["checking"]:
        return
    data["server"]["update"]["checking"] = True
    data["server"]["update"]["checked_at"] = datetime.now().strftime("%d/%m/%Y %H:%M")
    try:
        out, _ = run_cmd(["bash", VHSERVER_SCRIPT, "check-update"], timeout=30)
        for line in out.split("\n"):
            if "Local build:" in line:
                v = line.split(":")[-1].strip()
                data["server"]["update"]["local_build"] = v
            elif "Remote build:" in line:
                v = line.split(":")[-1].strip()
                data["server"]["update"]["remote_build"] = v
        data["server"]["update"]["available"] = (
            data["server"]["update"]["local_build"]
            and data["server"]["update"]["remote_build"]
            and data["server"]["update"]["local_build"] != data["server"]["update"]["remote_build"]
        )
    except:
        pass
    data["server"]["update"]["checking"] = False


def parse_log():
    global last_read_pos, server_start_time
    try:
        with open(LOG_FILE, "r", errors="replace") as f:
            f.seek(0, 2)
            file_size = f.tell()

            if last_read_pos > file_size:
                last_read_pos = 0
                return

            initial_scan = (last_read_pos == 0)
            f.seek(last_read_pos)
            for line in f:
                line = line.strip()
                ts = datetime.now(timezone.utc).isoformat()

                if "Game server connected" in line:
                    if not initial_scan:
                        for p in data["players"].values():
                            p["online"] = False
                        for n in list(player_sessions.keys()):
                            elapsed = time.time() - player_sessions.pop(n)
                            player_playtimes[n] = player_playtimes.get(n, 0) + elapsed
                    if not server_start_time:
                        server_start_time = time.time()
                        data["server"]["status"] = "online"
                        data["server"]["started_at"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                        if not initial_scan:
                            add_event("server", "Servidor iniciou")

                if initial_scan:
                    log_ts = parse_log_ts(line)
                    m = join_pattern.search(line)
                    if m:
                        name = m.group(1)
                        if name not in data["players"]:
                            data["players"][name] = {"name": name, "last_seen": ts, "online": False}
                        if name in player_sessions:
                            elapsed = log_ts - player_sessions.pop(name)
                            if elapsed > 0:
                                player_playtimes[name] = player_playtimes.get(name, 0) + elapsed
                        player_sessions[name] = log_ts
                    m = leave_pattern.search(line)
                    if m:
                        name = m.group(1)
                        if name not in data["players"]:
                            data["players"][name] = {"name": name, "last_seen": ts, "online": False}
                        if name in player_sessions:
                            elapsed = log_ts - player_sessions.pop(name)
                            if elapsed > 0:
                                player_playtimes[name] = player_playtimes.get(name, 0) + elapsed
                    m = day_pattern.search(line)
                    if m:
                        day = int(m.group(1))
                        data["server"]["days"] = day
                    continue

                m = join_pattern.search(line)
                if m:
                    name = m.group(1)
                    data["players"][name] = {"name": name, "last_seen": ts, "online": True}
                    player_sessions[name] = time.time()
                    add_event("join", f"{name} entrou no servidor")

                m = leave_pattern.search(line)
                if m:
                    name = m.group(1)
                    if name in data["players"]:
                        data["players"][name]["online"] = False
                    if name in player_sessions:
                        elapsed = time.time() - player_sessions.pop(name)
                        player_playtimes[name] = player_playtimes.get(name, 0) + elapsed
                    add_event("leave", f"{name} saiu do servidor")

                m = day_pattern.search(line)
                if m:
                    day = int(m.group(1))
                    data["server"]["days"] = day
                    add_event("day", f"Dia {day} amanheceu")

                m = death_pattern.search(line)
                if m and "died" in line.lower():
                    name = m.group(1).strip()
                    add_event("death", f"{name} morreu")

            if initial_scan:
                player_sessions.clear()
            last_read_pos = f.tell()
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"Log error: {e}")


def add_event(etype, text):
    event = {"type": etype, "text": text, "time": datetime.now(timezone.utc).isoformat()}
    event_store.insert(0, event)
    if len(event_store) > 100:
        event_store.pop()
    data["recent_events"] = event_store[:50]


def calculate_uptime():
    if server_start_time:
        seconds = int(time.time() - server_start_time)
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h}h {m}m {s}s"
    return "0s"


def check_server_status():
    global server_start_time
    while True:
        r = subprocess.run(["pgrep", "-f", "valheim_server.x86_64"], capture_output=True, timeout=5)
        running = (r.returncode == 0)
        if running:
            if not server_start_time:
                server_start_time = time.time()
                data["server"]["status"] = "online"
                data["server"]["started_at"] = datetime.now(TZ).strftime("%d/%m/%Y %H:%M:%S")
            else:
                data["server"]["status"] = "online"
        else:
            data["server"]["status"] = "stopped"
            data["server"]["started_at"] = ""
        time.sleep(10)


def update_check_loop():
    time.sleep(30)
    while True:
        check_update()
        time.sleep(3600)


def fetch_odineye():
    try:
        req = urllib.request.Request(f"{ODINEYE_URL}/serverDetails")
        r = urllib.request.urlopen(req, timeout=5)
        sd = json.loads(r.read())
        data["server"]["game_version"] = sd.get("GameVersion", "")
        data["server"]["players_max"] = sd.get("MaxNumberOfPlayers", 10)
    except:
        pass
    try:
        req = urllib.request.Request(f"{ODINEYE_URL}/bossDetails")
        r = urllib.request.urlopen(req, timeout=5)
        bd = json.loads(r.read())
        data["bosses"] = bd.get("Bosses", [])
    except:
        pass
    try:
        req = urllib.request.Request(f"{ODINEYE_URL}/worldDetails")
        r = urllib.request.urlopen(req, timeout=5)
        wd = json.loads(r.read())
        data["world_details"] = wd
        day = wd.get("DayNumber", 0)
        if day > 0:
            data["server"]["days"] = day
    except:
        pass
    try:
        req = urllib.request.Request(f"{ODINEYE_URL}/players")
        r = urllib.request.urlopen(req, timeout=5)
        pl = json.loads(r.read())
        data["odineye_players"] = {p["Name"]: p for p in pl}
    except:
        pass


def fetch_skills():
    try:
        req = urllib.request.Request(f"{SKILLS_URL}/skills")
        r = urllib.request.urlopen(req, timeout=5)
        data["skills_data"] = json.loads(r.read())
    except:
        pass

def fetch_admin_powers():
    try:
        req = urllib.request.Request(f"{ADMIN_POWERS_URL}/api/powers")
        r = urllib.request.urlopen(req, timeout=5)
        data["admin_powers"] = json.loads(r.read())
    except:
        pass

def odineye_loop():
    while True:
        fetch_odineye()
        fetch_skills()
        fetch_admin_powers()
        time.sleep(30)


class DashboardHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api":
            fetch_odineye()
            data["server"]["uptime"] = calculate_uptime()
            online = [p for p in data["players"].values() if p.get("online")]
            data["server"]["players_online"] = len(online)

            wd = data.get("world_details", {})
            day_cycle_map = {"morning": "Manh\u00e3", "afternoon": "Tarde", "night": "Noite", "unknown": "Desconhecido"}
            resp = copy.deepcopy(data)
            resp["server"]["day_cycle"] = day_cycle_map.get(wd.get("DayCycle", ""), wd.get("DayCycle", ""))
            resp["server"]["world_name"] = wd.get("WorldName", "")
            resp["server"]["seed_name"] = wd.get("SeedName", "")

            now = time.time()
            combined = dict(player_playtimes)
            for name, join_ts in player_sessions.items():
                if data["players"].get(name, {}).get("online", False):
                    combined[name] = combined.get(name, 0) + (now - join_ts)
            ranked = sorted(combined.items(), key=lambda x: -x[1])
            resp["player_ranking"] = []
            for i, (name, secs) in enumerate(ranked, 1):
                h = int(secs // 3600)
                m = int((secs % 3600) // 60)
                online_now = data["players"].get(name, {}).get("online", False)
                resp["player_ranking"].append({
                    "rank": i,
                    "name": name,
                    "hours": h,
                    "minutes": m,
                    "total_seconds": int(secs),
                    "online": online_now
                })

            self.send_json(resp)
        elif self.path == "/api/check-update":
            threading.Thread(target=check_update, daemon=True).start()
            self.send_json({"checking": True})
        elif self.path == "/api/admin/powers":
            self.send_proxy("GET", ADMIN_POWERS_URL + "/api/powers")
        elif self.path == "/":
            self.send_html()
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/admin/powers/toggle":
            body = self.rfile.read(int(self.headers["Content-Length"]))
            self.send_proxy("POST", ADMIN_POWERS_URL + "/api/powers/toggle", body)

    def send_proxy(self, method, url, body=None):
        try:
            req = urllib.request.Request(url, data=body, method=method)
            r = urllib.request.urlopen(req, timeout=5)
            self.send_response(r.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(r.read())
        except Exception as e:
            self.send_json({"error": str(e)})

    def send_json(self, obj):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(obj, indent=2).encode())

    def send_html(self):
        html = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dashboard - TENTANDO NAO MORRER</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Segoe UI', system-ui, sans-serif; background: #1a1a2e; color: #e0e0e0; min-height: 100vh; }
.header { background: linear-gradient(135deg, #16213e 0%, #0f3460 100%); padding: 20px; text-align: center; border-bottom: 2px solid #e94560; }
.header h1 { font-size: 1.8em; color: #e94560; }
.header p { color: #8899aa; margin-top: 5px; }
.container { max-width: 1200px; margin: 0 auto; padding: 20px; display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.card { background: #16213e; border-radius: 10px; padding: 20px; border: 1px solid #0f3460; }
.card h2 { color: #e94560; font-size: 1.2em; margin-bottom: 15px; border-bottom: 1px solid #0f3460; padding-bottom: 8px; }
.card.full { grid-column: 1 / -1; }
.stat-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
.stat { text-align: center; padding: 10px; background: #0f3460; border-radius: 8px; }
.stat .value { font-size: 2em; font-weight: bold; }
.stat .label { font-size: 0.8em; color: #8899aa; margin-top: 3px; }
.event { display: flex; align-items: center; gap: 10px; padding: 8px 0; border-bottom: 1px solid #0f3460; font-size: 0.9em; }
.event:last-child { border-bottom: none; }
.event .icon { font-size: 1.2em; width: 24px; text-align: center; }
.event .time { color: #667788; font-size: 0.8em; min-width: 70px; }
.event.join .icon { color: #4ecca3; }
.event.leave .icon { color: #e84560; }
.event.death .icon { color: #ff6b6b; }
.event.day .icon { color: #ffd93d; }
.event.server .icon { color: #6bcb77; }
.player-list { display: flex; flex-wrap: wrap; gap: 8px; }
.player-tag { background: #0f3460; padding: 5px 12px; border-radius: 15px; font-size: 0.9em; display: flex; align-items: center; gap: 6px; }
.player-tag .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.player-tag .online { background: #4ecca3; box-shadow: 0 0 6px #4ecca3; }
.player-tag .offline { background: #e84560; }
.refresh { text-align: center; color: #667788; font-size: 0.85em; margin-top: 15px; }
a { color: #4ecca3; text-decoration: none; }
a:hover { text-decoration: underline; }
.links { margin-top: 15px; text-align: center; display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; }
.links a { padding: 8px 16px; background: #0f3460; border-radius: 5px; font-size: 0.9em; }
.btn { padding: 8px 16px; border: none; border-radius: 5px; cursor: pointer; font-size: 0.9em; }
.btn-update { background: #e94560; color: #fff; }
.btn-update:hover { background: #d63851; }
.btn-update:disabled { background: #555; cursor: wait; }
.update-bar { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; padding: 10px 15px; border-radius: 8px; margin-top: 10px; }
.update-ok { background: #0f3460; }
.update-available { background: #3d1f1f; border: 1px solid #e94560; }
.update-info { font-size: 0.85em; color: #8899aa; }
.highlight { color: #e94560; font-weight: bold; }
@media (max-width: 768px) { .container { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<div class="header">
  <h1>TENTANDO NAO MORRER</h1>
  <p>Dashboard do servidor Valheim</p>
</div>
<div class="container" id="app">
  <div class="card full" id="stats">
    <h2>Status do Servidor</h2>
    <div class="stat-grid">
      <div class="stat"><div class="value" id="stPlayers" style="color:#4ecca3">0</div><div class="label">Jogadores Online</div></div>
      <div class="stat"><div class="value" id="stDays" style="color:#ffd93d">0</div><div class="label">Dias no Mundo</div></div>
      <div class="stat"><div class="value" id="stStatus" style="font-size:1.2em; color:#e84560">offline</div><div class="label">Status</div></div>
      <div class="stat"><div class="value" id="stUptime" style="font-size:1.2em">0s</div><div class="label">Uptime</div></div>
    </div>
    <div style="display:block;text-align:center;margin-top:8px;font-size:0.85em;color:#667788">
      <div>Iniciado em: <span id="stStarted">--</span></div>
      <div id="stWorldInfo" style="display:none"></div>
    </div>
  </div>

  <div class="card full" id="updateCard">
    <h2>Atualizações do Servidor</h2>
    <div id="updateContent">
      <div class="update-bar update-ok">
        <span id="updateStatus">Verificando...</span>
        <span class="update-info" id="updateInfo"></span>
        <button class="btn btn-update" id="btnCheck" onclick="checkUpdate()">Verificar Agora</button>
      </div>
    </div>
  </div>

  <div class="card">
    <h2>Jogadores</h2>
    <div class="player-list" id="playerList">
      <div style="color:#667788">Nenhum jogador visto ainda</div>
    </div>
  </div>
  <div class="card">
    <h2>Ranking de Tempo Jogado</h2>
    <div id="playerRanking">
      <div style="color:#667788">Nenhum dado dispon\u00edvel</div>
    </div>
  </div>
  <div class="card full">
    <h2>Progresso dos Bosses</h2>
    <div style="margin-bottom:10px;font-size:0.9em;color:#8899aa" id="worldInfo"></div>
    <div id="bossList"></div>
  </div>
  <div class="card full" id="adminCard" style="display:none">
    <h2>\u2699\ufe0f Admin Powers</h2>
    <div id="adminContent">
      <div style="color:#667788;text-align:center;padding:20px" id="adminLoading">Carregando players...</div>
    </div>
  </div>
  <div class="card">
    <h2>Eventos Recentes</h2>
    <div id="events">
      <div style="color:#667788">Nenhum evento registrado</div>
    </div>
  </div>
</div>
<div class="refresh" id="refreshInfo">Atualizando a cada 5 segundos</div>
<script>
async function checkUpdate() {
  const btn = document.getElementById('btnCheck');
  btn.disabled = true; btn.textContent = 'Verificando...';
  await fetch('/api/check-update');
  setTimeout(() => { btn.disabled = false; btn.textContent = 'Verificar Agora'; }, 5000);
}

async function fetchData() {
  try {
    const r = await fetch('/api');
    const d = await r.json();
    const s = d.server;

    document.getElementById('stPlayers').textContent = s.players_online;
    document.getElementById('stDays').textContent = s.days;
    document.getElementById('stUptime').textContent = s.uptime;
    document.getElementById('stStarted').textContent = s.started_at || '--';

    const wi = document.getElementById('stWorldInfo');
    const parts = [];
    if (s.world_name) parts.push('\U0001f30d Mundo: ' + s.world_name);
    if (s.seed_name) parts.push('\U0001f3f0 Semente: ' + s.seed_name);
    if (s.day_cycle) parts.push('\u2600\ufe0f Ciclo: ' + s.day_cycle);
    if (parts.length) { wi.innerHTML = parts.join(' | '); wi.style.display = 'inline'; }

    const st = document.getElementById('stStatus');
    if (s.status === 'online') { st.textContent = 'Online'; st.style.color = '#4ecca3'; }
    else if (s.status === 'starting') { st.textContent = 'Iniciando...'; st.style.color = '#ffd93d'; }
    else if (s.status === 'stopped') { st.textContent = 'Parado'; st.style.color = '#e84560'; }
    else { st.textContent = 'Offline'; st.style.color = '#666'; }

    const uc = document.getElementById('updateStatus');
    const ui = document.getElementById('updateInfo');
    if (s.update.checking) { uc.textContent = 'Verificando...'; }
    else if (s.update.available) {
      uc.innerHTML = '<span class="highlight">Atualização dispon\u00edvel!</span>';
      ui.textContent = 'Build local: ' + (s.update.local_build || '?') + ' | Remoto: ' + (s.update.remote_build || '?');
    } else if (s.update.local_build) {
      uc.textContent = 'Servidor atualizado';
      ui.textContent = 'Build: ' + s.update.local_build + ' | Verificado em: ' + (s.update.checked_at || '--');
    } else if (s.update.checked_at) {
      uc.textContent = 'Nenhuma atualização dispon\u00edvel';
      ui.textContent = 'Verificado em: ' + s.update.checked_at;
    } else {
      uc.textContent = 'Aguardando verifica\u00e7\u00e3o...';
    }
    const ucBar = document.querySelector('.update-bar');
    if (s.update.available) { ucBar.className = 'update-bar update-available'; }
    else { ucBar.className = 'update-bar update-ok'; }

    const bl = document.getElementById('bossList');
    bl.innerHTML = '';
    const bossInfo = {
      eikthyr:{name:'Eikthyr',bio:'Meadows',find:'Altar místico nos prados',summon:'2 Troféus de Cervo',weakness:'Perfurante (flechas)',strategy:'Use arco e flechas, esquive dos raios. Boss mais f\u00e1cil do jogo.'},
      gdking:{name:'The Elder',bio:'Black Forest',find:'Altar nas florestas escuras perto de ru\u00ednas',summon:'3 Sementes Ancestrais',weakness:'Fogo',strategy:'Flechas de fogo, use os pilares de pedra como cobertura. Muita vida.'},
      bonemass:{name:'Bonemass',bio:'Swamp',find:'Altar de cr\u00e2nio no brejo',summon:'10 Ossos Murchos',weakness:'Esmagamento (massa) - Imune a perfura\u00e7\u00e3o/corte',strategy:'Po\u00e7\u00e3o de resist\u00eancia a veneno OBRIGAT\u00d3RIA. Use Ma\u00e7a de Ferro.'},
      dragon:{name:'Moder',bio:'Mountain',find:'Altar nas montanhas pr\u00f3ximo a drakes',summon:'3 Ovos de Drag\u00e3o',weakness:'Fogo, Perfurante',strategy:'Po\u00e7\u00e3o de resist\u00eancia ao gelo. Arco com flechas de obsidiana.'},
      goblinking:{name:'Yagluth',bio:'Plains',find:'Altar nas plan\u00edcies c\u00edrculo de pedras',summon:'5 Totens Fuling',weakness:'Gelo, Esmagamento',strategy:'Po\u00e7\u00e3o de resist\u00eancia ao fogo. Use os dedos como cobertura.'},
      queen:{name:'The Queen',bio:'Mistlands',find:'Porta da Rainha nas Mistlands (precisa do Quebrador de Selos)',summon:'Quebrador de Selos (fragmentos) + 3 Trof\u00e9us de Soldado Buscador',weakness:'Perfurante, Fogo',strategy:'Equipamento de n\u00edvel m\u00e1ximo. Mage ou melee pesado. Invoca adds.'},
      fader:{name:'Fader',bio:'Ashlands',find:'Altar Chama Esmeralda em um coliseu nas Ashlands',summon:'3 Sinos (forjados com Fragmentos de Sino em Forja Negra)',weakness:'Gelo / Dano Espiritual - Resistente a fogo',strategy:'Po\u00e7\u00e3o de resist\u00eancia ao fogo OBRIGAT\u00d3RIA. Armas de gelo. Monte Asksvin para mobilidade.'}
    };
    if (d.bosses && d.bosses.length > 0) {
      d.bosses.forEach(b => {
        const info = bossInfo[b.Key] || {name:b.Name||b.Key,bio:'?',find:'?',summon:'?',weakness:'?',strategy:'?'};
        const card = document.createElement('div');
        card.style.cssText = 'background:#0f3460;border-radius:8px;padding:15px;margin-bottom:10px;';
        const header = document.createElement('div');
        header.style.cssText = 'display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;';
        const hleft = document.createElement('div');
        hleft.style.cssText = 'display:flex;align-items:center;gap:10px;';
        const icon = document.createElement('span');
        icon.textContent = b.IsDefeated ? '\u2714\uFE0F' : '\u274C';
        icon.style.fontSize = '1.3em';
        const name = document.createElement('span');
        name.textContent = info.name;
        name.style.fontWeight = 'bold';
        name.style.fontSize = '1.1em';
        hleft.appendChild(icon); hleft.appendChild(name);
        const status = document.createElement('span');
        status.textContent = b.IsDefeated ? 'Derrotado' : 'Vivo';
        status.style.cssText = 'padding:3px 12px;border-radius:12px;font-size:0.85em;font-weight:bold;' + (b.IsDefeated ? 'background:#1a4a3a;color:#4ecca3;' : 'background:#4a1a1a;color:#e84560;');
        header.appendChild(hleft); header.appendChild(status);
        card.appendChild(header);
        const body = document.createElement('div');
        body.style.cssText = 'font-size:0.85em;color:#b0c0d0;line-height:1.6;';
        body.innerHTML =
          '<div><span style="color:#8899aa">\U0001f4cd Bioma:</span> ' + info.bio + '</div>' +
          '<div><span style="color:#8899aa">\U0001f50d Encontrar:</span> ' + info.find + '</div>' +
          '<div><span style="color:#8899aa">\U0001fa84 Invocar:</span> ' + info.summon + '</div>' +
          '<div><span style="color:#8899aa">\U0001f5e1 Fraqueza:</span> ' + info.weakness + '</div>' +
          '<div><span style="color:#8899aa">\U0001f4a1 Estrat\u00e9gia:</span> ' + info.strategy + '</div>';
        card.appendChild(body);
        bl.appendChild(card);
      });
    } else { bl.innerHTML = '<div style="color:#667788;text-align:center;padding:20px;">Aguardando dados dos bosses...</div>'; }
    const wi2 = document.getElementById('worldInfo');
    if (d.world_details && d.world_details.WorldName) {
      wi2.innerHTML = '\U0001f30d Mundo: ' + d.world_details.WorldName + ' | Vers\u00e3o: ' + (d.server.game_version || '--');
    } else {
      wi2.textContent = 'Vers\u00e3o do servidor: ' + (d.server.game_version || '--');
    }

    const pl = document.getElementById('playerList');
    pl.innerHTML = '';
    const players = Object.values(d.players);
    if (players.length === 0) { pl.innerHTML = '<div style="color:#667788">Nenhum jogador visto ainda</div>'; }
    else {
      const skillsMap = {};
      if (d.skills_data) d.skills_data.forEach(s => { skillsMap[s.name] = s.skills; });
      players.forEach(p => {
        const oi = d.odineye_players ? d.odineye_players[p.name] : null;
        const tag = document.createElement('div');
        tag.style.cssText = 'background:#0f3460;border-radius:8px;padding:8px 12px;margin-bottom:5px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;';
        const dot = document.createElement('span');
        dot.style.cssText = 'width:8px;height:8px;border-radius:50%;display:inline-block;flex-shrink:0;' + (p.online ? 'background:#4ecca3;box-shadow:0 0 6px #4ecca3;' : 'background:#e84560;');
        tag.appendChild(dot);
        const nameSpan = document.createElement('span');
        nameSpan.style.cssText = 'font-weight:bold;font-size:0.95em;';
        nameSpan.textContent = p.name;
        tag.appendChild(nameSpan);
        if (p.online && oi) {
          const hpSpan = document.createElement('span');
          hpSpan.style.cssText = 'font-size:0.9em;';
          hpSpan.textContent = '\u2764\ufe0f' + Math.round(oi.Health) + '/' + Math.round(oi.MaxHealth);
          tag.appendChild(hpSpan);
          const spSpan = document.createElement('span');
          spSpan.style.cssText = 'font-size:0.9em;';
          spSpan.textContent = '\u26a1' + Math.round(oi.Stamina);
          tag.appendChild(spSpan);
        }
        if (p.online && skillsMap[p.name]) {
          const skills = skillsMap[p.name];
          const sorted = Object.keys(skills).sort((a,b) => skills[b]-skills[a]);
          const toggle = document.createElement('span');
          toggle.style.cssText = 'font-size:0.8em;color:#4ecca3;cursor:pointer;margin-left:auto;';
          toggle.textContent = '\u25bc Skills';
          toggle.id = 'stoggle_' + p.name.replace(/\\W/g,'_');
          tag.appendChild(toggle);
          const skillPanel = document.createElement('div');
          skillPanel.style.cssText = 'width:100%;display:none;padding:6px 0 2px 0;';
          skillPanel.id = 'spanel_' + p.name.replace(/\\W/g,'_');
          sorted.forEach(sk => {
            const lvl = Math.round(skills[sk]);
            const row = document.createElement('div');
            row.style.cssText = 'display:flex;align-items:center;gap:6px;font-size:0.78em;padding:1px 0;';
            const label = document.createElement('span');
            label.style.cssText = 'width:80px;text-align:right;color:#aabbcc;';
            label.textContent = sk.charAt(0).toUpperCase()+sk.slice(1).toLowerCase();
            row.appendChild(label);
            const barOuter = document.createElement('div');
            barOuter.style.cssText = 'flex:1;height:8px;background:#1a1a2e;border-radius:4px;overflow:hidden;';
            const barInner = document.createElement('div');
            const pct = Math.min(lvl/100, 1);
            const hue = Math.round(pct * 120);
            barInner.style.cssText = 'height:100%;width:'+pct*100+'%;background:hsl('+hue+',80%,50%);border-radius:4px;';
            barOuter.appendChild(barInner);
            row.appendChild(barOuter);
            const val = document.createElement('span');
            val.style.cssText = 'width:28px;text-align:right;color:#e0e0e0;';
            val.textContent = lvl;
            row.appendChild(val);
            skillPanel.appendChild(row);
          });
          tag.appendChild(skillPanel);
          toggle.onclick = function() {
            const sp = document.getElementById('spanel_' + p.name.replace(/\\W/g,'_'));
            const isHidden = sp.style.display === 'none';
            sp.style.display = isHidden ? 'block' : 'none';
            toggle.textContent = isHidden ? '\u25b2 Skills' : '\u25bc Skills';
          };
        }
        if (!p.online) {
          const off = document.createElement('span');
          off.style.cssText = 'font-size:0.75em;color:#667788;';
          off.textContent = 'Offline';
          tag.appendChild(off);
        }
        pl.appendChild(tag);
      });
    }

    const pr = document.getElementById('playerRanking');
    pr.innerHTML = '';
    if (d.player_ranking && d.player_ranking.length > 0) {
      const table = document.createElement('table');
      table.style.cssText = 'width:100%;border-collapse:collapse;font-size:0.9em;';
      d.player_ranking.forEach(r => {
        const tr = document.createElement('tr');
        tr.style.cssText = 'border-bottom:1px solid #0f3460;';
        const medals = {1:'\U0001f947',2:'\U0001f948',3:'\U0001f949'};
        const rankTd = document.createElement('td');
        rankTd.style.cssText = 'padding:6px 4px;text-align:center;width:30px;';
        rankTd.textContent = medals[r.rank] || '#' + r.rank;
        tr.appendChild(rankTd);
        const nameTd = document.createElement('td');
        nameTd.style.cssText = 'padding:6px 8px;';
        nameTd.textContent = r.name;
        tr.appendChild(nameTd);
        const timeTd = document.createElement('td');
        timeTd.style.cssText = 'padding:6px 4px;text-align:right;color:#8899aa;';
        timeTd.textContent = r.hours + 'h ' + r.minutes + 'min';
        tr.appendChild(timeTd);
        const statusTd = document.createElement('td');
        statusTd.style.cssText = 'padding:6px 4px;text-align:center;width:20px;';
        statusTd.textContent = r.online ? '\U0001F7E2' : '\u26AA';
        tr.appendChild(statusTd);
        table.appendChild(tr);
      });
      pr.appendChild(table);
    } else {
      pr.innerHTML = '<div style="color:#667788">Nenhum jogador registrado ainda</div>';
    }

    const ev = document.getElementById('events');
    ev.innerHTML = '';
    if (d.recent_events.length === 0) { ev.innerHTML = '<div style="color:#667788">Nenhum evento registrado</div>'; }
    else {
      d.recent_events.forEach(e => {
        const div = document.createElement('div');
        div.className = 'event ' + e.type;
        const icons = {join: '\u200b\u27a1\ufe0f', leave: '\u2b05\ufe0f', death: '\U0001f480', day: '\U0001f305', server: '\U0001f5a5\ufe0f'};
        div.innerHTML = '<span class="icon">' + (icons[e.type] || '\u2022') + '</span>'
          + '<span class="time">' + new Date(e.time).toLocaleTimeString('pt-BR', {timeZone:'America/Sao_Paulo'}) + '</span>'
          + '<span>' + e.text + '</span>';
        ev.appendChild(div);
      });
    }

    const ac = document.getElementById('adminCard');
    const al = document.getElementById('adminContent');
    if (d.admin_powers && d.admin_powers.length > 0) {
      ac.style.display = 'block';
      al.innerHTML = '';
      d.admin_powers.forEach(p => {
        const card = document.createElement('div');
        card.style.cssText = 'background:#0f3460;border-radius:8px;padding:12px;margin-bottom:8px;';
        const header = document.createElement('div');
        header.style.cssText = 'font-weight:bold;font-size:1em;margin-bottom:8px;';
        header.textContent = p.name;
        card.appendChild(header);
        const btnRow = document.createElement('div');
        btnRow.style.cssText = 'display:flex;flex-wrap:wrap;gap:6px;';
        const powerLabels = {invincible:'\u2764\ufe0f Invinc\u00edvel',hitkill:'\u2694\ufe0f HitKill',invisible:'\U0001f575\ufe0f Invis\u00edvel',nostamina:'\u26a1 Stamina',nohunger:'\U0001f354 Fome'};
        p.powers.forEach(pw => {
          const btn = document.createElement('button');
          const label = powerLabels[pw.id] || pw.id;
          btn.textContent = label;
          btn.style.cssText = 'padding:5px 12px;border:none;border-radius:15px;cursor:pointer;font-size:0.8em;font-weight:bold;transition:all 0.2s;' + (pw.enabled ? 'background:#e94560;color:#fff;box-shadow:0 0 8px #e94560;' : 'background:#1a1a2e;color:#8899aa;');
          btn.onmouseover = function(){ this.style.opacity = '0.8'; };
          btn.onmouseout = function(){ this.style.opacity = '1'; };
          btn.onclick = function(){
            btn.disabled = true;
            fetch('/api/admin/powers/toggle', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({player:p.name, power:pw.id})})
              .then(() => { btn.disabled = false; })
              .catch(() => { btn.disabled = false; });
            pw.enabled = !pw.enabled;
            btn.style.background = pw.enabled ? '#e94560' : '#1a1a2e';
            btn.style.color = pw.enabled ? '#fff' : '#8899aa';
            btn.style.boxShadow = pw.enabled ? '0 0 8px #e94560' : 'none';
          };
          btnRow.appendChild(btn);
        });
        card.appendChild(btnRow);
        al.appendChild(card);
      });
    } else { ac.style.display = 'none'; }

    document.getElementById('refreshInfo').textContent = 'Atualizado: ' + new Date().toLocaleTimeString('pt-BR', {timeZone:'America/Sao_Paulo'});
  } catch(e) { console.error('Erro:', e); }
}
fetchData();
setInterval(fetchData, 5000);
</script>
</body>
</html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        pass


def log_monitor():
    while True:
        parse_log()
        time.sleep(2)


def persist_loop():
    while True:
        save_saved({"playtimes": player_playtimes, "sessions": {k: v for k, v in player_sessions.items() if data["players"].get(k, {}).get("online")}})
        time.sleep(30)


if __name__ == "__main__":
    saved = load_saved()
    player_playtimes.update(saved.get("playtimes", {}))

    print("Iniciando dashboard Valheim...")
    print(f"Dashboard: http://0.0.0.0:{DASHBOARD_PORT}")
    print(f"API:       http://0.0.0.0:{DASHBOARD_PORT}/api")
    print(f"WebMap:    http://0.0.0.0:8081")
    threading.Thread(target=log_monitor, daemon=True).start()
    threading.Thread(target=check_server_status, daemon=True).start()
    threading.Thread(target=update_check_loop, daemon=True).start()
    threading.Thread(target=odineye_loop, daemon=True).start()
    threading.Thread(target=persist_loop, daemon=True).start()
    server = http.server.HTTPServer(("0.0.0.0", DASHBOARD_PORT), DashboardHandler)
    server.serve_forever()
