"""
🚀 CORE AGENT APPLICATION (DAY 03: CHATBOT VS REACT AGENT)
Thực thi so sánh giữa Chatbot Baseline (Cấp 2) và ReAct Agent kết nối MCP Server (Cấp 3).

ĐỀ TÀI: Trợ lý Tư vấn Sức khỏe Vinmec (Healthcare Assistant)

KIẾN TRÚC:
    app.py (MCP Client + Agent Core)
        │  messages history
        ├──> providers.py  ──> Gemini / OpenAI API  (Native Tool Calling)
        │  tool_call
        └──> mcp_server.py ──> tools.py ──> data/*.json  (Execution Layer)

VÒNG LẶP REACT THẬT SỰ:
    Khác bản starter (chỉ gọi Tool đúng một lần rồi tự ghép câu trả lời bằng f-string),
    bản này duy trì lịch sử hội thoại và nạp Observation ngược lại cho LLM sau mỗi lần
    gọi Tool. Nhờ đó LLM tự quyết định gọi tiếp Tool nào, và tự viết Final Answer:
        Thought -> Action -> Observation -> Thought -> Action -> Observation -> Final Answer
"""

import json
import os
import sys
import time
from datetime import datetime
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from mcp_server import MCPAcademicServer
from prompts import (
    CHATBOT_BASELINE_PROMPT,
    REACT_AGENT_SYSTEM_PROMPT,
    MAX_ITERATIONS
)
from providers import get_llm_provider

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ==============================================================================
# TIỆN ÍCH: NẠP CẤU HÌNH & GHI VẾT TRACE LOG
# ==============================================================================

def load_test_cases():
    """Tải danh sách 5 test cases từ config/test_cases.json hoặc config/test_cases.example.json"""
    config_path = os.path.join(BASE_DIR, "config", "test_cases.json")
    if not os.path.exists(config_path):
        example_path = os.path.join(BASE_DIR, "config", "test_cases.example.json")
        if os.path.exists(example_path):
            print("⚠️ [CONFIG NOTICE]: Chưa thấy file 'config/test_cases.json'. Đang dùng mẫu 'config/test_cases.example.json'.")
            print("👉 Hãy chạy: copy config\\test_cases.example.json config\\test_cases.json\n")
            config_path = example_path
        else:
            config_path = "test_cases.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_waterfall_trace(trace_data: list):
    """Ghi vết log Waterfall Trace Log ra file docs/trace_waterfall.json"""
    docs_dir = os.path.join(BASE_DIR, "docs")
    os.makedirs(docs_dir, exist_ok=True)
    trace_path = os.path.join(docs_dir, "trace_waterfall.json")
    with open(trace_path, "w", encoding="utf-8") as f:
        json.dump(trace_data, f, ensure_ascii=False, indent=2)
    print(f"📊 [OBSERVABILITY]: Đã lưu {len(trace_data)} sự kiện Waterfall Trace tại '{trace_path}'!")


def _truncate(text: str, limit: int = 400) -> str:
    """Rút gọn chuỗi dài khi in ra console cho dễ đọc (trace log vẫn giữ nguyên bản đầy đủ)"""
    text = str(text)
    return text if len(text) <= limit else text[:limit] + " ...[rút gọn]"


# ==============================================================================
# CẤP 2 — CHATBOT BASELINE (KHÔNG CÓ TOOL)
# ==============================================================================

def run_baseline_chatbot(user_query: str, provider):
    """Chạy Chatbot gốc (Cấp 2) không có công cụ gọi Tool"""
    print(f"\n💬 [CHATBOT BASELINE] Câu hỏi: {user_query}")
    response = provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)
    print(f"🤖 Chatbot phản hồi:\n{response}")
    return response


# ==============================================================================
# CẤP 3 — REACT AGENT LOOP (MULTI-TURN, MCP-ENHANCED)
# ==============================================================================

