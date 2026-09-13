"""
🧪 BỘ KIỂM THỬ TẦNG CÔNG CỤ & MCP SERVER (Offline — không tốn API Key)

Chạy:  python tests/test_tools.py

Bộ test này kiểm chứng toàn bộ hành vi của Execution Layer và MCP Server mà không cần
gọi LLM, nhờ đó có thể chạy lại nhiều lần miễn phí trước khi nghiệm thu trên API thật.
Dữ liệu trong data/ được sao lưu trước và khôi phục sau khi chạy, nên test không
làm bẩn trạng thái của repo.
"""

import json
import os
import shutil
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "src"))

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import tools
from mcp_server import MCPAcademicServer

DATA_FILES = ["doctors.json", "appointments.json", "medical_history.json"]

_passed = 0
_failed = []


def check(name: str, condition: bool, detail: str = ""):
    """Ghi nhận kết quả một phép kiểm tra"""
    global _passed
    if condition:
        _passed += 1
        print(f"  ✅ {name}")
    else:
        _failed.append(name)
        print(f"  ❌ {name}" + (f"\n       → {detail}" if detail else ""))


def call(tool_name: str, **kwargs) -> dict:
    """Gọi tool qua MCP Server và bóc phần result (giống hệt cách Agent làm)"""
    envelope = SERVER.call_tool(tool_name, kwargs)
    return envelope.get("result", envelope)


def snapshot_data() -> str:
    """Sao lưu thư mục data/ ra nơi tạm để khôi phục sau khi test"""
    tmp = tempfile.mkdtemp(prefix="vinmec_test_")
    for f in DATA_FILES:
        shutil.copy2(os.path.join(BASE_DIR, "data", f), os.path.join(tmp, f))
    return tmp


def restore_data(tmp: str):
    """Khôi phục data/ về đúng trạng thái trước khi chạy test"""
    for f in DATA_FILES:
        shutil.copy2(os.path.join(tmp, f), os.path.join(BASE_DIR, "data", f))
    shutil.rmtree(tmp, ignore_errors=True)


SERVER = MCPAcademicServer()


# ==============================================================================
# NHÓM 1 — MCP SERVER & TOOL REGISTRY
# ==============================================================================

def test_mcp_protocol():
    print("\n📡 NHÓM 1 — MCP Server & Tool Registry")

    schemas = SERVER.list_tools()
    names = [t["name"] for t in schemas]
    check("MCP Server công bố đủ 6 tools", len(schemas) == 6, f"thấy {names}")
    check("Có tool tra cứu lịch bác sĩ", "find_doctor_schedule" in names)
    check("Có tool đặt lịch khám", "book_medical_appointment" in names)
    check("Có tool bộ nhớ dài hạn", "get_patient_history" in names)
    check("Có tool xếp hạng bác sĩ", "rank_doctors_for_patient" in names)
    check("Có tool tra lịch hẹn", "list_my_appointments" in names)
    check("Có tool hủy lịch hẹn", "cancel_appointment" in names)

    # Mọi schema phải đúng chuẩn JSON Schema mà Native Tool Calling yêu cầu
    for t in schemas:
        p = t.get("parameters", {})
        check(f"Schema '{t['name']}' đúng chuẩn JSON Schema",
              p.get("type") == "object" and isinstance(p.get("properties"), dict)
              and isinstance(p.get("required"), list) and bool(t.get("description")),
              f"parameters={p}")
        # Mọi trường required phải được khai báo trong properties
        missing = [r for r in p.get("required", []) if r not in p.get("properties", {})]
        check(f"Schema '{t['name']}' không có required lạc",
              not missing, f"thiếu khai báo: {missing}")

    env = SERVER.call_tool("find_doctor_schedule", {"specialty": "Tiêu hóa"})
    check("Phản hồi đúng khung JSON-RPC 2.0",
          env.get("jsonrpc") == "2.0" and "id" in env and "result" in env
          and env.get("server") == "vinmec-healthcare-mcp-server",
          f"envelope keys={list(env.keys())}")
    check("Phản hồi có đo độ trễ (observability)", isinstance(env.get("latency_ms"), float))

    unknown = call("cong_cu_khong_ton_tai")
    check("Tool không tồn tại trả lỗi rõ ràng", unknown.get("status") == "UNKNOWN_TOOL")


