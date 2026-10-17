# Hướng dẫn sử dụng SpiderAgents

Ngày cập nhật: 16/10/2026. Tài liệu mô tả bản code trong repository hiện tại.
Tên giao diện là **SpiderAgents**; backend và CLI đang phát triển là **OpenSpider**.

## 1. Bắt đầu từ đâu?

SpiderAgents kết hợp ba nhóm công việc:

| Nhu cầu | Màn hình / tính năng |
|---|---|
| Tổ chức một bài toán phân tích dữ liệu | Projects: mục tiêu, instructions, hội thoại và tham chiếu kết nối |
| Trao đổi với agent, theo dõi tool | Chat, chọn agent và model |
| Hỏi đáp tài liệu cá nhân | Knowledge Base, upload, index và tìm kiếm |
| Chạy tác vụ có lịch | Cron Jobs; xem cấu hình và trạng thái thực thi |
| Kết nối hệ thống bên ngoài | MCP; API riêng cần MCP server, tool hoặc extension tương ứng |
| Cá nhân hóa giao diện | Appearance Settings: màu, sáng/tối, nền và animation |

Với người dùng mới: chạy ứng dụng → cấu hình model → tạo project → bắt đầu chat
→ thêm tài liệu hoặc kết nối khi bài toán cần đến chúng.

## 2. Chuẩn bị môi trường Windows

- PowerShell, Git, Python `>=3.10,<3.14` theo `pyproject.toml`.
- Node.js và npm chạy được bộ công cụ Vite của `console/`.
- API key của provider nếu dùng model từ dịch vụ bên ngoài; hoặc model server
  local đã khởi động nếu dùng Ollama/LM Studio.

Kiểm tra các executable đang được dùng:

```powershell
python --version
python -m pip --version
node --version
npm --version
```

Vào repository, thay đường dẫn dưới đây bằng vị trí clone trên máy:

```powershell
cd "C:\path\to\SpiderAgents"
python -m pip install -e ".[dev]"
```

Nếu dùng virtual environment, kích hoạt môi trường đó trước khi cài và chạy.
Luôn dùng cùng một Python cho `pip`, test và `python -m openspider`.

## 3. Chạy bản local với dữ liệu đã dùng trong phiên preview

Dữ liệu trong phiên phát triển hiện tại nằm ở `logs/projects-preview` và
`logs/projects-preview.secret`. Để mở lại chat, projects, model config và PDF
đã upload, dùng đúng hai đường dẫn này. Không cần chạy lại `init`.

### Terminal 1: backend

Chạy từ thư mục gốc repository:

```powershell
$env:OPENSPIDER_WORKING_DIR=Join-Path $PWD "logs/projects-preview"
$env:OPENSPIDER_SECRET_DIR=Join-Path $PWD "logs/projects-preview.secret"
$env:OPENSPIDER_DATABASE_ENABLED="false"
$env:OPENSPIDER_AUTH_ENABLED="false"

python -m openspider app --host 127.0.0.1 --port 8000
```

Đây là cấu hình local tắt đăng nhập, chỉ bind loopback. Khi triển khai cho nhiều
người dùng, cần bật authentication và cấu hình bảo vệ truy cập tương ứng.

### Terminal 2: frontend có tự cập nhật khi sửa UI

```powershell
cd "C:\path\to\SpiderAgents\console"
npm ci
npm run dev -- --host 127.0.0.1
```

Mở **<http://127.0.0.1:5173/>**. Giữ cả hai terminal đang chạy.
`npm ci` cần cho lần cài đầu hoặc khi lockfile thay đổi.

| Thành phần | Địa chỉ | Ghi chú |
|---|---|---|
| Giao diện Vite | `http://127.0.0.1:5173` | Truy cập ứng dụng tại đây khi develop |
| Backend | `http://127.0.0.1:8000` | Vite proxy `/api` tới cổng này |
| Ví dụ API | `http://127.0.0.1:5173/api/models/active?scope=global` | Đi qua proxy frontend |

Proxy trong `console/vite.config.ts` hiện trỏ cố định đến `127.0.0.1:8000`.
Nếu chỉ đổi backend sang 8088/8089 mà không đổi proxy, frontend sẽ lỗi kết nối API.
Nếu cổng 5173 bận, Vite có thể chọn cổng khác; đọc URL mà terminal in ra.

Nhấn **Ctrl+C** trong từng terminal để dừng. Tránh chạy hai backend cùng ghi
vào một working directory. Biến `$env:...` chỉ tồn tại trong terminal hiện tại;
khi mở terminal mới, cần thiết lập lại.

