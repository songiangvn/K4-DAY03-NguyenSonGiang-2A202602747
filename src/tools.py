"""
🛠️ TOOL DEFINITIONS & EXECUTION BACKEND
Mã nguồn chứa danh sách Tool Schemas (JSON Schema) và Execution Layer phục vụ cho MCP Server.

ĐỀ TÀI: Trợ lý Tư vấn Sức khỏe Vinmec (Healthcare Assistant)
  - Tool 1 (Tra cứu):    find_doctor_schedule      -> Tìm bác sĩ & khung giờ khám còn trống
  - Tool 2 (Hành động):  book_medical_appointment  -> Đặt lịch khám và ghi vào sổ lịch hẹn
  - Tool 3 (Bộ nhớ):     get_patient_history       -> Tra cứu tiền sử khám bệnh (Long-term Memory)
  - Tool 4 (Xếp hạng):   rank_doctors_for_patient  -> Chấm điểm & xếp hạng bác sĩ theo tiền sử bệnh nhân
  - Tool 5 (Tra lịch hẹn): list_my_appointments    -> Xem các lịch hẹn sắp tới của bệnh nhân
  - Tool 6 (Hủy lịch):   cancel_appointment        -> Hủy phiếu hẹn và trả khung giờ về lịch trống

⚕️ RANH GIỚI CHUYÊN MÔN: Các công cụ chỉ TRA CỨU và TÓM TẮT dữ liệu đã được bác sĩ ghi nhận
từ trước, đồng thời GỢI Ý bác sĩ dựa trên sự phù hợp về chuyên khoa. Hệ thống KHÔNG chẩn đoán
bệnh mới và KHÔNG kê đơn thuốc.
"""

import json
import os
import unicodedata
from datetime import date, datetime
from typing import Dict, Any, List

# ==============================================================================
# 0. TẦNG TRUY XUẤT DỮ LIỆU (DATA ACCESS LAYER)
# Dữ liệu mô phỏng được tách riêng ra thư mục data/ thay vì hard-code trong source,
# giúp Tool Layer giữ đúng hình dạng của một data layer thật: đọc/ghi qua repository.
# ==============================================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DOCTORS_PATH = os.path.join(DATA_DIR, "doctors.json")
APPOINTMENTS_PATH = os.path.join(DATA_DIR, "appointments.json")
HISTORY_PATH = os.path.join(DATA_DIR, "medical_history.json")

# Mốc thời gian "hiện tại" của kịch bản Lab, dùng để quy đổi tiền sử ra khoảng cách tương đối
# ("cách đây 6 tháng") thay vì chỉ in ra ngày tuyệt đối.
TODAY = date(2026, 9, 13)


def _load_json(path: str) -> Dict[str, Any]:
    """Đọc một file dữ liệu JSON theo đường dẫn tuyệt đối"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: str, payload: Dict[str, Any]) -> None:
    """Ghi dữ liệu xuống file JSON (dùng khi Agent đặt lịch thành công)"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _normalize(text: str) -> str:
    """
    Chuẩn hóa chuỗi tiếng Việt về dạng không dấu, chữ thường.
    Nhờ đó Agent gõ 'Tiêu hóa', 'tieu hoa' hay 'TIÊU HÓA' đều khớp cùng một chuyên khoa.
    """
    if not text:
        return ""
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return " ".join(stripped.lower().split())


def _months_ago(date_str: str) -> int:
    """Số tháng tính từ một mốc ngày (YYYY-MM-DD) đến 'hiện tại' của kịch bản"""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return -1
    return (TODAY.year - d.year) * 12 + (TODAY.month - d.month)


def _humanize_gap(months: int) -> str:
    """Diễn đạt khoảng cách thời gian theo cách người đọc dễ hình dung"""
    if months < 0:
        return "không rõ thời điểm"
    if months == 0:
        return "trong tháng này"
    if months == 1:
        return "cách đây 1 tháng"
    if months < 12:
        return f"cách đây {months} tháng"
    years, rem = divmod(months, 12)
    return f"cách đây {years} năm" if rem == 0 else f"cách đây {years} năm {rem} tháng"


def _find_patient(db: Dict[str, Any], patient_id: str = "", phone: str = "") -> Dict[str, Any]:
    """Định vị hồ sơ bệnh nhân theo mã bệnh nhân (ưu tiên) hoặc số điện thoại"""
    patients = db["patients"]
    if patient_id:
        key = patient_id.strip().upper()
        if key in patients:
            return patients[key]
    if phone:
        digits = "".join(ch for ch in phone if ch.isdigit())
        for p in patients.values():
            if "".join(ch for ch in p.get("phone", "") if ch.isdigit()) == digits:
                return p
    return {}


# ==============================================================================
# 1. KHAI BÁO TOOL SCHEMAS CHUẨN NATIVE JSON SCHEMA (TASK 1.2)
# ==============================================================================