# ==============================================================================
# NHÓM 2 — TRA CỨU LỊCH BÁC SĨ
# ==============================================================================

def test_find_schedule():
    print("\n🔍 NHÓM 2 — Tra cứu lịch bác sĩ")

    r = call("find_doctor_schedule", specialty="Tiêu hóa")
    check("Tra theo chuyên khoa có dấu", r.get("status") == "SUCCESS" and r.get("total_doctors", 0) >= 2)

    r2 = call("find_doctor_schedule", specialty="tieu hoa")
    check("Tra theo chuyên khoa KHÔNG dấu cho cùng kết quả",
          r2.get("status") == "SUCCESS" and r2.get("total_doctors") == r.get("total_doctors"))

    r3 = call("find_doctor_schedule", specialty="TIÊU HÓA")
    check("Không phân biệt hoa/thường", r3.get("status") == "SUCCESS")

    r4 = call("find_doctor_schedule", symptom="đau dạ dày")
    check("Suy chuyên khoa từ triệu chứng", r4.get("matched_by") == "symptom" and r4.get("specialty") == "Tieu hoa")

    r5 = call("find_doctor_schedule", symptom="nổi mẩn ngứa")
    check("Triệu chứng da liễu → khoa Da liễu", r5.get("specialty") == "Da lieu")

    r6 = call("find_doctor_schedule", symptom="đau đầu")
    check("Triệu chứng thần kinh → khoa Thần kinh", r6.get("specialty") == "Than kinh")

    r7 = call("find_doctor_schedule", specialty="Ung bướu")
    check("Chuyên khoa không tồn tại trả NOT_FOUND",
          r7.get("status") == "NOT_FOUND" and r7.get("available_specialties"))

    r8 = call("find_doctor_schedule", symptom="đau răng sâu")
    check("Triệu chứng lạ không suy được chuyên khoa", r8.get("status") == "NOT_FOUND")

    r9 = call("find_doctor_schedule", specialty="Da liễu", date="2026-09-14")
    check("Ngày bác sĩ kín lịch trả NO_SLOT", r9.get("status") == "NO_SLOT")

    r10 = call("find_doctor_schedule")
    check("Không truyền tham số → liệt kê toàn bệnh viện",
          r10.get("status") == "SUCCESS" and r10.get("matched_by") == "all")

    # Bác sĩ kín lịch hoàn toàn trong phạm vi tra cứu phải bị loại khỏi kết quả
    r11 = call("find_doctor_schedule", specialty="Tiêu hóa", date="2026-09-14")
    ids = [d["doctor_id"] for d in r11.get("doctors", [])]
    check("Bác sĩ kín lịch bị loại khỏi kết quả", "BS007" not in ids, f"thấy {ids}")

    # Mọi khung giờ trả về phải thực sự còn trống
    empty = [d["doctor_id"] for d in r.get("doctors", [])
             if not any(d["available_slots"].values())]
    check("Không trả về bác sĩ có lịch rỗng", not empty, f"bác sĩ rỗng: {empty}")


# ==============================================================================
# NHÓM 3 — BỘ NHỚ DÀI HẠN (TIỀN SỬ KHÁM BỆNH)
# ==============================================================================