### Chạy UI đã build cùng backend

Dừng bản dev nếu đang chạy. Từ thư mục gốc:

```powershell
cd console
npm ci
$env:NODE_OPTIONS="--max-old-space-size=8192"
npm run build
cd ..

$env:OPENSPIDER_WORKING_DIR=Join-Path $PWD "logs/projects-preview"
$env:OPENSPIDER_SECRET_DIR=Join-Path $PWD "logs/projects-preview.secret"
$env:OPENSPIDER_DATABASE_ENABLED="false"
$env:OPENSPIDER_AUTH_ENABLED="false"
$env:OPENSPIDER_CONSOLE_STATIC_DIR=Join-Path $PWD "console/dist"

python -m openspider app --host 127.0.0.1 --port 8089
```

Mở **<http://127.0.0.1:8089/>**; không cần Vite. Chạy lại build sau khi sửa UI.
`OPENSPIDER_CONSOLE_STATIC_DIR` chỉ định rõ bundle dùng cho backend, tránh lấy
nhầm giao diện đóng gói cũ. Đây là cách phục vụ bundle local, chưa phải hướng
dẫn triển khai production nhiều người dùng.

### Khởi tạo bộ dữ liệu hoàn toàn mới

Nếu muốn một workspace riêng thay vì dữ liệu preview, chọn đường dẫn mới trước:

```powershell
$env:OPENSPIDER_WORKING_DIR=Join-Path $PWD "runtime/personal"
$env:OPENSPIDER_SECRET_DIR=Join-Path $PWD "runtime/personal.secret"
$env:OPENSPIDER_DATABASE_ENABLED="false"
$env:OPENSPIDER_AUTH_ENABLED="false"
python -m openspider init --defaults
python -m openspider app --host 127.0.0.1 --port 8000
```

Chỉ dùng bước init cho bộ dữ liệu mới. Không trộn working directory của bộ dữ
liệu này với secret directory của bộ khác. File `.env` ở gốc repository được
backend đọc khi khởi động; các biến đã đặt trong terminal có ưu tiên hơn.

## 4. Cấu hình LLM và kiểm tra khả năng chat

1. Mở **Settings → Models**.
2. Với provider có sẵn, mở **Settings** trên thẻ provider. Với dịch vụ tương thích
   OpenAI riêng, chọn **Add Provider** và đúng protocol dịch vụ cung cấp.
3. Nhập Base URL và API key. Dùng URL theo nhà cung cấp; không tự thêm `/v1` nếu
   endpoint không yêu cầu. Lưu cấu hình.
4. Mở **Models** trên thẻ provider để thêm hoặc khám phá model nếu được hỗ trợ.
   Model ID phải đúng với endpoint; tên hiển thị có thể khác ID.
5. Dùng kiểm tra kết nối provider và kiểm tra từng model trong phần quản lý.
6. Chọn provider/model ở **Default LLM** rồi **Save**.
7. Mở Chat, chọn đúng agent và kiểm tra model trên thanh chọn. Gửi một câu ngắn
   để xác nhận đường chạy chat thực tế.

**Default LLM** là mặc định toàn hệ thống. Model chọn riêng cho agent trong Chat
có ưu tiên cao hơn mặc định này. Vì vậy, thay model global chưa chắc đổi model
của agent đã có cấu hình riêng. `active_model: null` của agent có thể có nghĩa
agent đang dùng model global, không tự nó chứng minh cấu hình bị lỗi.

Test provider thành công chứng minh endpoint kiểm tra phản hồi; test model gửi
một yêu cầu nhỏ. Hai bước này chưa chứng minh mọi tool, ảnh, streaming dài hoặc
giới hạn context đều tương thích. Không đưa API key vào prompt, ảnh chụp hay Git.

## 5. Projects và Chat cho bài toán data science

1. Mở **Projects → Create a project**.
2. Chọn project trống hoặc template: Data exploration, Machine learning,
   Data pipeline, Research.
3. Điền tên, mô tả, mục tiêu và instructions. Ví dụ:

   > Phân tích churn từ CSV. Kiểm tra chất lượng dữ liệu, tránh leakage,
   > chia train/test trước khi fit preprocessing, báo cáo baseline và metric.
   > Trước khi ghi đè dữ liệu nguồn, trình bày thay đổi dự kiến.