TOOLS_SCHEMA = [
    # --------------------------------------------------------------------------
    # Tool 1 — TRA CỨU: tìm bác sĩ và khung giờ khám còn trống.
    # Cho phép LLM tra theo chuyên khoa HOẶC theo triệu chứng người bệnh mô tả,
    # vì bệnh nhân thường không tự biết mình cần khám khoa nào.
    # --------------------------------------------------------------------------
    {
        "name": "find_doctor_schedule",
        "description": (
            "Tra cứu danh sách bác sĩ và các khung giờ khám còn trống tại Vinmec. "
            "Dùng công cụ này khi người bệnh muốn biết khám khoa nào, bác sĩ nào đang rảnh, "
            "hoặc chỉ mô tả triệu chứng mà chưa biết nên khám chuyên khoa gì. "
            "Bắt buộc phải gọi công cụ này TRƯỚC khi đặt lịch, để lấy được doctor_id chính xác."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "specialty": {
                    "type": "string",
                    "description": (
                        "Tên chuyên khoa cần tra cứu. Các chuyên khoa hiện có: "
                        "'Tiêu hóa', 'Tim mạch', 'Cơ xương khớp', 'Nhi khoa', 'Da liễu'. "
                        "Để trống nếu chỉ biết triệu chứng."
                    )
                },
                "symptom": {
                    "type": "string",
                    "description": (
                        "Triệu chứng người bệnh mô tả bằng tiếng Việt, ví dụ: 'đau dạ dày', "
                        "'đau ngực', 'đau lưng', 'nổi mẩn ngứa'. "
                        "Hệ thống sẽ tự suy ra chuyên khoa phù hợp. Để trống nếu đã biết chuyên khoa."
                    )
                },
                "date": {
                    "type": "string",
                    "description": (
                        "Ngày mong muốn khám theo định dạng YYYY-MM-DD (ví dụ: '2026-09-15'). "
                        "Để trống để xem toàn bộ lịch trống của các ngày sắp tới."
                    )
                }
            },
            "required": []
        }
    },

    # --------------------------------------------------------------------------
    # TASK 1.2 — Tool 2 — HÀNH ĐỘNG: đặt lịch khám.
    # Schema khai báo đủ các trường LLM phải trích xuất từ hội thoại, trong đó
    # doctor_id / date / time_slot / patient_name là bắt buộc vì thiếu một trường
    # thì không định danh được suất khám cần giữ chỗ.
    # --------------------------------------------------------------------------
    {
        "name": "book_medical_appointment",
        "description": (
            "Đặt lịch khám bệnh với một bác sĩ cụ thể tại Vinmec và ghi vào sổ lịch hẹn. "
            "CHỈ gọi công cụ này SAU KHI đã xác nhận bác sĩ đó thực sự còn trống khung giờ mong muốn "
            "(qua find_doctor_schedule hoặc rank_doctors_for_patient). "
            "Nếu truyền kèm patient_id, phiếu hẹn sẽ tự động đính kèm bản tóm tắt tiền sử "
            "(Quick Note) để bác sĩ đọc nhanh trước giờ khám. "
            "Công cụ trả về mã phiếu hẹn nếu đặt thành công."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": (
                        "Mã bệnh nhân tại Vinmec (ví dụ: 'BN2024001'). Truyền vào để phiếu hẹn "
                        "kèm Quick Note tiền sử cho bác sĩ. Để trống nếu là bệnh nhân mới."
                    )
                },
                "doctor_id": {
                    "type": "string",
                    "description": "Mã bác sĩ lấy từ kết quả find_doctor_schedule (ví dụ: 'BS001')."
                },
                "date": {
                    "type": "string",
                    "description": "Ngày khám theo định dạng YYYY-MM-DD (ví dụ: '2026-09-15')."
                },
                "time_slot": {
                    "type": "string",
                    "description": "Khung giờ khám theo định dạng HH:MM (ví dụ: '09:00'). Phải là giờ còn trống."
                },
                "patient_name": {
                    "type": "string",
                    "description": "Họ và tên đầy đủ của người bệnh đăng ký khám."
                },
                "patient_phone": {
                    "type": "string",
                    "description": "Số điện thoại liên hệ của người bệnh (ví dụ: '0912345678')."
                },
                "symptom_note": {
                    "type": "string",
                    "description": "Ghi chú ngắn về triệu chứng hoặc lý do khám, giúp bác sĩ chuẩn bị trước."
                }
            },
            "required": ["doctor_id", "date", "time_slot", "patient_name"]
        }
    },

    # --------------------------------------------------------------------------
    # Tool 3 — BỘ NHỚ DÀI HẠN: tra cứu tiền sử khám bệnh của bệnh nhân.
    # Đây là nguồn "long-term memory" giúp Agent nhớ được bệnh nhân đã khám gì,
    # với ai, kết quả ra sao — dữ liệu tồn tại XUYÊN PHIÊN hội thoại.
    # --------------------------------------------------------------------------
    {
        "name": "get_patient_history",
        "description": (
            "Tra cứu hồ sơ bệnh án và tiền sử các lần khám trước của một bệnh nhân tại Vinmec. "
            "Trả về bệnh mạn tính, dị ứng thuốc, danh sách các lần khám đã qua (triệu chứng, chẩn đoán "
            "của bác sĩ, hướng điều trị, dặn dò tái khám) kèm khoảng cách thời gian so với hiện tại. "
            "Hãy gọi công cụ này khi người bệnh cung cấp mã bệnh nhân hoặc số điện thoại, TRƯỚC KHI "
            "gợi ý bác sĩ hoặc đặt lịch, để tư vấn dựa trên bệnh sử thay vì chỉ dựa vào triệu chứng hiện tại."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": "Mã bệnh nhân tại Vinmec (ví dụ: 'BN2024001'). Đây là cách định danh chính xác nhất."
                },
                "phone": {
                    "type": "string",
                    "description": "Số điện thoại đã đăng ký của bệnh nhân, dùng khi người bệnh không nhớ mã bệnh nhân."
                }
            },
            "required": []
        }
    },

    # --------------------------------------------------------------------------
    # Tool 4 — XẾP HẠNG CÓ GIẢI TRÌNH: chấm điểm các bác sĩ đang trống lịch
    # dựa trên tiền sử của chính bệnh nhân, trả kèm lý do từng bậc xếp hạng
    # để Agent giải thích minh bạch cho người bệnh (không phải lý do LLM tự bịa).
    # --------------------------------------------------------------------------
    {
        "name": "rank_doctors_for_patient",
        "description": (
            "Chấm điểm và xếp hạng các bác sĩ đang còn lịch trống theo mức độ phù hợp với một bệnh nhân cụ thể, "
            "dựa trên tiền sử khám bệnh của họ. Tiêu chí gồm: bác sĩ đã từng trực tiếp điều trị cho bệnh nhân "
            "(tính liên tục chăm sóc), sự khớp giữa chuyên khoa của bác sĩ với bệnh mạn tính đã ghi nhận, "
            "số năm kinh nghiệm và mức độ sớm của lịch trống. "
            "Mỗi bác sĩ trả về kèm điểm số và lý do xếp hạng cụ thể để giải thích minh bạch cho người bệnh. "
            "Gọi công cụ này sau khi đã có tiền sử bệnh nhân và cần chọn ra bác sĩ phù hợp nhất."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": "Mã bệnh nhân cần xếp hạng bác sĩ (ví dụ: 'BN2024001')."
                },
                "specialty": {
                    "type": "string",
                    "description": (
                        "Chuyên khoa cần khám lần này: 'Tiêu hóa', 'Tim mạch', 'Cơ xương khớp', "
                        "'Nhi khoa', 'Da liễu'. Để trống nếu muốn suy ra từ triệu chứng."
                    )
                },
                "symptom": {
                    "type": "string",
                    "description": "Triệu chứng hiện tại của người bệnh, dùng để suy ra chuyên khoa nếu chưa biết."
                },
                "date": {
                    "type": "string",
                    "description": "Ngày mong muốn khám theo định dạng YYYY-MM-DD. Để trống để xét mọi ngày còn trống."
                }
            },
            "required": ["patient_id"]
        }
    },

    # --------------------------------------------------------------------------
    # Tool 5 — TRA LỊCH HẸN: xem các phiếu hẹn sắp tới của bệnh nhân.
    # Cần thiết để Agent biết bệnh nhân đang giữ chỗ những suất khám nào,
    # tránh đặt chồng lịch hoặc để sót lịch cũ khi người bệnh muốn đổi giờ.
    # --------------------------------------------------------------------------
    {
        "name": "list_my_appointments",
        "description": (
            "Liệt kê các lịch hẹn khám đang còn hiệu lực của một bệnh nhân tại Vinmec. "
            "Hãy gọi công cụ này khi người bệnh hỏi 'tôi có lịch nào', muốn ĐỔI hoặc HỦY lịch, "
            "hoặc khi bạn cần kiểm tra xem họ đã có lịch hẹn trùng giờ chưa trước khi đặt thêm."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": "Mã bệnh nhân tại Vinmec (ví dụ: 'BN2024002')."
                },
                "patient_phone": {
                    "type": "string",
                    "description": "Số điện thoại đã đăng ký, dùng khi người bệnh không nhớ mã bệnh nhân."
                }
            },
            "required": []
        }
    },

    # --------------------------------------------------------------------------
    # Tool 6 — HỦY LỊCH: hủy phiếu hẹn và TRẢ LẠI khung giờ vào lịch trống.
    # Đây là cặp đối xứng với book_medical_appointment, giúp trạng thái hệ thống
    # luôn nhất quán khi người bệnh đổi ý.
    # --------------------------------------------------------------------------
    {
        "name": "cancel_appointment",
        "description": (
            "Hủy một phiếu hẹn khám đã đặt và trả khung giờ đó về lại lịch trống của bác sĩ. "
            "Dùng khi người bệnh muốn hủy lịch, hoặc khi họ ĐỔI sang khung giờ khác — "
            "lúc đó hãy hủy phiếu hẹn cũ sau khi đã đặt được phiếu mới, để họ không bị giữ hai chỗ. "
            "Cần mã phiếu hẹn dạng 'VM-YYYYMMDD-NNN' (lấy từ list_my_appointments nếu người bệnh không nhớ)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "booking_id": {
                    "type": "string",
                    "description": "Mã phiếu hẹn cần hủy, ví dụ 'VM-20260915-001'."
                },
                "reason": {
                    "type": "string",
                    "description": "Lý do hủy, ví dụ 'người bệnh đổi sang khung giờ khác'."
                }
            },
            "required": ["booking_id"]
        }
    }
]