def test_patient_history():
    print("\n🧠 NHÓM 3 — Bộ nhớ dài hạn (tiền sử khám bệnh)")

    r = call("get_patient_history", patient_id="BN2024001")
    check("Tra tiền sử theo mã bệnh nhân", r.get("status") == "SUCCESS" and r.get("total_visits") == 3)
    check("Trả về cảnh báo dị ứng thuốc", "Penicillin" in r.get("allergies", []))
    check("Trả về bệnh mạn tính", bool(r.get("chronic_conditions")))

    r2 = call("get_patient_history", patient_id="bn2024001")
    check("Mã bệnh nhân không phân biệt hoa/thường", r2.get("status") == "SUCCESS")

    r3 = call("get_patient_history", phone="0987654321")
    check("Tra tiền sử theo số điện thoại", r3.get("patient_id") == "BN2024002")

    r4 = call("get_patient_history", phone="098 765 4321")
    check("Số điện thoại có khoảng trắng vẫn khớp", r4.get("patient_id") == "BN2024002")

    # Lịch sử phải xếp mới nhất trước để Agent đọc được diễn tiến
    dates = [v["date"] for v in r.get("visit_history", [])]
    check("Lịch sử xếp theo thứ tự mới → cũ", dates == sorted(dates, reverse=True), str(dates))

    check("Mỗi lần khám có khoảng cách thời gian tương đối",
          all(v.get("time_gap") and v.get("months_ago", -1) >= 0 for v in r.get("visit_history", [])))

    qn = r.get("quick_note", {})
    check("Quick Note có headline", bool(qn.get("headline")))
    check("Quick Note có nội dung tóm tắt", len(qn.get("bullets", [])) >= 3)
    check("Quick Note cảnh báo dị ứng", any("DỊ ỨNG" in a for a in qn.get("alerts", [])))

    # Bệnh nhân chưa từng khám
    r5 = call("get_patient_history", patient_id="BN2024005")
    check("Bệnh nhân mới: trả SUCCESS với 0 lần khám",
          r5.get("status") == "SUCCESS" and r5.get("total_visits") == 0)
    check("Bệnh nhân mới: Quick Note vẫn có nội dung", bool(r5.get("quick_note", {}).get("bullets")))

    # Cảnh báo vấn đề còn đang theo dõi
    r6 = call("get_patient_history", patient_id="BN2024003")
    check("Cảnh báo vấn đề đang theo dõi",
          any("đang theo dõi" in a.lower() for a in r6.get("quick_note", {}).get("alerts", [])))

    # Tiền sử rất cũ vẫn quy đổi đúng sang đơn vị năm
    r7 = call("get_patient_history", patient_id="BN2024008")
    check("Tiền sử nhiều năm quy đổi ra 'năm'",
          "năm" in r7.get("visit_history", [{}])[0].get("time_gap", ""),
          r7.get("visit_history", [{}])[0].get("time_gap"))

    check("Không có định danh trả MISSING_IDENTIFIER",
          call("get_patient_history").get("status") == "MISSING_IDENTIFIER")
    check("Mã bệnh nhân không tồn tại trả NOT_FOUND",
          call("get_patient_history", patient_id="BN9999999").get("status") == "NOT_FOUND")
    check("Số điện thoại không tồn tại trả NOT_FOUND",
          call("get_patient_history", phone="0000000000").get("status") == "NOT_FOUND")


# ==============================================================================
# NHÓM 4 — XẾP HẠNG BÁC SĨ THEO TIỀN SỬ
# ==============================================================================

