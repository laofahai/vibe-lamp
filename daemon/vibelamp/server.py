import json
import logging
import signal
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from . import config, lamp_client, ota, discovery
from .model import SessionStore, REMOVE
from .normalize import transition, codex_transition

log = logging.getLogger("vibelamp.server")
store = SessionStore(config.SESSION_TTL_SEC)

# 心跳线程停止信号：set() 后线程在下一轮醒来时优雅退出。
_stop = threading.Event()

# 已知合法状态白名单（normalize 只应产出这些；外加 model.REMOVE 走删除分支）。
# 防御层：未知 state 丢弃并告警，避免坏数据进入 store 推给灯。
_KNOWN_STATES = {"idle", "working", "done", "error", "needs_you"}

# path → 归一化器
_ROUTES = {
    "/event": transition,
    "/event/codex": codex_transition,
}

# —— 调试面板状态（仅供本机 127.0.0.1 网页观测，纯标准库，不影响推灯主链路）——
# 最近事件环形缓冲：每条收到的钩子事件记一行（时间/事件名/会话/归一化结果），供面板回看。
_events = deque(maxlen=200)
# 最近一次推灯结果：面板据此显示「链路正常 / 推送失败(灯失联)」。
_lamp_health = {"ok": None, "ts": None, "target": None}
# 手动测试覆盖：非 None 时 _push_current 改推这份 wire（把灯钉在测试色），用于验证灯/链路。
_test_override = None
_test_lock = threading.Lock()
# 手动测试允许的状态（off/idle → 灭灯）。
_TEST_STATES = {"working", "done", "needs_you", "error", "idle", "off"}


def _result_str(state, tool):
    """把归一化结果压成一行人类可读串，给事件流显示。"""
    if state == REMOVE:
        return "removed"
    if tool and tool != "none":
        return state + "/" + tool
    return state


def _record_event(path, event, sid, result):
    """把一条钩子事件追加进环形缓冲（供调试面板事件流回看）。"""
    _events.append({
        "ts": time.time(),
        "path": path,
        "name": (event or {}).get("hook_event_name") or "?",
        "sid": sid or "",
        "result": result,
    })


def _push_current():
    """把当前应显示的 wire 推给灯。测试覆盖生效时改推 override；记录链路健康。"""
    with _test_lock:
        override = _test_override
    wire = override if override is not None else store.to_wire()
    ok = lamp_client.push(wire)
    _lamp_health["ok"] = ok
    _lamp_health["ts"] = time.time()
    _lamp_health["target"] = config.LAMP_URL
    return ok


def _state_payload():
    """GET /api/state 的载荷：会话快照 + 实际推灯的 wire + 链路健康 + 测试覆盖标记。"""
    with _test_lock:
        override = _test_override
    effective = override if override is not None else store.to_wire()
    return {
        "sessions": store.snapshot(),
        "wire": effective,                 # 灯实际显示的（含测试覆盖）
        "live_wire": store.to_wire(),      # 真实会话推导出的（不含覆盖）
        "override": override,
        "lamp": dict(_lamp_health),
        "now": time.time(),
    }


def _apply_test(cmd):
    """调试面板手动测试：把灯钉在某测试色（action=set），或恢复实时（clear/live）。

    set 时构造一份 wire override，由 _push_current 在覆盖期改推它；面板上点「恢复实时」
    清除覆盖。覆盖期间真实会话仍正常更新 store（面板照常显示），只是灯先听测试。"""
    global _test_override
    action = (cmd or {}).get("action")
    with _test_lock:
        if action == "set":
            state = cmd.get("state", "off")
            tool = cmd.get("tool", "none") or "none"
            if state in ("off", "idle") or state not in _TEST_STATES:
                _test_override = {"sessions": []}
            else:
                _test_override = {"sessions": [{"state": state, "tool": tool}]}
        else:                              # clear / live / 其它 → 取消覆盖
            _test_override = None
        override = _test_override
    _push_current()
    return {"ok": True, "override": override}


