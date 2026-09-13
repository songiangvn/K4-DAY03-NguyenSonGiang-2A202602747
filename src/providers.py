"""
🔌 MULTI-PROVIDER LLM ADAPTER (Google Gemini, OpenAI & Offline Mock)
Hỗ trợ Native Tool Calling đa lượt (multi-turn) và chuyển đổi linh hoạt qua biến môi trường LLM_PROVIDER.

ĐIỂM NÂNG CẤP SO VỚI BẢN STARTER:
    Bản starter chỉ gửi đúng một câu prompt cho LLM mỗi vòng lặp, nên LLM không hề
    "nhìn thấy" kết quả Observation của vòng trước -> không thể suy luận nhiều bước.
    Bản này truyền cả LỊCH SỬ HỘI THOẠI (conversation history) gồm các lượt
    user / tool_call / tool_result, nhờ đó Agent thực hiện được chuỗi ReAct thật sự:
        Thought -> Action -> Observation -> Thought -> Action -> ... -> Final Answer
"""

import os
import re
import sys
import json
import time
from typing import Dict, Any, List
from dotenv import load_dotenv

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

load_dotenv()


# Số lần thử lại tối đa khi nhà cung cấp trả lỗi giới hạn tốc độ (HTTP 429)
MAX_RETRY_ON_RATE_LIMIT = int(os.getenv("LLM_MAX_RETRY", "4"))


def _is_rate_limit_error(err: Exception) -> bool:
    """Nhận diện lỗi vượt hạn mức gọi API (429 / RESOURCE_EXHAUSTED / quota)"""
    msg = str(err).lower()
    return "429" in msg or "resource_exhausted" in msg or "quota" in msg or "rate limit" in msg


def _retry_delay_seconds(err: Exception, attempt: int) -> float:
    """
    Xác định thời gian chờ trước khi thử lại.
    Ưu tiên giá trị retryDelay do chính API đề nghị; nếu không có thì dùng
    exponential backoff (8s, 16s, 32s...) để chắc chắn vượt qua cửa sổ giới hạn/phút.
    """
    m = re.search(r"retry in (\d+(?:\.\d+)?)s", str(err), re.IGNORECASE)
    if not m:
        m = re.search(r"'retryDelay':\s*'(\d+(?:\.\d+)?)s'", str(err))
    if m:
        return float(m.group(1)) + 2.0          # cộng biên an toàn
    return min(8.0 * (2 ** attempt), 64.0)      # backoff lũy thừa, trần 64s


# Bản đồ từ khóa → triệu chứng chuẩn, dùng cho MockOfflineProvider suy ra chuyên khoa.
# Thứ tự có ý nghĩa: mục đứng trước được ưu tiên khi câu hỏi chứa nhiều từ khóa
# (ví dụ "nóng rát sau xương ức" là tiêu hóa, không phải cơ xương khớp).
_SYMPTOM_KEYWORDS = [
    ("đau dạ dày", ["dạ dày", "da day", "tiêu hóa", "trào ngược", "ợ chua",
                    "đầy hơi", "thượng vị", "xương ức", "buồn nôn"]),
    ("đau ngực", ["đau ngực", "tim mạch", "huyết áp", "hồi hộp", "đánh trống ngực", "khó thở"]),
    ("đau lưng", ["đau lưng", "đau khớp", "cột sống", "vai gáy", "xương khớp"]),
    ("nổi mẩn ngứa", ["mẩn", "ngứa", "da liễu", "viêm da", "mụn", "rụng tóc"]),
    ("đau đầu", ["đau đầu", "đau nửa đầu", "migraine", "mất ngủ", "chóng mặt"]),
    ("đau họng", ["đau họng", "viêm xoang", "nghẹt mũi", "ù tai", "tai mũi họng"]),
    ("tiểu đường", ["tiểu đường", "đái tháo đường", "tuyến giáp", "nội tiết", "khát nước"]),
    ("sốt cao trẻ em", ["trẻ", "bé nhà", "con tôi", "nhi khoa", "biếng ăn"]),
]


def _guess_symptom(question_lower: str) -> str:
    """Suy ra triệu chứng chuẩn từ câu hỏi (chỉ dùng cho Mock offline)"""
    for symptom, keywords in _SYMPTOM_KEYWORDS:
        if any(k in question_lower for k in keywords):
            return symptom
    return ""


