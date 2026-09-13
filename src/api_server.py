"""
🌐 HTTP API SERVER — CẦU NỐI GIỮA GIAO DIỆN WEB VÀ REACT AGENT

Phơi ReAct Agent (Cấp 3) ra dưới dạng HTTP API để giao diện Next.js gọi vào,
dùng thư viện chuẩn `http.server` nên KHÔNG cần cài thêm dependency nào.

Chạy:
    python src/api_server.py            # mặc định cổng 8080
    python src/api_server.py --port 9000

Các endpoint:
    GET  /api/health     — trạng thái hệ thống, provider, danh sách tool đang công bố
    GET  /api/doctors    — danh mục bác sĩ & chuyên khoa (phục vụ dropdown trên UI)
    GET  /api/patients   — danh sách bệnh nhân mô phỏng (phục vụ demo chọn hồ sơ)
    POST /api/chat       — gửi câu hỏi, nhận lại toàn bộ chuỗi ReAct + câu trả lời
    GET  /api/trace      — đọc lại Waterfall Trace Log gần nhất
"""

import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv

from app import run_react_agent, save_waterfall_trace
from mcp_server import MCPAcademicServer
from providers import get_llm_provider
from tools import DOCTORS_PATH, HISTORY_PATH, _load_json

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Khởi tạo một lần, dùng chung cho mọi request
PROVIDER = get_llm_provider()
MCP = MCPAcademicServer()

# Trace log theo phiên — phục vụ hiển thị lại trên giao diện
SESSIONS: dict = {}

# Bộ nhớ hội thoại ngắn hạn theo phiên — giữ các lượt hỏi/đáp trước đó để Agent
# nhớ ngữ cảnh qua nhiều lượt chat (ví dụ người bệnh trả lời "tôi khám lần đầu").
CONVERSATIONS: dict = {}

# Số lượt hội thoại gần nhất được giữ lại (tránh phình context và tốn token)
MAX_HISTORY_TURNS = 12


def _json_bytes(payload) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