def handle_path_event(path, event):
    """按端点路由到对应归一化器。未知路径返回 False。"""
    normalize_fn = _ROUTES.get(path)
    if normalize_fn is None:
        return False
    t = normalize_fn(event)
    if t is None:
        _record_event(path, event, None, "ignored")
        return True       # 路径有效但事件被忽略
    sid, state, tool = t
    # 未知 state 防御：只放行白名单状态与删除信号，其余丢弃并告警。
    if state != REMOVE and state not in _KNOWN_STATES:
        log.warning("丢弃未知状态 %r（会话 %s）", state, sid)
        _record_event(path, event, sid, "dropped:" + str(state))
        return True       # 路径/事件有效，仅该状态不可信 → 忽略
    # in_flight：PreToolUse 表示某工具刚开跑、还没等到 PostToolUse（可能是长构建）。
    # 用于自愈分档——有工具在跑时给更长的静默超时，避免长任务被误判空闲灭灯。
    in_flight = (event or {}).get("hook_event_name") == "PreToolUse"
    store.update(sid, state, tool, in_flight=in_flight)
    _record_event(path, event, sid, _result_str(state, tool))
    _push_current()
    return True


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass          # 客户端提前断开（面板轮询常见）→ 不让它冒泡成 500

    def _send_json(self, code, obj):
        self._send(code, "application/json", json.dumps(obj).encode("utf-8"))

    def do_GET(self):
        # 调试面板（只读观测 + 测试入口），仅本机访问。
        path = urlsplit(self.path).path
        if path in ("/", "/index.html"):
            return self._send(200, "text/html; charset=utf-8",
                              _DASHBOARD_HTML.encode("utf-8"))
        if path == "/api/state":
            return self._send_json(200, _state_payload())
        if path == "/api/events":
            return self._send_json(200, {"events": list(_events)})
        if path == "/api/discover":
            try:
                return self._send_json(200, {"devices": discovery.scan(timeout=3.0)})
            except Exception as e:
                log.exception("discover failed: %s", e)
                return self._send_json(500, {"devices": [], "error": str(e)})
        if path == "/healthz":
            return self._send_json(200, {"ok": True})
        return self._send(404, "text/plain; charset=utf-8", b"not found")

    def do_POST(self):
        # Content-Length 缺失/非数字时按 0 处理，绝不让钩子收到连接重置/500。
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
            if length < 0:
                length = 0
        except (TypeError, ValueError):
            length = 0
        body = self.rfile.read(length) if length else b"{}"
        path = urlsplit(self.path).path
        if path == "/api/ota":
            try:
                qs = parse_qs(urlsplit(self.path).query)
                filename = (qs.get("filename") or ["firmware.bin"])[0]
                ok = ota.upload_bytes(body, filename=filename)
                return self._send_json(200 if ok else 502, {"ok": bool(ok)})
            except Exception as e:
                log.exception("ota upload failed: %s", e)
                return self._send_json(500, {"ok": False, "error": str(e)})
        if path == "/api/bind":
            try:
                item = json.loads(body or b"{}")
                cfg = discovery.bind(item)
                _lamp_health["target"] = cfg.get("lamp_url")
                return self._send_json(200, {"ok": True, "config": cfg})
            except Exception as e:
                log.exception("bind failed: %s", e)
                return self._send_json(500, {"ok": False, "error": str(e)})
        try:
            event = json.loads(body or b"{}")
        except Exception:
            self.send_response(400); self.end_headers(); return
        # 调试面板手动测试：直接钉灯，不进会话模型。
        if path == "/api/test":
            try:
                result = _apply_test(event)
            except Exception as e:
                log.exception("apply_test failed: %s", e)
                result = {"ok": False}
            return self._send_json(200, result)
        try:
            ok = handle_path_event(path, event)
        except Exception as e:
            log.exception("handle_path_event failed: %s", e)   # 绝不让钩子失败
            ok = True
        if not ok:
            self.send_response(404); self.end_headers(); return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, *a):
        pass


def _heartbeat_loop():
    """每 HEARTBEAT_SEC 清扫死会话、自愈卡住的 working、并重推；收到停止信号即优雅退出。"""
    # 用 Event.wait 替代 time.sleep：停止信号一到立即返回，不必等满一个周期。
    while not _stop.wait(config.HEARTBEAT_SEC):
        try:
            store.sweep()
            # ESC/kill 不发任何钩子 → working 会卡住（蓝）；静默超时降级 idle 让灯自愈。
            # needs_you(红·该你了)故意不在此降级——要一直提醒你（见 model.demote_stale）。
            # 两档：没工具在跑用短超时、有长构建在跑用长超时。
            store.demote_stale(config.WORKING_IDLE_TIMEOUT_SEC,
                               config.WORKING_TOOL_TIMEOUT_SEC)
            _push_current()
        except Exception as e:
            log.debug("heartbeat error: %s", e)