def _extract_name(question: str) -> str:
    """
    Trích họ tên người bệnh từ câu hỏi tự nhiên (chỉ dùng cho Mock offline).
    Bắt các mẫu thường gặp: 'tôi tên X', 'tên tôi là X', 'tôi là X'.
    """
    patterns = [
        r"t[ôo]i t[êe]n(?:\s+l[àa])?\s+([A-ZÀ-Ỹ][\wÀ-ỹ]*(?:\s+[A-ZÀ-Ỹ][\wÀ-ỹ]*){1,3})",
        r"t[êe]n t[ôo]i l[àa]\s+([A-ZÀ-Ỹ][\wÀ-ỹ]*(?:\s+[A-ZÀ-Ỹ][\wÀ-ỹ]*){1,3})",
        r"t[ôo]i l[àa]\s+([A-ZÀ-Ỹ][\wÀ-ỹ]*(?:\s+[A-ZÀ-Ỹ][\wÀ-ỹ]*){1,3})",
    ]
    for pat in patterns:
        m = re.search(pat, question)
        if m:
            return m.group(1).strip()
    return "Bệnh nhân chưa định danh"


class BaseLLMProvider:
    """Interface cơ sở cho các LLM Provider hỗ trợ Native Tool Calling"""

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        raise NotImplementedError

    def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools_schema: List[Dict[str, Any]],
        system_prompt: str = ""
    ) -> Dict[str, Any]:
        """
        Nhận vào LỊCH SỬ HỘI THOẠI thay vì một chuỗi prompt đơn lẻ.

        Mỗi phần tử của `messages` có dạng:
            {"role": "user",        "content": "<câu hỏi người dùng>"}
            {"role": "tool_call",   "tool_name": "...", "arguments": {...}}
            {"role": "tool_result", "tool_name": "...", "content": {...}}

        Trả về một trong hai dạng:
            {"type": "tool_call", "tool_name": ..., "arguments": {...}, "thought": ...}
            {"type": "text",      "content": "...",                     "thought": ...}
        """
        raise NotImplementedError


# ==============================================================================
# MOCK OFFLINE PROVIDER — mô phỏng suy luận đa bước để gỡ lỗi miễn phí
# ==============================================================================

