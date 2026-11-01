"""Lot 42 — application par ancres (tolérante aux modifs du Lot 41). Usage : python3 apply_l42.py /app <dossier_l42>"""
import re, sys, pathlib
root, src = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
# ---------- agent
p = root / "avatar_agent/agent.py"; s = p.read_text()
if "Lot 42 : écran en direct" not in s:
    block = (src / "agent_block.py").read_text()
    a = '\nif __name__ == "__main__":'
    assert s.count(a) == 1, "ancre __main__"
    s = s.replace(a, block + "\n" + a, 1)
    g = "    await session.generate_reply(instructions=GREET"
    assert s.count(g) == 1, "ancre GREET"
    s = s.replace(g, "    await attach_screen(ctx, session, identity)  # Lot 42 : écran en direct + internet + autonomie\n" + g, 1)
    s, n = re.subn(r"max_tool_steps=\d+", "max_tool_steps=60", s)
    assert n >= 1, "max_tool_steps"
    p.write_text(s)
# ---------- frontend
w = root / "frontend/src/components/admin/avatarScreenWatch.js"
w.write_text((src / "avatarScreenWatch.js").read_text())
d = root / "frontend/src/components/admin/AvatarDock.jsx"; s = d.read_text()
if "startScreenWatch" not in s:
    imp = [l for l in s.splitlines() if l.startswith("import ")][-1]
    s = s.replace(imp, imp + '\nimport { startScreenWatch, stopScreenWatch, markAgentAction } from "./avatarScreenWatch";', 1)
    a = "await r.connect(data.url, data.token);"
    assert s.count(a) == 1, "ancre connect"
    s = s.replace(a, a + "\n    startScreenWatch(r);", 1)
    a = 'function reset(message = "") {'
    assert s.count(a) == 1, "ancre reset"
    s = s.replace(a, a + "\n  stopScreenWatch();", 1)
    a = "Object.entries(HANDLERS).forEach(([name, fn]) => r.registerRpcMethod(name, fn));"
    assert s.count(a) == 1, "ancre rpc"
    s = s.replace(a, "Object.entries(HANDLERS).forEach(([name, fn]) => r.registerRpcMethod(name, async (d) => { markAgentAction(); try { return await fn(d); } finally { markAgentAction(); } }));", 1)
    d.write_text(s)
print("L42 OK")