class AgentAPIHandler(BaseHTTPRequestHandler):
    """Bộ xử lý request cho API của Trợ lý Vinmec"""

    server_version = "VinmecAgentAPI/1.0"

    # ----------------------------------------------------------------- helpers
    def _send(self, status: int, payload):
        body = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        """Rút gọn log mặc định cho đỡ rối terminal"""
        sys.stderr.write(f"  · {self.command} {self.path} → {args[1] if len(args) > 1 else ''}\n")

    # ------------------------------------------------------------------ routes
    def do_OPTIONS(self):
        self._send(204, {})

    def do_GET(self):
        route = urlparse(self.path).path

        if route in ("/api/health", "/health"):
            tools = MCP.list_tools()
            model = getattr(PROVIDER, "model_name", "n/a")
            is_mock = PROVIDER.__class__.__name__ == "MockOfflineProvider"
            return self._send(200, {
                "status": "ok",
                "provider": PROVIDER.__class__.__name__,
                "model": model,
                "live_llm": not is_mock,
                "mcp_server": MCP.server_name,
                "mcp_version": MCP.version,
                "tools": [
                    {"name": t["name"], "description": t.get("description", "")[:160]}
                    for t in tools
                ],
            })

        if route == "/api/doctors":
            db = _load_json(DOCTORS_PATH)
            return self._send(200, {
                "specialties": list(db["specialties"].keys()),
                "doctors": list(db["doctors"].values()),
            })

        if route == "/api/patients":
            db = _load_json(HISTORY_PATH)
            return self._send(200, {
                "patients": [
                    {
                        "patient_id": p["patient_id"],
                        "full_name": p["full_name"],
                        "phone": p.get("phone", ""),
                        "year_of_birth": p.get("year_of_birth"),
                        "gender": p.get("gender"),
                        "chronic_conditions": p.get("chronic_conditions", []),
                        "allergies": p.get("allergies", []),
                        "total_visits": len(p.get("visit_history", [])),
                    }
                    for p in db["patients"].values()
                ]
            })

        if route == "/api/trace":
            path = os.path.join(BASE_DIR, "docs", "trace_waterfall.json")
            if not os.path.exists(path):
                return self._send(200, {"trace": []})
            with open(path, "r", encoding="utf-8") as f:
                return self._send(200, {"trace": json.load(f)})

        return self._send(404, {"error": f"Không có endpoint '{route}'"})

    def do_POST(self):
        route = urlparse(self.path).path
        if route != "/api/chat":
            return self._send(404, {"error": f"Không có endpoint '{route}'"})

        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError) as e:
            return self._send(400, {"error": f"Body không phải JSON hợp lệ: {e}"})

        message = (payload.get("message") or "").strip()
        if not message:
            return self._send(400, {"error": "Thiếu trường 'message'"})

        session_id = payload.get("session_id") or f"WEB-{int(time.time())}"
        turn = len(SESSIONS.get(session_id, [])) + 1

        # Nạp lại bộ nhớ hội thoại của phiên để Agent nhớ ngữ cảnh các lượt trước
        history = CONVERSATIONS.setdefault(session_id, [])

        started = time.time()
        try:
            logs = run_react_agent(message, PROVIDER, MCP,
                                   test_case_id=f"{session_id}-T{turn:02d}",
                                   history=history)
        except Exception as e:
            return self._send(500, {"error": f"Agent gặp lỗi khi xử lý: {e}"})

        # Cắt bớt lịch sử quá dài, nhưng luôn giữ lượt hỏi đầu tiên làm ngữ cảnh gốc
        if len(history) > MAX_HISTORY_TURNS * 3:
            CONVERSATIONS[session_id] = history[:1] + history[-(MAX_HISTORY_TURNS * 2):]

        elapsed = round((time.time() - started) * 1000, 2)

        # Bóc các thành phần giao diện cần hiển thị
        steps = []
        final_answer = ""
        booking = None
        ranked = None
        patient = None

        for ev in logs:
            if ev["action_type"] == "TOOL_EXECUTION":
                obs = ev.get("observation", {})
                steps.append({
                    "step": ev["step"],
                    "kind": "tool",
                    "thought": ev.get("thought", ""),
                    "tool_name": ev["tool_name"],
                    "arguments": ev.get("arguments", {}),
                    "status": obs.get("status"),
                    "summary": _summarize(ev["tool_name"], obs),
                    "llm_latency_ms": ev.get("llm_latency_ms"),
                    "mcp_latency_ms": ev.get("mcp_latency_ms"),
                })
                if ev["tool_name"] == "book_medical_appointment" and obs.get("booking_id"):
                    booking = obs["appointment"] | {"booking_id": obs["booking_id"]}
                elif ev["tool_name"] == "rank_doctors_for_patient" and obs.get("ranked_doctors"):
                    ranked = {
                        "specialty": obs.get("specialty"),
                        "recommendation": obs.get("recommendation"),
                        "scoring_criteria": obs.get("scoring_criteria"),
                        "doctors": obs["ranked_doctors"],
                    }
                elif ev["tool_name"] == "find_doctor_schedule" and obs.get("doctors"):
                    ranked = ranked or {
                        "specialty": obs.get("specialty"),
                        "recommendation": "",
                        "doctors": [
                            d | {"rank": i + 1, "match_score": None,
                                 "is_returning_doctor": False, "ranking_reasons": []}
                            for i, d in enumerate(obs["doctors"])
                        ],
                    }
                elif ev["tool_name"] == "get_patient_history" and obs.get("status") == "SUCCESS":
                    patient = {
                        "patient_id": obs.get("patient_id"),
                        "full_name": obs.get("full_name"),
                        "allergies": obs.get("allergies", []),
                        "chronic_conditions": obs.get("chronic_conditions", []),
                        "total_visits": obs.get("total_visits", 0),
                        "quick_note": obs.get("quick_note", {}),
                        "visit_history": obs.get("visit_history", []),
                    }
            else:
                final_answer = ev.get("output", "")
                steps.append({
                    "step": ev["step"],
                    "kind": "final",
                    "thought": ev.get("thought", ""),
                    "summary": "Tổng hợp câu trả lời cho người bệnh",
                })

        SESSIONS.setdefault(session_id, []).extend(logs)
        save_waterfall_trace(SESSIONS[session_id])

        self._send(200, {
            "session_id": session_id,
            "turn": turn,
            "answer": final_answer,
            "steps": steps,
            "patient": patient,
            "ranked": ranked,
            "booking": booking,
            "tool_calls": sum(1 for s in steps if s["kind"] == "tool"),
            "elapsed_ms": elapsed,
            "provider": PROVIDER.__class__.__name__,
            "model": getattr(PROVIDER, "model_name", "n/a"),
        })


