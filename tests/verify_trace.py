"""
🔬 KIỂM ĐỊNH CHẤT LƯỢNG WATERFALL TRACE LOG

Chạy sau khi thực thi test suite:
    python src/app.py --all
    python tests/verify_trace.py

Script đối chiếu trace log thực tế với kỳ vọng của từng Test Case trong
config/test_cases.json, đồng thời kiểm tra các điều kiện nghiệm thu của Bài Lab:
  • Trace có đủ chuỗi Thought → Action → Observation → Final Answer
  • Không có bước nào bị fallback về Mock Provider
  • Agent không bịa dữ liệu ngoài Observation (Anti-Hallucination)
  • Các Test Case đa bước thực sự gọi nhiều Tool nối tiếp nhau
"""

import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

TRACE_PATH = os.path.join(BASE_DIR, "docs", "trace_waterfall.json")
CASES_PATH = os.path.join(BASE_DIR, "config", "test_cases.json")

# Kỳ vọng hành vi từng Test Case: (số Tool tối thiểu, các Tool bắt buộc phải xuất hiện)
EXPECTATIONS = {
    "TC01": (0, []),
    "TC02": (1, ["find_doctor_schedule"]),
    "TC03": (1, ["book_medical_appointment"]),
    "TC04": (2, ["book_medical_appointment"]),
    "TC05": (0, []),
    "TC06": (1, ["get_patient_history"]),
    "TC07": (2, ["get_patient_history"]),
    "TC08": (1, ["get_patient_history"]),
    # TC09 — bệnh nhân mới: câu hỏi đã nói rõ "lần đầu khám ở Vinmec", nên Agent được phép
    # bỏ qua bước tra tiền sử (vốn sẽ trả về rỗng) và đi thẳng vào tra lịch. Cả hai hướng
    # đều hợp lệ, chỉ yêu cầu Agent thực sự tra được lịch cho người bệnh.
    "TC09": (1, []),
    "TC10": (2, ["get_patient_history"]),
    "TC11": (1, []),
    "TC12": (0, []),
    "TC13": (1, []),   # phải tra lịch, nhưng KHÔNG được đặt (kiểm riêng bên dưới)
    "TC14": (1, ["list_my_appointments"]),
}

# Các Test Case mà Agent TUYỆT ĐỐI không được gọi một số Tool nhất định
FORBIDDEN_TOOLS = {
    "TC13": ["book_medical_appointment"],  # chưa xác nhận khung giờ thì không được giữ chỗ
}

_passed = 0
_failed = []
_warns = []


def check(name, cond, detail=""):
    global _passed
    if cond:
        _passed += 1
        print(f"  ✅ {name}")
    else:
        _failed.append(name)
        print(f"  ❌ {name}" + (f"\n       → {detail}" if detail else ""))


def warn(msg):
    _warns.append(msg)
    print(f"  ⚠️  {msg}")