class MockOfflineProvider(BaseLLMProvider):
    """
    Offline Mock Provider dùng để chạy thử mà không tốn API Key.
    Mock này CÓ ĐỌC lịch sử hội thoại, nên vẫn tái hiện được chuỗi ReAct đa bước:
    tra cứu bác sĩ trước, rồi mới đặt lịch dựa trên doctor_id vừa quan sát được.
    """

    def __init__(self):
        self.model_name = "Offline-Mock-Model-2026"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        return (
            f"[Mock Chatbot Response]: Xin chào! Tôi đã nhận được câu hỏi '{prompt}'. "
            "(Chế độ Chatbot không có Tool tra cứu dữ liệu thời gian thực)."
        )

    def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools_schema: List[Dict[str, Any]],
        system_prompt: str = ""
    ) -> Dict[str, Any]:
        # Câu hỏi gốc của người dùng luôn nằm ở lượt đầu tiên
        user_query = next((m["content"] for m in messages if m["role"] == "user"), "")
        q = user_query.lower()

        # Thu thập các Observation đã nhận được từ MCP Server ở những vòng trước
        observations = [m for m in messages if m["role"] == "tool_result"]
        called_tools = [m["tool_name"] for m in messages if m["role"] == "tool_call"]

        want_booking = any(k in q for k in ["đặt lịch", "dat lich", "đặt luôn", "đăng ký khám", "book"])

        # --- Ưu tiên tuyệt đối: phát hiện dấu hiệu cấp cứu thì dừng mọi quy trình đặt lịch ---
        emergency_signs = [
            "nôn ra máu", "non ra mau", "phân đen", "phan den", "xuất huyết", "xuat huyet",
            "đau ngực dữ dội", "khó thở nặng", "co giật", "co giat", "ngất", "liệt",
            "đau bụng dữ dội", "dau bung du doi"
        ]
        if any(s in q for s in emergency_signs):
            return {
                "type": "text",
                "content": (
                    "[Mock Agent] ⚠️ Những dấu hiệu bạn mô tả có thể là tình huống cấp cứu. "
                    "Bạn hãy đến khoa Cấp cứu gần nhất hoặc gọi 115 NGAY, không nên chờ đặt lịch khám thường. "
                    "Khi đến viện, nhớ báo cho nhân viên y tế về tiền sử bệnh và các thuốc bạn bị dị ứng. "
                    "Tôi không thể chẩn đoán bệnh hay kê đơn thuốc — việc đó cần bác sĩ trực tiếp thăm khám."
                ),
                "thought": (
                    "Người bệnh mô tả dấu hiệu nguy hiểm. Theo quy tắc an toàn, tôi phải hướng dẫn cấp cứu "
                    "ngay thay vì đặt lịch khám thường, và từ chối yêu cầu chẩn đoán/kê đơn."
                )
            }

        # Mã bệnh nhân người dùng cung cấp (nếu có) — chìa khóa vào bộ nhớ dài hạn
        bn_match = re.search(r"\b(BN\d{6,})\b", user_query, re.IGNORECASE)
        patient_id = bn_match.group(1).upper() if bn_match else ""

        # Không có mã bệnh nhân nhưng có số điện thoại -> vẫn định danh được.
        # Bỏ khoảng trắng/dấu chấm trong số trước khi khớp ("0905 112 233" -> "0905112233").
        phone_match = re.search(r"0[\d\s.\-]{8,14}\d", user_query)
        phone = re.sub(r"\D", "", phone_match.group(0)) if phone_match else ""
        if len(phone) != 10:
            phone = ""

        # --- Vòng 1 ưu tiên: định danh được bệnh nhân thì tra tiền sử trước mọi thứ khác ---
        if (patient_id or phone) and "get_patient_history" not in called_tools:
            args = {"patient_id": patient_id} if patient_id else {"phone": phone}
            return {
                "type": "tool_call",
                "tool_name": "get_patient_history",
                "arguments": args,
                "thought": (
                    f"Người bệnh cung cấp {'mã bệnh nhân ' + patient_id if patient_id else 'số điện thoại ' + phone}. "
                    "Tôi tra tiền sử khám bệnh trước để tư vấn dựa trên bệnh sử thay vì chỉ dựa vào triệu chứng hiện tại."
                )
            }

        # Nếu tra bằng số điện thoại thành công thì lấy lại mã bệnh nhân từ Observation
        if not patient_id:
            hist_obs = next((m["content"] for m in observations
                             if m["tool_name"] == "get_patient_history"), {})
            if hist_obs.get("status") == "SUCCESS":
                patient_id = hist_obs.get("patient_id", "")

        # --- Không tìm thấy hồ sơ -> coi như bệnh nhân mới, chuyển sang tra lịch thường ---
        if ("get_patient_history" in called_tools
                and "find_doctor_schedule" not in called_tools
                and "rank_doctors_for_patient" not in called_tools):
            hist_obs = next((m["content"] for m in observations
                             if m["tool_name"] == "get_patient_history"), {})
            if hist_obs.get("status") != "SUCCESS":
                symptom = _guess_symptom(q)
                return {
                    "type": "tool_call",
                    "tool_name": "find_doctor_schedule",
                    "arguments": {"symptom": symptom} if symptom else {},
                    "thought": (
                        "Không tìm thấy hồ sơ tiền sử — xem như bệnh nhân khám lần đầu. "
                        "Tôi chuyển sang tra lịch bác sĩ dựa trên triệu chứng hiện tại."
                    )
                }

        # --- Đã có tiền sử -> xếp hạng bác sĩ phù hợp nhất với bệnh nhân này ---
        if (patient_id
                and "get_patient_history" in called_tools
                and "rank_doctors_for_patient" not in called_tools
                and "book_medical_appointment" not in called_tools):
            args = {"patient_id": patient_id}
            symptom = _guess_symptom(q)
            if symptom:
                args["symptom"] = symptom
            else:
                # Không rõ triệu chứng -> suy từ chuyên khoa đã khám gần nhất trong tiền sử
                hist = next((m["content"] for m in observations
                             if m["tool_name"] == "get_patient_history"), {})
                visits = hist.get("visit_history") or []
                args["specialty"] = visits[0]["specialty"] if visits else "Tiêu hóa"
            return {
                "type": "tool_call",
                "tool_name": "rank_doctors_for_patient",
                "arguments": args,
                "thought": (
                    "Đã nắm được tiền sử bệnh nhân. Tôi xếp hạng các bác sĩ đang trống lịch "
                    "theo mức độ phù hợp với bệnh sử này để đề xuất lựa chọn tốt nhất."
                )
            }

        # --- Đã xếp hạng -> đặt lịch với bác sĩ đứng đầu ---
        if (want_booking
                and "rank_doctors_for_patient" in called_tools
                and "book_medical_appointment" not in called_tools):
            ranked = next((m["content"] for m in observations
                           if m["tool_name"] == "rank_doctors_for_patient"), {})
            if ranked.get("status") == "SUCCESS" and ranked.get("ranked_doctors"):
                top = ranked["ranked_doctors"][0]
                return {
                    "type": "tool_call",
                    "tool_name": "book_medical_appointment",
                    "arguments": {
                        "patient_id": ranked["patient_id"],
                        "doctor_id": top["doctor_id"],
                        "date": top["earliest_slot"]["date"],
                        "time_slot": top["earliest_slot"]["time"],
                        "patient_name": ranked["patient_name"],
                        "symptom_note": user_query
                    },
                    "thought": (
                        f"{top['full_name']} đứng đầu bảng xếp hạng với {top['match_score']}/100 điểm. "
                        "Tôi đặt lịch với bác sĩ này vào khung giờ trống sớm nhất."
                    )
                }

        # --- Vòng 1: chưa có Observation nào ---
        if not observations:
            # Câu hỏi kiến thức chung (quy trình, thủ tục, bảo hiểm...) -> trả lời thẳng, không gọi Tool
            general_keywords = ["quy trình", "quy trinh", "thủ tục", "bảo hiểm", "giờ làm việc", "địa chỉ"]
            needs_data = any(k in q for k in [
                "bác sĩ", "bac si", "lịch", "lich", "khám", "kham", "trống", "trong",
                "đặt", "dat", "khoa", "đau", "dau", "bs0", "bs9"
            ])
            if any(k in q for k in general_keywords) and not want_booking:
                return {
                    "type": "text",
                    "content": (
                        "[Mock Agent] Quy trình khám bệnh tại Vinmec gồm các bước cơ bản: "
                        "(1) Đăng ký và lấy số thứ tự tại quầy lễ tân; (2) Khám lâm sàng với bác sĩ chuyên khoa; "
                        "(3) Thực hiện cận lâm sàng nếu được chỉ định; (4) Bác sĩ kết luận và kê đơn; "
                        "(5) Thanh toán và nhận thuốc tại nhà thuốc bệnh viện."
                    ),
                    "thought": "Đây là câu hỏi kiến thức chung về quy trình, tôi trả lời trực tiếp mà không cần gọi Tool."
                }

            # Người bệnh đã cung cấp sẵn mã bác sĩ cụ thể -> đặt lịch thẳng, không cần tra cứu
            if want_booking:
                m = re.search(r"\bbs\s*0*(\d{1,3})\b", q)
                d_match = re.search(r"(\d{4}-\d{2}-\d{2})", user_query)
                t_match = re.search(r"\b(\d{1,2}:\d{2})\b", user_query)
                if m and d_match and t_match:
                    return {
                        "type": "tool_call",
                        "tool_name": "book_medical_appointment",
                        "arguments": {
                            "doctor_id": f"BS{int(m.group(1)):03d}",
                            "date": d_match.group(1),
                            "time_slot": t_match.group(1),
                            "patient_name": "Nguyễn Sơn Giang",
                            "patient_phone": "0912345678",
                            "symptom_note": user_query
                        },
                        "thought": (
                            "Người bệnh đã chỉ định rõ mã bác sĩ, ngày và giờ khám, "
                            "tôi gọi thẳng book_medical_appointment để giữ chỗ."
                        )
                    }

            if "ung bướu" in q or "ung buou" in q:
                args = {"specialty": "Ung bướu"}
            else:
                symptom = _guess_symptom(q)
                args = {"symptom": symptom} if symptom else {}
                # Người bệnh nêu rõ ngày mong muốn thì tra đúng ngày đó trước
                d = re.search(r"(\d{4}-\d{2}-\d{2})", user_query)
                if d and args:
                    args["date"] = d.group(1)

            return {
                "type": "tool_call",
                "tool_name": "find_doctor_schedule",
                "arguments": args,
                "thought": (
                    "Người bệnh mô tả nhu cầu khám nhưng tôi chưa có dữ liệu bác sĩ. "
                    "Tôi cần gọi find_doctor_schedule để biết chuyên khoa phù hợp và khung giờ còn trống."
                )
            }

        last_obs = observations[-1]["content"]
        last_tool = observations[-1]["tool_name"]

        # --- Hết chỗ trong ngày yêu cầu: chủ động tra lại không giới hạn ngày ---
        if last_obs.get("status") == "NO_SLOT" and last_tool in (
                "find_doctor_schedule", "rank_doctors_for_patient"):
            prev_args = next((m["arguments"] for m in reversed(messages)
                              if m["role"] == "tool_call" and m["tool_name"] == last_tool), {})
            if prev_args.get("date"):
                retry_args = {k: v for k, v in prev_args.items() if k != "date"}
                return {
                    "type": "tool_call",
                    "tool_name": last_tool,
                    "arguments": retry_args,
                    "thought": (
                        f"Ngày {prev_args['date']} đã kín lịch. Tôi tra lại bỏ giới hạn ngày "
                        "để tìm khung giờ trống gần nhất đề xuất cho người bệnh."
                    )
                }

        # --- Vòng 2: đã tra cứu xong, nếu người bệnh muốn đặt lịch thì tiến hành đặt ---
        if (want_booking
                and "book_medical_appointment" not in called_tools
                and last_obs.get("status") == "SUCCESS"
                and last_obs.get("doctors")):

            # Ưu tiên bác sĩ nhiều kinh nghiệm nhất trong danh sách quan sát được
            doctor = max(last_obs["doctors"], key=lambda d: d.get("experience_years", 0))
            # Chọn ngày & khung giờ trống sớm nhất từ kết quả quan sát được
            chosen_date, chosen_slot = "", ""
            for d, slots in sorted(doctor["available_slots"].items()):
                if slots:
                    chosen_date, chosen_slot = d, slots[0]
                    break

            # Lấy danh tính từ hồ sơ đã tra được; nếu chưa có thì trích tên từ chính câu hỏi
            hist_obs = next((m["content"] for m in observations
                             if m["tool_name"] == "get_patient_history"), {})
            booking_args = {
                "doctor_id": doctor["doctor_id"],
                "date": chosen_date,
                "time_slot": chosen_slot,
                "patient_name": hist_obs.get("full_name") or _extract_name(user_query),
                "symptom_note": user_query
            }
            if hist_obs.get("patient_id"):
                booking_args["patient_id"] = hist_obs["patient_id"]
            if phone:
                booking_args["patient_phone"] = phone

            return {
                "type": "tool_call",
                "tool_name": "book_medical_appointment",
                "arguments": booking_args,
                "thought": (
                    f"Quan sát cho thấy {doctor['full_name']} ({doctor['specialty']}) còn trống "
                    f"{chosen_slot} ngày {chosen_date}. Tôi sẽ gọi book_medical_appointment để giữ chỗ."
                )
            }

        # --- Vòng cuối: tổng hợp Final Answer từ toàn bộ Observation ---
        if last_obs.get("status") == "SUCCESS" and last_obs.get("booking_id"):
            ap = last_obs["appointment"]
            content = (
                f"Đã đặt lịch khám thành công. Mã phiếu hẹn: {last_obs['booking_id']}. "
                f"Bác sĩ {ap['doctor_name']} - {ap['specialty']}, {ap['time_slot']} ngày {ap['date']}, "
                f"tại {ap['room']}. Phí khám: {ap['consultation_fee_vnd']:,} VNĐ."
            )
            qn = ap.get("doctor_quick_note", {})
            if qn.get("bullets"):
                content += (
                    "\n\nBác sĩ đã được gửi kèm bản tóm tắt bệnh sử của bạn:\n"
                    + "\n".join(f"  • {b}" for b in qn["bullets"])
                )
                if qn.get("alerts"):
                    content += "\n" + "\n".join(f"  {a}" for a in qn["alerts"])

        elif last_obs.get("status") == "SUCCESS" and last_obs.get("ranked_doctors"):
            top = last_obs["ranked_doctors"][0]
            lines = [f"{last_obs['recommendation']}", "", "Lý do đề xuất:"]
            lines += [f"  • {r}" for r in top["ranking_reasons"]]
            if len(last_obs["ranked_doctors"]) > 1:
                lines.append("\nCác lựa chọn khác:")
                for d in last_obs["ranked_doctors"][1:]:
                    lines.append(
                        f"  • {d['full_name']} ({d['match_score']}/100 điểm) — "
                        f"trống sớm nhất {d['earliest_slot']['time']} ngày {d['earliest_slot']['date']}"
                    )
            content = "\n".join(lines)

        elif last_obs.get("status") == "SUCCESS" and "visit_history" in last_obs:
            qn = last_obs["quick_note"]
            lines = [qn["headline"], ""] + [f"  • {b}" for b in qn["bullets"]]
            if qn.get("alerts"):
                lines += [""] + [f"  {a}" for a in qn["alerts"]]
            content = "\n".join(lines)
        elif last_obs.get("status") == "SUCCESS" and last_obs.get("doctors"):
            lines = []
            for d in last_obs["doctors"]:
                free = "; ".join(f"{k}: {', '.join(v)}" for k, v in d["available_slots"].items() if v)
                lines.append(f"- {d['full_name']} ({d['title']}), {d['room']}, phí {d['consultation_fee_vnd']:,} VNĐ. Lịch trống: {free}")
            content = (
                f"Với triệu chứng của bạn, chuyên khoa phù hợp là {last_obs['specialty']}. "
                f"Hiện có {last_obs['total_doctors']} bác sĩ còn lịch trống:\n" + "\n".join(lines)
            )
        else:
            content = last_obs.get("message", "Rất tiếc, hệ thống chưa tìm được thông tin phù hợp.")

        return {
            "type": "text",
            "content": f"[Mock Agent] {content}",
            "thought": "Đã có đủ dữ liệu quan sát từ MCP Server, tôi tổng hợp câu trả lời cuối cùng cho người bệnh."
        }


