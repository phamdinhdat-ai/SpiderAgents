# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=line-too-long
"""Compactor prompt templates for context compression."""

SYSTEM_PROMPT_EN = """\
You are a context compaction assistant. Your role is to create structured summaries of conversations
that can be used to restore context in future sessions. Focus on preserving critical information while reducing token count."""

SYSTEM_PROMPT_ZH = """\
你是一个上下文压缩助手。你的角色是创建对话的结构化摘要，
这些摘要可以在未来会话中用于恢复上下文。专注于保留关键信息，同时减少token数量。"""

SUMMARY_PROMPT_EN = """\
# Summary of previous conversation
Previous conversation logs are offloaded to dialog/YYYY-MM-DD.jsonl (or nearby date files).
Here is the summary:
{summary}
The above is a summary of previous conversation, use it as context to maintain continuity."""

SUMMARY_PROMPT_ZH = """\
# 之前对话的摘要
之前的对话日志已转储到 dialog/YYYY-MM-DD.jsonl（或相近日期的文件）。
以下是摘要：
{summary}
以上是之前对话的摘要，请将其作为上下文以保持对话的连续性。"""

INITIAL_USER_MESSAGE_EN = """\
# Task
Create a structured summary from the conversation above.

# Rules:
- Keep each section concise
- Preserve exact file paths, function names, and error messages

# Output Format:

## Goal
[What is the user trying to accomplish? Can be multiple items if the session covers different tasks.]

## Constraints & Preferences
- [Any constraints, preferences, or requirements mentioned by user]
- [Or "(none)" if none were mentioned]

## Progress
### Done
- [x] [Completed tasks/changes]

### In Progress
- [ ] [Current work]

### Blocked
- [Issues preventing progress, if any]

## Key Decisions
- **[Decision]**: [Brief rationale]

## Next Steps
1. [Ordered list of what should happen next]

## Critical Context
- [Any data, examples, or references needed to continue]
- [Or "(none)" if not applicable]

Output the structured summary following the format above."""

INITIAL_USER_MESSAGE_ZH = """\
# 任务
根据上面的对话创建一个结构化摘要。

# 规则：
- 保持每个部分简洁
- 保留确切的文件路径、函数名称和错误消息

# 输出示例：

## 目标
[用户试图完成什么？如果会话涵盖不同任务，可以有多个项目。]

## 约束和偏好
- [任何用户提到的约束、偏好或要求]
- [或者如果没有提到则为"(none)"]

## 进展
### 已完成
- [x] [已完成的任务/更改]

### 进行中
- [ ] [当前工作]

### 阻塞
- [如果有任何阻碍进展的问题]

## 关键决策
- **[决策]**: [简短理由]

## 下一步
1. [接下来应该发生的事情的有序列表]

## 关键上下文
- [任何继续工作所需的数据、示例或参考资料]
- [或者如果不适用则为"(none)"]

请按照上面示例的格式，输出结构化摘要。"""

UPDATE_USER_MESSAGE_EN = """\
# Task
Update the structured summary with new conversation messages.

# Rules:
- PRESERVE all existing information from the previous summary
- ADD new progress, decisions, and context from the new messages
- UPDATE the Progress section: move items from "In Progress" to "Done" when completed
- UPDATE "Next Steps" based on what was accomplished
- PRESERVE exact file paths, function names, and error messages
- If something is no longer relevant, you may remove it

# Output Format:

## Goal
[Preserve existing goals, add new ones if the task expanded]

## Constraints & Preferences
- [Preserve existing, add new ones discovered]

## Progress
### Done
- [x] [Include previously done items AND newly completed items]

### In Progress
- [ ] [Current work - update based on progress]

### Blocked
- [Current blockers - remove if resolved]

## Key Decisions
- **[Decision]**: [Brief rationale] (preserve all previous, add new)

## Next Steps
1. [Update based on current state]

## Critical Context
- [Preserve important context, add new if needed]

Output the structured summary following the format above."""

UPDATE_USER_MESSAGE_ZH = """\
# 任务
使用新的对话内容来更新结构化摘要。

# 规则：
- 保留来自先前摘要的所有现有信息
- 从新消息中添加新的进展、决策和上下文
- 更新进度部分：当完成时将项目从"进行中"移到"已完成"
- 根据已完成的内容更新"下一步"
- 保留确切的文件路径、函数名称和错误消息
- 如果某些内容不再相关，您可以删除它

# 输出示例：

## 目标
[保留现有目标，如果任务扩展则添加新目标]

## 约束和偏好
- [保留现有内容，添加发现的新内容]

## 进展
### 已完成
- [x] [包含以前完成的项目和新完成的项目]

### 进行中
- [ ] [当前工作 - 根据进展更新]

### 阻塞
- [当前阻塞问题 - 如果解决则删除]

## 关键决策
- **[决策]**: [简短理由]（保留所有之前的内容，添加新的）

## 下步
1. [根据当前状态更新]

## 关键上下文
- [保留重要上下文，如需要则添加新的]

请按照上面示例的格式，输出结构化摘要。"""