4. Chọn tham chiếu kết nối MCP của mình nếu cần, rồi lưu project.
5. Chọn agent trong sidebar và bắt đầu hội thoại từ project.
6. Theo dõi câu trả lời, tool input/output và yêu cầu phê duyệt. Kiểm tra file,
   metric hoặc kết quả thực thi trước khi kết luận công việc hoàn tất.
7. Dùng banner project phía trên Chat để quay về project. Danh sách hội thoại
   của project được hiển thị theo agent đang chọn.
8. Archive khi kết thúc; restore trước khi tiếp tục hội thoại trong project đó.

Instructions và template là ngữ cảnh cho agent. Chúng không tự cài Python package,
không tạo notebook server, GPU hay môi trường thực thi độc lập cho mỗi project.
Đường dẫn dữ liệu và công cụ phải truy cập được từ máy/container chạy backend.
Tham chiếu MCP trong project không tự cấp thêm quyền hoặc tự kết nối server.

## 6. Knowledge Base

### Upload và sử dụng

1. Chọn đúng agent, mở **Knowledge Base**, upload tài liệu.
2. Chờ trạng thái **ready** và kiểm tra số chunks lớn hơn 0.
3. Tìm kiếm trong KB hoặc yêu cầu agent liệt kê tài liệu rồi hỏi nội dung cụ thể.
4. Kiểm tra trích dẫn tên file và nội dung đoạn được truy xuất.

Pipeline tiếp nhận PDF, DOCX, XLSX/XLSM, Markdown, TXT/LOG, CSV/TSV. PDF dùng
`pdfplumber` khi có, rồi fallback sang `pypdf`; `pypdf` đã có trong dependencies.
DOCX và Excel cần parser dependency tương ứng (`python-docx`, `openpyxl`) trong
môi trường chạy. Không có OCR tự động trong `PDFParser`: PDF chỉ chứa ảnh có thể
không tạo được văn bản và cần xử lý OCR bên ngoài trước.

| Trạng thái | Ý nghĩa / xử lý |
|---|---|
| `pending` | Chưa xử lý |
| `indexing` | Đang parse, chia chunk, embedding và ghi store |
| `ready` | Đã index; kiểm tra tiếp bằng truy vấn liên quan |
| `error` | Xem `error_message`, sửa nguyên nhân rồi re-index |

Re-index giữ nguyên document ID, tên file và quyền chia sẻ; không cần upload lại
để khôi phục sau lỗi parser. Kiểm tra cả `succeeded` và `failed` trong kết quả.
Nội dung trả lời cũ trong lịch sử Chat vẫn giữ trạng thái tại thời điểm trả lời;
hãy hỏi lại hoặc mở KB để đọc trạng thái mới.

### Có và không có embedding

- Khi đã cấu hình embedding trong `running.reme_light_memory_config` của agent,
  hệ thống gọi embedding endpoint rồi tìm kiếm qua vector store.
- Khi chưa có embedding và dùng **LocalVectorStore**, tìm kiếm chuyển sang từ
  khóa; hỗ trợ so khớp tiếng Việt có/không dấu và lọc tài liệu được phép xem.
- Tìm kiếm từ khóa không tương đương tìm kiếm ngữ nghĩa. Chế độ fallback này
  không được triển khai chung cho mọi vector backend.
- Cấu hình model chat và cấu hình embedding là hai phần riêng biệt.

## 7. MCP, tools, jobs và approval

Trong **MCP**, tạo cấu hình theo transport:

| Transport | Thông tin cần có |
|---|---|
| `stdio` | Command, arguments, môi trường và thư mục chạy nếu cần; executable phải tồn tại trên máy backend |
| `streamable_http` | URL MCP endpoint và headers xác thực nếu dịch vụ yêu cầu |
| `sse` | URL SSE MCP và headers theo server tương ứng |

Bật cấu hình, kiểm tra trạng thái kết nối và tool thực tế được cung cấp trước
khi yêu cầu agent sử dụng. Một REST API thông thường chưa phải MCP server;
muốn dùng từ agent cần adapter MCP hoặc tool/extension gọi API đó.

Để chạy định kỳ, mở **Cron Jobs**, thiết lập lịch, nội dung và đích nhận phù hợp
với form hiện có. Theo dõi kết quả từng lần chạy; có thể pause/resume và chạy
thử bằng chức năng của trang. Backend cần duy trì hoạt động để scheduler chạy.

Với thao tác yêu cầu approval, đọc tool, tham số và phạm vi ảnh hưởng rồi chọn
chấp thuận hoặc từ chối. Không coi câu trả lời “đã thực hiện” của LLM là bằng
chứng: cần tool output, trạng thái job hoặc kết quả từ hệ thống đích.

