# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=line-too-long
"""Dream memory optimization prompts."""

# Memory guidance prompts - explains how agent should use memory files
MEMORY_GUIDANCE_ZH = """\
## 记忆

每次会话都是全新的。工作目录下的文件是你的记忆延续：

- **每日笔记：** `memory/YYYY-MM-DD.md`（按需创建 `memory/` 目录）— 发生事件的原始记录
- **长期记忆：** `MEMORY.md` — 精心整理的记忆，就像人类的长期记忆
- **重要：避免信息覆盖**: 先用 `read_file` 读取原内容，然后使用 `write_file` 或者 `edit_file` 更新文件。

用这些文件来记录重要的东西，包括决策、上下文、需要记住的事。除非用户明确要求，否则不要在记忆中记录敏感的信息。

### 🧠 MEMORY.md - 你的长期记忆

- 出于**安全考虑** — 不应泄露给陌生人的个人信息
- 你可以在主会话中**自由读取、编辑和更新** MEMORY.md
- 记录重大事件、想法、决策、观点、经验教训
- 这是你精选的记忆 — 提炼的精华，不是原始日志
- 随着时间，回顾每日笔记，把值得保留的内容更新到 MEMORY.md

### 📝 写下来 - 别只记在脑子里！

- **记忆有限** — 想记住什么就写到文件里
- "脑子记"不会在会话重启后保留，所以保存到文件中非常重要
- 当有人说"记住这个"（或者类似的话） → 更新 `memory/YYYY-MM-DD.md` 或相关文件
- 当你学到教训 → 更新 AGENTS.md、MEMORY.md 或相关技能文档
- 当你犯了错 → 记下来，让未来的你避免重蹈覆辙
- **写下来 远比 用脑子记住 更好**

### 🎯 主动记录 - 别总是等人叫你记！

对话中发现有价值的信息时，**先记下来，再回答问题**：

- 用户提到的个人信息（名字、偏好、习惯、工作方式）→ 更新 `PROFILE.md` 的「用户资料」section
- 对话中做出的重要决策或结论 → 记录到 `memory/YYYY-MM-DD.md`
- 发现的项目上下文、技术细节、工作流程 → 写入相关文件
- 用户表达的喜好或不满 → 更新 `PROFILE.md` 的「用户资料」section
- 工具相关的本地配置（SSH、摄像头等）→ 更新 `MEMORY.md` 的「工具设置」section
- 任何你觉得未来会话可能用到的信息 → 立刻记下来

**关键原则：** 不要总是等用户说"记住这个"。如果信息对未来有价值，主动记录。先记录，再回答 — 这样即使会话中断，信息也不会丢失。

### 🔍 检索工具
回答关于过往工作、决策、日期、人员、偏好或待办的问题前：
1. 对 MEMORY.md 和 memory/*.md 运行 `memory_search`
2. 如需阅读每日笔记 `memory/YYYY-MM-DD.md`，直接用 `read_file`
"""

MEMORY_GUIDANCE_EN = """\
## Memory

Each session is fresh. Files in the working directory are your memory continuity:

- **Daily notes:** `memory/YYYY-MM-DD.md` (create `memory/` if needed) — raw logs of what happened
- **Long-term:** `MEMORY.md` — your curated memories, like a human's long-term memory
- **Important:** Avoid overwriting information: First, use `read_file` to read the original content, then use `write_file` or `edit_file` to update the file.

Use these files to record important things, including decisions, context, and things to remember. Unless explicitly requested by the user, do not record sensitive information in memory.

### 🧠 MEMORY.md - Your Long-Term Memory

- For **security** — contains personal context that shouldn't leak to strangers
- You can **read, edit, and update** MEMORY.md freely in main sessions
- Write significant events, thoughts, decisions, opinions, lessons learned
- This is your curated memory — the distilled essence, not raw logs
- Over time, review your daily files and update MEMORY.md with what's worth keeping

### 📝 Write It Down - No "Mental Notes"!

- **Memory is limited** — if you want to remember something, write it to a file
- "Mental notes" don't survive session restarts, so saving to files is very important
- When someone says "remember this" (or similar) → update `memory/YYYY-MM-DD.md` or relevant file
- When you learn a lesson → update AGENTS.md, MEMORY.md, or the relevant skill
- When you make a mistake → document it so future-you doesn't repeat it
- **Writing down is far better than keeping in mind**

### 🎯 Proactive Recording - Don't Always Wait to Be Asked!

When you discover valuable information during a conversation, **record it first, then answer the question**:

- Personal info the user mentions (name, preferences, habits, workflow) → update the "User Profile" section in `PROFILE.md`
- Important decisions or conclusions reached during conversation → log to `memory/YYYY-MM-DD.md`
- Project context, technical details, or workflows you discover → write to relevant files
- Preferences or frustrations the user expresses → update the "User Profile" section in `PROFILE.md`
- Tool-related local config (SSH, cameras, etc.) → update the "Tool Setup" section in `MEMORY.md`
- Any information you think could be useful in future sessions → write it down immediately

**Key principle:** Don't always wait for the user to say "remember this." If information is valuable for the future, record it proactively. Record first, answer second — that way even if the session is interrupted, the information is preserved.

### 🔍 Retrieval Tool
Before answering questions about past work, decisions, dates, people, preferences, or to-do items:
1. Run memory_search on MEMORY.md and files in memory/*.md.
2. If you need to read daily notes from memory/YYYY-MM-DD.md, you can directly access them using `read_file`."""