# ==============================================================================
# 2. HÀM THỰC THI TOOL (EXECUTION LAYER)
# ==============================================================================

def execute_find_doctor_schedule(specialty: str = "", symptom: str = "", date: str = "") -> str:
    """
    Thực thi tra cứu bác sĩ & lịch khám còn trống.
    Ưu tiên lọc theo specialty; nếu không có thì suy ra chuyên khoa từ symptom.
    """
    db = _load_json(DOCTORS_PATH)
    doctors: Dict[str, Any] = db["doctors"]
    specialties: Dict[str, List[str]] = db["specialties"]

    resolved_specialty = ""
    matched_by = "all"

    # Bước 1: xác định chuyên khoa cần tra cứu
    if specialty:
        norm_input = _normalize(specialty)
        for name in specialties:
            if _normalize(name) == norm_input or norm_input in _normalize(name):
                resolved_specialty = name
                matched_by = "specialty"
                break
        if not resolved_specialty:
            return json.dumps({
                "status": "NOT_FOUND",
                "message": f"Vinmec hiện chưa có chuyên khoa '{specialty}'.",
                "available_specialties": list(specialties.keys())
            }, ensure_ascii=False)

    elif symptom:
        norm_symptom = _normalize(symptom)
        for key, spec_name in db["symptom_to_specialty"].items():
            if key in norm_symptom or norm_symptom in key:
                resolved_specialty = spec_name
                matched_by = "symptom"
                break
        if not resolved_specialty:
            return json.dumps({
                "status": "NOT_FOUND",
                "message": (
                    f"Chưa thể tự xác định chuyên khoa từ triệu chứng '{symptom}'. "
                    "Đề nghị người bệnh chọn trực tiếp một chuyên khoa."
                ),
                "available_specialties": list(specialties.keys())
            }, ensure_ascii=False)

    # Bước 2: lọc danh sách bác sĩ theo chuyên khoa đã xác định
    if resolved_specialty:
        doctor_ids = specialties[resolved_specialty]
    else:
        doctor_ids = list(doctors.keys())

    # Bước 3: dựng kết quả kèm khung giờ còn trống
    results = []
    for did in doctor_ids:
        doc = doctors[did]
        slots = doc["available_slots"]

        if date:
            free_slots = {date: slots.get(date, [])}
        else:
            free_slots = slots

        # Bỏ qua bác sĩ đã kín lịch hoàn toàn trong phạm vi tra cứu
        if not any(free_slots.values()):
            continue

        results.append({
            "doctor_id": doc["doctor_id"],
            "full_name": doc["full_name"],
            "title": doc["title"],
            "specialty": doc["specialty"],
            "experience_years": doc["experience_years"],
            "room": doc["room"],
            "consultation_fee_vnd": doc["consultation_fee_vnd"],
            "available_slots": free_slots
        })

    if not results:
        scope = f"chuyên khoa {resolved_specialty}" if resolved_specialty else "toàn bệnh viện"
        day_note = f" trong ngày {date}" if date else ""
        return json.dumps({
            "status": "NO_SLOT",
            "message": f"Không còn bác sĩ nào trống lịch ở {scope}{day_note}.",
            "suggestion": "Đề nghị người bệnh chọn ngày khác hoặc chuyên khoa khác."
        }, ensure_ascii=False)

    return json.dumps({
        "status": "SUCCESS",
        "matched_by": matched_by,
        "specialty": resolved_specialty or "Tất cả chuyên khoa",
        "total_doctors": len(results),
        "doctors": results
    }, ensure_ascii=False)