def test_ranking():
    print("\n🏆 NHÓM 4 — Xếp hạng bác sĩ theo tiền sử")

    r1 = call("rank_doctors_for_patient", patient_id="BN2024001", specialty="Tiêu hóa")
    check("Xếp hạng thành công", r1.get("status") == "SUCCESS")
    top1 = r1["ranked_doctors"][0]
    check("BN2024001 → ưu tiên BS001 (đã từng điều trị)",
          top1["doctor_id"] == "BS001" and top1["is_returning_doctor"],
          f"hạng 1 là {top1['doctor_id']}")

    r2 = call("rank_doctors_for_patient", patient_id="BN2024002", specialty="Tiêu hóa")
    top2 = r2["ranked_doctors"][0]
    check("BN2024002 → ưu tiên BS002 (bác sĩ riêng của họ)",
          top2["doctor_id"] == "BS002" and top2["is_returning_doctor"],
          f"hạng 1 là {top2['doctor_id']}")

    check("Cùng chuyên khoa nhưng hai bệnh nhân ra hai kết quả khác nhau",
          top1["doctor_id"] != top2["doctor_id"])

    # Điểm phải giảm dần và rank phải liên tục
    scores = [d["match_score"] for d in r1["ranked_doctors"]]
    check("Điểm xếp hạng giảm dần", scores == sorted(scores, reverse=True), str(scores))
    ranks = [d["rank"] for d in r1["ranked_doctors"]]
    check("Thứ hạng đánh số liên tục từ 1", ranks == list(range(1, len(ranks) + 1)), str(ranks))
    check("Điểm nằm trong thang 0-100", all(0 <= s <= 100 for s in scores), str(scores))

    check("Mỗi bác sĩ đều có lý do giải trình",
          all(len(d["ranking_reasons"]) >= 3 for d in r1["ranked_doctors"]))
    check("Có câu đề xuất tổng hợp cho người bệnh", bool(r1.get("recommendation")))
    check("Công bố công thức chấm điểm", bool(r1.get("scoring_criteria")))
    check("Mỗi bác sĩ có khung giờ trống sớm nhất",
          all(d["earliest_slot"].get("date") and d["earliest_slot"].get("time")
              for d in r1["ranked_doctors"]))

    # Bác sĩ quen phải hơn hẳn bác sĩ lạ
    returning = [d for d in r1["ranked_doctors"] if d["is_returning_doctor"]]
    stranger = [d for d in r1["ranked_doctors"] if not d["is_returning_doctor"]]
    if returning and stranger:
        check("Bác sĩ đã điều trị ăn điểm vượt trội",
              returning[0]["match_score"] - stranger[0]["match_score"] >= 40,
              f"{returning[0]['match_score']} vs {stranger[0]['match_score']}")

    # Bệnh nhân mới: không ai là bác sĩ quen, xếp hạng theo chuyên môn
    r3 = call("rank_doctors_for_patient", patient_id="BN2024005", specialty="Tiêu hóa")
    check("Bệnh nhân mới vẫn xếp hạng được", r3.get("status") == "SUCCESS")
    check("Bệnh nhân mới: không bác sĩ nào là 'bác sĩ quen'",
          not any(d["is_returning_doctor"] for d in r3["ranked_doctors"]))

    r4 = call("rank_doctors_for_patient", patient_id="BN2024001", symptom="đau dạ dày")
    check("Xếp hạng suy được chuyên khoa từ triệu chứng", r4.get("specialty") == "Tieu hoa")

    r5 = call("rank_doctors_for_patient", patient_id="BN2024006", specialty="Nội tiết")
    check("BN2024006 → ưu tiên BS012 khoa Nội tiết",
          r5["ranked_doctors"][0]["doctor_id"] == "BS012")

    check("Bệnh nhân không tồn tại trả NOT_FOUND",
          call("rank_doctors_for_patient", patient_id="BN9999999", specialty="Tiêu hóa").get("status") == "NOT_FOUND")
    check("Chuyên khoa lạ trả NOT_FOUND",
          call("rank_doctors_for_patient", patient_id="BN2024001", specialty="Ung bướu").get("status") == "NOT_FOUND")
    check("Ngày kín lịch trả NO_SLOT",
          call("rank_doctors_for_patient", patient_id="BN2024001",
               specialty="Da liễu", date="2026-09-14").get("status") == "NO_SLOT")


# ==============================================================================
# NHÓM 5 — ĐẶT LỊCH KHÁM & TRẠNG THÁI BỀN VỮNG
# ==============================================================================

