"""
🔌 MODEL CONTEXT PROTOCOL (MCP) SERVER MODULE
Mô phỏng kiến trúc MCP Server (Client-Server Architecture) cung cấp công cụ chuẩn hóa.

Server công bố Tool Registry qua list_tools() và thực thi Tool qua call_tool(),
phản hồi đóng gói theo đúng khung JSON-RPC 2.0 để Agent Core (MCP Client) tiêu thụ.
"""

import json
import sys
import time
from typing import Dict, Any, List
from tools import TOOLS_SCHEMA, dispatch_tool_call

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


class MCPAcademicServer:
    """
    Giả lập MCP Server tuân thủ chuẩn giao thức Model Context Protocol.
    Đề tài: Trợ lý Tư vấn Sức khỏe Vinmec (vinmec-healthcare-mcp-server).
    """

    def __init__(self, server_name: str = "vinmec-healthcare-mcp-server"):
        self.server_name = server_name
        self.version = "2026.1.0"
        self.protocol_version = "2.0"
        self._request_seq = 0

    def list_tools(self) -> List[Dict[str, Any]]:
        """Trả về danh sách các Tools chuẩn giao thức MCP"""
        return TOOLS_SCHEMA

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        [TASK 2.1] Thực thi request gọi Tool theo chuẩn MCP JSON-RPC 2.0.

        Luồng xử lý:
          1. Chuyển yêu cầu xuống Tool Router qua dispatch_tool_call() -> nhận chuỗi JSON.
          2. Parse chuỗi JSON đó thành Python Dictionary bằng json.loads().
          3. Đóng gói phản hồi theo khung JSON-RPC 2.0 để MCP Client bóc tách.

        Trả về Dict gồm các trường bắt buộc:
            jsonrpc / server / tool / result
        kèm các trường mở rộng phục vụ observability: id, arguments, latency_ms.
        """
        self._request_seq += 1
        request_id = self._request_seq
        started_at = time.time()

        # Bước 1: Định tuyến yêu cầu xuống Execution Layer
        raw_result = dispatch_tool_call(tool_name, arguments)

        # Bước 2: Giải mã chuỗi JSON thành Dictionary
        try:
            content = json.loads(raw_result)
        except (json.JSONDecodeError, TypeError) as e:
            # Tool trả về chuỗi không hợp lệ -> phản hồi khung "error" của JSON-RPC 2.0
            return {
                "jsonrpc": self.protocol_version,
                "id": request_id,
                "server": self.server_name,
                "tool": tool_name,
                "error": {
                    "code": -32700,
                    "message": f"Parse error: Tool '{tool_name}' trả về dữ liệu không phải JSON hợp lệ ({e}).",
                    "raw": str(raw_result)
                }
            }

        elapsed_ms = round((time.time() - started_at) * 1000, 2)

        # Bước 3: Đóng gói phản hồi thành công theo chuẩn JSON-RPC 2.0
        return {
            "jsonrpc": self.protocol_version,
            "id": request_id,
            "server": self.server_name,
            "tool": tool_name,
            "arguments": arguments,
            "result": content,
            "latency_ms": elapsed_ms
        }


if __name__ == "__main__":
    print("==========================================================")
    print("🔌 KIỂM THỬ ĐỘC LẬP MCP SERVER (vinmec-healthcare-mcp-server)")
    print("==========================================================")

    server = MCPAcademicServer()
    tools = server.list_tools()
    print(f"✅ Khởi tạo thành công MCP Server: {server.server_name} (Version: {server.version})")
    print(f"📦 Số lượng Tools công bố: {len(tools)}")
    print()

    for t in tools:
        required = t.get("parameters", {}).get("required", [])
        props = list(t.get("parameters", {}).get("properties", {}).keys())
        print(f"   • {t['name']}: {len(props)} tham số | bắt buộc: {required or 'không có'}")

    # Kiểm tra trạng thái TODO 1.2 (Tool Schema của công cụ hành động)
    action_tool = next((t for t in tools if t.get("name") == "book_medical_appointment"), None)
    if action_tool and not action_tool.get("parameters", {}).get("properties"):
        print("⏳ [TODO 1.2]: Tool 'book_medical_appointment' chưa được định nghĩa properties trong 'src/tools.py'.")
    else:
        print("✅ [TODO 1.2]: Tool 'book_medical_appointment' đã có schema đầy đủ.")

    # Kiểm tra bộ nhớ dài hạn (Long-term Memory) qua MCP
    mem = server.call_tool("get_patient_history", {"patient_id": "BN2024001"})
    mem_res = mem.get("result", {})
    if mem_res.get("status") == "SUCCESS":
        print(f"🧠 [LONG-TERM MEMORY]: Truy xuất hồ sơ '{mem_res['full_name']}' "
              f"({mem_res['total_visits']} lần khám) thành công.")

    # Kiểm tra trạng thái TODO 2.1 (call_tool)
    test_result = server.call_tool("find_doctor_schedule", {"symptom": "đau dạ dày"})
    if not test_result:
        print("⏳ [TODO 2.1]: Hàm call_tool() đang trả về rỗng. Hãy hoàn thiện TODO 2.1 trong 'src/mcp_server.py'!")
    else:
        print("✅ [TODO 2.1]: Test dispatch tool 'find_doctor_schedule' thành công:")
        res = test_result.get("result", {})
        print(f"   Khung JSON-RPC: jsonrpc={test_result['jsonrpc']} | id={test_result['id']} | tool={test_result['tool']}")
        print(f"   Kết quả: {res.get('status')} | Chuyên khoa suy ra: {res.get('specialty')} | "
              f"Số bác sĩ trống lịch: {res.get('total_doctors')}")
        print(f"   Độ trễ MCP: {test_result['latency_ms']} ms")