def execute_book_medical_appointment(
    doctor_id: str,
    date: str,
    time_slot: str,
    patient_name: str,
    patient_phone: str = "",
    symptom_note: str = "",
    patient_id: str = ""
) -> str:
    """
    Thực thi đặt lịch khám: kiểm tra suất khám còn trống, ghi phiếu hẹn
    và loại khung giờ đã đặt khỏi lịch trống của bác sĩ.

    Nếu định danh được bệnh nhân (qua patient_id hoặc số điện thoại), phiếu hẹn
    sẽ đính kèm 'Quick Note' tóm tắt tiền sử để bác sĩ đọc nhanh trước giờ khám.
    """
    db = _load_json(DOCTORS_PATH)
    doctors = db["doctors"]

    # Kiểm tra 1: bác sĩ có tồn tại trong hệ thống không
    doctor_id = (doctor_id or "").strip().upper()
    if doctor_id not in doctors:
        return json.dumps({
            "status": "NOT_FOUND",
            "message": f"Không tìm thấy bác sĩ có mã '{doctor_id}' trong hệ thống Vinmec.",
            "hint": "Hãy gọi find_doctor_schedule trước để lấy đúng doctor_id."
        }, ensure_ascii=False)

    doctor = doctors[doctor_id]

    # Kiểm tra 2: bác sĩ có lịch làm việc ngày đó không
    if date not in doctor["available_slots"]:
        return json.dumps({
            "status": "INVALID_DATE",
            "message": f"Bác sĩ {doctor['full_name']} không có lịch làm việc ngày {date}.",
            "available_dates": list(doctor["available_slots"].keys())
        }, ensure_ascii=False)

    day_slots = doctor["available_slots"][date]

    # Kiểm tra 3: khung giờ có còn trống không (chống đặt trùng lịch)
    if time_slot not in day_slots:
        return json.dumps({
            "status": "SLOT_TAKEN",
            "message": (
                f"Khung giờ {time_slot} ngày {date} của bác sĩ {doctor['full_name']} "
                "không còn trống hoặc không hợp lệ."
            ),
            "remaining_slots": day_slots
        }, ensure_ascii=False)

    # Ghi phiếu hẹn xuống sổ lịch hẹn
    book = _load_json(APPOINTMENTS_PATH)
    seq = book["_meta"]["last_booking_seq"] + 1
    booking_id = f"VM-{date.replace('-', '')}-{seq:03d}"

    record = {
        "booking_id": booking_id,
        "patient_name": patient_name,
        "patient_phone": patient_phone or "Chưa cung cấp",
        "doctor_id": doctor_id,
        "doctor_name": doctor["full_name"],
        "specialty": doctor["specialty"],
        "room": doctor["room"],
        "date": date,
        "time_slot": time_slot,
        "symptom_note": symptom_note or "Không có ghi chú",
        "consultation_fee_vnd": doctor["consultation_fee_vnd"],
        "state": "CONFIRMED"
    }

    # Đính kèm Quick Note tiền sử để bác sĩ nắm nhanh bệnh nhân trước giờ khám
    hist_db = _load_json(HISTORY_PATH)
    patient = _find_patient(hist_db, patient_id, patient_phone)
    if patient:
        record["patient_id"] = patient["patient_id"]
        record["doctor_quick_note"] = _build_quick_note(patient, doctor["specialty"])
    else:
        record["patient_id"] = patient_id or "Chưa định danh"
        record["doctor_quick_note"] = {
            "headline": f"{patient_name} — chưa tìm thấy hồ sơ tiền sử trong hệ thống.",
            "bullets": ["Bệnh nhân mới hoặc chưa cung cấp mã bệnh nhân, cần khai thác bệnh sử tại phòng khám."],
            "alerts": []
        }

    book["appointments"].append(record)
    book["_meta"]["last_booking_seq"] = seq
    _save_json(APPOINTMENTS_PATH, book)

    # Khóa khung giờ vừa đặt để lần tra cứu sau không còn thấy suất này
    day_slots.remove(time_slot)
    _save_json(DOCTORS_PATH, db)

    return json.dumps({
        "status": "SUCCESS",
        "booking_id": booking_id,
        "message": (
            f"Đã đặt lịch khám thành công cho {patient_name} với {doctor['full_name']} "
            f"({doctor['specialty']}) vào {time_slot} ngày {date} tại {doctor['room']}."
        ),
        "appointment": record
    }, ensure_ascii=False)