def test_booking():
    print("\n📅 NHÓM 5 — Đặt lịch khám & trạng thái bền vững")

    before = call("find_doctor_schedule", specialty="Tiêu hóa", date="2026-09-15")
    slots_before = next(d["available_slots"]["2026-09-15"]
                        for d in before["doctors"] if d["doctor_id"] == "BS001")

    r = call("book_medical_appointment", patient_id="BN2024001", doctor_id="BS001",
             date="2026-09-15", time_slot="09:30", patient_name="Nguyen Son Giang",
             patient_phone="0912345678", symptom_note="đau thượng vị tái phát")
    check("Đặt lịch thành công", r.get("status") == "SUCCESS")
    check("Trả về mã phiếu hẹn đúng định dạng",
          str(r.get("booking_id", "")).startswith("VM-20260915-"), r.get("booking_id"))

    ap = r["appointment"]
    check("Phiếu hẹn gắn đúng mã bệnh nhân", ap.get("patient_id") == "BN2024001")
    check("Phiếu hẹn có Quick Note cho bác sĩ", bool(ap.get("doctor_quick_note", {}).get("bullets")))
    check("Quick Note cảnh báo dị ứng cho bác sĩ",
          any("DỊ ỨNG" in a for a in ap["doctor_quick_note"].get("alerts", [])))
    check("Quick Note nêu riêng diễn tiến cùng chuyên khoa",
          any("Tieu hoa" in b or "Tiêu hóa" in b for b in ap["doctor_quick_note"]["bullets"]))

    # Trạng thái phải bền vững: khung giờ đã đặt bị khóa
    after = call("find_doctor_schedule", specialty="Tiêu hóa", date="2026-09-15")
    slots_after = next(d["available_slots"]["2026-09-15"]
                       for d in after["doctors"] if d["doctor_id"] == "BS001")
    check("Khung giờ đã đặt bị khóa khỏi lịch trống",
          "09:30" in slots_before and "09:30" not in slots_after,
          f"trước={slots_before} sau={slots_after}")

    r2 = call("book_medical_appointment", doctor_id="BS001", date="2026-09-15",
              time_slot="09:30", patient_name="Nguoi Khac")
    check("Đặt trùng khung giờ bị từ chối", r2.get("status") == "SLOT_TAKEN")
    check("Từ chối kèm gợi ý khung giờ còn lại", bool(r2.get("remaining_slots")))

    # Mã phiếu hẹn phải tăng dần, không trùng
    r3 = call("book_medical_appointment", patient_id="BN2024002", doctor_id="BS002",
              date="2026-09-15", time_slot="08:00", patient_name="Tran Thi Binh")
    check("Mã phiếu hẹn không trùng nhau", r3.get("booking_id") != r.get("booking_id"))

    check("Bác sĩ không tồn tại trả NOT_FOUND",
          call("book_medical_appointment", doctor_id="BS999", date="2026-09-15",
               time_slot="09:00", patient_name="X").get("status") == "NOT_FOUND")
    check("Ngày bác sĩ không làm việc trả INVALID_DATE",
          call("book_medical_appointment", doctor_id="BS001", date="2026-12-25",
               time_slot="09:00", patient_name="X").get("status") == "INVALID_DATE")
    check("Khung giờ không hợp lệ trả SLOT_TAKEN",
          call("book_medical_appointment", doctor_id="BS001", date="2026-09-16",
               time_slot="23:59", patient_name="X").get("status") == "SLOT_TAKEN")

    # Bệnh nhân chưa định danh vẫn đặt được, Quick Note báo rõ là bệnh nhân mới
    r4 = call("book_medical_appointment", doctor_id="BS004", date="2026-09-16",
              time_slot="08:30", patient_name="Khach Vang Lai")
    check("Bệnh nhân chưa định danh vẫn đặt được lịch", r4.get("status") == "SUCCESS")
    check("Quick Note báo rõ chưa có hồ sơ tiền sử",
          "chưa" in r4["appointment"]["doctor_quick_note"]["headline"].lower())

    # Ghi bền vững xuống sổ lịch hẹn
    book = json.load(open(os.path.join(BASE_DIR, "data", "appointments.json"), encoding="utf-8"))
    check("Phiếu hẹn được ghi bền vững xuống file", len(book["appointments"]) >= 3)
    check("Bộ đếm phiếu hẹn tăng đúng", book["_meta"]["last_booking_seq"] >= 3)