## 8. Cá nhân hóa giao diện

Mở biểu tượng bánh răng **Appearance Settings** trên header. Chọn Spider-Verse,
Symbiote, Neon Web hoặc Spider Studio; tùy chỉnh màu chính, màu phụ, sợi mạng và
nền. Có thể đổi sáng/tối, font, bo góc và bật/tắt animation.
Animation tôn trọng thiết lập giảm chuyển động của hệ điều hành. Preferences
được lưu trong trình duyệt; không mặc định đồng bộ sang thiết bị khác.
Chi tiết: [Appearance và điều hướng](18-spider-appearance-and-navigation.md).

## 9. Dữ liệu, sao lưu và lỗi thường gặp

**Thư mục preview đang chứa dữ liệu thật dù tên nằm dưới `logs/`. Không xóa toàn
bộ `logs/` để dọn log.** Khi ứng dụng đã dừng, sao lưu cả working directory và
secret directory; nếu dùng PostgreSQL, sao lưu database tương ứng. Giữ file sao
lưu chứa secrets ở nơi có quyền truy cập phù hợp. Không commit runtime hay key.

| Hiện tượng | Kiểm tra |
|---|---|
| Không mở được trang | Hai terminal còn chạy không? URL/cổng thực tế Vite là gì? |
| Vite báo `ECONNREFUSED` | Backend đã ready ở 8000 chưa? Proxy có đúng cổng không? |
| Backend mở được nhưng không có UI | Dùng Vite 5173 hoặc build `console/dist`; kiểm tra `OPENSPIDER_CONSOLE_STATIC_DIR` |
| Cổng đã được sử dụng | Kiểm tra tiến trình đang nghe cổng; dừng đúng phiên cũ trước khi chạy lại |
| Không thấy chat, project hoặc provider cũ | Kiểm tra lại hai biến thư mục và chế độ database của terminal |
| Lưu Default LLM nhưng Chat vẫn model cũ | Kiểm tra agent đang chọn và cấu hình model riêng của agent |
| Provider test được nhưng chat lỗi | Kiểm tra model ID, protocol, quyền model, quota và log của lần chat |
| PDF báo thiếu `pypdf` | Cài lại dependencies bằng cùng Python chạy backend |
| PDF không có text | Kiểm tra PDF scan, mã hóa hoặc lỗi file; OCR bên ngoài nếu cần |
| KB ready nhưng không tìm ra | Dùng từ khóa cụ thể; kiểm tra agent, quyền truy cập và cấu hình embedding |
| MCP kết nối thất bại | Kiểm tra command/URL, dependency của server, headers và môi trường backend |

API kiểm tra nhanh qua frontend trong chế độ local tắt auth:

```powershell
Invoke-RestMethod "http://127.0.0.1:5173/api/models/active?scope=effective&agent_id=default"
Invoke-RestMethod "http://127.0.0.1:5173/api/knowledge/status?kb_name=default"
```

Khi bật auth, các endpoint có thể yêu cầu Bearer token; không paste token vào
báo lỗi công khai. Log phiên chạy tương tác nằm trong terminal; các lần chạy có
redirect trước đây dùng `logs/projects-preview-server.log`.

### Nếu dùng PostgreSQL thay cho SQLite/JSON

Mật khẩu mặc định đã được loại khỏi code và Compose. Trước khi chạy
`docker compose -f docker-compose.postgres.yaml up -d`, đặt hai biến
`OPENSPIDER_POSTGRES_PASSWORD` và `OPENSPIDER_PGADMIN_PASSWORD` trong `.env`
local, dùng mật khẩu riêng cho từng dịch vụ. Compose sẽ báo lỗi nếu còn để trống.

Đặt `OPENSPIDER_DATABASE_URL` theo cùng thông tin database: driver
`postgresql+asyncpg`, user `openspider`, database `openspider`, host `localhost`,
port `5433` cho Compose này. Password trong URL cần URL-encode nếu có ký tự đặc
biệt. Cung cấp URL trước khi migrate hoặc bật `OPENSPIDER_DATABASE_ENABLED=true`.
URL fallback trong code không chứa thông tin xác thực và không tự khớp với
mật khẩu do bạn đặt. Thay biến môi trường không tự đổi password của database
đã tồn tại trong volume; không xóa volume để áp cấu hình mới.

Đọc tiếp: [Kiến trúc hệ thống](20-kien-truc-he-thong.md),
[Projects](17-projects.md), [mục lục tài liệu](README.md).