# ==============================================================================
# 3. LONG-TERM MEMORY: TIỀN SỬ KHÁM BỆNH & XẾP HẠNG BÁC SĨ
# ==============================================================================

def _resolve_specialty(db_doctors: Dict[str, Any], specialty: str = "", symptom: str = "") -> str:
    """Xác định tên chuyên khoa chuẩn từ input chuyên khoa hoặc triệu chứng (trả '' nếu không khớp)"""
    specialties = db_doctors["specialties"]
    if specialty:
        norm = _normalize(specialty)
        for name in specialties:
            if _normalize(name) == norm or norm in _normalize(name):
                return name
    if symptom:
        norm_symptom = _normalize(symptom)
        for key, spec_name in db_doctors["symptom_to_specialty"].items():
            if key in norm_symptom or norm_symptom in key:
                return spec_name
    return ""


def _build_quick_note(patient: Dict[str, Any], upcoming_specialty: str = "") -> Dict[str, Any]:
    """
    Sinh 'Quick Note' — bản tóm tắt bệnh sử ngắn gọn để bác sĩ đọc nhanh trước giờ khám.

    Chỉ tóm tắt lại những gì bác sĩ đã ghi nhận trong các lần khám trước;
    không suy luận chẩn đoán mới.
    """
    history = patient.get("visit_history", [])
    if not history:
        return {
            "headline": f"{patient['full_name']} — bệnh nhân chưa có lịch sử khám tại Vinmec.",
            "chronic_conditions": patient.get("chronic_conditions", []),
            "allergies": patient.get("allergies", []),
            "total_visits": 0,
            "bullets": ["Chưa có tiền sử khám tại hệ thống, cần khai thác bệnh sử từ đầu."],
            "alerts": []
        }

    sorted_history = sorted(history, key=lambda v: v["date"], reverse=True)
    latest = sorted_history[0]
    gap = _months_ago(latest["date"])

    bullets = [
        f"Đã khám {len(history)} lần tại Vinmec, gần nhất {_humanize_gap(gap)} "
        f"({latest['date']}) tại khoa {latest['specialty']}.",
        f"Chẩn đoán gần nhất: {latest['diagnosis']} — kết quả: {latest['outcome']}.",
        f"Dặn dò của bác sĩ lần trước: {latest['follow_up_note']}"
    ]

    # Các lần khám cùng chuyên khoa với lần hẹn sắp tới thì đặc biệt đáng chú ý
    if upcoming_specialty:
        same_spec = [v for v in sorted_history if _normalize(v["specialty"]) == _normalize(upcoming_specialty)]
        if len(same_spec) > 1:
            bullets.append(
                f"Riêng khoa {upcoming_specialty}: đã khám {len(same_spec)} lần "
                f"(gần nhất {_humanize_gap(_months_ago(same_spec[0]['date']))}), "
                "cần đối chiếu diễn tiến giữa các lần."
            )

    # Cảnh báo an toàn — thông tin bác sĩ cần biết trước khi kê đơn
    alerts = []
    if patient.get("allergies"):
        alerts.append(f"⚠️ DỊ ỨNG: {', '.join(patient['allergies'])} — lưu ý khi kê đơn.")
    if patient.get("chronic_conditions"):
        alerts.append(f"📌 Bệnh mạn tính đang theo dõi: {', '.join(patient['chronic_conditions'])}.")
    if any(v["outcome"] == "Dang theo doi" for v in sorted_history):
        pending = next(v for v in sorted_history if v["outcome"] == "Dang theo doi")
        alerts.append(f"🔄 Còn vấn đề đang theo dõi từ lần khám {pending['date']}: {pending['diagnosis']}.")

    return {
        "headline": (
            f"{patient['full_name']} ({patient.get('gender', '')}, sinh {patient.get('year_of_birth', '?')}) — "
            f"{len(history)} lần khám, gần nhất {_humanize_gap(gap)}."
        ),
        "chronic_conditions": patient.get("chronic_conditions", []),
        "allergies": patient.get("allergies", []),
        "blood_type": patient.get("blood_type", ""),
        "total_visits": len(history),
        "bullets": bullets,
        "alerts": alerts
    }