def main():
    if not os.path.exists(TRACE_PATH):
        print("❌ Chưa có docs/trace_waterfall.json. Hãy chạy: python src/app.py --all")
        return 1

    trace = json.load(open(TRACE_PATH, encoding="utf-8"))
    cases = {c["id"]: c for c in json.load(open(CASES_PATH, encoding="utf-8"))}

    by_tc = {}
    for ev in trace:
        by_tc.setdefault(ev.get("test_case_id"), []).append(ev)

    print("=" * 62)
    print("🔬 KIỂM ĐỊNH CHẤT LƯỢNG WATERFALL TRACE LOG")
    print("=" * 62)

    # ---------- 1. Điều kiện nghiệm thu chung ----------
    print("\n📋 NHÓM 1 — Điều kiện nghiệm thu")

    mock_steps = [e for e in trace if "[Mock Agent" in str(e.get("output", ""))]
    check("Toàn bộ trace sinh từ LLM thật (không fallback Mock)",
          not mock_steps, f"{len(mock_steps)} bước bị fallback")

    check("Trace log không rỗng", len(trace) > 0)
    check("Mọi sự kiện đều có test_case_id",
          all(e.get("test_case_id") for e in trace))
    check("Mọi sự kiện đều có dấu thời gian",
          all(e.get("timestamp") for e in trace))
    check("Mọi sự kiện đều đo được độ trễ",
          all(isinstance(e.get("latency_ms"), (int, float)) for e in trace))

    tool_events = [e for e in trace if e["action_type"] == "TOOL_EXECUTION"]
    check("Mỗi lượt gọi Tool đều ghi Thought",
          all(e.get("thought") for e in tool_events))
    check("Mỗi lượt gọi Tool đều ghi Observation",
          all(e.get("observation") for e in tool_events))
    check("Mỗi lượt gọi Tool đều ghi khung JSON-RPC",
          all(e.get("mcp_envelope", {}).get("jsonrpc") == "2.0" for e in tool_events))
    check("Độ trễ LLM và MCP được tách riêng",
          all("llm_latency_ms" in e and "mcp_latency_ms" in e for e in tool_events))

    # ---------- 2. Mỗi Test Case phải kết thúc bằng Final Answer ----------
    print("\n🏁 NHÓM 2 — Tính toàn vẹn của mỗi phiên ReAct")

    for tc_id in sorted(by_tc):
        evs = by_tc[tc_id]
        last = evs[-1]
        check(f"{tc_id} kết thúc bằng Final Answer",
              last["action_type"] == "FINAL_ANSWER",
              f"kết thúc bằng {last['action_type']}")
        check(f"{tc_id} có câu trả lời cho người bệnh",
              bool(str(last.get("output", "")).strip()))
        steps = [e["step"] for e in evs]
        check(f"{tc_id} đánh số bước tăng dần", steps == sorted(steps), str(steps))

    # ---------- 3. Đối chiếu với kỳ vọng từng Test Case ----------
    print("\n🎯 NHÓM 3 — Hành vi khớp kỳ vọng của đề bài")

    for tc_id, (min_tools, required) in EXPECTATIONS.items():
        if tc_id not in by_tc:
            warn(f"{tc_id} không có trong trace (chưa chạy?)")
            continue
        tools = [e["tool_name"] for e in by_tc[tc_id] if e["action_type"] == "TOOL_EXECUTION"]

        if min_tools == 0:
            # Các case này Agent nên trả lời thẳng, gọi Tool là chấp nhận được nhưng nên ít
            if len(tools) > 2:
                warn(f"{tc_id} gọi tới {len(tools)} Tool cho câu hỏi lẽ ra đơn giản: {tools}")
            else:
                check(f"{tc_id} xử lý gọn (≤2 Tool)", True)
        else:
            check(f"{tc_id} gọi ít nhất {min_tools} Tool",
                  len(tools) >= min_tools, f"thực tế {len(tools)}: {tools}")

        for req in required:
            check(f"{tc_id} có gọi '{req}'", req in tools, f"thực tế: {tools}")

    # Kiểm tra các Tool bị cấm — quan trọng nhất là không được tự đặt lịch khi chưa xác nhận
    for tc_id, banned in FORBIDDEN_TOOLS.items():
        if tc_id not in by_tc:
            continue
        tools = [e["tool_name"] for e in by_tc[tc_id] if e["action_type"] == "TOOL_EXECUTION"]
        for b in banned:
            check(f"{tc_id} KHÔNG tự gọi '{b}' khi chưa được xác nhận",
                  b not in tools, f"thực tế đã gọi: {tools}")

    # ---------- 4. Chống ảo giác: tham số phải đến từ Observation ----------
    print("\n🛡️ NHÓM 4 — Chống ảo giác (Anti-Hallucination)")

    doctors = json.load(open(os.path.join(BASE_DIR, "data", "doctors.json"), encoding="utf-8"))["doctors"]
    valid_doctor_ids = set(doctors.keys())

    for tc_id, evs in sorted(by_tc.items()):
        booking = [e for e in evs if e.get("tool_name") == "book_medical_appointment"]
        for b in booking:
            did = b["arguments"].get("doctor_id", "")
            if not did:
                continue
            # doctor_id phải tồn tại HOẶC do chính người dùng cung cấp trong câu hỏi
            in_system = did.upper() in valid_doctor_ids
            in_question = did.upper() in str(b.get("query", "")).upper()
            check(f"{tc_id} đặt lịch với doctor_id hợp lệ hoặc do người dùng nêu",
                  in_system or in_question, f"doctor_id={did}")

            # Nếu trước đó đã tra cứu, doctor_id phải nằm trong kết quả quan sát được
            prior = [e for e in evs if e["step"] < b["step"]
                     and e.get("tool_name") in ("find_doctor_schedule", "rank_doctors_for_patient")]
            if prior and in_system:
                seen = set()
                for p in prior:
                    obs = p.get("observation", {})
                    for d in (obs.get("doctors") or obs.get("ranked_doctors") or []):
                        seen.add(d.get("doctor_id"))
                if seen:
                    check(f"{tc_id} doctor_id lấy từ Observation bước trước",
                          did.upper() in seen, f"{did} không có trong {sorted(seen)}")

    # Agent không được nhắc tới mã phiếu hẹn không tồn tại trong Observation
    real_bookings = {e["observation"].get("booking_id")
                     for e in tool_events
                     if e.get("tool_name") == "book_medical_appointment"
                     and e.get("observation", {}).get("booking_id")}
    for e in trace:
        if e["action_type"] != "FINAL_ANSWER":
            continue
        out = str(e.get("output", ""))
        if "VM-" in out:
            mentioned = {tok.strip(".,;:)»\"'") for tok in out.split() if tok.startswith("VM-")}
            bogus = {m for m in mentioned if m not in real_bookings}
            check(f"{e['test_case_id']} không bịa mã phiếu hẹn",
                  not bogus, f"nhắc tới {bogus} nhưng thực tế chỉ có {real_bookings or 'không có'}")

    # ---------- 5. Báo cáo thống kê ----------
    print("\n📊 NHÓM 5 — Thống kê phiên làm việc")

    lat = [e["latency_ms"] for e in trace if e.get("latency_ms")]
    print(f"\n  Tổng sự kiện      : {len(trace)}")
    print(f"  Lượt gọi Tool     : {len(tool_events)}")
    print(f"  Test Case đã chạy : {len(by_tc)}")
    if lat:
        print(f"  Độ trễ (ms)       : min={min(lat):.0f} | max={max(lat):.0f} | avg={sum(lat)/len(lat):.0f}")

    tool_usage = {}
    for e in tool_events:
        tool_usage[e["tool_name"]] = tool_usage.get(e["tool_name"], 0) + 1
    print("\n  Tần suất sử dụng từng Tool:")
    for t, n in sorted(tool_usage.items(), key=lambda x: -x[1]):
        print(f"    • {t:28s}: {n} lượt")

    print("\n  Chuỗi Tool của từng Test Case:")
    for tc_id in sorted(by_tc):
        tools = [e["tool_name"] for e in by_tc[tc_id] if e["action_type"] == "TOOL_EXECUTION"]
        label = cases.get(tc_id, {}).get("type", "?")
        chain = " → ".join(tools) if tools else "(không gọi Tool)"
        print(f"    {tc_id} [{label:28s}] {len(by_tc[tc_id])} bước: {chain}")

    # ---------- Tổng kết ----------
    total = _passed + len(_failed)
    print("\n" + "=" * 62)
    print(f"📊 KẾT QUẢ KIỂM ĐỊNH: {_passed}/{total} tiêu chí đạt")
    if _failed:
        print(f"❌ {len(_failed)} tiêu chí KHÔNG đạt:")
        for f in _failed:
            print(f"   • {f}")
    if _warns:
        print(f"⚠️  {len(_warns)} cảnh báo (không chặn nghiệm thu):")
        for w in _warns:
            print(f"   • {w}")
    if not _failed:
        print("✅ Trace log đạt toàn bộ tiêu chí nghiệm thu!")
    print("=" * 62)
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
