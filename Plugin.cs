using System;
using System.Collections;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Reflection;
using System.Text;
using System.Threading;
using BepInEx;
using HarmonyLib;
using UnityEngine;

namespace AdminPowers
{
    [BepInPlugin("valheim.adminpowers", "Admin Powers", "1.0.0")]
    public class AdminPowersPlugin : BaseUnityPlugin
    {
        static readonly ConcurrentDictionary<string, HashSet<string>> _powers = new ConcurrentDictionary<string, HashSet<string>>();
        static readonly string[] POWER_LIST = { "invincible", "hitkill", "invisible", "nostamina", "nohunger" };

        static Type _tChar, _tHitData, _tZNet, _tZDOMan, _tZDO, _tZNetView, _tSEMan, _tPlayer;
        static MethodInfo _miGetZDO, _miGetStr, _miGetAttacker;
        static FieldInfo _fiNview, _fiOwner, _fiGhost, _fiDmg;
        static PropertyInfo _piInstance;
        static Harmony _harmony;
        const BindingFlags FLAGS = BindingFlags.Instance | BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;

        void Awake()
        {
            LoadReflection();
            PatchHarmony();
            StartHttp();
            Logger.LogInfo("Admin Powers loaded on :8091");
        }

        void LoadReflection()
        {
            var av = Assembly.LoadFrom(Path.Combine(Paths.GameRootPath, "valheim_server_Data/Managed/assembly_valheim.dll"));

            _tChar = av.GetType("Character");
            _tHitData = av.GetType("HitData");
            _tZNet = av.GetType("ZNet");
            _tZDOMan = av.GetType("ZDOMan");
            _tZDO = av.GetType("ZDO");
            _tZNetView = av.GetType("ZNetView");
            _tSEMan = av.GetType("SEMan");
            _tPlayer = av.GetType("Player");

            _fiNview = _tChar.GetField("m_nview", FLAGS);
            _fiOwner = _tSEMan.GetField("m_owner", FLAGS);
            _fiGhost = _tPlayer?.GetField("m_ghostMode", FLAGS);
            _fiDmg = _tHitData.GetField("m_damage", FLAGS);

            _miGetZDO = _tZNetView.GetMethod("GetZDO", Type.EmptyTypes);
            _miGetStr = _tZDO.GetMethod("GetString", new[]{ typeof(string), typeof(string) });
            _miGetAttacker = _tHitData.GetMethod("GetAttacker", Type.EmptyTypes);

            _piInstance = _tZNet.GetProperty("instance", FLAGS);

            var ok = _fiNview != null && _miGetZDO != null && _miGetStr != null;
            Logger.LogInfo("Reflection: " + (ok ? "OK" : "FAIL"));
            if (!ok)
            {
                if (_fiNview == null) Logger.LogError("  m_nview not found");
                if (_miGetZDO == null) Logger.LogError("  GetZDO not found");
                if (_miGetStr == null) Logger.LogError("  GetString not found");
            }
        }

        void PatchHarmony()
        {
            _harmony = new Harmony("valheim.adminpowers");
            var rpcDmg = _tChar.GetMethod("RPC_Damage", FLAGS);
            if (rpcDmg != null)
            {
                _harmony.Patch(rpcDmg, new HarmonyMethod(typeof(AdminPowersPlugin).GetMethod("PreRPC", FLAGS)));
                Logger.LogInfo("Patched Character.RPC_Damage");
            }
            else Logger.LogError("RPC_Damage not found");

            var haveStam = _tChar.GetMethod("HaveStamina", new[]{ typeof(float) });
            if (haveStam != null)
            {
                _harmony.Patch(haveStam, new HarmonyMethod(typeof(AdminPowersPlugin).GetMethod("PreHaveStamina", FLAGS)));
                Logger.LogInfo("Patched Character.HaveStamina");
            }
            else Logger.LogInfo("HaveStamina not found, nostamina power unavailable");

            var useStam = _tChar.GetMethod("UseStamina", new[]{ typeof(float) });
            if (useStam != null)
            {
                _harmony.Patch(useStam, new HarmonyMethod(typeof(AdminPowersPlugin).GetMethod("PreUseStamina", FLAGS)));
                Logger.LogInfo("Patched Character.UseStamina");
            }
            else Logger.LogInfo("UseStamina not found");

            var inGhost = _tPlayer?.GetMethod("InGhostMode", Type.EmptyTypes);
            if (inGhost != null)
            {
                _harmony.Patch(inGhost, null, new HarmonyMethod(typeof(AdminPowersPlugin).GetMethod("PostGhost", FLAGS)));
                Logger.LogInfo("Patched Player.InGhostMode");
            }
            else Logger.LogError("InGhostMode not found");
        }

        static bool PreRPC(Component __instance, object hit)
        {
            try
            {
                string targetName = GetName(__instance);
                if (targetName == null) return true;

                if (Has(targetName, "invincible") || Has(targetName, "hitkill"))
                    return false;

                Component attacker = null;
                try { attacker = _miGetAttacker.Invoke(hit, null) as Component; } catch {}

                string atkName = attacker != null ? GetName(attacker) : null;
                if (atkName != null && Has(atkName, "hitkill"))
                {
                    object dmg = _fiDmg.GetValue(hit);
                    if (dmg != null)
                    {
                        foreach (var f in dmg.GetType().GetFields(FLAGS))
                            if (f.FieldType == typeof(float))
                            {
                                float v = (float)f.GetValue(dmg);
                                if (v > 0f) f.SetValue(dmg, 999999f);
                            }
                    }
                }
                return true;
            }
            catch { return true; }
        }