def execute_get_patient_history(patient_id: str = "", phone: str = "") -> str:
    """Tra cứu tiền sử khám bệnh — nguồn Long-term Memory của Agent"""
    if not patient_id and not phone:
        return json.dumps({
            "status": "MISSING_IDENTIFIER",
            "message": "Không có mã bệnh nhân hoặc số điện thoại nên chưa tra được hồ sơ.",
            "hint": (
                "ĐỪNG hỏi lại người bệnh mã lần nữa nếu họ đã nói không nhớ/không có. "
                "Hãy xem như bệnh nhân khám lần đầu và chuyển sang gọi find_doctor_schedule "
                "với triệu chứng họ đã mô tả."
            )
        }, ensure_ascii=False)

    db = _load_json(HISTORY_PATH)
    patient = _find_patient(db, patient_id, phone)

    if not patient:
        return json.dumps({
            "status": "NOT_FOUND",
            "message": (
                f"Không tìm thấy hồ sơ bệnh nhân với "
                f"{'mã ' + patient_id if patient_id else 'số điện thoại ' + phone}."
            ),
            "hint": "Có thể đây là bệnh nhân khám lần đầu — hãy tiếp tục tư vấn dựa trên triệu chứng hiện tại."
        }, ensure_ascii=False)

    # Bổ sung khoảng cách thời gian tương đối cho từng lần khám
    visits = []
    for v in sorted(patient.get("visit_history", []), key=lambda x: x["date"], reverse=True):
        months = _months_ago(v["date"])
        visits.append({**v, "months_ago": months, "time_gap": _humanize_gap(months)})

    return json.dumps({
        "status": "SUCCESS",
        "patient_id": patient["patient_id"],
        "full_name": patient["full_name"],
        "year_of_birth": patient.get("year_of_birth"),
        "gender": patient.get("gender"),
        "blood_type": patient.get("blood_type"),
        "allergies": patient.get("allergies", []),
        "chronic_conditions": patient.get("chronic_conditions", []),
        "total_visits": len(visits),
        "visit_history": visits,
        "quick_note": _build_quick_note(patient),
        "disclaimer": "Dữ liệu tiền sử do bác sĩ ghi nhận trước đó. Hệ thống không chẩn đoán bệnh mới."
    }, ensure_ascii=False)