# ==============================================================================
# NHÓM 5b — TRA CỨU & HỦY LỊCH HẸN
# ==============================================================================

def test_cancel_flow():
    print("\n🔁 NHÓM 5b — Tra cứu & hủy lịch hẹn")

    b1 = call("book_medical_appointment", patient_id="BN2024002", doctor_id="BS006",
              date="2026-09-15", time_slot="11:00", patient_name="Tran Thi Binh",
              patient_phone="0987654321", symptom_note="nổi mẩn ngứa")
    check("Đặt được lịch để thử hủy", b1.get("status") == "SUCCESS")
    bid = b1.get("booking_id")

    lst = call("list_my_appointments", patient_id="BN2024002")
    check("Tra được lịch hẹn theo mã bệnh nhân",
          lst.get("status") == "SUCCESS" and lst.get("total", 0) >= 1)
    check("Lịch hẹn trả về đúng mã phiếu vừa đặt",
          any(a["booking_id"] == bid for a in lst.get("appointments", [])))

    lst_phone = call("list_my_appointments", patient_phone="0987654321")
    check("Tra được lịch hẹn theo số điện thoại", lst_phone.get("total", 0) >= 1)

    # Khung giờ phải bị khóa khi đang giữ chỗ
    before = call("find_doctor_schedule", specialty="Da liễu", date="2026-09-15")
    slots_before = before["doctors"][0]["available_slots"]["2026-09-15"]
    check("Khung giờ đang giữ chỗ bị khóa", "11:00" not in slots_before, str(slots_before))

    c = call("cancel_appointment", booking_id=bid, reason="thử nghiệm")
    check("Hủy phiếu hẹn thành công", c.get("status") == "SUCCESS")
    check("Hủy xong có thông báo trả lại khung giờ", bool(c.get("released_slot")))

    # Khung giờ phải được trả lại, đúng thứ tự thời gian
    after = call("find_doctor_schedule", specialty="Da liễu", date="2026-09-15")
    slots_after = after["doctors"][0]["available_slots"]["2026-09-15"]
    check("Khung giờ được trả về lịch trống", "11:00" in slots_after, str(slots_after))
    check("Khung giờ trả về giữ đúng thứ tự", slots_after == sorted(slots_after), str(slots_after))

    lst2 = call("list_my_appointments", patient_id="BN2024002")
    check("Lịch đã hủy không còn trong danh sách",
          all(a["booking_id"] != bid for a in lst2.get("appointments", [])))

    check("Hủy lại lần hai trả ALREADY_CANCELLED",
          call("cancel_appointment", booking_id=bid).get("status") == "ALREADY_CANCELLED")
    check("Mã phiếu không tồn tại trả NOT_FOUND",
          call("cancel_appointment", booking_id="VM-99999999-999").get("status") == "NOT_FOUND")
    check("Thiếu mã phiếu trả MISSING_IDENTIFIER",
          call("cancel_appointment", booking_id="").get("status") == "MISSING_IDENTIFIER")
    check("Tra lịch không có định danh trả MISSING_IDENTIFIER",
          call("list_my_appointments").get("status") == "MISSING_IDENTIFIER")
    check("Bệnh nhân chưa có lịch trả danh sách rỗng",
          call("list_my_appointments", patient_id="BN2024005").get("total") == 0)

    # Kịch bản ĐỔI LỊCH: đặt mới rồi hủy cũ — hệ thống phải còn đúng 1 chỗ
    old = call("book_medical_appointment", patient_id="BN2024007", doctor_id="BS011",
               date="2026-09-15", time_slot="09:00", patient_name="Nguyen Thi Mai")
    new = call("book_medical_appointment", patient_id="BN2024007", doctor_id="BS011",
               date="2026-09-16", time_slot="08:00", patient_name="Nguyen Thi Mai")
    call("cancel_appointment", booking_id=old["booking_id"], reason="đổi giờ")
    final = call("list_my_appointments", patient_id="BN2024007")
    check("Đổi lịch xong chỉ còn đúng 1 chỗ giữ",
          final.get("total") == 1 and final["appointments"][0]["booking_id"] == new["booking_id"],
          f"còn {final.get('total')} lịch")


