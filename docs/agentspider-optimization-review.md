# AgentSpider: review UI và logic, kế hoạch tối ưu

Ngày review: 2026-10-15. Phạm vi: console React/TypeScript và backend OpenSpider.

Định hướng: người dùng trao đổi qua chat, biến yêu cầu thành tác vụ có thể theo
dõi, và kết nối hạ tầng qua các công cụ được kiểm soát quyền. Giữ nền tảng hiện
có; ưu tiên sửa tính đúng đắn, khả năng vận hành và luồng sử dụng trước khi
mở rộng tính năng hoặc thay đổi nhận diện.

Đây là review mã nguồn và kiểm tra tự động có chọn lọc. Chưa kiểm tra hình ảnh
trong trình duyệt, gọi LLM thật, chạy job lên hạ tầng hay đo tải production.
Các đề xuất giao diện bên dưới cần được kiểm chứng bằng prototype và thao tác
thực tế. Không có thay đổi implementation hoặc credential trong đợt review.

## Phát hiện cần xử lý

### F01 — P0: approval chưa được giới hạn theo người dùng ở backend

- [console.py:392](../src/openspider/app/routers/console.py#L392) lấy toàn bộ
  approval từ singleton, trả cả session, agent và tham số tool; frontend tự lọc.
- [approval.py:94](../src/openspider/app/routers/approval.py#L94) chỉ so sánh
  root session với session do client gửi. Token xác nhận chỉ được kiểm tra nếu
  client cung cấp; request HTTP không có token vẫn đi tiếp. Endpoint không đối
  chiếu người dùng đã xác thực với chủ sở hữu approval.
- [commands.ts:40](../console/src/api/modules/commands.ts#L40) gọi trực tiếp
  endpoint HTTP mà không gửi resolution token.

Hệ quả từ code: người dùng có quyền gọi API thông báo có thể nhận ID của approval
khác và gửi lại ID/root session để resolve. Middleware xác thực hiện có kiểm
tra token đăng nhập, nhưng không thay thế kiểm tra ownership của tài nguyên.
Đã gọi trực tiếp handler với request giả của Bob và approval giả thuộc Alice:
handler trả success khi session khớp và thiếu resolution token. Chưa thực hiện
khai thác end-to-end qua HTTP server.

Hướng sửa: lọc ở server theo principal, agent và cây session được phép; lấy actor
audit từ request đã xác thực; bắt buộc token xác nhận ở HTTP; đường lệnh kênh
chỉ được miễn token khi đã kiểm tra danh tính và quyền của người gửi. Bảo đảm
resolve lặp hoặc đồng thời trả kết quả xác định, không gây lỗi vì `resolved=None`.

### F02 — P0: API danh sách MCP trả header chưa che

[mcp.py:399](../src/openspider/app/routers/mcp.py#L399) trả trực tiếp `headers`,
trong khi API chi tiết tại dòng 431 đã dùng `_mask_env_dict`. Header có thể chứa
Authorization/API key và được đưa xuống trình duyệt khi mở danh sách MCP.
Đã tái hiện bằng cách gọi handler với store giả: header tổng hợp được trả nguyên
giá trị. Không sử dụng credential thật.

Hướng sửa: thống nhất serializer che secret cho list/detail/create/update/toggle;
kiểm tra cả nested fields, URL có token và lỗi/log. API chỉnh sửa phải phân biệt
giữ nguyên, thay thế và xóa secret; không dùng giá trị đã che như secret mới.

### F03 — P1: lazy loading bị vô hiệu hóa bởi đăng ký module eager

[main.tsx:13](../console/src/main.tsx#L13) gọi `registerHostModulesEager()`;
[dynamicModuleRegistry.ts:82](../console/src/plugins/dynamicModuleRegistry.ts#L82)
import eager toàn bộ module trong `pages`, dù router khai báo nhiều trang lazy.
Đây là nguyên nhân rõ ràng làm tăng phần mã được tải khi khởi động. Mức ảnh
hưởng lên thời gian render cần đo; chưa kết luận đây là nguyên nhân duy nhất
của lỗi hết bộ nhớ khi build.

Hướng sửa: registry giữ loader và chỉ resolve module cần cho route/plugin đang
dùng; bảo toàn thứ tự plugin patch trước khi render. Không thay bằng việc gọi
hàm dynamic hiện tại rồi import tuần tự tất cả module ở startup. Tách nhóm
chunk dựa trên dependency thực tế và kiểm tra lại vòng `utils-vendor ↔ ui-vendor`.

### F04 — P1: vòng đời job chưa đủ dữ liệu cho vận hành

[CronManager:270](../src/openspider/app/crons/manager.py#L270) tạo task nền;
trạng thái tại dòng 443 chỉ ghi vào `_states` trong RAM. API run trả
`started=true`, chưa có ID cho mỗi lần chạy. UI có client `getCronJobState`
nhưng trang Cron hiện không dùng nó để theo dõi kết quả.

Hệ quả: restart mất trạng thái lần chạy; khó phân biệt nhiều lần chạy cùng job,
khó nối thao tác trong chat với kết quả thực thi và lịch sử lỗi.

Hướng sửa: bổ sung bản ghi JobRun vào cơ chế storage hiện có, không bắt buộc đổi
toàn bộ sang PostgreSQL. Mỗi lần chạy có run_id, owner, agent/session, timestamps,
trạng thái, lỗi đã lọc secret, kết quả/artifact và liên kết approval. Track task
để shutdown/cancel có kiểm soát. Sau restart đánh dấu lần chạy bị gián đoạn;
không tự chạy lại thao tác hạ tầng không bảo đảm idempotency.

### F05 — P1: cập nhật cron có thể làm lệch persistence và runtime

[create_or_replace_job:157](../src/openspider/app/crons/manager.py#L157) ghi repo
trước khi `_register_or_update` validate/build trigger. Cron sai có thể đã được
lưu dù request báo lỗi. `_register_or_update:329` còn thay semaphore mỗi lần
cập nhật: tác vụ đang chạy giữ semaphore cũ, tác vụ mới dùng semaphore mới,
có nguy cơ vượt giới hạn concurrency khi sửa job đang chạy.
Đã tái hiện thứ tự ghi bằng spec cron `99 * * * *` và repo giả: `upsert_job`
được gọi trước khi trigger ném ValueError. Chưa stress test nhánh concurrency.

Hướng sửa: validate toàn bộ spec/trigger trước khi ghi; thiết kế rollback hoặc
reconciliation nếu scheduler update lỗi; giữ bộ điều phối concurrency ổn định
theo job và xác định chính sách khi đổi giới hạn trong lúc chạy.

### F06 — P1: PlanPanel có thể giữ kết nối của agent cũ

[PlanPanel:87](../console/src/components/PlanPanel/index.tsx#L87) subscribe SSE
chỉ phụ thuộc `open`. Khi đổi agent mà drawer vẫn mở, kết nối không được tạo
lại theo agent; GET fallback có thể dùng agent mới trong khi SSE vẫn dùng agent
cũ. Bộ lọc phía UI hiện dựa trên session. Việc subscribe server ở
[plan.py:145](../src/openspider/app/routers/plan.py#L145) cũng theo agent, chưa
theo principal/session; cần rà quyền trước khi mở rộng sự kiện realtime.

Hướng sửa: dùng khóa `{user, agent, session}`, abort subscription và GET cũ khi
đổi scope; version sự kiện/snapshot để kết quả cũ không ghi đè mới; lọc quyền
subscription và dữ liệu ở server.

### F07 — P2: polling có thể chồng request và che lỗi kết nối

[ConsolePollService:73](../console/src/components/ConsolePollService/index.tsx#L73)
poll 2,5 giây bằng interval, không chặn request đang chạy, bỏ qua lỗi; PlanPanel
vẫn poll 5 giây khi đã có SSE. Mỗi tab mở tạo thêm lượt gọi.

Hướng sửa trước mắt: một request mỗi vòng, timeout/abort, backoff, tạm dừng khi
tab ẩn và hiển thị trạng thái offline. Sau đó gom sự kiện approval/job/plan
qua kết nối có phạm vi quyền và cơ chế snapshot/resync; polling chỉ là fallback.
Không cần chuyển toàn bộ hệ thống sang WebSocket.

### F08 — P2: cache danh tính và lỗi API chưa có vòng đời thống nhất

[config.ts:45](../console/src/api/config.ts#L45) xóa token/username nhưng không
xóa role cache hoặc reset các promise username/role. Điều này có thể làm UI dùng
lại role cũ khi đổi danh tính trong cùng ứng dụng; không đồng nghĩa vượt quyền
backend. [useCronJobs](../console/src/pages/Control/CronJobs/useCronJobs.ts) không
hủy response cũ khi đổi agent; biến `mounted` hiện không bảo vệ lần `setJobs`
sau await. Chat còn GET active model trước mỗi lần gửi và quy mọi lỗi thành
thiếu cấu hình model tại [index.tsx:905](../console/src/pages/Chat/index.tsx#L905).

Hướng sửa: gom auth/session lifecycle; invalidation khi đổi token/user; query
cache theo scope và loại bỏ response cũ. Phân biệt 401, 403, offline, timeout,
model chưa cấu hình và provider lỗi. Cache active model có invalidation thay
vì thêm round trip cố định cho mọi tin nhắn.

### F09 — P2: progress và thông tin vận hành trong UI còn mơ hồ

[PlanPanel:116](../console/src/components/PlanPanel/index.tsx#L116) cộng cả
`abandoned` vào progress; outcome subtask luôn có dấu tick. Người dùng có thể
hiểu một plan đóng toàn bộ bước là hoàn thành thành công. Trình tạo MCP chủ yếu
nhận JSON; card biểu diễn enabled, chưa phải bằng chứng kết nối khỏe hoặc có
quyền gọi tool. [i18n.ts](../console/src/i18n.ts) chưa đăng ký tiếng Việt.

Hướng sửa: tách phần trăm đã xử lý khỏi tỷ lệ thành công; hiển thị failed/skipped/
cancelled rõ ràng. Với connection, tách configured, enabled, connecting, healthy,
degraded và failed; có lần kiểm tra cuối, quyền truy cập và lỗi có hướng xử lý.

### F10 — P1: credential tạm và cấu hình môi trường cần được chuẩn hóa

`key_vilao.key` có ba trường `url`, `model`, `apikey`; đang untracked và chưa được
`.gitignore` bảo vệ. Không sao chép giá trị vào báo cáo. ProviderManager đã tích
hợp `security.secret_store`, vì vậy nên dùng đường lưu provider hiện có thay
vì tạo thêm kho secret. Luồng lưu MCP qua SQLite hiện nhận chuỗi headers/env;
cần bổ sung thiết kế mã hóa tương ứng cho cả SQLite và PostgreSQL.

Kế hoạch nhập credential: validate cấu trúc, ánh xạ sang custom provider sau khi
xác nhận giao thức tương thích, lưu API key qua secret store, chọn model đúng
scope, kiểm tra kết nối có timeout và trả lỗi đã che. Bảo vệ file tạm khỏi Git;
chỉ xóa file khi đã nhập và kiểm tra thành công. Không tự suy luận khóa đã lộ
hoặc tự rotate khóa. Tuyệt đối không đưa provider key vào frontend `TOKEN`.

Ngoài ra, Vite dev proxy đang trỏ cổng 8000 trong khi CLI mặc định 8088; thống
nhất cấu hình dev/documentation để chạy đúng backend, giữ deployment hiện hữu.

## Luồng UI đề xuất

Điều hướng chính: **Chat · Jobs · Connections**. Cấu hình model, agent, quyền,
skills và chẩn đoán nằm trong nhóm Settings hoặc trang chi tiết tương ứng.
Giữ các URL cũ qua redirect để không làm hỏng liên kết.

Desktop: sidebar gọn; hội thoại ở giữa; drawer tác vụ theo ngữ cảnh ở bên phải.
Drawer cho biết mục tiêu, hạ tầng đích, các bước, trạng thái hiện tại, approval,
kết quả và lịch sử. Trên mobile, drawer dùng toàn màn hình và navigation thu gọn.

| Màn hình | Kết quả người dùng cần thấy |
|---|---|
| Chat | Agent/model/connection đang dùng; gửi yêu cầu; trạng thái stream; Stop; tác vụ liên quan |
| Task drawer | Kế hoạch thực hiện; bước đang chờ/chạy; approval với target rõ; log và artifact |
| Jobs | Job theo lịch và các lần chạy; queued/running/waiting approval/succeeded/failed/cancelled/interrupted; lọc và mở chi tiết |
| Connections | Form theo loại kết nối, secret đã che, Test connection, quyền dùng tool và trạng thái thực tế; JSON là chế độ nâng cao |

Đây là đề xuất UX từ review code, chưa phải kết quả usability test. Ưu tiên
hierarchy, mật độ thông tin, trạng thái loading/empty/error, keyboard focus và
responsive trước việc bổ sung animation hoặc hiệu ứng nền.

## Kế hoạch triển khai theo thứ tự

Ước lượng dưới đây dành cho một lập trình viên đã quen repo, chưa gồm thời gian
chờ môi trường và phản hồi sản phẩm; điều chỉnh sau impact analysis.

| Giai đoạn | Phạm vi / phụ thuộc | Điều kiện nghiệm thu | Ước lượng |
|---|---|---|---|
| 0 — Baseline | Hoàn tất index; reproduction F01/F02/F05/F06; đo UI/build/request | Có baseline và test lỗi tái hiện; chưa dùng hạ tầng thật | 1–2 ngày |
| 1 — Quyền và credential | F01, F02, F10; chuẩn hóa auth scope | User A không xem/resolve approval của B; HTTP thiếu token bị từ chối; không có secret trong response/log/build; provider nhập và test đúng scope | 2–4 ngày |
| 2 — Job đáng tin cậy | F04/F05; API/schema/storage trước UI | Mỗi lần run có ID; trạng thái giữ qua restart; cancel rõ; cron sai không làm lệch dữ liệu; update không vượt concurrency | 3–5 ngày |
| 3 — State và tốc độ UI | F03/F06/F07/F08; giữ tương thích plugin | Route tải theo nhu cầu; đổi agent/session không nhận state cũ; không poll chồng; build hoàn tất trên cấu hình CI đã định | 2–4 ngày |
| 4 — UI thống nhất | Dựa trên JobRun API và scope đã ổn định; F09 | Một luồng chat → approval → chạy → kết quả; Jobs/Connections usable trên desktop và mobile; tiếng Việt cho luồng chính | 3–5 ngày |

Không tăng concurrency hoặc thêm retry đại trà trước khi có số đo và phân loại
tool có side effect. Retry thao tác hạ tầng cần idempotency key hoặc policy rõ.
Không cần thay AgentScope, thiết kế lại toàn bộ storage hay thêm hàng đợi ngoài
ngay từ giai đoạn đầu.

## Đo lường và kiểm thử nghiệm thu

- Đo baseline cold/warm: thời gian shell/chat sẵn sàng, JS tải ban đầu, request
  trước khi gửi chat, thời gian stream đầu tiên tách khỏi độ trễ provider, và
  thời gian cập nhật trạng thái job. So sánh trên cùng máy, browser và provider.
- Mục tiêu thử nghiệm sau baseline: giảm ít nhất 30% JS tải ban đầu; bỏ request
  active-model thừa khi cache hợp lệ; không có request polling chồng; trạng thái
  tác vụ xuất hiện trong 1 giây trên môi trường local, không tính thời gian LLM.
  Đây là mục tiêu, chưa phải kết quả đã đạt.
- Regression backend: ownership hai user/hai agent, approval token thiếu/sai/
  hết hạn/resolve lặp, masking secret, cron invalid, sửa job đang chạy, timeout,
  cancel, restart và tương thích SQLite/PostgreSQL.
- Regression UI: đổi scope khi request chậm, reconnect/resync, offline/401/403,
  loading/empty/error, trạng thái thất bại không có tick thành công, form giữ
  secret cũ, keyboard và kích thước 360/768/1440 px.
- E2E: tạo yêu cầu trong chat → duyệt đúng actor → JobRun chạy qua tool guard →
  kết quả/artifact; reload vẫn theo dõi được. Dùng fake provider và fake connector
  trước, smoke test thật chỉ sau khi credential và quyền đã được cấu hình.
- Khôi phục test ChatPage đang bị loại khỏi Vitest trong `vite.config.ts:86`;
  test unit với mock thư viện không thay thế kiểm thử tích hợp UI thực tế.

## Kết quả kiểm tra trong đợt review

| Kiểm tra | Kết quả |
|---|---|
| UI: config, request, agentStore | 34 test đạt, 3 file; log `logs/review-ui-tests.log` |
| Backend: OpenAI stream compatibility, auth/admin | 23 test đạt khi tách thư mục runtime/secret; log `logs/review-backend-tests-isolated.log` |
| Build console | `tsc -b` đạt; Vite transform 14.656 module, báo circular chunk và hết heap khoảng 2 GB; log `logs/review-ui-build.log` |
| Backend test lần đầu | 15 đạt, 8 lỗi quyền ghi master key ngoài workspace; không xem đây là 8 lỗi logic sản phẩm |
| Credential | Chỉ kiểm tra cấu trúc và tên trường; chưa gọi URL, xác thực key hoặc thay cấu hình |
| Reproduction trực tiếp handler | 3/3 tái hiện: approval khác owner thiếu resolution token, MCP header chưa che, persist cron trước validation; toàn bộ dùng mock/dữ liệu giả |
| Browser, tải và hạ tầng | Chưa kiểm tra trong đợt review |

GitNexus báo index cũ (`b8485b0` so với HEAD `20b10b3`). Lần analyze trong
sandbox thất bại; lần chạy lại ngoài sandbox đã thành công trong 164,4 giây:
33.103 nodes, 58.732 edges, 300 flows, index tại HEAD `20b10b3`. Công cụ cập nhật
số liệu generated trong AGENTS.md và CLAUDE.md. Query khái niệm vẫn báo thiếu
FTS index, nên không dùng kết quả tìm kiếm rỗng để kết luận không có flow.

Impact upstream bước đầu trên index mới: `post_approval_approve` có 0 direct
callers/0 process được graph ghi nhận, risk LOW; `create_or_replace_job` có 2
direct callers (`create_job`, `replace_job`), 0 process, 1 module Crons, risk LOW.
Đây là độ phủ call graph tĩnh: router được gọi qua HTTP và không có direct
caller không có nghĩa ít rủi ro bảo mật. Context của `registerHostModulesEager`
xác nhận main.tsx gọi registry; context `list_mcp_clients` tìm được hai execution
flows. Cần sửa FTS ở bước baseline và chạy lại impact cho đúng patch triển khai.

Trước mọi chỉnh sửa symbol ở giai đoạn triển khai phải chạy impact upstream và
báo direct callers, affected processes, risk
theo AGENTS.md; HIGH/CRITICAL cần cảnh báo trước khi sửa. Trước commit chạy
detect_changes. Toàn bộ implementation tiếp theo chỉ sửa backend OpenSpider,
console và các test/config/docs liên quan; giữ nguyên baseline QwenPaw.