def run_react_agent(user_query: str, provider, mcp_server: MCPAcademicServer,
                    test_case_id: str = "ADHOC", history: list = None) -> list:
    """
    [REACT AGENT LOOP] Thực thi vòng lặp Thought -> Action -> Observation với MCP Server.

    Duy trì `messages` làm bộ nhớ hội thoại: mỗi Observation nhận được từ MCP Server
    đều được nạp ngược lại cho LLM, nên LLM có thể suy luận nhiều bước liên tiếp
    và tự viết câu trả lời cuối cùng.

    Tham số:
        history — bộ nhớ NGẮN HẠN của phiên chat: các lượt hỏi/đáp trước đó.
                  Nhờ đó Agent nhớ được ngữ cảnh khi người bệnh trả lời tiếp
                  ("tôi mới khám lần đầu"), thay vì hỏi đi hỏi lại cùng một câu.
                  Danh sách này được BỔ SUNG tại chỗ để phía gọi giữ lại cho lượt sau.

    Trả về danh sách trace log của phiên thực thi.
    """
    print(f"\n🤖 [REACT AGENT] Câu hỏi: {user_query}")

    trace_logs = []
    tools_list = mcp_server.list_tools()
    tool_call_count = 0

    # Bộ nhớ hội thoại = lịch sử các lượt trước (nếu có) + câu hỏi hiện tại
    if history is None:
        history = []
    history.append({"role": "user", "content": user_query})
    messages = history

    session_start = time.time()
    step = 0

    while step < MAX_ITERATIONS:
        step += 1
        step_start = time.time()
        print(f"\n--- 🔄 Vòng lặp ReAct Loop (Step {step}/{MAX_ITERATIONS}) ---")

        # === THOUGHT: LLM suy luận dựa trên toàn bộ lịch sử hội thoại ===
        llm_response = provider.generate_with_tools(
            messages, tools_list, system_prompt=REACT_AGENT_SYSTEM_PROMPT
        )
        llm_latency = round((time.time() - step_start) * 1000, 2)

        thought = llm_response.get("thought", "Đang suy luận...")
        print(f"🧠 [Thought]: {_truncate(thought)}")

        # ------------------------------------------------------------------
        # TRƯỜNG HỢP 1: LLM đã đủ dữ liệu -> tự viết Final Answer
        # ------------------------------------------------------------------
        if llm_response.get("type") == "text":
            final_content = llm_response.get("content", "")
            print(f"🏁 [Final Answer]: {final_content}")

            # Ghi câu trả lời vào bộ nhớ hội thoại để lượt chat sau còn nhớ ngữ cảnh
            messages.append({"role": "assistant", "content": final_content})

            trace_logs.append({
                "test_case_id": test_case_id,
                "step": step,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "query": user_query,
                "action_type": "FINAL_ANSWER",
                "thought": thought,
                "output": final_content,
                "latency_ms": llm_latency
            })
            break

        # ------------------------------------------------------------------
        # TRƯỜNG HỢP 2: LLM đề xuất gọi Tool (Action) -> thực thi qua MCP Server
        # ------------------------------------------------------------------
        if llm_response.get("type") == "tool_call":
            tool_name = llm_response.get("tool_name")
            arguments = llm_response.get("arguments", {}) or {}
            tool_call_count += 1

            print(f"🛠️ [Action Proposed]: {tool_name}({json.dumps(arguments, ensure_ascii=False)})")

            # --- ACTION: gửi yêu cầu JSON-RPC 2.0 tới MCP Server ---
            mcp_start = time.time()
            mcp_result = mcp_server.call_tool(tool_name, arguments)
            mcp_latency = round((time.time() - mcp_start) * 1000, 2)

            # --- OBSERVATION: bóc kết quả từ khung phản hồi JSON-RPC ---
            if "error" in mcp_result:
                obs_data = {"status": "MCP_ERROR", "message": mcp_result["error"]["message"]}
            else:
                obs_data = mcp_result.get("result", {})

            if not obs_data:
                obs_data = {
                    "status": "EMPTY_RESPONSE",
                    "message": "MCP Server trả về kết quả rỗng."
                }
                print("⚠️ [CHÚ Ý]: MCP Server trả về rỗng — kiểm tra lại hàm call_tool() trong 'src/mcp_server.py'.")

            print(f"👁️ [Observation từ MCP Server]: {_truncate(json.dumps(obs_data, ensure_ascii=False))}")
            print(f"   ⏱️ MCP latency: {mcp_latency} ms | Trạng thái: {obs_data.get('status')}")

            trace_logs.append({
                "test_case_id": test_case_id,
                "step": step,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "query": user_query,
                "action_type": "TOOL_EXECUTION",
                "thought": thought,
                "tool_name": tool_name,
                "arguments": arguments,
                "mcp_envelope": {
                    "jsonrpc": mcp_result.get("jsonrpc"),
                    "id": mcp_result.get("id"),
                    "server": mcp_result.get("server")
                },
                "observation": obs_data,
                "llm_latency_ms": llm_latency,
                "mcp_latency_ms": mcp_latency,
                "latency_ms": round(llm_latency + mcp_latency, 2)
            })

            # --- NẠP OBSERVATION NGƯỢC LẠI CHO LLM (điểm mấu chốt của ReAct thật) ---
            messages.append({
                "role": "tool_call",
                "tool_name": tool_name,
                "arguments": arguments,
                "call_id": llm_response.get("call_id")
            })
            messages.append({
                "role": "tool_result",
                "tool_name": tool_name,
                "content": obs_data,
                "call_id": llm_response.get("call_id")
            })

            # Quay lại đầu vòng lặp: LLM sẽ đọc Observation và quyết định bước tiếp theo
            continue

        # ------------------------------------------------------------------
        # TRƯỜNG HỢP 3: phản hồi không nhận dạng được -> dừng an toàn
        # ------------------------------------------------------------------
        print(f"⚠️ [Cảnh báo]: Phản hồi LLM không hợp lệ: {llm_response}")
        break

    else:
        # Vòng lặp chạy hết MAX_ITERATIONS mà LLM vẫn chưa chốt câu trả lời
        print(f"⏹️ [Dừng an toàn]: Đã đạt giới hạn {MAX_ITERATIONS} vòng lặp ReAct.")
        trace_logs.append({
            "test_case_id": test_case_id,
            "step": step,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "query": user_query,
            "action_type": "MAX_ITERATION_STOP",
            "thought": "Đạt giới hạn số vòng lặp, dừng để tránh lặp vô hạn.",
            "output": "Agent chưa hoàn tất trong giới hạn vòng lặp cho phép.",
            "latency_ms": 0.0
        })

    total_ms = round((time.time() - session_start) * 1000, 2)
    print(f"\n📈 [Tổng kết phiên]: {step} vòng lặp | {tool_call_count} lượt gọi Tool | Tổng thời gian: {total_ms} ms")

    return trace_logs