def execute_rank_doctors_for_patient(
    patient_id: str,
    specialty: str = "",
    symptom: str = "",
    date: str = ""
) -> str:
    """
    Chấm điểm & xếp hạng bác sĩ theo mức độ phù hợp với tiền sử bệnh nhân.

    Thang điểm tất định (tối đa 100), mỗi tiêu chí đều kèm lý do giải trình:
        +40  Bác sĩ đã từng trực tiếp điều trị cho bệnh nhân này (liên tục chăm sóc)
        +15  Mỗi lần khám trước đó với chính bác sĩ này (trần +30)
        +20  Chuyên khoa khớp với bệnh mạn tính đang theo dõi
        +0-15 Thâm niên (experience_years, quy đổi tuyến tính, trần 30 năm)
        +0-10 Mức độ sớm của khung giờ trống gần nhất
    """
    hist_db = _load_json(HISTORY_PATH)
    patient = _find_patient(hist_db, patient_id)
    if not patient:
        return json.dumps({
            "status": "NOT_FOUND",
            "message": f"Không tìm thấy hồ sơ bệnh nhân '{patient_id}' để xếp hạng bác sĩ."
        }, ensure_ascii=False)

    doc_db = _load_json(DOCTORS_PATH)
    resolved = _resolve_specialty(doc_db, specialty, symptom)
    if not resolved:
        return json.dumps({
            "status": "NOT_FOUND",
            "message": (
                f"Chưa xác định được chuyên khoa từ "
                f"{'chuyên khoa ' + specialty if specialty else 'triệu chứng ' + symptom}."
            ),
            "available_specialties": list(doc_db["specialties"].keys())
        }, ensure_ascii=False)

    history = patient.get("visit_history", [])
    chronic_norm = " ".join(_normalize(c) for c in patient.get("chronic_conditions", []))

    ranked = []
    for did in doc_db["specialties"][resolved]:
        doc = doc_db["doctors"][did]

        # Lọc khung giờ còn trống trong phạm vi ngày yêu cầu
        slots = {date: doc["available_slots"].get(date, [])} if date else doc["available_slots"]
        free_dates = sorted(d for d, s in slots.items() if s)
        if not free_dates:
            continue

        score = 0
        reasons = []

        # Tiêu chí 1 & 2: tính liên tục chăm sóc
        past_visits = [v for v in history if v["doctor_id"] == did]
        if past_visits:
            score += 40
            recent = max(past_visits, key=lambda v: v["date"])
            gap_text = _humanize_gap(_months_ago(recent["date"]))
            reasons.append(
                f"Đã trực tiếp điều trị cho bệnh nhân {len(past_visits)} lần, gần nhất {gap_text} "
                f"với chẩn đoán '{recent['diagnosis']}' (+40 điểm liên tục chăm sóc)"
            )
            bonus = min(len(past_visits) * 15, 30)
            score += bonus
            reasons.append(f"Đã nắm được diễn tiến bệnh qua {len(past_visits)} lần khám trước (+{bonus} điểm)")
        else:
            reasons.append("Chưa từng khám cho bệnh nhân này (+0 điểm liên tục chăm sóc)")

        # Tiêu chí 3: chuyên khoa khớp bệnh mạn tính
        if chronic_norm and _normalize(doc["specialty"]) in chronic_norm:
            score += 20
            reasons.append(
                f"Chuyên khoa {doc['specialty']} khớp trực tiếp với bệnh mạn tính đang theo dõi (+20 điểm)"
            )
        elif chronic_norm and resolved == doc["specialty"]:
            score += 10
            reasons.append(f"Đúng chuyên khoa {resolved} cần khám lần này (+10 điểm)")

        # Tiêu chí 4: thâm niên
        exp = doc["experience_years"]
        exp_score = round(min(exp / 30, 1.0) * 15)
        score += exp_score
        reasons.append(f"{exp} năm kinh nghiệm, học hàm {doc['title']} (+{exp_score} điểm thâm niên)")

        # Tiêu chí 5: mức độ sớm của lịch trống
        days_until = (datetime.strptime(free_dates[0], "%Y-%m-%d").date() - TODAY).days
        slot_score = max(0, 10 - max(days_until, 0))
        score += slot_score
        reasons.append(
            f"Khung giờ sớm nhất: {slots[free_dates[0]][0]} ngày {free_dates[0]} (+{slot_score} điểm độ sớm)"
        )

        ranked.append({
            "doctor_id": did,
            "full_name": doc["full_name"],
            "title": doc["title"],
            "specialty": doc["specialty"],
            "experience_years": exp,
            "room": doc["room"],
            "consultation_fee_vnd": doc["consultation_fee_vnd"],
            "match_score": score,
            "is_returning_doctor": bool(past_visits),
            "ranking_reasons": reasons,
            "earliest_slot": {"date": free_dates[0], "time": slots[free_dates[0]][0]},
            "available_slots": {d: slots[d] for d in free_dates}
        })

    if not ranked:
        return json.dumps({
            "status": "NO_SLOT",
            "message": f"Không còn bác sĩ nào trống lịch ở chuyên khoa {resolved}"
                       + (f" trong ngày {date}." if date else "."),
            "suggestion": "Đề nghị người bệnh chọn ngày khác."
        }, ensure_ascii=False)

    ranked.sort(key=lambda d: d["match_score"], reverse=True)
    for i, d in enumerate(ranked, 1):
        d["rank"] = i

    top = ranked[0]
    if top["is_returning_doctor"]:
        recommendation = (
            f"Đề xuất {top['full_name']} — đây là bác sĩ đã theo dõi bệnh nhân từ trước, "
            f"nắm được diễn tiến bệnh nên không phải khai thác lại bệnh sử từ đầu."
        )
    else:
        recommendation = (
            f"Đề xuất {top['full_name']} — phù hợp nhất về chuyên môn "
            f"({top['experience_years']} năm kinh nghiệm) và có lịch trống sớm."
        )

    return json.dumps({
        "status": "SUCCESS",
        "patient_id": patient["patient_id"],
        "patient_name": patient["full_name"],
        "specialty": resolved,
        "total_candidates": len(ranked),
        "recommendation": recommendation,
        "ranked_doctors": ranked,
        "scoring_criteria": (
            "Thang 100 điểm: từng điều trị cho bệnh nhân (+40), số lần khám trước (+tối đa 30), "
            "khớp bệnh mạn tính (+20), thâm niên (+tối đa 15), độ sớm lịch trống (+tối đa 10)."
        )
    }, ensure_ascii=False)


# ==============================================================================
# 3b. QUẢN LÝ LỊCH HẸN: TRA CỨU & HỦY
# ==============================================================================