# 当前活动的 HTTP 服务实例（便于信号处理与测试驱动 shutdown）。
_httpd = None


def serve(port=None):
    """启动守护进程：心跳线程 + HTTP 服务，并装好优雅退出。

    port 默认取 config.LISTEN_PORT；测试可传 0 让系统分配空闲端口。
    """
    global _httpd
    _stop.clear()
    hb = threading.Thread(target=_heartbeat_loop, daemon=True)
    hb.start()
    listen_port = config.LISTEN_PORT if port is None else port
    httpd = ThreadingHTTPServer((config.LISTEN_HOST, listen_port), Handler)
    _httpd = httpd

    def _graceful_shutdown(signum, _frame):
        log.info("收到信号 %s，正在优雅退出守护进程……", signum)
        _stop.set()                 # 通知心跳线程退出
        # shutdown() 须在另一线程调用（不能在 serve_forever 所在线程里调）。
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    # 注册 launchd SIGTERM 与 Ctrl-C SIGINT；非主线程注册会抛 ValueError，吞掉即可。
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _graceful_shutdown)
        except (ValueError, OSError):
            pass

    log.info("vibelamp daemon listening %s:%d -> %s（调试面板 http://%s:%d/）",
             config.LISTEN_HOST, httpd.server_address[1], config.LAMP_URL,
             config.LISTEN_HOST, httpd.server_address[1])
    try:
        httpd.serve_forever()
    finally:
        _stop.set()                 # 兜底：任何退出路径都让心跳线程收手
        httpd.server_close()        # 释放监听 socket
        hb.join(timeout=config.HEARTBEAT_SEC + 1.0)
        _httpd = None
        log.info("vibelamp daemon 已停止")