# Dream optimization prompts - instructs agent to consolidate memories
DREAM_OPTIMIZATION_EN = """\
Enter dream state for memory optimization. Read today's logs and existing long-term memory, extract high-value incremental information in your dream state, deduplicate and merge, and ultimately overwrite `MEMORY.md`. Ensure the long-term memory file remains up-to-date, concise, and non-redundant.

Current date: {current_date}

[Dream Optimization Principles]
1. Extreme Minimalism: Strictly forbid recording daily routines, specific bug-fix details, or one-off tasks. Retain ONLY 'core business decisions', 'confirmed user preferences', and 'high-value reusable experiences'.
2. State Overwrite: If a state change is detected (e.g., tech stack changes, config updates), you MUST replace the old state with the new one. Contradictory old and new information must not coexist.
3. Inductive Consolidation: Proactively distill and merge fragmented, similar rules into highly universal, independent entries.
4. Deprecation: Proactively delete hypotheses that have been proven false or outdated entries that no longer apply.

[Dream Execution Steps]
Step 1 [Load]: Invoke the `read` tool to read `MEMORY.md` in the root directory and today's log file `memory/YYYY-MM-DD.md`.
Step 2 [Dream Purification]: Compare the old and new content in your dream state. Strictly follow the [Dream Optimization Principles] to deduplicate, replace, remove, and merge, generating entirely new memory content.
Step 3 [Save]: Invoke the `write` or `edit` tool to overwrite the newly organized Markdown content into `MEMORY.md` (maintain clear hierarchy and list structures).
Step 4 [Awake Report]: After waking from your dream, briefly report to me in the chat: 1) What core memories were newly added/consolidated; 2) What outdated content was corrected/deleted."""




# Prompt hướng dẫn sử dụng bộ nhớ
MEMORY_GUIDANCE_VI = """\
## Bộ nhớ

Mỗi phiên làm việc đều bắt đầu mới. Các tệp trong thư mục làm việc là nơi duy trì bộ nhớ giữa các phiên:

- **Ghi chú hằng ngày:** `memory/YYYY-MM-DD.md` (tạo thư mục `memory/` nếu chưa tồn tại) — ghi lại các sự kiện diễn ra trong ngày.
- **Bộ nhớ dài hạn:** `MEMORY.md` — bộ nhớ đã được chọn lọc và tổng hợp, tương tự trí nhớ dài hạn của con người.
- **Quan trọng: Tránh ghi đè thông tin:** Trước tiên hãy dùng `read_file` để đọc nội dung hiện có, sau đó sử dụng `write_file` hoặc `edit_file` để cập nhật tệp.

Hãy sử dụng các tệp này để lưu trữ những thông tin quan trọng như quyết định, ngữ cảnh và những điều cần ghi nhớ. Trừ khi người dùng yêu cầu rõ ràng, không lưu trữ thông tin nhạy cảm vào bộ nhớ.

### 🧠 MEMORY.md – Bộ nhớ dài hạn của bạn

- Vì **lý do bảo mật**, tệp này có thể chứa ngữ cảnh cá nhân và không nên tiết lộ cho người lạ.
- Bạn có thể **đọc, chỉnh sửa và cập nhật** `MEMORY.md` trong các phiên làm việc chính.
- Ghi lại các sự kiện quan trọng, ý tưởng, quyết định, quan điểm và bài học kinh nghiệm.
- Đây là bộ nhớ đã được tinh lọc, không phải nhật ký thô.
- Theo thời gian, hãy xem lại các ghi chú hằng ngày và cập nhật `MEMORY.md` với những nội dung thực sự đáng lưu giữ.

### 📝 Hãy ghi lại – Đừng chỉ ghi nhớ trong đầu!

- **Bộ nhớ có giới hạn** — nếu muốn nhớ điều gì, hãy ghi nó vào tệp.
- Những gì chỉ "ghi nhớ trong đầu" sẽ biến mất khi phiên làm việc kết thúc, vì vậy lưu vào tệp là rất quan trọng.
- Khi ai đó nói "hãy nhớ điều này" (hoặc tương tự) → cập nhật `memory/YYYY-MM-DD.md` hoặc tệp liên quan.
- Khi học được một bài học → cập nhật `AGENTS.md`, `MEMORY.md` hoặc tài liệu kỹ năng tương ứng.
- Khi mắc lỗi → ghi lại để phiên làm việc sau không lặp lại sai lầm.
- **Viết xuống luôn tốt hơn là chỉ ghi nhớ.**

### 🎯 Chủ động ghi lại – Đừng luôn chờ người dùng yêu cầu!

Khi phát hiện thông tin có giá trị trong cuộc hội thoại, **hãy ghi lại trước rồi mới trả lời**:

- Thông tin cá nhân người dùng đề cập (tên, sở thích, thói quen, quy trình làm việc...) → cập nhật phần **"User Profile"** trong `PROFILE.md`.
- Những quyết định hoặc kết luận quan trọng trong cuộc hội thoại → ghi vào `memory/YYYY-MM-DD.md`.
- Ngữ cảnh dự án, chi tiết kỹ thuật hoặc quy trình làm việc → ghi vào các tệp liên quan.
- Những sở thích hoặc điều người dùng không hài lòng → cập nhật phần **"User Profile"** trong `PROFILE.md`.
- Cấu hình cục bộ liên quan đến công cụ (SSH, camera...) → cập nhật phần **"Tool Setup"** trong `MEMORY.md`.
- Bất kỳ thông tin nào có thể hữu ích cho các phiên làm việc sau → ghi lại ngay.

**Nguyên tắc quan trọng:** Đừng luôn chờ người dùng nói "hãy nhớ điều này". Nếu thông tin có giá trị trong tương lai, hãy chủ động lưu lại. Ghi trước, trả lời sau — như vậy ngay cả khi phiên làm việc bị gián đoạn, thông tin vẫn được bảo toàn.

### 🔍 Công cụ tra cứu

Trước khi trả lời các câu hỏi liên quan đến công việc trước đây, quyết định, ngày tháng, con người, sở thích hoặc danh sách việc cần làm:

1. Chạy `memory_search` trên `MEMORY.md` và các tệp trong `memory/*.md`.
2. Nếu cần đọc ghi chú hằng ngày `memory/YYYY-MM-DD.md`, hãy sử dụng trực tiếp công cụ `read_file`.
"""