def execute_list_my_appointments(patient_id: str = "", patient_phone: str = "") -> str:
    """Liệt kê các phiếu hẹn còn hiệu lực của bệnh nhân (trạng thái CONFIRMED)"""
    if not patient_id and not patient_phone:
        return json.dumps({
            "status": "MISSING_IDENTIFIER",
            "message": "Cần mã bệnh nhân hoặc số điện thoại để tra lịch hẹn.",
            "hint": "Nếu người bệnh không nhớ, hãy hỏi họ mã phiếu hẹn dạng 'VM-YYYYMMDD-NNN'."
        }, ensure_ascii=False)

    book = _load_json(APPOINTMENTS_PATH)
    pid = (patient_id or "").strip().upper()
    phone_digits = "".join(ch for ch in (patient_phone or "") if ch.isdigit())

    matched = []
    for ap in book["appointments"]:
        if ap.get("state") != "CONFIRMED":
            continue
        ap_phone = "".join(ch for ch in str(ap.get("patient_phone", "")) if ch.isdigit())
        if (pid and str(ap.get("patient_id", "")).upper() == pid) or \
           (phone_digits and ap_phone == phone_digits):
            matched.append({
                "booking_id": ap["booking_id"],
                "doctor_name": ap["doctor_name"],
                "specialty": ap["specialty"],
                "room": ap["room"],
                "date": ap["date"],
                "time_slot": ap["time_slot"],
                "symptom_note": ap.get("symptom_note", ""),
                "consultation_fee_vnd": ap.get("consultation_fee_vnd"),
            })

    matched.sort(key=lambda a: (a["date"], a["time_slot"]))

    if not matched:
        return json.dumps({
            "status": "SUCCESS",
            "total": 0,
            "appointments": [],
            "message": "Người bệnh hiện chưa có lịch hẹn nào đang chờ khám."
        }, ensure_ascii=False)

    return json.dumps({
        "status": "SUCCESS",
        "total": len(matched),
        "appointments": matched,
        "message": f"Người bệnh đang có {len(matched)} lịch hẹn sắp tới."
    }, ensure_ascii=False)


def execute_cancel_appointment(booking_id: str, reason: str = "") -> str:
    """
    Hủy phiếu hẹn và TRẢ khung giờ về lại lịch trống của bác sĩ.
    Đây là thao tác đối xứng với đặt lịch, giữ cho trạng thái hệ thống luôn nhất quán.
    """
    booking_id = (booking_id or "").strip().upper()
    if not booking_id:
        return json.dumps({
            "status": "MISSING_IDENTIFIER",
            "message": "Cần mã phiếu hẹn để hủy lịch.",
            "hint": "Gọi list_my_appointments để lấy mã phiếu hẹn của người bệnh."
        }, ensure_ascii=False)

    book = _load_json(APPOINTMENTS_PATH)
    record = next((a for a in book["appointments"] if a["booking_id"].upper() == booking_id), None)

    if not record:
        return json.dumps({
            "status": "NOT_FOUND",
            "message": f"Không tìm thấy phiếu hẹn có mã '{booking_id}'.",
            "hint": "Hãy gọi list_my_appointments để xem đúng mã phiếu hẹn."
        }, ensure_ascii=False)

    if record.get("state") == "CANCELLED":
        return json.dumps({
            "status": "ALREADY_CANCELLED",
            "message": f"Phiếu hẹn {booking_id} đã được hủy trước đó rồi.",
            "appointment": record
        }, ensure_ascii=False)

    # Đánh dấu hủy trong sổ lịch hẹn
    record["state"] = "CANCELLED"
    record["cancel_reason"] = reason or "Người bệnh yêu cầu hủy"
    _save_json(APPOINTMENTS_PATH, book)

    # Trả khung giờ về lịch trống của bác sĩ (giữ thứ tự thời gian cho dễ đọc)
    db = _load_json(DOCTORS_PATH)
    doctor = db["doctors"].get(record["doctor_id"])
    restored = False
    if doctor and record["date"] in doctor["available_slots"]:
        slots = doctor["available_slots"][record["date"]]
        if record["time_slot"] not in slots:
            slots.append(record["time_slot"])
            slots.sort()
            _save_json(DOCTORS_PATH, db)
            restored = True

    return json.dumps({
        "status": "SUCCESS",
        "booking_id": booking_id,
        "message": (
            f"Đã hủy phiếu hẹn {booking_id} ({record['doctor_name']}, "
            f"{record['time_slot']} ngày {record['date']})."
            + (" Khung giờ đã được trả lại cho người khác đặt." if restored else "")
        ),
        "released_slot": {
            "doctor_id": record["doctor_id"],
            "doctor_name": record["doctor_name"],
            "date": record["date"],
            "time_slot": record["time_slot"],
        } if restored else None,
    }, ensure_ascii=False)


# ==============================================================================
# 4. TOOL ROUTER & DISPATCHER
# ==============================================================================

TOOL_ROUTER = {
    "find_doctor_schedule": execute_find_doctor_schedule,
    "book_medical_appointment": execute_book_medical_appointment,
    "get_patient_history": execute_get_patient_history,
    "rank_doctors_for_patient": execute_rank_doctors_for_patient,
    "list_my_appointments": execute_list_my_appointments,
    "cancel_appointment": execute_cancel_appointment,
}


def dispatch_tool_call(tool_name: str, arguments: Dict[str, Any]) -> str:
    """Hàm trung chuyển thực thi tool"""
    if tool_name in TOOL_ROUTER:
        try:
            return TOOL_ROUTER[tool_name](**arguments)
        except Exception as e:
            return json.dumps({"status": "EXECUTION_ERROR", "error": str(e)}, ensure_ascii=False)
    return json.dumps({"status": "UNKNOWN_TOOL", "error": f"Tool '{tool_name}' không tồn tại!"}, ensure_ascii=False)