# ==============================================================================
# GOOGLE GEMINI PROVIDER
# ==============================================================================

class GeminiProvider(BaseLLMProvider):
    """Google Gemini Provider (Native Tool Calling đa lượt với Google GenAI SDK)"""

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "gemini-2.5-flash"

    def _has_key(self) -> bool:
        return bool(self.api_key) and self.api_key != "your_gemini_api_key_here"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self._has_key():
            return "[Gemini Error]: Chưa cấu hình GEMINI_API_KEY trong file .env! Đang sử dụng chế độ Mock."
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)
            config = types.GenerateContentConfig(
                system_instruction=system_prompt if system_prompt else None
            )
            response = client.models.generate_content(
                model=self.model_name, contents=prompt, config=config
            )
            return response.text or ""
        except Exception as e:
            return f"[Gemini Exception]: {str(e)}"

    def _build_contents(self, messages: List[Dict[str, Any]], types) -> List[Any]:
        """Chuyển lịch sử hội thoại nội bộ sang định dạng `contents` của Gemini SDK"""
        contents = []
        for m in messages:
            role = m["role"]

            if role == "user":
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part(text=m["content"])]
                ))

            elif role == "assistant":
                # Câu trả lời Agent đã gửi ở lượt chat trước (bộ nhớ ngắn hạn)
                contents.append(types.Content(
                    role="model",
                    parts=[types.Part(text=m["content"])]
                ))

            elif role == "tool_call":
                # Lượt model đề xuất gọi hàm
                contents.append(types.Content(
                    role="model",
                    parts=[types.Part(function_call=types.FunctionCall(
                        name=m["tool_name"],
                        args=m["arguments"]
                    ))]
                ))

            elif role == "tool_result":
                # Lượt trả kết quả Observation về cho model
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part(function_response=types.FunctionResponse(
                        name=m["tool_name"],
                        response={"result": m["content"]}
                    ))]
                ))

        return contents

    def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools_schema: List[Dict[str, Any]],
        system_prompt: str = ""
    ) -> Dict[str, Any]:
        if not self._has_key():
            print("ℹ️ [Gemini Provider]: Chưa tìm thấy GEMINI_API_KEY hợp lệ. Tự động chuyển sang Mock Offline.")
            return MockOfflineProvider().generate_with_tools(messages, tools_schema, system_prompt)

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)

            # Chuẩn hóa function declarations cho Gemini SDK
            function_declarations = []
            for tool in tools_schema:
                if not tool.get("name") or not tool.get("parameters"):
                    continue
                function_declarations.append({
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {})
                })

            config = types.GenerateContentConfig(
                system_instruction=system_prompt if system_prompt else None,
                tools=[{"function_declarations": function_declarations}] if function_declarations else None,
                temperature=0.2
            )

            contents = self._build_contents(messages, types)

            # Gọi API kèm cơ chế thử lại khi vượt hạn mức (free tier giới hạn ~5 request/phút)
            response = None
            last_error = None
            for attempt in range(MAX_RETRY_ON_RATE_LIMIT):
                try:
                    response = client.models.generate_content(
                        model=self.model_name, contents=contents, config=config
                    )
                    break
                except Exception as api_err:
                    last_error = api_err
                    if not _is_rate_limit_error(api_err) or attempt == MAX_RETRY_ON_RATE_LIMIT - 1:
                        raise
                    wait_s = _retry_delay_seconds(api_err, attempt)
                    print(f"⏳ [Rate Limit]: Gemini giới hạn tốc độ, chờ {wait_s:.0f}s rồi thử lại "
                          f"(lần {attempt + 1}/{MAX_RETRY_ON_RATE_LIMIT - 1})...")
                    time.sleep(wait_s)

            if response is None:
                raise last_error if last_error else RuntimeError("Không nhận được phản hồi từ Gemini.")

            # Gemini có đề xuất gọi Tool không?
            if response.function_calls:
                call = response.function_calls[0]
                args = dict(call.args) if getattr(call, "args", None) else {}

                # Gemini có thể kèm cả phần suy luận dạng text trước khi gọi hàm
                reasoning = ""
                try:
                    for part in response.candidates[0].content.parts:
                        if getattr(part, "text", None):
                            reasoning += part.text.strip() + " "
                except Exception:
                    pass

                return {
                    "type": "tool_call",
                    "tool_name": call.name,
                    "arguments": args,
                    "thought": reasoning.strip() or (
                        f"Cần dữ liệu thực tế để trả lời chính xác, tôi gọi công cụ '{call.name}' "
                        f"với tham số: {json.dumps(args, ensure_ascii=False)}"
                    )
                }

            return {
                "type": "text",
                "content": response.text or "",
                "thought": "Đã có đủ thông tin cần thiết, tôi tổng hợp câu trả lời cuối cùng cho người bệnh."
            }

        except Exception as e:
            print(f"⚠️ [Gemini API Warning]: Không thể kết nối live API ({str(e)}). Tự động fallback về Mock.")
            return MockOfflineProvider().generate_with_tools(messages, tools_schema, system_prompt)