        static bool PreHaveStamina(Component __instance, float __0, ref bool __result)
        {
            try
            {
                string name = GetName(__instance);
                if (name != null && Has(name, "nostamina")) { __result = true; return false; }
                return true;
            }
            catch { return true; }
        }

        static bool PreUseStamina(Component __instance, float __0)
        {
            try
            {
                string name = GetName(__instance);
                if (name != null && Has(name, "nostamina")) return false;
            }
            catch {}
            return true;
        }

        static void PostGhost(ref bool __result, Component __instance)
        {
            try
            {
                string name = GetName(__instance);
                if (name != null && Has(name, "invisible"))
                    __result = true;
            }
            catch {}
        }

        static string GetName(Component c)
        {
            if (c == null) return null;
            var nv = _fiNview.GetValue(c);
            if (nv == null) return null;
            var zdo = _miGetZDO.Invoke(nv, null);
            if (zdo == null) return null;
            return (string)_miGetStr.Invoke(zdo, new object[] { "name", "" });
        }

        static bool Has(string player, string power)
        {
            if (string.IsNullOrEmpty(player)) return false;
            if (_powers.TryGetValue(player, out var set) && set != null)
                return set.Contains(power);
            return false;
        }

        void StartHttp()
        {
            new Thread(() =>
            {
                try
                {
                    var hl = new HttpListener();
                    hl.Prefixes.Add("http://*:8091/");
                    hl.Start();
                    Logger.LogInfo("HTTP :8091 ready");
                    while (true)
                    {
                        try { Handle(hl.GetContext()); }
                        catch (Exception e) { Logger.LogError("HTTP: " + e.Message); }
                    }
                }
                catch (Exception e) { Logger.LogError("HTTP init: " + e.Message); }
            }).Start();
        }

        void Handle(HttpListenerContext ctx)
        {
            var path = ctx.Request.Url.AbsolutePath.TrimEnd('/');
            if (path == "/api/powers" && ctx.Request.HttpMethod == "GET")
                Ok(ctx, "application/json", BuildPlayersJson());
            else if (path == "/api/powers/toggle" && ctx.Request.HttpMethod == "POST")
            {
                string json;
                using (var r = new StreamReader(ctx.Request.InputStream)) json = r.ReadToEnd();
                Toggle(json);
                Ok(ctx, "application/json", "{\"ok\":true}");
            }
            else Ok(ctx, "text/plain", "Not found", 404);
        }

        void Toggle(string json)
        {
            try
            {
                var d = JsonParse(json);
                if (!d.TryGetValue("player", out var p) || !d.TryGetValue("power", out var w)) return;
                var set = _powers.GetOrAdd(p, _ => new HashSet<string>());
                lock (set) { if (set.Contains(w)) set.Remove(w); else set.Add(w); }
                Logger.LogInfo($"{p}: {w} = {(Has(p,w)?"ON":"OFF")}");
            }
            catch (Exception e) { Logger.LogError("Toggle: " + e.Message); }
        }

        string BuildPlayersJson()
        {
            var names = new List<string>();
            try
            {
                object znet = null;
                try { znet = _piInstance.GetValue(null, null); } catch {}
                if (znet == null) try { znet = _piInstance.GetValue(null); } catch {}
                if (znet != null)
                {
                    var fieldPeers = _tZNet.GetField("m_peers", FLAGS);
                    IList peers = null;
                    if (fieldPeers != null) peers = (IList)fieldPeers.GetValue(znet);
                    if (peers != null && peers.Count > 0)
                    {
                        var tPeer = peers[0].GetType();
                        var fiDisp = tPeer.GetField("m_playerName", FLAGS);
                        foreach (var peer in peers)
                        {
                            var n = fiDisp?.GetValue(peer) as string;
                            if (!string.IsNullOrEmpty(n)) names.Add(n);
                        }
                    }
                }
            }
            catch {}

            var sb = new StringBuilder("[");
            bool first = true;
            foreach (var name in names)
            {
                if (!first) sb.Append(",");
                first = false;
                sb.Append("{\"name\":").Append(Escape(name)).Append(",\"powers\":[");
                _powers.TryGetValue(name, out var set);
                bool pFirst = true;
                foreach (var pw in POWER_LIST)
                {
                    if (!pFirst) sb.Append(",");
                    pFirst = false;
                    sb.Append("{\"id\":").Append(Escape(pw))
                      .Append(",\"enabled\":")
                      .Append(set != null && set.Contains(pw) ? "true" : "false")
                      .Append("}");
                }
                sb.Append("]}");
            }
            sb.Append("]");
            return sb.ToString();
        }

        static string Escape(string s) =>
            s == null ? "null" : "\"" + s.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";

        Dictionary<string, string> JsonParse(string json)
        {
            var r = new Dictionary<string, string>();
            try
            {
                int i = json.IndexOf('{'), j = json.LastIndexOf('}');
                if (i >= 0 && j > i)
                {
                    foreach (var part in json.Substring(i + 1, j - i - 1).Split(','))
                    {
                        var eq = part.IndexOf(':');
                        if (eq > 0)
                            r[part.Substring(0, eq).Trim().Trim('"')] = part.Substring(eq + 1).Trim().Trim('"');
                    }
                }
            }
            catch {}
            return r;
        }

        void Ok(HttpListenerContext ctx, string ct, string body, int code = 200)
        {
            var buf = Encoding.UTF8.GetBytes(body);
            ctx.Response.StatusCode = code;
            ctx.Response.ContentType = ct;
            ctx.Response.ContentLength64 = buf.Length;
            ctx.Response.OutputStream.Write(buf, 0, buf.Length);
            ctx.Response.OutputStream.Close();
        }
    }
}
