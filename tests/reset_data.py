"""
♻️ KHÔI PHỤC DỮ LIỆU MÔ PHỎNG VỀ TRẠNG THÁI BAN ĐẦU

Agent ghi thật xuống data/ khi đặt lịch (phiếu hẹn mới + khóa khung giờ đã đặt).
Chạy script này để đưa lịch bác sĩ và sổ phiếu hẹn về nguyên trạng trước khi
demo hoặc trước khi chạy lại test suite nghiệm thu.

    python tests/reset_data.py
"""

import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Lịch làm việc gốc của từng bác sĩ (nguồn chân lý để khôi phục)
ORIGINAL_SLOTS = {
    "BS001": {"2026-09-14": ["08:00", "09:00", "10:30", "14:00"],
              "2026-09-15": ["08:30", "09:30", "15:00"],
              "2026-09-16": ["08:00", "10:00"]},
    "BS002": {"2026-09-14": ["09:30", "15:30"],
              "2026-09-15": ["08:00", "10:00", "14:30", "16:00"],
              "2026-09-16": ["09:00", "11:00"]},
    "BS007": {"2026-09-14": [], "2026-09-15": [], "2026-09-16": ["14:00", "15:30"]},
    "BS003": {"2026-09-14": ["10:00"], "2026-09-15": ["08:00", "09:00"], "2026-09-16": []},
    "BS008": {"2026-09-14": ["08:30", "13:30", "16:00"],
              "2026-09-15": ["10:30", "14:00"],
              "2026-09-16": ["08:00", "09:30", "15:00"]},
    "BS004": {"2026-09-14": ["08:00", "09:00", "13:30", "15:00"],
              "2026-09-15": ["09:00", "14:00"],
              "2026-09-16": ["08:30", "10:30", "14:00"]},
    "BS005": {"2026-09-14": ["08:00", "08:30", "09:00", "14:00", "14:30"],
              "2026-09-15": ["08:00", "09:30", "15:00"],
              "2026-09-16": ["08:00", "10:00", "13:30"]},
    "BS009": {"2026-09-14": ["10:00", "10:30"],
              "2026-09-15": ["08:30", "11:00", "14:00"],
              "2026-09-16": ["09:00"]},
    "BS006": {"2026-09-14": [], "2026-09-15": ["10:00", "11:00", "16:00"],
              "2026-09-16": ["09:00", "15:00"]},
    "BS010": {"2026-09-14": ["09:00", "14:30"],
              "2026-09-15": ["08:00", "10:30", "15:30"],
              "2026-09-16": ["08:30", "13:00"]},
    "BS011": {"2026-09-14": ["10:00", "11:00"],
              "2026-09-15": ["09:00", "14:00", "16:00"],
              "2026-09-16": ["08:00", "10:30"]},
    "BS012": {"2026-09-14": ["08:00", "13:00"],
              "2026-09-15": ["09:30", "14:30"],
              "2026-09-16": ["08:00", "10:00", "15:00"]},
}


def main():
    doctors_path = os.path.join(DATA_DIR, "doctors.json")
    appts_path = os.path.join(DATA_DIR, "appointments.json")

    db = json.load(open(doctors_path, encoding="utf-8"))
    restored = 0
    for did, slots in ORIGINAL_SLOTS.items():
        if did in db["doctors"]:
            if db["doctors"][did]["available_slots"] != slots:
                restored += 1
            db["doctors"][did]["available_slots"] = json.loads(json.dumps(slots))

    with open(doctors_path, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

    old = json.load(open(appts_path, encoding="utf-8"))
    removed = len(old.get("appointments", []))
    with open(appts_path, "w", encoding="utf-8") as f:
        json.dump({
            "_meta": {
                "description": "So dat lich kham Vinmec - Agent ghi bo sung khi dat lich thanh cong",
                "last_booking_seq": 0,
            },
            "appointments": [],
        }, f, ensure_ascii=False, indent=2)

    total_slots = sum(len(s) for d in db["doctors"].values() for s in d["available_slots"].values())
    print("♻️  ĐÃ KHÔI PHỤC DỮ LIỆU MÔ PHỎNG")
    print(f"   • Lịch bác sĩ  : {len(ORIGINAL_SLOTS)} bác sĩ, {total_slots} khung giờ trống "
          f"({restored} bác sĩ được khôi phục)")
    print(f"   • Sổ phiếu hẹn : đã xóa {removed} phiếu hẹn, đặt lại bộ đếm về 0")
    print("   • Tiền sử bệnh nhân giữ nguyên (chỉ đọc, Agent không ghi vào).")


if __name__ == "__main__":
    main()