SYSTEM_PROMPT_VI = """\
Bạn là một trợ lý nén ngữ cảnh. Nhiệm vụ của bạn là tạo các bản tóm tắt có cấu trúc từ cuộc hội thoại,
để có thể sử dụng nhằm khôi phục ngữ cảnh trong các phiên làm việc sau.
Hãy tập trung vào việc giữ lại những thông tin quan trọng nhất trong khi giảm số lượng token.
"""

SUMMARY_PROMPT_VI = """\
# Tóm tắt cuộc hội thoại trước
Các nhật ký hội thoại trước đã được lưu vào dialog/YYYY-MM-DD.jsonl (hoặc các tệp ngày gần đó).
Dưới đây là bản tóm tắt:
{summary}

Phần trên là bản tóm tắt của cuộc hội thoại trước. Hãy sử dụng nó làm ngữ cảnh để duy trì tính liên tục của cuộc hội thoại.
"""

INITIAL_USER_MESSAGE_VI = """\
# Nhiệm vụ
Tạo một bản tóm tắt có cấu trúc từ cuộc hội thoại ở trên.

# Quy tắc
- Giữ cho mỗi phần ngắn gọn.
- Bảo toàn chính xác đường dẫn tệp, tên hàm và thông báo lỗi.

# Định dạng đầu ra

## Mục tiêu
[Người dùng đang cố gắng hoàn thành điều gì? Có thể có nhiều mục nếu phiên làm việc bao gồm nhiều nhiệm vụ.]

## Ràng buộc & Yêu cầu
- [Bất kỳ ràng buộc, sở thích hoặc yêu cầu nào do người dùng đề cập]
- [Hoặc "(không có)" nếu không có]

## Tiến độ

### Đã hoàn thành
- [x] [Các nhiệm vụ/thay đổi đã hoàn thành]

### Đang thực hiện
- [ ] [Công việc hiện tại]

### Đang bị chặn
- [Các vấn đề đang ngăn cản tiến độ, nếu có]

## Các quyết định quan trọng
- **[Quyết định]**: [Lý do ngắn gọn]

## Các bước tiếp theo
1. [Danh sách theo thứ tự những việc cần thực hiện tiếp theo]

## Ngữ cảnh quan trọng
- [Bất kỳ dữ liệu, ví dụ hoặc tài liệu tham khảo nào cần thiết để tiếp tục]
- [Hoặc "(không có)" nếu không áp dụng]

Hãy xuất bản tóm tắt có cấu trúc theo đúng định dạng trên.
"""

UPDATE_USER_MESSAGE_VI = """\
# Nhiệm vụ
Cập nhật bản tóm tắt có cấu trúc bằng các nội dung hội thoại mới.

# Quy tắc
- GIỮ NGUYÊN toàn bộ thông tin hiện có từ bản tóm tắt trước.
- THÊM các tiến độ, quyết định và ngữ cảnh mới từ các tin nhắn mới.
- CẬP NHẬT phần Tiến độ: chuyển các mục từ "Đang thực hiện" sang "Đã hoàn thành" khi đã xong.
- CẬP NHẬT mục "Các bước tiếp theo" dựa trên những gì đã hoàn thành.
- Bảo toàn chính xác đường dẫn tệp, tên hàm và thông báo lỗi.
- Nếu một thông tin không còn phù hợp, bạn có thể loại bỏ.

# Định dạng đầu ra

## Mục tiêu
[Giữ nguyên các mục tiêu hiện có và bổ sung mục tiêu mới nếu phạm vi công việc được mở rộng.]

## Ràng buộc & Yêu cầu
- [Giữ nguyên các yêu cầu hiện có và bổ sung những yêu cầu mới được phát hiện]

## Tiến độ

### Đã hoàn thành
- [x] [Bao gồm cả các mục đã hoàn thành trước đây và các mục mới hoàn thành]

### Đang thực hiện
- [ ] [Công việc hiện tại — cập nhật theo tiến độ]

### Đang bị chặn
- [Các vấn đề hiện đang cản trở tiến độ — xóa nếu đã được giải quyết]

## Các quyết định quan trọng
- **[Quyết định]**: [Lý do ngắn gọn] (giữ lại tất cả các quyết định trước đó và bổ sung các quyết định mới)

## Các bước tiếp theo
1. [Cập nhật dựa trên trạng thái hiện tại]

## Ngữ cảnh quan trọng
- [Giữ lại các thông tin quan trọng và bổ sung nếu cần]

Hãy xuất bản tóm tắt có cấu trúc theo đúng định dạng trên.
"""