def _summarize(tool_name: str, obs: dict) -> str:
    """Rút gọn Observation thành một dòng cho giao diện hiển thị trong Tool Trace"""
    status = obs.get("status")

    if tool_name == "get_patient_history":
        if status == "SUCCESS":
            n = obs.get("total_visits", 0)
            return (f"Tìm thấy hồ sơ {obs.get('full_name')} — {n} lượt khám trước đây"
                    if n else f"{obs.get('full_name')} là bệnh nhân khám lần đầu")
        return obs.get("message", "Không tìm thấy hồ sơ bệnh nhân")

    if tool_name == "find_doctor_schedule":
        if status == "SUCCESS":
            return f"Tìm được {obs.get('total_doctors')} bác sĩ khoa {obs.get('specialty')} còn lịch trống"
        return obs.get("message", "Không có lịch phù hợp")

    if tool_name == "rank_doctors_for_patient":
        if status == "SUCCESS":
            docs = obs.get("ranked_doctors") or []
            top = docs[0] if docs else {}
            return (f"Đã xếp hạng {len(docs)} bác sĩ — dẫn đầu: "
                    f"{top.get('full_name')} ({top.get('match_score')}/100)")
        return obs.get("message", "Chưa xếp hạng được bác sĩ")

    if tool_name == "book_medical_appointment":
        if status == "SUCCESS":
            return f"Đặt lịch thành công — mã phiếu hẹn {obs.get('booking_id')}"
        return obs.get("message", "Không đặt được lịch")

    return obs.get("message", status or "")


def main():
    port = 8080
    if "--port" in sys.argv:
        try:
            port = int(sys.argv[sys.argv.index("--port") + 1])
        except (IndexError, ValueError):
            pass

    is_mock = PROVIDER.__class__.__name__ == "MockOfflineProvider"
    print("=" * 60)
    print("🌐 VINMEC HEALTHCARE AGENT — HTTP API SERVER")
    print("=" * 60)
    print(f"🔌 LLM Provider : {PROVIDER.__class__.__name__} "
          f"({getattr(PROVIDER, 'model_name', 'n/a')})")
    if is_mock:
        print("   ⚠️  Đang chạy Mock offline — điền GEMINI_API_KEY vào .env để dùng LLM thật.")
    print(f"🌐 MCP Server   : {MCP.server_name} v{MCP.version}")
    print(f"🛠️  Tools        : {[t['name'] for t in MCP.list_tools()]}")
    print(f"\n🚀 API sẵn sàng tại http://localhost:{port}")
    print(f"   • GET  /api/health")
    print(f"   • GET  /api/doctors  |  /api/patients  |  /api/trace")
    print(f"   • POST /api/chat     {{\"message\": \"...\"}}")
    print("\n(Ctrl+C để dừng)\n")

    server = ThreadingHTTPServer(("0.0.0.0", port), AgentAPIHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Đã dừng API server.")
        server.shutdown()


if __name__ == "__main__":
    main()