# —— 调试面板（单文件 HTML，内联 CSS/JS，1s 轮询 /api/state 与 /api/events）——
# 纯前端，无外部依赖；状态→颜色映射与固件/文档一致，仅用于「看得见」地调试。
_DASHBOARD_HTML = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VibeLamp 调试面板</title>
<style>
:root{--bg:#0d1117;--panel:#161b22;--border:#30363d;--fg:#e6edf3;--dim:#8b949e}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
 font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
header{display:flex;align-items:center;gap:16px;padding:14px 18px;border-bottom:1px solid var(--border)}
.swatch{width:46px;height:46px;border-radius:10px;border:1px solid var(--border);
 box-shadow:0 0 0 3px #0008 inset;flex:none}
.li{display:flex;flex-direction:column}.li b{font-size:15px}.li span{color:var(--dim);font-size:12px}
main{padding:18px;display:grid;gap:18px;max-width:1040px}
section{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:14px}
section h2{margin:0 0 10px;font-size:12px;color:var(--dim);letter-spacing:.06em;text-transform:uppercase}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--border);white-space:nowrap}
th{color:var(--dim);font-weight:500}
td.r{color:#e6edf3}
.btns{display:flex;flex-wrap:wrap;gap:8px}
button{cursor:pointer;border:1px solid var(--border);background:#21262d;color:var(--fg);
 padding:7px 12px;border-radius:8px;font:inherit}
button:hover{border-color:#58a6ff}
.iconbtn{padding:6px 10px;font-size:12px}
.banner{padding:8px 12px;border-radius:8px;background:#3d2d00;border:1px solid #9e7700;
 color:#f0d68a;display:none}.banner.on{display:block}
.banner a{color:#f0d68a}
.modal{position:fixed;inset:0;background:#0009;display:none;align-items:center;justify-content:center;padding:18px}
.modal.on{display:flex}
.dialog{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:16px;
 width:min(460px,100%);box-shadow:0 18px 60px #000a}
.dialog h2{margin:0 0 12px;font-size:15px}
.dialog input{width:100%;box-sizing:border-box;margin:8px 0 12px}
.dialog .row{display:flex;gap:8px;justify-content:flex-end}
.dim{color:var(--dim)}.ok{color:#3fb950}.bad{color:#f85149}
@keyframes breathe{0%,100%{opacity:.35}50%{opacity:1}}
@keyframes blink{0%,49%{opacity:1}50%,100%{opacity:.12}}
@keyframes flash{0%,79%{opacity:1}40%{opacity:.1}}
@keyframes fade{0%{opacity:1}100%{opacity:.3}}
.anim-breathe{animation:breathe 2.4s ease-in-out infinite}
.anim-blink{animation:blink 1.1s steps(1) infinite}
.anim-flash{animation:flash .5s steps(1) infinite}
.anim-fade{animation:fade 2s ease-out infinite alternate}
</style></head><body>
<header>
 <div id="sw" class="swatch"></div>
 <div class="li"><b id="lampstate">—</b><span id="lampsub"></span></div>
 <div class="li" style="margin-left:auto;text-align:right">
  <b id="health">链路 —</b><span id="target"></span></div>
 <button class="iconbtn" onclick="openBind()">绑定</button>
 <button class="iconbtn" onclick="openOta()">固件</button>
</header>
<main>
 <div id="banner" class="banner">🧪 测试模式:灯被钉在测试色,实时状态暂不上灯 —
  <a href="#" onclick="test('clear');return false">点此恢复实时</a></div>
 <section><h2>手动测试 · 直接给灯推一个状态色(验证灯 / 链路是否通)</h2>
  <div class="btns">
   <button onclick="test('set','working','code')">🔵 蓝·写码</button>
   <button onclick="test('set','working','command')">🟣 紫·命令</button>
   <button onclick="test('set','working','search')">🩵 青·检索</button>
   <button onclick="test('set','done','none')">🟢 绿·完成</button>
   <button onclick="test('set','needs_you','none')">🔴 红·该你了</button>
   <button onclick="test('set','error','none')">🔴 红·错误常亮</button>
   <button onclick="test('set','off')">⚫ 灭</button>
   <button onclick="test('clear')">↩︎ 恢复实时</button>
  </div></section>
 <section><h2>当前会话</h2>
  <table><thead><tr><th>会话</th><th>状态</th><th>工具</th><th>距上次事件</th></tr></thead>
  <tbody id="sessions"></tbody></table></section>
 <section><h2>事件流 · 最近 200 条(新→旧)</h2>
  <table><thead><tr><th>时间</th><th>事件</th><th>会话</th><th>→ 结果</th></tr></thead>
 <tbody id="events"></tbody></table></section>
</main>
<div id="otaModal" class="modal" onclick="closeOta(event)">
 <div class="dialog" onclick="event.stopPropagation()">
  <h2>固件升级</h2>
  <div class="dim">上传到当前绑定的灯。请使用 PlatformIO 生成的 firmware.bin，升级时不要断电。</div>
  <input id="otaFile" type="file" accept=".bin">
  <div id="otaMsg" class="dim">当前目标见右上角。</div>
  <div class="row"><button onclick="hideOta()">取消</button><button onclick="otaUpload()">上传</button></div>
 </div>
</div>
<div id="bindModal" class="modal" onclick="closeBind(event)">
 <div class="dialog" onclick="event.stopPropagation()">
  <h2>绑定设备</h2>
  <div class="dim">灯配网成功后，扫描当前局域网。IP 变了也没关系，绑定后会按设备名/MAC 自动找回。</div>
  <div class="row" style="margin-top:12px"><button onclick="scanDevices()">扫描设备</button></div>
  <div id="bindMsg" class="dim" style="margin-top:10px">尚未扫描。</div>
  <div id="deviceList" style="margin-top:10px"></div>
  <div class="row"><button onclick="hideBind()">关闭</button></div>
 </div>
</div>
<script>
const COLOR={
 'working/code':['#1e66ff','蓝 · 写码','breathe'],
 'working/command':['#a020f0','紫 · 命令','breathe'],
 'working/search':['#00c8c8','青 · 检索','breathe'],
 'working/none':['#1e66ff','蓝 · 工作','breathe'],
 'done/none':['#18c018','绿 · 完成','fade'],
 'needs_you/none':['#ff2828','红 · 该你了','blink'],
 'error/none':['#ff2828','红 · 错误','']};
function colorFor(wire){
 const s=((wire&&wire.sessions)||[])[0];
 if(!s) return ['#1c2128','熄灭 · idle',''];
 return COLOR[s.state+'/'+s.tool]||COLOR[s.state+'/none']||['#888888',s.state,''];}
function fmt(ts){return new Date(ts*1000).toTimeString().slice(0,8);}
function shortSid(sid){if(!sid)return '';const p=sid.split(':');return p[0]+':'+((p[1]||'').slice(0,8));}
function esc(s){return String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
async function tick(){
 try{
  const st=await (await fetch('/api/state')).json();
  const [col,label,anim]=colorFor(st.wire);
  const sw=document.getElementById('sw');
  sw.style.background=col; sw.className='swatch'+(anim?(' anim-'+anim):'');
  document.getElementById('lampstate').textContent=label;
  document.getElementById('lampsub').textContent=((st.wire&&st.wire.sessions)||[]).length+' 个活动会话上灯';
  document.getElementById('banner').className='banner'+(st.override?' on':'');
  const h=st.lamp||{},he=document.getElementById('health');
  if(h.ok===true){he.textContent='链路 正常 ✓';he.className='ok';}
  else if(h.ok===false){he.textContent='链路 推送失败(灯可能失联)';he.className='bad';}
  else{he.textContent='链路 —';he.className='';}
  document.getElementById('target').textContent=h.target||'';
  const ss=st.sessions||[];
  document.getElementById('sessions').innerHTML = ss.length
   ? ss.map(s=>`<tr><td>${esc(shortSid(s.sid))}</td><td class="r">${esc(s.state)}</td><td class="dim">${esc(s.tool)}</td><td class="dim">${s.age_sec}s</td></tr>`).join('')
   : '<tr><td colspan="4" class="dim">无</td></tr>';
  const ev=await (await fetch('/api/events')).json();
  document.getElementById('events').innerHTML =
   (ev.events||[]).slice().reverse().map(e=>`<tr><td class="dim">${fmt(e.ts)}</td><td>${esc(e.name)}</td><td class="dim">${esc(shortSid(e.sid))}</td><td class="r">${esc(e.result)}</td></tr>`).join('');
 }catch(e){}
}
async function test(action,state,tool){
 try{await fetch('/api/test',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({action,state,tool})});}catch(e){}
 tick();
}
function openOta(){document.getElementById('otaModal').className='modal on';}
function hideOta(){document.getElementById('otaModal').className='modal';}
function closeOta(e){if(e.target.id==='otaModal')hideOta();}
function openBind(){document.getElementById('bindModal').className='modal on';}
function hideBind(){document.getElementById('bindModal').className='modal';}
function closeBind(e){if(e.target.id==='bindModal')hideBind();}
async function scanDevices(){
 const msg=document.getElementById('bindMsg'), list=document.getElementById('deviceList');
 msg.textContent='正在扫描当前局域网...'; list.innerHTML='';
 try{
  const out=await (await fetch('/api/discover')).json();
  const ds=out.devices||[];
  msg.textContent=ds.length?('发现 '+ds.length+' 台设备'):'没有发现设备。确认灯已配网并和 Mac 在同一局域网。';
  list.innerHTML=ds.map(d=>`<div style="border:1px solid var(--border);border-radius:8px;padding:8px;margin:8px 0">
   <b>${esc(d.host||'')}</b><br><span class="dim">${esc(d.mac||'')} · ${esc(d.ip||'')}</span>
   <div class="row" style="margin-top:8px"><button onclick='bindDevice(${JSON.stringify(d)})'>绑定这台</button></div>
  </div>`).join('');
 }catch(e){msg.textContent='扫描失败：'+e;}
}
async function bindDevice(d){
 const msg=document.getElementById('bindMsg');
 try{
  const out=await (await fetch('/api/bind',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)})).json();
  msg.textContent=out.ok?'已绑定 '+d.host+'，后续会自动使用 '+d.ip:'绑定失败';
  tick();
 }catch(e){msg.textContent='绑定失败：'+e;}
}
async function otaUpload(){
 const input=document.getElementById('otaFile'), msg=document.getElementById('otaMsg');
 if(!input.files.length){msg.textContent='请先选择 firmware.bin'; return;}
 const file=input.files[0];
 msg.textContent='正在上传 '+file.name+'，不要断电...';
 try{
  const res=await fetch('/api/ota?filename='+encodeURIComponent(file.name), {
   method:'POST',
   headers:{'Content-Type':'application/octet-stream'},
   body:await file.arrayBuffer()
  });
  const out=await res.json();
  msg.textContent=out.ok?'上传成功，灯正在重启':'上传失败：守护进程无法把固件传给灯';
 }catch(e){msg.textContent='上传失败：'+e;}
}
tick(); setInterval(tick,1000);
</script></body></html>"""
