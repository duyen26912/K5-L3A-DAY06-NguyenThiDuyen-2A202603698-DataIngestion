# Benchmark — Bộ luật Lao động 2019

> **Trạng thái: ĐÃ CHỐT ngày 2026-11-13, trước mọi lần chạy truy xuất.** Câu hỏi do AI (Claude) soạn nháp; học viên đã đối chiếu từng câu với PDF. Không sửa tập test sau mốc này.

## File

- `questions.jsonl`: 20 câu, mỗi dòng một câu.
- Kiểm chứng tự động: `cd starter && python scripts/verify_benchmark.py`. Script kiểm tra từng `evidence_quote` có nằm nguyên văn trên `gold_page` (text đã chuẩn hóa ở `starter/results/pages.jsonl`) và đúng `gold_dieu`; giá trị filter khớp chương của evidence; câu hỏi không chứa số Điều/trang; đủ ≥15 dev, ≥5 test, ≥3 câu filter (≥1 ở test).

## Trường dữ liệu

| Trường | Ý nghĩa |
|---|---|
| `id`, `split` | `dXX` = dev, `tXX` = test |
| `type` | `truc_tiep`, `dien_dat_lai`, `dieu_kien`, `ngoai_le`, `metadata_filter` (chỉ để phân tích lỗi) |
| `gold_source_id`, `gold_page` | `blld-2019` và trang vật lý của PDF (page 1 = trang 3 Công báo) |
| `gold_dieu` | Điều chứa evidence (phụ, giúp phân tích lỗi) |
| `evidence_quote` | Chuỗi nguyên văn từ text đã chuẩn hóa. Nếu là danh sách thì chunk phải chứa **tất cả** các chuỗi |
| `alt_gold` | Nguồn hợp lệ khác, chấp nhận bất kỳ nguồn nào (chỉ `t05`) |
| `filter` | `{"chuong": "<số La Mã>"}` hoặc `null` |
| `filter_context` | Vì sao filter là input có sẵn từ người dùng trước khi truy xuất |

## Phân bố và cách chia

- **Dev 15 / Test 5**, chia tay trước khi chạy bất kỳ truy xuất nào.
- Loại câu: 7 trực tiếp, 4 diễn đạt lại, 4 điều kiện, 1 ngoại lệ, 4 metadata filter (2 dev: `d13`, `d14`; 2 test: `t04`, `t05`).
- Phủ các chương III, VI, VII, VIII, X, XI, XII, XIV. Test lấy các điều **khác** dev (Điều 46, 102, 107, 109, 190/194) để hạn chế rò rỉ; cùng chương với dev nên vẫn có rủi ro chủ đề gần nhau (ví dụ `t01`, `t03` và `d01`, `d05` đều về thời giờ làm việc).

## Filter

Filter duy nhất là `chuong`, lấy từ tiêu đề "Chương …" trong văn bản (không đoán). Filter được coi là **input giả định do người dùng cung cấp trước** (ví dụ người dùng đang xem một chương cụ thể). Câu filter cố tình dùng từ chung, dễ nhầm giữa các chương:

- `d13`: "thời hiệu" (kỷ luật, Ch. VIII) dễ nhầm với thời hiệu tranh chấp (Ch. XIV).
- `d14`: "thời hạn tối đa, gia hạn" (giấy phép lao động, Ch. XI) dễ nhầm với thời hạn hợp đồng (Ch. III).
- `t04`: "khấu trừ lương" (Ch. VI) dễ nhầm với bồi thường thiệt hại (Điều 129, Ch. VIII).
- `t05`: "thời hiệu Tòa án" (Ch. XIV) dễ nhầm với thời hiệu kỷ luật (Ch. VIII); có 2 gold hợp lệ (Điều 190, 194).

Cấu hình A và B không dùng filter. Cấu hình C chỉ áp filter cho 4 câu này; 16 câu còn lại C chạy không filter.

## Tiêu chí chọn chiến lược (chốt trước khi xem test)

1. Evidence Hit@3 trên **dev** cao nhất.
2. Nếu chênh lệch ≤ 1 câu (≤ 1/15): chọn cấu hình có Hit@1 dev cao hơn.
3. Nếu vẫn hòa: ưu tiên coherence trung bình cao hơn, rồi ít chunk hơn.

Tập test chỉ chạy một lần sau khi đã chốt cấu hình trên dev.

## Hạn chế đã biết

- Người soạn câu hỏi cũng là người làm pipeline nên có thiên lệch; câu do AI soạn nháp, học viên duyệt.
- 5 câu test là mẫu rất nhỏ, kết quả chỉ mang tính minh họa.
- `d06` có evidence ngắn ("Kết hôn: nghỉ 03 ngày"), phần "hưởng nguyên lương" nằm ở trang 47. Đây là ca dùng để quan sát grounding khi điều luật vắt qua hai trang.
- Văn bản là bản gốc 2019, chưa gồm các sửa đổi sau này; đáp án chỉ đúng theo bản này.

## Lịch sử

- 2026-11-13: bản nháp 20 câu do Claude soạn, đã qua `verify_benchmark.py`.
- 2026-11-13: học viên đối chiếu từng câu với PDF, không sửa câu nào, chốt benchmark. Chưa chạy truy xuất nào trước mốc này.
