# Checkpoint trước phiên bản tiếp theo

Ngày chốt: 17/10/2026. Nhánh: `feat/master-frontend`.
Giữ nguyên package version **1.1.7b1**; đây là commit gom thay đổi hiện tại,
không tạo release/tag, không đổi tên package và không triển khai production.

## Nội dung bản chốt

- Projects theo user: brief, mục tiêu, instructions, tham chiếu kết nối và chat.
- Shell SpiderAgents, palette màu tùy chỉnh, nền spider/web, animation và reduced motion.
- Sửa điều hướng Project → Chat và tránh response cũ ghi đè chat đang chọn.
- Sửa commit SQLite cho thao tác ghi không trả hàng dữ liệu.
- Bổ sung dependency PDF, khôi phục/re-index trên cùng bản ghi, giữ ACL và báo lỗi đúng.
- Tìm kiếm từ khóa cho local Knowledge Base khi chưa cấu hình embedding.
- Hướng dẫn sử dụng Windows và kiến trúc tiếng Việt trong [19](19-huong-dan-su-dung.md)
  và [20](20-kien-truc-he-thong.md).

## Dọn dữ liệu nhạy cảm

- Không đưa `.env`, `key_vilao.key`, private keys/certificates, auth data,
  database, logs, runtime, node_modules hoặc bundle build vào commit.
- Mở rộng `.gitignore`, đồng thời kiểm tra nội dung staged và đối chiếu credentials
  local mà không in giá trị ra báo cáo.
- Bỏ mật khẩu database hardcode khỏi constants, migration script, `.env.example`
  và hướng dẫn; migration dùng cùng cấu hình URL với application.
- Compose yêu cầu `OPENSPIDER_POSTGRES_PASSWORD` và `OPENSPIDER_PGADMIN_PASSWORD`
  do người vận hành cung cấp. `OPENSPIDER_DATABASE_URL` phải được đặt tương ứng.
  Không thay `.env` hoặc credentials local của người dùng trong đợt dọn này.
- Password từng nằm trong commit cũ vẫn tồn tại trong lịch sử Git. Đợt này không
  rewrite lịch sử hoặc force-push; cần đổi password cũ nếu còn được sử dụng.

Không sửa baseline `src/qwenpaw/`. Không xóa dữ liệu preview dưới `logs/`.
Hướng dẫn cấu hình PostgreSQL sau thay đổi nằm trong [hướng dẫn sử dụng](19-huong-dan-su-dung.md).

## Kiểm chứng

- 62 backend tests liên quan Projects, KB, chat updates và console đã qua.
- 42 frontend tests thuộc 7 file đã qua theo các lượt chạy: 37 test ở 6 file
  regression và 5 test Projects khi chạy lại riêng. Lượt chạy cùng build có 3
  test Projects vượt giới hạn 5 giây; chạy riêng với `--maxWorkers=1
  --testTimeout=30000 --hookTimeout=30000` thì cả 5 qua, không sửa code/test
  để thay đổi kết quả. Lượt đầu chạy nhiều worker còn gặp timeout khởi động worker.
- TypeScript và build production đã qua; vẫn có cảnh báo vendor chunk lớn và
  module vừa import động vừa import tĩnh.
- Python syntax, Compose YAML, yêu cầu password qua biến môi trường và ưu tiên
  biến `OPENSPIDER_DATABASE_URL` đã được kiểm tra.
- Lint toàn console: 127 errors, 79 warnings tồn tại từ trước. Trong các file UI
  thay đổi, 5 lỗi và 3 cảnh báo; các dòng có lỗi đã đối chiếu với `HEAD` trước
  checkpoint. Chưa xử lý toàn bộ nợ lint trong phạm vi chốt phiên bản này.
- GitNexus trên bản staged đầy đủ đánh giá **CRITICAL: 280 symbol, 41 luồng**,
  gồm cả file mới cùng các thay đổi chat/runner và theme. Đây là rủi ro tổng hợp,
  không đồng nghĩa tất cả đường chạy đã được test.

Không coi checkpoint là chứng nhận production: live PostgreSQL, mọi MCP server,
toàn bộ model/tool combinations và triển khai nhiều worker chưa được xác minh.