# ==============================================================================
# OPENAI PROVIDER
# ==============================================================================

class OpenAIProvider(BaseLLMProvider):
    """OpenAI Provider (Native Tool Calling đa lượt với OpenAI SDK)"""

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "gpt-4o-mini"

    def _has_key(self) -> bool:
        return bool(self.api_key) and self.api_key != "your_openai_api_key_here"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self._has_key():
            return "[OpenAI Error]: Chưa cấu hình OPENAI_API_KEY trong file .env! Đang sử dụng chế độ Mock."
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            msgs = []
            if system_prompt:
                msgs.append({"role": "system", "content": system_prompt})
            msgs.append({"role": "user", "content": prompt})
            response = client.chat.completions.create(model=self.model_name, messages=msgs)
            return response.choices[0].message.content or ""
        except Exception as e:
            return f"[OpenAI Exception]: {str(e)}"

    def _build_messages(self, messages: List[Dict[str, Any]], system_prompt: str) -> List[Dict[str, Any]]:
        """Chuyển lịch sử hội thoại nội bộ sang định dạng messages của OpenAI Chat Completions"""
        out = []
        if system_prompt:
            out.append({"role": "system", "content": system_prompt})

        for idx, m in enumerate(messages):
            role = m["role"]

            if role == "user":
                out.append({"role": "user", "content": m["content"]})

            elif role == "assistant":
                # Câu trả lời Agent đã gửi ở lượt chat trước (bộ nhớ ngắn hạn)
                out.append({"role": "assistant", "content": m["content"]})

            elif role == "tool_call":
                call_id = m.get("call_id") or f"call_{idx}"
                out.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": m["tool_name"],
                            "arguments": json.dumps(m["arguments"], ensure_ascii=False)
                        }
                    }]
                })

            elif role == "tool_result":
                call_id = m.get("call_id") or f"call_{idx - 1}"
                out.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps(m["content"], ensure_ascii=False)
                })

        return out

    def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools_schema: List[Dict[str, Any]],
        system_prompt: str = ""
    ) -> Dict[str, Any]:
        if not self._has_key():
            print("ℹ️ [OpenAI Provider]: Chưa tìm thấy OPENAI_API_KEY hợp lệ. Tự động chuyển sang Mock Offline.")
            return MockOfflineProvider().generate_with_tools(messages, tools_schema, system_prompt)

        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)

            tools = []
            for tool in tools_schema:
                if not tool.get("name"):
                    continue
                tools.append({
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {})
                    }
                })

            payload = self._build_messages(messages, system_prompt)

            # Gọi API kèm cơ chế thử lại khi vượt hạn mức
            response = None
            last_error = None
            for attempt in range(MAX_RETRY_ON_RATE_LIMIT):
                try:
                    response = client.chat.completions.create(
                        model=self.model_name,
                        messages=payload,
                        tools=tools if tools else None,
                        tool_choice="auto" if tools else None,
                        temperature=0.2
                    )
                    break
                except Exception as api_err:
                    last_error = api_err
                    if not _is_rate_limit_error(api_err) or attempt == MAX_RETRY_ON_RATE_LIMIT - 1:
                        raise
                    wait_s = _retry_delay_seconds(api_err, attempt)
                    print(f"⏳ [Rate Limit]: OpenAI giới hạn tốc độ, chờ {wait_s:.0f}s rồi thử lại "
                          f"(lần {attempt + 1}/{MAX_RETRY_ON_RATE_LIMIT - 1})...")
                    time.sleep(wait_s)

            if response is None:
                raise last_error if last_error else RuntimeError("Không nhận được phản hồi từ OpenAI.")

            msg = response.choices[0].message
            if msg.tool_calls:
                call = msg.tool_calls[0]
                args = json.loads(call.function.arguments) if call.function.arguments else {}
                return {
                    "type": "tool_call",
                    "tool_name": call.function.name,
                    "arguments": args,
                    "call_id": call.id,
                    "thought": (msg.content or "").strip() or (
                        f"Cần dữ liệu thực tế để trả lời chính xác, tôi gọi công cụ '{call.function.name}' "
                        f"với tham số: {json.dumps(args, ensure_ascii=False)}"
                    )
                }

            return {
                "type": "text",
                "content": msg.content or "",
                "thought": "Đã có đủ thông tin cần thiết, tôi tổng hợp câu trả lời cuối cùng cho người bệnh."
            }

        except Exception as e:
            print(f"⚠️ [OpenAI API Warning]: Không thể kết nối live API ({str(e)}). Tự động fallback về Mock.")
            return MockOfflineProvider().generate_with_tools(messages, tools_schema, system_prompt)


# ==============================================================================
# FACTORY
# ==============================================================================

def get_llm_provider() -> BaseLLMProvider:
    """Factory function khởi tạo Provider theo biến môi trường LLM_PROVIDER"""
    provider_type = os.getenv("LLM_PROVIDER", "gemini").lower()

    if provider_type == "gemini":
        key = os.getenv("GEMINI_API_KEY")
        if key and key != "your_gemini_api_key_here":
            return GeminiProvider()
        print("ℹ️ [Factory]: Chưa có GEMINI_API_KEY hợp lệ -> dùng MockOfflineProvider (miễn phí).")
        return MockOfflineProvider()

    if provider_type == "openai":
        key = os.getenv("OPENAI_API_KEY")
        if key and key != "your_openai_api_key_here":
            return OpenAIProvider()
        print("ℹ️ [Factory]: Chưa có OPENAI_API_KEY hợp lệ -> dùng MockOfflineProvider (miễn phí).")
        return MockOfflineProvider()

    return MockOfflineProvider()