# ==============================================================================
# CHƯƠNG TRÌNH CHÍNH
# ==============================================================================

def _print_header(provider, mcp_server):
    print("==========================================================")
    print("🏥 VINMEC HEALTHCARE AGENT - DAY 03 LAB: CHATBOT VS REACT AGENT")
    print("==========================================================")
    print(f"🔌 LLM Provider: {provider.__class__.__name__} (model: {getattr(provider, 'model_name', 'n/a')})")
    print(f"🌐 MCP Server: {mcp_server.server_name} v{mcp_server.version}")
    print(f"🛠️ Tools công bố: {[t['name'] for t in mcp_server.list_tools()]}\n")


if __name__ == "__main__":
    provider = get_llm_provider()
    mcp_server = MCPAcademicServer()

    _print_header(provider, mcp_server)

    tests = load_test_cases()
    print(f"✅ Đã tải thành công {len(tests)} Test Cases thử nghiệm.\n")

    # ----------------------------------------------------------------------
    # CHẾ ĐỘ 1: ĐÀM THOẠI TRỰC TIẾP
    # ----------------------------------------------------------------------
    if "--interactive" in sys.argv:
        print("🎮 [INTERACTIVE MODE] Trò chuyện trực tiếp với ReAct Agent Vinmec:")
        print("💡 Gợi ý câu hỏi thử nghiệm:")
        print("   - Kiến thức chung:  'Quy trình khám bệnh tại Vinmec gồm những bước nào?'")
        print("   - Tra cứu bác sĩ:   'Tôi bị đau dạ dày, nên khám khoa nào và bác sĩ nào còn trống lịch?'")
        print("   - Đặt lịch đa bước: 'Tôi bị đau dạ dày, đặt giúp tôi lịch khám sớm nhất, tên tôi là Nguyễn Sơn Giang'")
        print("   - Gõ 'exit' hoặc 'quit' để kết thúc phiên trò chuyện.\n")

        session_traces = []
        turn = 0
        while True:
            try:
                user_input = input("👤 Người bệnh hỏi: ").strip()
                if not user_input or user_input.lower() in ["exit", "quit"]:
                    print("👋 Tạm biệt! Chúc bạn nhiều sức khỏe.")
                    break
                turn += 1
                logs = run_react_agent(user_input, provider, mcp_server, test_case_id=f"CHAT-{turn:02d}")
                session_traces.extend(logs)
                save_waterfall_trace(session_traces)
            except (KeyboardInterrupt, EOFError):
                print("\n👋 Đã thoát phiên tương tác.")
                break

    # ----------------------------------------------------------------------
    # CHẾ ĐỘ 2: CHẠY TOÀN BỘ TEST SUITE
    # ----------------------------------------------------------------------
    elif "--all" in sys.argv:
        print(f"🚀 [TEST SUITE MODE] Kiểm tra {len(tests)} Test Cases:")
        completed_count = 0
        todo_count = 0
        total_tool_calls = 0
        all_traces = []

        # Giãn cách giữa các Test Case để không vượt hạn mức request/phút của free tier.
        # Chỉnh qua biến môi trường TESTCASE_DELAY (giây); đặt 0 khi chạy Mock offline.
        is_mock = provider.__class__.__name__ == "MockOfflineProvider"
        tc_delay = float(os.getenv("TESTCASE_DELAY", "0" if is_mock else "20"))
        if tc_delay > 0:
            print(f"⏱️ Giãn cách giữa các Test Case: {tc_delay:.0f}s (tránh lỗi 429 rate limit)\n")

        for idx, tc in enumerate(tests):
            if idx > 0 and tc_delay > 0:
                print(f"\n⏳ Nghỉ {tc_delay:.0f}s trước Test Case kế tiếp để giữ hạn mức API...")
                time.sleep(tc_delay)

            print(f"\n==================================================")
            print(f"🧪 [{tc['id']}] Loại test: {tc['type']} (Độ phức tạp: {tc['complexity']})")
            print(f"📌 Kỳ vọng: {tc['expected_behavior']}")

            if tc["question"].strip().startswith("TODO"):
                print(f"⏸️ [CHƯA KÍCH HOẠT - ĐANG LÀ TODO]:")
                print(f"   {tc['question']}")
                print(f"   👉 Hãy mở file 'config/test_cases.json' để viết câu hỏi thực tế cho Test Case này!")
                todo_count += 1
            else:
                logs = run_react_agent(tc["question"], provider, mcp_server, test_case_id=tc["id"])
                all_traces.extend(logs)
                total_tool_calls += sum(1 for l in logs if l["action_type"] == "TOOL_EXECUTION")
                completed_count += 1

        print(f"\n==================================================")
        print(f"📊 [KẾT QUẢ TEST SUITE]: Đã thực thi {completed_count}/{len(tests)} Test Cases | "
              f"{todo_count} Test Cases đang chờ điền câu hỏi (TODO)")
        print(f"🛠️ Tổng số lượt gọi Tool qua MCP Server: {total_tool_calls} lượt")

        # Kiểm chứng điều kiện nghiệm thu: toàn bộ trace phải sinh từ LLM API thật
        mock_steps = [t for t in all_traces if "[Mock Agent" in str(t.get("output", ""))]
        if not is_mock:
            if mock_steps:
                print(f"⚠️ [CẢNH BÁO NGHIỆM THU]: {len(mock_steps)} bước bị fallback về Mock do lỗi API "
                      f"(thường là 429 rate limit). Trace log chưa thuần LLM thật.")
                print(f"   👉 Hãy tăng giãn cách rồi chạy lại: "
                      f"$env:TESTCASE_DELAY='30'; python src/app.py --all")
            else:
                print(f"✅ [NGHIỆM THU]: Toàn bộ {len(all_traces)} bước đều sinh từ LLM API thật "
                      f"({provider.model_name}) — đủ điều kiện nộp bài.")

        if all_traces:
            save_waterfall_trace(all_traces)
        print(f"💡 Để trò chuyện trực tiếp từng câu: Chạy 'python src/app.py --interactive'")

    # ----------------------------------------------------------------------
    # CHẾ ĐỘ 3: SO SÁNH TRỰC TIẾP CHATBOT (CẤP 2) VS REACT AGENT (CẤP 3)
    # ----------------------------------------------------------------------
    elif "--compare" in sys.argv:
        demo_query = ("Tôi bị đau dạ dày mấy hôm nay, cho tôi hỏi nên khám chuyên khoa nào "
                      "và bác sĩ nào còn trống lịch khám?")
        print("⚖️ [COMPARE MODE] So sánh Chatbot Baseline (Cấp 2) vs ReAct Agent (Cấp 3)")
        print(f"❓ Cùng một câu hỏi: {demo_query}")

        print("\n------------- CẤP 2: LLM CHATBOT (KHÔNG CÓ TOOL) -------------")
        run_baseline_chatbot(demo_query, provider)

        print("\n------------- CẤP 3: REACT AGENT (MCP + TOOL) -------------")
        logs = run_react_agent(demo_query, provider, mcp_server, test_case_id="COMPARE")
        save_waterfall_trace(logs)

        print("\n💡 Nhận xét: Chatbot chỉ nói chung chung vì không truy cập được dữ liệu thời gian thực,")
        print("   còn ReAct Agent gọi Tool qua MCP Server nên trả về đúng tên bác sĩ và khung giờ có thật.")

    # ----------------------------------------------------------------------
    # CHẾ ĐỘ MẶC ĐỊNH
    # ----------------------------------------------------------------------
    else:
        print("ℹ️ HƯỚNG DẪN SỬ DỤNG CHƯƠNG TRÌNH:")
        print("  1. Chat trực tiếp liên tục:      python src/app.py --interactive")
        print("  2. Chạy toàn bộ Test Cases:      python src/app.py --all")
        print("  3. So sánh Chatbot vs Agent:     python src/app.py --compare\n")

        sample = next((t for t in tests if t["id"] == "TC04"), tests[1])
        print(f"--- 🏁 DEMO CHẠY THỬ 1 TEST CASE MẪU ({sample['id']}: {sample['type']}) ---")
        logs = run_react_agent(sample["question"], provider, mcp_server, test_case_id=sample["id"])
        save_waterfall_trace(logs)
        print("\n💡 Hãy thử ngay lệnh: python src/app.py --interactive để chat trực tiếp!")
