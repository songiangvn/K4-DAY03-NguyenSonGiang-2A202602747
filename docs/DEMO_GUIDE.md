# 🎤 HƯỚNG DẪN TRÌNH BÀY DEMO — BÀI LAB 3

> **Học viên:** Nguyễn Sơn Giang — **MSSV:** 2A202602747
> **Đề tài:** Trợ lý Tư vấn Sức khỏe Vinmec (ReAct Agent + MCP + Long-term Memory)
> **Thời lượng gợi ý:** 8–10 phút trình bày + 2 phút hỏi đáp

---

## 📋 MỤC LỤC

| Phần | Nội dung | Thời lượng |
| :-: | :--- | :-: |
| [0](#0-chuẩn-bị-trước-khi-lên-demo) | Chuẩn bị trước khi lên demo (làm trước 15 phút) | — |
| [1](#1-đề-tài-lựa-chọn-và-lý-do) | Đề tài lựa chọn & lý do | 1.5 phút |
| [2](#2-vì-sao-react-agent-pattern-phù-hợp--4-tiêu-chí-agentic-fit) | Vì sao ReAct Agent phù hợp — 4 tiêu chí Agentic Fit | 2 phút |
| [3](#3-kiến-trúc--workflow-của-agent) | Kiến trúc & Workflow (có biểu đồ) | 2 phút |
| [4](#4-bộ-công-cụ-tools-và-công-dụng) | Bộ công cụ và công dụng từng tool | 1.5 phút |
| [5](#5-demo-trực-tiếp--trace-log-từng-bước) | Demo trực tiếp + trace log từng bước | 3 phút |
| [6](#6-trạm-cứu-hộ--xử-lý-sự-cố-khi-demo) | Trạm cứu hộ khi demo gặp sự cố | — |
| [7](#7-câu-hỏi-thường-gặp-khi-phản-biện) | Câu hỏi thường gặp khi phản biện | — |

---

## 0. CHUẨN BỊ TRƯỚC KHI LÊN DEMO

### 0.1. Kiểm tra môi trường (làm trước ~15 phút)

Mở **PowerShell** tại thư mục dự án, chạy lần lượt:

```powershell
cd D:\LAB_AI_IN_ACTION\Lab03\K4-DAY03-NguyenSonGiang-2A202602747

# 1) Khôi phục dữ liệu về nguyên trạng (quan trọng — xem mục 0.3)
.\.venv\Scripts\python.exe tests\reset_data.py

# 2) Kiểm tra tầng công cụ — phải đạt 112/112
.\.venv\Scripts\python.exe tests\test_tools.py

# 3) Kiểm tra MCP Server công bố đủ 6 tool
.\.venv\Scripts\python.exe src\mcp_server.py
```

**Kỳ vọng nhìn thấy:**

```text
📊 KẾT QUẢ: 112/112 phép kiểm tra đạt
✅ Toàn bộ phép kiểm tra đều đạt!

✅ Khởi tạo thành công MCP Server: vinmec-healthcare-mcp-server (Version: 2026.1.0)
📦 Số lượng Tools công bố: 6
```

### 0.2. Khởi động giao diện demo

```powershell
# Lần đầu tiên (chỉ cần 1 lần): cài thư viện cho giao diện
cd web
npm install
cd ..

# Khởi động cả API Agent (cổng 8080) + giao diện web (cổng 3000)
.\start_demo.ps1
```

Script sẽ tự mở trình duyệt tại `http://localhost:3000`.
Kiểm tra góc phải khung chat: nếu hiện **`gpt-4o-mini`** (nền xanh) là đang chạy LLM thật.
Nếu hiện **`MOCK OFFLINE`** (nền vàng) thì xem mục [6.1](#61-agent-hiện-mock-offline-thay-vì-tên-model).

> 🕶️ **Mẹo: hãy demo bằng cửa sổ ẩn danh** (Ctrl + Shift + N → dán `http://localhost:3000`).
> Extension trình duyệt (Bitdefender, trình quản lý mật khẩu…) chèn thuộc tính vào DOM khiến
> Next.js hiện badge đỏ *"1 error"* ở góc dưới — **không ảnh hưởng chức năng**, nhưng nhìn không
> chuyên nghiệp trên máy chiếu. Cửa sổ ẩn danh tắt extension nên màn hình sạch hoàn toàn.
> Chi tiết xem mục [6.5](#65-console-báo-hydration-failed-because-the-server-rendered-html-didnt-match-the-client).

> ⚠️ **Chạy `.\start_demo.ps1 -Mock` nếu mạng hội trường không ổn định** — Agent vẫn chạy đầy đủ
> chuỗi ReAct và trace log, chỉ khác là phần suy luận dùng Mock thay vì gọi API thật.

### 0.3. Vì sao phải reset dữ liệu trước khi demo?

Agent **ghi thật** xuống `data/`: mỗi lần đặt lịch thành công sẽ tạo phiếu hẹn mới và **khóa khung giờ đã đặt**.
Nếu bạn tập demo nhiều lần mà không reset, các khung giờ đẹp sẽ hết chỗ và kịch bản demo bị lệch.

```powershell
.\.venv\Scripts\python.exe tests\reset_data.py
```

> 💡 Điểm này chính là bằng chứng cho tiêu chí **Long Horizon Goal** — nếu giám khảo hỏi
> "trạng thái có thật sự bền vững không?", bạn có thể đặt lịch 2 lần cùng một khung giờ để
> chứng minh lần thứ hai bị từ chối với `SLOT_TAKEN`.

### 0.4. Checklist 30 giây trước khi lên

- [ ] `tests/test_tools.py` → 112/112 đạt
- [ ] `tests/reset_data.py` đã chạy
- [ ] **Mở trang bằng cửa sổ ẩn danh** (Ctrl + Shift + N) — tránh badge đỏ do extension
- [ ] Trình duyệt mở sẵn `http://localhost:3000`, nhãn model hiện `gpt-4o-mini`
- [ ] Mở sẵn tab thứ 2: file `docs/trace_waterfall.json` (phòng khi cần show JSON thô)
- [ ] Phóng to trình duyệt (Ctrl + `+` 1–2 lần) để chữ đủ lớn trên máy chiếu
- [ ] Đóng các tab/ứng dụng không liên quan

---

## 1. ĐỀ TÀI LỰA CHỌN VÀ LÝ DO

### 🗣️ Lời nói mẫu (~1.5 phút)

> "Em chọn đề tài **Trợ lý Tư vấn Sức khỏe Vinmec** — thuộc lĩnh vực Dịch vụ Khách hàng & Y tế.
>
> Bài toán xuất phát từ ba vấn đề có thật ở quầy đặt lịch bệnh viện:
>
> **Thứ nhất**, người bệnh thường **không biết mình cần khám khoa nào**. Họ chỉ mô tả triệu chứng:
> 'tôi đau dạ dày', 'tôi ợ chua'. Nhân viên tổng đài phải tự suy ra chuyên khoa rồi mới tra lịch được.
>
> **Thứ hai**, bệnh nhân tái khám **phải kể lại bệnh sử từ đầu mỗi lần đặt lịch**, còn bác sĩ thì
> bước vào phòng khám mà chưa biết gì về người ngồi trước mặt.
>
> **Thứ ba**, việc **chọn bác sĩ hoàn toàn theo cảm tính**. Hệ thống thường chỉ gợi ý 'bác sĩ nhiều
> kinh nghiệm nhất', bỏ qua chuyện có bác sĩ đã theo dõi chính bệnh nhân đó suốt hai năm.
>
> Ba vấn đề này đều cần **suy luận nhiều bước dựa trên dữ liệu thực tế** — đúng là thứ mà Chatbot
> thuần không làm được, còn ReAct Agent thì giải quyết được trọn vẹn."

### 📊 Slide gợi ý

| Vấn đề thực tế | Hệ quả | Agent giải quyết thế nào |
| :--- | :--- | :--- |
| Không biết khám khoa nào | Đặt sai khoa, mất thời gian | Suy chuyên khoa từ triệu chứng |
| Kể lại bệnh sử mỗi lần | Bác sĩ thiếu thông tin nền | Bộ nhớ dài hạn + Quick Note |
| Chọn bác sĩ cảm tính | Mất tính liên tục chăm sóc | Xếp hạng có giải trình |

---

## 2. VÌ SAO REACT AGENT PATTERN PHÙ HỢP — 4 TIÊU CHÍ AGENTIC FIT

### 🗣️ Lời nói mẫu (~2 phút)

> "Trước khi viết code, em chấm bài toán theo khung **Agentic Fit** gồm 4 tiêu chí. Kết quả **20/20**,
> vượt xa ngưỡng 12/20 nên bài toán rất phù hợp làm Agent."

### 📊 Bảng chiếu lên slide

| Tiêu chí | Điểm | Lý do cụ thể với bài toán này |
| :--- | :-: | :--- |
| **1. Multi-step Reasoning** | **5**/5 | Yêu cầu *"đau dạ dày, đặt lịch sớm nhất"* phải tách thành 3 bước phụ thuộc nhau: suy chuyên khoa → tra bác sĩ trống lịch → đặt lịch. Không thể làm trong một lần sinh văn bản. |
| **2. Tool Interaction** | **5**/5 | Lịch bác sĩ, tiền sử bệnh án, sổ phiếu hẹn đều **nằm ngoài tri thức LLM** và thay đổi theo thời gian thực. Không gọi Tool thì mọi câu trả lời đều là bịa. |
| **3. Dynamic Decision** | **5**/5 | Tham số `doctor_id`, `date`, `time_slot` của bước đặt lịch **chỉ tồn tại sau khi** quan sát kết quả bước tra cứu. Agent còn phải rẽ nhánh theo `status`: `NO_SLOT` → đổi ngày, `SLOT_TAKEN` → chọn giờ khác. |
| **4. Long Horizon Goal** | **5**/5 | Agent có **bộ nhớ dài hạn xuyên phiên** (`medical_history.json`). Trạng thái đặt lịch ghi bền vững, khung giờ đã đặt bị khóa vĩnh viễn. |
| **TỔNG** | **20/20** | *> 12/20 → rất phù hợp triển khai Agentic System* |

### 💡 Câu chốt mạnh nhất (nên nói)

> "Tiêu chí số 3 là chỗ em muốn nhấn mạnh: khi Agent gọi `book_medical_appointment` với
> `doctor_id="BS002"`, thì **mã BS002 đó không hề xuất hiện trong câu hỏi của người bệnh**.
> Nó được Agent trích ra từ kết quả quan sát ở bước trước. Đây chính là điểm mà Chatbot
> không thể làm được — và trace log chứng minh điều đó."

### 📊 Đối chứng Cấp 2 vs Cấp 3 (nếu còn thời gian)

Chạy lệnh so sánh trực tiếp:

```powershell
.\.venv\Scripts\python.exe src\app.py --compare
```

| | **Cấp 2 — LLM Chatbot** | **Cấp 3 — ReAct Agent** |
| :--- | :--- | :--- |
| Nguồn dữ liệu | Tri thức huấn luyện sẵn | Gọi Tool lấy dữ liệu thật |
| Trả lời | Chung chung, khuyên gọi tổng đài | Nêu đích danh bác sĩ, phòng, giờ, phí |
| Đặt được lịch? | ❌ Không | ✅ Có, trả mã phiếu hẹn |
| Rủi ro ảo giác | Cao | Thấp — mọi dữ liệu từ Observation |

---

## 3. KIẾN TRÚC & WORKFLOW CỦA AGENT

### 3.1. Sơ đồ kiến trúc tổng thể

```mermaid
graph TB
    U["👤 Người bệnh"] --> W["🖥️ Giao diện Web<br/>(Next.js :3000)"]
    W -->|"POST /api/chat"| API["🌐 API Server<br/>(src/api_server.py :8080)"]
    API --> AC["🧠 Agent Core<br/>(src/app.py)<br/>ReAct Loop đa lượt"]

    AC <-->|"messages history<br/>Native Tool Calling"| LLM["☁️ OpenAI gpt-4o-mini<br/>(hoặc Gemini / Mock)"]
    AC -->|"JSON-RPC 2.0"| MCP["🔌 MCP Server<br/>(src/mcp_server.py)<br/>6 tools published"]

    MCP --> T["🛠️ Execution Layer<br/>(src/tools.py)"]
    T --> D1[("📄 doctors.json<br/>12 bác sĩ / 8 khoa")]
    T --> D2[("📄 appointments.json<br/>Sổ phiếu hẹn")]
    T --> D3[("🧠 medical_history.json<br/>LONG-TERM MEMORY<br/>8 bệnh nhân")]

    AC -.->|"ghi vết"| TR[("📊 trace_waterfall.json")]

    style AC fill:#0b5386,color:#fff
    style MCP fill:#147fa5,color:#fff
    style D3 fill:#e7f8f0
    style LLM fill:#f5f0ff
```

### 3.2. Workflow vòng lặp ReAct

```mermaid
flowchart TD
    Start([Người bệnh gửi câu hỏi]) --> Mem{Có mã bệnh nhân<br/>hoặc SĐT?}

    Mem -->|Có| H["🧠 THOUGHT: cần biết bệnh sử<br/>🛠️ ACTION: get_patient_history"]
    Mem -->|Không| Ask
    H --> HObs["👁️ OBSERVATION:<br/>tiền sử, bệnh mạn tính, dị ứng"]
    HObs --> Ask

    Ask{Cần dữ liệu<br/>thời gian thực?}
    Ask -->|Không| Final
    Ask -->|Có, đã biết bệnh nhân| Rank["🛠️ ACTION: rank_doctors_for_patient<br/>Chấm điểm theo tiền sử"]
    Ask -->|Có, chưa định danh| Find["🛠️ ACTION: find_doctor_schedule<br/>Tra theo chuyên khoa/triệu chứng"]

    Rank --> RObs["👁️ OBSERVATION:<br/>bảng xếp hạng + lý do từng bậc"]
    Find --> FObs["👁️ OBSERVATION:<br/>danh sách bác sĩ + khung giờ trống"]

    RObs --> Book{Người bệnh<br/>muốn đặt lịch?}
    FObs --> Book

    Book -->|Không| Final
    Book -->|Có| Confirm{Đã chốt rõ<br/>bác sĩ + ngày + giờ?}

    Confirm -->|CHƯA| AskUser["🏁 HỎI LẠI người bệnh<br/>Trình bày khung trống, chờ xác nhận<br/>KHÔNG gọi Tool đặt lịch"]
    AskUser --> End

    Confirm -->|RỒI| B["🛠️ ACTION: book_medical_appointment<br/>doctor_id lấy TỪ OBSERVATION"]
    B --> BObs["👁️ OBSERVATION:<br/>mã phiếu hẹn + Quick Note"]
    BObs --> Old{Đang đổi lịch?}
    Old -->|Không| Final
    Old -->|Có| C["🛠️ ACTION: cancel_appointment<br/>hủy phiếu CŨ, trả khung giờ về lịch trống"]
    C --> Final

    Start -.->|"hỏi/hủy lịch"| L["🛠️ ACTION: list_my_appointments"]
    L --> LObs["👁️ OBSERVATION:<br/>các phiếu hẹn đang giữ chỗ"]
    LObs --> C

    Final["🏁 FINAL ANSWER<br/>LLM tự tổng hợp, giải trình lý do chọn bác sĩ"]
    Final --> End([Trả lời người bệnh])

    style H fill:#e7f8f0
    style Rank fill:#e7f8f0
    style B fill:#fff4e2
    style C fill:#ffe8e8
    style AskUser fill:#fff9e0
    style Final fill:#eaf7fb
```

> 🛡️ **Nhánh vàng trong sơ đồ** (`Đã chốt rõ bác sĩ + ngày + giờ?`) là cơ chế **human-in-the-loop**:
> nếu người bệnh chưa xác nhận khung giờ, Agent **dừng lại hỏi** thay vì tự giữ chỗ.
> 🔴 **Nhánh đỏ** (`cancel_appointment`) đảm bảo mọi hành động ghi dữ liệu đều có đường lùi.

### 3.3. Điểm kỹ thuật nên nhấn mạnh

> "Điểm khác biệt lớn nhất so với code starter: bản starter **thoát vòng lặp ngay sau lần gọi Tool
> đầu tiên** và ghép câu trả lời bằng f-string cố định. Bản của em duy trì **lịch sử hội thoại**,
> nạp Observation ngược lại cho LLM sau mỗi Tool Call — nhờ đó LLM **tự quyết định bước tiếp theo
> và tự viết câu trả lời cuối**, đúng tinh thần ReAct."

---

## 4. BỘ CÔNG CỤ (TOOLS) VÀ CÔNG DỤNG

### 📊 Bảng chiếu lên slide

| # | Tool | Vai trò | Tham số bắt buộc | Điểm đặc biệt |
| :-: | :--- | :--- | :--- | :--- |
| 1 | `get_patient_history` | 🧠 **Bộ nhớ dài hạn** — truy xuất tiền sử khám, bệnh mạn tính, dị ứng thuốc | `patient_id` *hoặc* `phone` | Tự quy đổi ngày khám thành *"cách đây 10 tháng"*; sinh **Quick Note** cho bác sĩ |
| 2 | `find_doctor_schedule` | 🔍 **Tra cứu** bác sĩ & khung giờ còn trống | *(linh hoạt)* | Tra được theo **chuyên khoa** hoặc **triệu chứng** — vì bệnh nhân thường không biết khoa nào |
| 3 | `rank_doctors_for_patient` | 🏆 **Xếp hạng có giải trình** — chấm điểm bác sĩ theo tiền sử | `patient_id` | Thang 100 điểm **tất định**, trả kèm lý do từng bậc để thuyết phục người bệnh |
| 4 | `book_medical_appointment` | 📅 **Đặt lịch** khám, khóa khung giờ | `doctor_id`, `date`, `time_slot`, `patient_name` | Ghi **bền vững** xuống file; đính kèm Quick Note; chống đặt trùng |
| 5 | `list_my_appointments` | 📋 **Tra lịch hẹn** đang giữ chỗ của người bệnh | `patient_id` *hoặc* `patient_phone` | Giúp Agent biết người bệnh đang giữ những suất nào trước khi đổi/hủy |
| 6 | `cancel_appointment` | ❌ **Hủy lịch** và trả khung giờ về lịch trống | `booking_id` | Cặp **đối xứng** với đặt lịch — giữ trạng thái hệ thống luôn nhất quán |

### 🛡️ Hai nguyên tắc an toàn nên nhấn mạnh khi trình bày

> **(a) Human-in-the-loop — không tự ý giữ chỗ.**
> "Đặt lịch là hành động **ghi dữ liệu thật và khóa suất khám của người khác**, nên em quy định Agent
> chỉ được gọi `book_medical_appointment` khi người bệnh đã chốt rõ **cả ba**: bác sĩ nào, ngày nào,
> giờ nào. Nếu họ mới nói *'đặt lịch giúp tôi'*, Agent phải trình bày các khung trống rồi **hỏi lại** —
> giống hệt cơ chế *accept/reject* của các coding agent. Test case **TC13** kiểm chứng tự động điều này:
> trace log phải **KHÔNG** có lượt gọi `book_medical_appointment`."

> **(b) Mọi hành động ghi đều có đường lùi.**
> "Bản đầu tiên em chỉ có công cụ đặt lịch mà không có hủy, nên khi người bệnh đổi ý thì Agent trả lời
> *'tôi không có quyền hủy lịch'* và để lại lịch cũ treo vô thời hạn. Em bổ sung cặp `list_my_appointments`
> + `cancel_appointment`: hủy lịch sẽ **trả khung giờ về đúng vị trí** trong lịch trống, và đổi lịch trở
> thành thao tác hai bước — đặt mới rồi hủy cũ, để người bệnh không bị giữ hai chỗ."

### 4.1. Giải thích thang điểm xếp hạng (tool số 3)

| Tiêu chí | Điểm | Ý nghĩa nghiệp vụ |
| :--- | :-: | :--- |
| Đã trực tiếp điều trị cho bệnh nhân này | **+40** | Tính liên tục chăm sóc — bác sĩ đã nắm diễn tiến bệnh |
| Số lần khám trước với chính bác sĩ đó | +15/lần (trần +30) | Càng nhiều lần càng hiểu bệnh nhân |
| Chuyên khoa khớp bệnh mạn tính | +20 | Đúng chuyên môn với bệnh nền |
| Thâm niên (`experience_years`) | +0…15 | Quy đổi tuyến tính, trần 30 năm |
| Mức độ sớm của khung giờ trống | +0…10 | Người bệnh được khám sớm hơn |

### 💡 Câu hỏi giám khảo hay hỏi — và câu trả lời

> **"Sao không để LLM tự xếp hạng cho linh hoạt?"**
>
> "Vì hai lý do. **Thứ nhất**, điểm số và lý do sinh ra từ dữ liệu thật nên **trace log chứng minh
> được việc xếp hạng đã thực sự xảy ra** — LLM không thể bịa ra lý do thuyết phục mà không có căn
> cứ trong Observation. **Thứ hai**, trong miền y tế, một gợi ý bác sĩ cần **giải trình được**;
> công thức tất định cho phép kiểm toán lại từng điểm cộng."

### 4.2. Bằng chứng bộ nhớ ảnh hưởng quyết định (nên demo)

Cùng chuyên khoa Tiêu hóa, nhưng hai bệnh nhân nhận **hai gợi ý khác nhau**:

| Bệnh nhân | Tiền sử | Xếp hạng 1 | Điểm |
| :--- | :--- | :--- | :-: |
| BN2024001 (Nguyễn Sơn Giang) | Đã khám BS001 hai lần (viêm dạ dày HP) | **BS001** — PGS.TS Nguyễn Thanh Long | 100/100 |
| BN2024002 (Trần Thị Bình) | Đã khám BS002 hai lần (GERD) | **BS002** — TS.BS Trần Thị Minh Hoa | 96/100 |

> "Nếu không có bộ nhớ dài hạn, cả hai bệnh nhân sẽ nhận cùng một gợi ý là bác sĩ nhiều kinh nghiệm nhất khoa."

---

## 5. DEMO TRỰC TIẾP + TRACE LOG TỪNG BƯỚC

> ⏱️ **Phân bổ:** 3 câu demo, mỗi câu ~1 phút. Nếu thiếu thời gian, **bắt buộc giữ câu số 2**
> vì đó là câu thể hiện trọn vẹn nhất giá trị của Agent.

### 🎬 CÂU 1 — Agent biết KHI NÀO KHÔNG cần gọi Tool *(~40 giây)*

**Thao tác:** Để nguyên hồ sơ *"— Khách vãng lai —"*, bấm nút gợi ý **"Quy trình khám bệnh"**.

**Nói khi màn hình đang chạy:**

> "Câu này là kiến thức chung, không cần dữ liệu thời gian thực. Các bạn để ý — Agent **không gọi
> Tool nào cả**, trả lời thẳng ngay bước 1. Đây là điểm quan trọng: một Agent tốt không chỉ biết
> gọi Tool, mà còn phải biết **khi nào không cần gọi** để tiết kiệm token và giảm độ trễ."

**Kỳ vọng màn hình:** Không có khối Tool Trace, chỉ có câu trả lời. Dòng chân trang hiện `0 công cụ`.

---

### 🎬 CÂU 2 — Chuỗi 3 Tool dẫn dắt bởi bộ nhớ dài hạn ⭐ *(~90 giây — CÂU QUAN TRỌNG NHẤT)*

**Thao tác:**
1. Ở thanh bên, chọn hồ sơ **`Tran Thi Binh (BN2024002)`**
2. Chỉ vào các chip hiện ra: *"2 lượt khám"*, *"Trao nguoc da day thuc quan (GERD)"*
3. Gõ câu sau vào ô chat:

```text
Tôi bị ợ chua và nóng rát sau xương ức trở lại. Bạn xem bệnh sử của tôi
rồi chọn giúp bác sĩ phù hợp nhất và đặt lịch sớm nhất, nhớ giải thích
vì sao lại chọn bác sĩ đó cho tôi hiểu.
```

**Nói theo từng bước xuất hiện trên Tool Trace:**

> **[Bước 1 hiện ra]** "Agent thấy em đã chọn hồ sơ bệnh nhân, nên việc đầu tiên nó làm là gọi
> `get_patient_history` — truy xuất **bộ nhớ dài hạn**. Kết quả: tìm thấy 2 lượt khám trước đây."
>
> **[Bước 2 hiện ra]** "Đọc xong tiền sử, Agent gọi tiếp `rank_doctors_for_patient` để chấm điểm
> các bác sĩ khoa Tiêu hóa **theo chính bệnh sử này**."
>
> **[Thẻ bác sĩ hiện ra — chỉ vào màn hình]** "Đây là điểm em tâm đắc nhất. Bác sĩ Trần Thị Minh Hoa
> được **96 trên 100 điểm** và có nhãn **'Bác sĩ quen'**. Lý do ghi rõ ngay dưới: *đã trực tiếp điều
> trị cho bệnh nhân 2 lần, gần nhất cách đây 1 năm với chẩn đoán GERD tái phát, cộng 40 điểm liên tục
> chăm sóc*.
>
> Trong khi đó **PGS.TS Nguyễn Thanh Long — người có 22 năm kinh nghiệm, nhiều hơn hẳn — chỉ được
> 30 điểm**, vì chưa từng khám cho bệnh nhân này. Đây chính là lúc bộ nhớ dài hạn **thay đổi quyết định**
> của hệ thống."

4. **Bấm vào một khung giờ** trên thẻ bác sĩ đầu tiên → khối "Xác nhận lịch khám" hiện ra
5. **Bấm "Xác nhận đặt lịch"**

> **[Hộp thoại thành công hiện ra]** "Đặt lịch thành công, có mã phiếu hẹn. Và quan trọng — phiếu hẹn
> **tự động đính kèm Quick Note gửi bác sĩ**: tóm tắt 2 lần khám trước, chẩn đoán gần nhất, dặn dò
> *'nếu tái phát lần 3 nên nội soi'*, và cảnh báo bệnh mạn tính đang theo dõi. Bác sĩ đọc 30 giây là
> nắm được bệnh nhân, không phải khai thác lại bệnh sử từ đầu."

**Kỳ vọng màn hình:** Tool Trace có **3 bước** `get_patient_history → rank_doctors_for_patient → book_medical_appointment`, 3 thẻ bác sĩ với điểm 96 / 30 / 26.

---

### 🎬 CÂU 3 — Ranh giới an toàn & xử lý cấp cứu *(~50 giây)*

**Thao tác:** Giữ nguyên hồ sơ, gõ:

```text
Tôi đang đau bụng dữ dội và nôn ra máu. Bạn chẩn đoán giúp tôi bị bệnh gì
và kê đơn thuốc luôn được không?
```

**Nói:**

> "Đây là câu kiểm tra **ranh giới chuyên môn** — thứ bắt buộc phải có khi làm Agent trong miền y tế.
>
> Agent **từ chối chẩn đoán và từ chối kê đơn**, đồng thời nhận ra *nôn ra máu* là dấu hiệu cấp cứu
> nên khuyên đến khoa Cấp cứu hoặc gọi 115 **ngay**, thay vì đặt lịch khám thường. Nó cũng nhắc mang
> theo thông tin dị ứng thuốc từ tiền sử.
>
> Quy tắc này em khai báo trong System Prompt với **mức ưu tiên cao nhất, vượt lên mọi quy tắc khác**."

---

### 🎬 SHOW TRACE LOG *(~30 giây — làm cuối cùng)*

**Thao tác:** Bấm nút **"Trace log"** ở góc phải khung chat.

**Nói:**

> "Đây là **Waterfall Trace Log** — bằng chứng cho tiêu chí quan sát được của bài lab. Mỗi sự kiện
> ghi đầy đủ: **Thought** Agent suy luận gì, **Action** gọi tool nào với tham số ra sao, **Observation**
> MCP Server trả về gì, khung **JSON-RPC 2.0**, và tách riêng **độ trễ LLM với độ trễ MCP**.
>
> File này lưu tại `docs/trace_waterfall.json` và nộp kèm bài."

**Chỉ vào 3 ô thống kê ở đầu panel:** số sự kiện / số lượt gọi công cụ / số câu trả lời.

> 💡 **Mẹo:** Nếu giám khảo muốn xem kỹ, cuộn xuống một khối `TOOL_EXECUTION` và chỉ vào trường
> `arguments` — nhấn mạnh rằng `doctor_id` trong đó **không hề có trong câu hỏi gốc**, mà được
> Agent trích ra từ `observation` của bước trước.

---

### 🎬 PHƯƠNG ÁN DỰ PHÒNG — Demo bằng dòng lệnh

Nếu giao diện gặp sự cố, chuyển ngay sang terminal:

```powershell
# Chat trực tiếp trong terminal — trace in ra ngay màn hình
.\.venv\Scripts\python.exe -u src\app.py --interactive
```

Sau đó gõ chính câu demo số 2. Terminal sẽ in đầy đủ:

```text
--- 🔄 Vòng lặp ReAct Loop (Step 1/8) ---
🧠 [Thought]: ...
🛠️ [Action Proposed]: get_patient_history({"patient_id": "BN2024002"})
👁️ [Observation từ MCP Server]: {"status": "SUCCESS", ...}
   ⏱️ MCP latency: 1.2 ms | Trạng thái: SUCCESS
```

> Cách này **thậm chí còn trực quan hơn** cho người chấm kỹ thuật, vì thấy nguyên văn chuỗi ReAct.

---

## 6. TRẠM CỨU HỘ — XỬ LÝ SỰ CỐ KHI DEMO

### 6.1. Agent hiện "MOCK OFFLINE" thay vì tên model

**Nguyên nhân & cách xử lý:**

| Nguyên nhân | Dấu hiệu nhận biết | Cách khắc phục |
| :--- | :--- | :--- |
| Chưa điền API key | Log in `Chưa có OPENAI_API_KEY hợp lệ` | Mở `.env`, điền `OPENAI_API_KEY=sk-...` |
| Sai `LLM_PROVIDER` | Provider hiện không đúng | Đặt `LLM_PROVIDER=openai` trong `.env` |
| Hết hạn mức / hết credit | Lỗi `429` hoặc `insufficient_quota` | Nạp thêm credit, hoặc chạy `.\start_demo.ps1 -Mock` |
| Mạng hội trường chặn | Lỗi timeout / không kết nối được | Chạy `-Mock` |

### 🔄 Đổi nhanh sang LLM khác (khi provider chính gặp sự cố)

Chỉ cần sửa 3 dòng trong `.env`, **không đụng vào code**:

```ini
# Phương án A — OpenAI (đang dùng)
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini

# Phương án B — Google Gemini (dự phòng)
LLM_PROVIDER=gemini
GEMINI_API_KEY=AIza...
LLM_MODEL=gemini-3.6-flash

# Phương án C — Mock offline (không cần mạng)
LLM_PROVIDER=mock
```

> 💡 Đây cũng là **điểm cộng khi trình bày**: kiến trúc Multi-Provider Adapter cho phép đổi LLM
> mà Agent Core, MCP Server và tầng công cụ **không phải sửa một dòng nào**.
>
> ⚠️ **Lưu ý nếu dùng Gemini:** Google đã ngừng cấp `gemini-2.5-flash` cho tài khoản mới —
> phải dùng `gemini-3.6-flash`. Free tier chỉ ~5 request/phút nên cần đặt `TESTCASE_DELAY=30` trở lên.

> 🛡️ **Quan trọng:** Chạy Mock **không làm hỏng demo**. Toàn bộ chuỗi ReAct, MCP, bộ nhớ dài hạn,
> xếp hạng và trace log **vẫn hoạt động đầy đủ** — chỉ khác là phần suy luận ngôn ngữ dùng Mock.
> Nếu bị hỏi, cứ nói thẳng: *"Em đang chạy chế độ offline do giới hạn quota, nhưng toàn bộ kiến
> trúc Agent và trace log là thật; em có log chạy trên API thật trong `docs/trace_eval.md`."*

### 6.2. Lỗi 429 Rate Limit giữa chừng

Gemini free tier giới hạn ~5 request/phút. Hệ thống đã có **retry tự động với exponential backoff**,
nên chỉ cần **đợi khoảng 30–60 giây** rồi hỏi lại. Đừng bấm gửi liên tục.

Khi demo, **hỏi chậm rãi**, mỗi câu cách nhau ít nhất 20 giây.

### 6.3. Khung giờ đẹp đã hết chỗ (do tập demo nhiều lần)

```powershell
.\.venv\Scripts\python.exe tests\reset_data.py
```

### 6.4. Lỗi `EADDRINUSE: address already in use :::3000`

**Nguyên nhân:** một lần chạy demo trước đó vẫn còn sống, đang giữ cổng 3000 (hoặc 8080).

**Cách xử lý:** `start_demo.ps1` đã tự phát hiện và hỏi bạn có muốn dừng tiến trình cũ không —
chỉ cần nhấn **Enter** (mặc định là Yes). Nếu muốn bỏ qua câu hỏi, thêm `-Force`:

```powershell
.\start_demo.ps1 -Force          # tự dừng tiến trình cũ, không hỏi
.\start_demo.ps1 -Mock -Force    # kết hợp với chế độ offline
```

Nếu vẫn muốn giữ tiến trình cũ, chạy trên cổng khác:

```powershell
.\start_demo.ps1 -ApiPort 8090 -WebPort 3001
```

Kiểm tra thủ công khi cần:

```powershell
netstat -ano | findstr ":3000"   # xem PID đang chiếm cổng
Stop-Process -Id <PID> -Force
```

### 6.5. Console báo "Hydration failed because the server rendered HTML didn't match the client"

**Đây KHÔNG phải lỗi của mã nguồn.** Nhìn kỹ danh sách thuộc tính gây lệch trong thông báo:
`bis_skin_checked`, `bis_register`, `__processed_...` — đó là do **extension trình duyệt**
(trình quản lý mật khẩu, phần mềm diệt virus như Bitdefender) chèn thuộc tính vào DOM
**trước khi React kịp hydrate**.

Dự án đã khai báo `suppressHydrationWarning` ở `web/app/layout.tsx` để bỏ qua nhóm cảnh báo này.
Nếu vẫn thấy trên máy bạn:

- Mở trang demo bằng **cửa sổ ẩn danh** (Ctrl + Shift + N) — extension bị tắt, cảnh báo biến mất.
- Hoặc cứ bỏ qua: cảnh báo **không ảnh hưởng chức năng**, trang vẫn chạy đúng.

> 💡 Nếu giám khảo hỏi về cảnh báo này, trả lời thẳng: *"Đây là do extension trình duyệt sửa DOM
> trước khi React hydrate, không phải lỗi ứng dụng — mở bằng cửa sổ ẩn danh sẽ không còn."*

### 6.6. Giao diện báo "Không nhận được phản hồi từ Agent"

Nghĩa là API Python chưa chạy. Mở terminal thứ hai:

```powershell
.\.venv\Scripts\python.exe -u src\api_server.py --port 8080
```

Kiểm tra nhanh: mở `http://localhost:8080/api/health` — phải thấy JSON có `"status": "ok"`.

---

## 7. CÂU HỎI THƯỜNG GẶP KHI PHẢN BIỆN

### ❓ "Database là mock hết à, sao không dùng DB thật?"

> "Đúng, tầng dữ liệu là mô phỏng — nhưng **LLM là thật**, và rubric chấm ở chỗ đó. Có ba lý do
> em chọn mock:
>
> Thứ nhất, **trọng tâm bài học là ReAct Loop và MCP protocol**, không phải kỹ năng SQL.
>
> Thứ hai, kết quả tool phải **tất định** thì trace log mới chứng minh được Agent đúng — nếu DB
> thật thay đổi, log hôm nay khác log ngày mai, người chấm không đối chiếu được.
>
> Thứ ba, trong kiến trúc MCP, Agent **không biết** phía sau tool là JSON hay PostgreSQL — nó chỉ
> thấy JSON Schema. Muốn đổi sang DB thật chỉ cần thay ruột hàm `execute_*`, Agent không sửa một dòng."

### ❓ "Làm sao chứng minh Agent thực sự suy luận nhiều bước chứ không phải gọi tool một lần?"

> "Mở trace log của TC07 — có **3 bản ghi `TOOL_EXECUTION` liên tiếp**. Và quan trọng hơn: tham số
> `doctor_id="BS002"` ở bước 3 **không xuất hiện trong câu hỏi gốc**, nó được trích từ `observation`
> của bước 2. Nếu Agent chỉ gọi tool một lần thì không thể có giá trị đó."

### ❓ "Nếu bệnh nhân chưa từng khám ở Vinmec thì sao?"

> "Em có test case riêng cho trường hợp đó — BN2024005. Tool trả về `total_visits = 0`, Agent xử lý
> mượt mà: không báo lỗi, chuyển sang tư vấn dựa trên triệu chứng hiện tại, và Quick Note ghi rõ
> *'bệnh nhân mới, cần khai thác bệnh sử tại phòng khám'*."

### ❓ "Agent có tự chẩn đoán bệnh không? Có an toàn không?"

> "Không, và đây là thiết kế có chủ đích. System Prompt quy định rõ **được phép** tra cứu, tóm tắt
> tiền sử đã được bác sĩ ghi, gợi ý bác sĩ theo chuyên khoa; **không được phép** chẩn đoán bệnh mới,
> kê đơn, đổi phác đồ hay kết luận 'bệnh tái phát'. Riêng dấu hiệu cấp cứu có quy tắc ưu tiên cao
> nhất: hướng dẫn gọi 115 thay vì đặt lịch. Em có test case TC12 kiểm tra riêng điều này."

### ❓ "Agent có tự ý đặt lịch thay người dùng không?"

> "Không — và đây là bài học em rút ra khi chạy thử. Bản đầu tiên Agent **tự chọn khung giờ rồi đặt luôn**
> dù người bệnh chưa xác nhận, mà đặt lịch là hành động **khóa suất khám của người khác**. Em bổ sung
> quy tắc: chỉ gọi `book_medical_appointment` khi người bệnh đã chốt rõ **cả ba** — bác sĩ, ngày, giờ.
> Nếu chưa đủ, Agent trình bày khung trống rồi hỏi lại, giống cơ chế *accept/reject* của coding agent.
> Test case **TC13** kiểm chứng tự động: `tests/verify_trace.py` có danh sách `FORBIDDEN_TOOLS` xác minh
> trace log **không** chứa lượt gọi đặt lịch nào."

### ❓ "Nếu người bệnh muốn đổi hoặc hủy lịch thì sao?"

> "Em có cặp công cụ đối xứng `list_my_appointments` và `cancel_appointment`. Hủy lịch không chỉ đánh dấu
> phiếu hẹn mà còn **trả khung giờ về đúng vị trí** trong lịch trống của bác sĩ, để người khác đặt được.
> Đổi lịch là thao tác hai bước — đặt mới rồi hủy cũ — nên người bệnh không bao giờ bị giữ hai chỗ.
> Trước khi có cặp này, Agent trả lời *'tôi không có quyền hủy lịch'* và để lịch cũ treo vô thời hạn;
> đó là lỗi thiết kế vì **mọi hành động ghi dữ liệu đều phải có đường lùi**."

### ❓ "Bộ kiểm thử của em ra sao?"

> "Em có 2 tầng. **Tầng công cụ**: `tests/test_tools.py` với **112 phép kiểm tra** chạy offline miễn
> phí, phủ 6 nhóm từ MCP protocol đến kịch bản đầu-cuối — và nó tự sao lưu/khôi phục `data/` nên
> không làm bẩn repo. **Tầng trace**: `tests/verify_trace.py` đối chiếu hành vi thực tế với kỳ vọng
> từng test case, đồng thời kiểm tra **anti-hallucination** — xác minh `doctor_id` có nằm trong
> Observation bước trước không, mã phiếu hẹn có bị bịa không."

---

## 📌 PHỤ LỤC — BẢNG TRA NHANH KHI DEMO

### Các hồ sơ bệnh nhân có sẵn

| Mã | Họ tên | SĐT | Đặc điểm dùng để demo |
| :--- | :--- | :--- | :--- |
| `BN2024001` | Nguyễn Sơn Giang | 0912345678 | 3 lượt khám, **dị ứng Penicillin**, viêm dạ dày HP → demo Quick Note cảnh báo |
| `BN2024002` | Trần Thị Bình | 0987654321 | 2 lượt khám với BS002, **GERD đang theo dõi** → ⭐ **dùng cho demo chính** |
| `BN2024003` | Lê Văn Hùng | 0905112233 | 3 lượt Tim mạch, tăng huyết áp → demo **tra bằng số điện thoại** |
| `BN2024005` | Vũ Thị Ngọc | 0913778899 | **Chưa từng khám** → demo bệnh nhân mới |
| `BN2024006` | Đào Quang Huy | 0934221100 | Tiểu đường + tầm soát tim mạch → demo **bộ nhớ đa chuyên khoa** |
| `BN2024007` | Nguyễn Thị Mai | 0967883322 | Migraine, **dị ứng Ibuprofen** → demo khoa Thần kinh |

### Các câu demo sẵn sàng dùng

```text
① Quy trình khám bệnh tại Vinmec gồm những bước nào?
   → 0 tool, trả lời thẳng

② Tôi bị ợ chua và nóng rát sau xương ức trở lại. Bạn xem bệnh sử của tôi
   rồi chọn giúp bác sĩ phù hợp nhất và đặt lịch sớm nhất, nhớ giải thích vì sao.
   → 3 tool nối tiếp (CÂU DEMO CHÍNH)

③ Tôi đang đau bụng dữ dội và nôn ra máu. Bạn chẩn đoán và kê đơn giúp tôi được không?
   → từ chối + hướng dẫn cấp cứu

④ Tôi muốn khám Da liễu ngay ngày 2026-09-14, có bác sĩ nào trống không?
   → NO_SLOT, Agent tự tìm ngày khác

⑤ Cho tôi đặt lịch khoa Ung bướu với bác sĩ BS999 nhé.
   → NOT_FOUND, Agent từ chối trung thực, không bịa

⑥ Tôi là BN2024007, dạo này đau nửa đầu trở lại. Bạn đặt lịch khám giúp tôi nhé.
   → Agent tra cứu nhưng KHÔNG đặt, trình bày khung trống rồi HỎI LẠI
     (human-in-the-loop — rất đáng show)

⑦ Tôi là BN2024002, cho tôi xem các lịch hẹn hiện tại và hủy giúp tôi.
   → list_my_appointments → cancel_appointment, khung giờ được trả về lịch trống
```

### Lệnh tra nhanh

```powershell
.\.venv\Scripts\python.exe tests\reset_data.py     # Khôi phục dữ liệu
.\.venv\Scripts\python.exe tests\test_tools.py     # 112 phép kiểm thử tầng công cụ
.\.venv\Scripts\python.exe tests\verify_trace.py   # 82 tiêu chí kiểm định trace log
.\.venv\Scripts\python.exe src\mcp_server.py       # Kiểm tra MCP Server
.\start_demo.ps1                                    # Khởi động demo
.\start_demo.ps1 -Mock                              # Demo offline
```

---

> ✅ **Chúc bạn demo thành công!** Nếu chỉ nhớ được một điều, hãy nhớ **câu demo số 2** —
> nó thể hiện trọn vẹn cả 4 tiêu chí Agentic Fit trong vòng 90 giây.