# ==============================================================================
# NHÓM 6 — KỊCH BẢN ĐẦU-CUỐI (END-TO-END)
# ==============================================================================

def test_end_to_end():
    print("\n🔗 NHÓM 6 — Kịch bản đầu-cuối (mô phỏng chuỗi ReAct)")

    # Kịch bản: bệnh nhân cũ quay lại, hệ thống phải tự chọn đúng bác sĩ quen
    hist = call("get_patient_history", patient_id="BN2024007")
    check("E2E-1 Đọc được tiền sử BN2024007", hist.get("status") == "SUCCESS")

    ranked = call("rank_doctors_for_patient", patient_id="BN2024007", symptom="đau đầu")
    check("E2E-2 Suy đúng chuyên khoa Thần kinh", ranked.get("specialty") == "Than kinh")
    top = ranked["ranked_doctors"][0]
    check("E2E-3 Chọn đúng bác sĩ đã theo dõi Migraine", top["doctor_id"] == "BS011")

    booked = call("book_medical_appointment",
                  patient_id="BN2024007", doctor_id=top["doctor_id"],
                  date=top["earliest_slot"]["date"], time_slot=top["earliest_slot"]["time"],
                  patient_name=ranked["patient_name"], symptom_note="đau đầu tái phát")
    check("E2E-4 Đặt lịch thành công với bác sĩ được xếp hạng 1", booked.get("status") == "SUCCESS")
    check("E2E-5 Phiếu hẹn mang Quick Note đúng bệnh nhân",
          booked["appointment"]["patient_id"] == "BN2024007")
    check("E2E-6 Quick Note cảnh báo dị ứng Ibuprofen",
          any("Ibuprofen" in a for a in booked["appointment"]["doctor_quick_note"]["alerts"]))

    # Kịch bản bệnh nhân đa chuyên khoa: tiểu đường đi khám tim mạch
    ranked2 = call("rank_doctors_for_patient", patient_id="BN2024006", specialty="Tim mạch")
    top2 = ranked2["ranked_doctors"][0]
    check("E2E-7 BN đa chuyên khoa → ưu tiên bác sĩ tim mạch đã gặp (BS008)",
          top2["doctor_id"] == "BS008", f"hạng 1 là {top2['doctor_id']}")

    # Kịch bản hết chỗ: phải đề xuất phương án thay thế chứ không im lặng
    no_slot = call("rank_doctors_for_patient", patient_id="BN2024001",
                   specialty="Da liễu", date="2026-09-14")
    check("E2E-8 Hết chỗ thì có gợi ý thay thế",
          no_slot.get("status") == "NO_SLOT" and bool(no_slot.get("suggestion")))


# ==============================================================================
# ĐIỂM VÀO
# ==============================================================================

if __name__ == "__main__":
    print("=" * 62)
    print("🧪 BỘ KIỂM THỬ TẦNG CÔNG CỤ & MCP SERVER (offline, không tốn API)")
    print("=" * 62)

    backup = snapshot_data()
    try:
        test_mcp_protocol()
        test_find_schedule()
        test_patient_history()
        test_ranking()
        test_booking()
        test_cancel_flow()
        test_end_to_end()
    finally:
        restore_data(backup)
        print("\n♻️  Đã khôi phục thư mục data/ về trạng thái ban đầu.")

    total = _passed + len(_failed)
    print("\n" + "=" * 62)
    print(f"📊 KẾT QUẢ: {_passed}/{total} phép kiểm tra đạt")
    if _failed:
        print(f"❌ {len(_failed)} phép kiểm tra KHÔNG đạt:")
        for f in _failed:
            print(f"   • {f}")
    else:
        print("✅ Toàn bộ phép kiểm tra đều đạt!")
    print("=" * 62)

    sys.exit(1 if _failed else 0)