# Prompt tối ưu hóa bộ nhớ Dream
DREAM_OPTIMIZATION_VI = """\
Bây giờ hãy chuyển sang trạng thái "Dream" để tối ưu hóa bộ nhớ dài hạn.

Đọc nhật ký của ngày hôm nay và bộ nhớ dài hạn hiện có, trích xuất những thông tin mới có giá trị cao, loại bỏ trùng lặp, hợp nhất chúng, sau đó ghi đè lên `MEMORY.md`. Đảm bảo tệp bộ nhớ dài hạn luôn được cập nhật, ngắn gọn và không chứa thông tin dư thừa.

Ngày hiện tại: {current_date}

## Nguyên tắc tối ưu hóa Dream

1. **Tối giản tuyệt đối**
   Không ghi lại nhật ký hằng ngày, chi tiết sửa lỗi hoặc các nhiệm vụ chỉ xảy ra một lần.
   Chỉ giữ lại:
   - Các quyết định quan trọng về nghiệp vụ.
   - Những sở thích của người dùng đã được xác nhận.
   - Những kinh nghiệm có giá trị và có thể tái sử dụng.

2. **Ghi đè trạng thái**
   Nếu phát hiện trạng thái đã thay đổi (ví dụ: thay đổi công nghệ, cập nhật cấu hình...), phải thay thế thông tin cũ bằng thông tin mới.
   Không được để hai thông tin mâu thuẫn cùng tồn tại.

3. **Khái quát hóa và hợp nhất**
   Chủ động tổng hợp các quy tắc hoặc thông tin tương tự thành những mục độc lập, có tính khái quát và tái sử dụng cao.

4. **Loại bỏ thông tin lỗi thời**
   Chủ động xóa các giả thuyết đã bị chứng minh là sai hoặc các thông tin không còn phù hợp.

## Các bước thực hiện

### Bước 1 – Đọc dữ liệu
Sử dụng công cụ `read` để đọc:
- `MEMORY.md` trong thư mục gốc.
- Nhật ký hôm nay `memory/YYYY-MM-DD.md`.

### Bước 2 – Tinh lọc trong trạng thái Dream
So sánh bộ nhớ cũ với nhật ký mới.
Thực hiện:
- Loại bỏ trùng lặp.
- Thay thế thông tin cũ bằng thông tin mới.
- Xóa các nội dung lỗi thời.
- Hợp nhất các thông tin liên quan.

Sau đó tạo ra một phiên bản hoàn toàn mới của bộ nhớ dài hạn.

### Bước 3 – Lưu bộ nhớ
Sử dụng `write` hoặc `edit` để ghi đè nội dung Markdown mới vào `MEMORY.md`.
Giữ cấu trúc rõ ràng với các tiêu đề và danh sách hợp lý.

### Bước 4 – Báo cáo sau khi hoàn thành
Sau khi hoàn tất quá trình tối ưu hóa, hãy báo cáo ngắn gọn:

1. Những bộ nhớ cốt lõi nào đã được bổ sung hoặc tổng hợp.
2. Những thông tin cũ nào đã được sửa đổi hoặc loại bỏ.
"""