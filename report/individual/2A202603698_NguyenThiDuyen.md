# Báo cáo cá nhân — Day 6

Nguyễn Thị Duyên · 2A202603698 · L3A

## Dữ liệu và pipeline

**Chủ đề, nguồn, quyền sử dụng, số trang và cách tính trang**

- Văn bản: Bộ luật Lao động số 45/2019/QH14, bản đăng Công báo số 993 + 994 ngày 26-12-2019, trang Công báo 3–95. Link nguồn ghi trong [data/manifest.json](../../data/manifest.json).
- Quyền sử dụng: đây là văn bản quy phạm pháp luật, thuộc diện không được bảo hộ quyền tác giả theo Luật Sở hữu trí tuệ, Điều 15. Văn bản không chứa dữ liệu cá nhân.
- Phiên bản: văn bản gốc, có hiệu lực từ 01/01/2021. Corpus **chưa** gồm các lần sửa đổi sau đó, nên không dùng được làm tư vấn pháp lý hiện hành.
- Số trang: PDF có 94 trang vật lý, trong đó **93 trang được tính**. Trang 94 bị loại vì sau khi chuẩn hóa còn dưới 50 ký tự. Quy tắc: tính mọi trang có nội dung điều luật, không có trang bìa hay mục lục.
- Tổng cộng 189.093 ký tự sau chuẩn hóa, gồm 17 chương và Điều 1–220.
- Trong manifest, mỗi trang đều ghi số ký tự và số trang Công báo tương ứng.

**Chuẩn hóa, lỗi gặp phải và giới hạn**

- Trích xuất bằng pypdf ở chế độ `extraction_mode="layout"`. Chế độ mặc định tách sai giữa các âm tiết, ví dụ "ng ười".
- Văn bản được chuẩn hóa Unicode NFC.
- Các dòng bị ngắt do dàn trang được ghép lại theo thụt lề: dòng thụt lề là đầu đoạn mới, dòng sát lề trái là phần tiếp nối của đoạn trước.
- Header Công báo ("CÔNG BÁO/Số 993 + 994/Ngày 26-12-2019") được xóa khỏi text, còn số trang Công báo được giữ lại thành metadata.
- Tiêu đề chương viết hoa kéo dài nhiều dòng (Chương V, X, XI, XVI) ban đầu bị cắt cụt. Đã sửa bằng cách nối các dòng viết hoa liên tiếp.
- Offset của tiêu đề từng bị lệch do lỗi khi đếm vị trí. Đã sửa và thêm bước kiểm tra: offset của mỗi tiêu đề phải trỏ đúng vào "Chương/Mục/Điều N".
- Số Điều phải tăng đúng từng bậc 1. Nhờ vậy, các "Điều" nằm trong đoạn trích dẫn của Điều 219 không bị nhận nhầm là tiêu đề.
- Hai bản PDF thử trước đó bị loại:
  - một bản là ảnh scan, không có lớp chữ;
  - một bản từ trang tổng hợp bị lẫn footer, nhãn và hộp ghi chú biên tập.
- Log quá trình ingest: `starter/results/ingest_log.json`.

**Embedding, vector store, metric, lệnh chạy và chi phí**

- Model embedding: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
  - Chạy local trên CPU, 384 chiều, vector được chuẩn hóa L2.
  - Query và document dùng cùng một encoder, không thêm prefix.
  - `max_seq_length` = 128 token.
  - Phiên bản thư viện: sentence-transformers 6.3.0, torch 2.15.0+cpu, transformers 5.22.2.
- Vector store: PostgreSQL 16.16 + pgvector 0.8.7, chạy bằng Docker image `pgvector/pgvector:0.8.7-pg16`.
  - Dùng một bảng `chunks` với khóa chính `(strategy, chunk_id)`.
  - Metric cosine (`<=>`). Tìm kiếm **chính xác** (exact), không tạo chỉ mục ANN, nên khi áp filter không bị mất recall như với tìm kiếm gần đúng.
- Lệnh chạy:
  - `python -m src.ingestion`
  - `python -m src.run --split dev`, sau khi đã chốt cấu hình thì chạy `--split test`
  - Chi tiết trong [README.md](../../README.md).
- Chi phí: 0 USD, vì model chạy local.
- Thời gian:
  - Đọc corpus khoảng 4 giây.
  - Nạp model khoảng 8 giây.
  - Mỗi index mất khoảng 12 giây (gần như toàn bộ là thời gian embed).
  - Truy vấn trung bình 19–36 ms mỗi câu.

**Metadata bắt buộc, trường lọc bổ sung, nguồn giá trị và lý do chọn**

- Mỗi chunk có các trường: `document_id`, `source` (đường dẫn PDF), `page` (trang PDF), `cong_bao_page`, `char_start/char_end`, `content_hash`.
- Metadata cấu trúc gồm:
  - `chuong` (TEXT, số La Mã) và `chuong_title`
  - `muc` (INTEGER)
  - `dieu` (INTEGER, là Điều tại vị trí đầu chunk)
  - `dieu_list` (mọi Điều mà chunk có chứa chữ)
- Giá trị các trường cấu trúc lấy trực tiếp từ tiêu đề trong văn bản; không có giá trị nào được tự đoán.
- Trường dùng để lọc là `chuong`. Mỗi chương tương ứng một chủ đề lớn (hợp đồng, tiền lương, kỷ luật, tranh chấp…), nên khi người dùng đã biết ngữ cảnh chủ đề thì lọc theo chương sẽ loại được các điều có câu chữ giống nhau nhưng thuộc chủ đề khác. Ví dụ điển hình là "thời hiệu", xuất hiện ở cả Chương VIII và Chương XIV.
- Filter là **input giả định được cung cấp trước** (trường `filter_context` trong benchmark), không suy ra từ gold.

## Cấu hình và benchmark

**Ba cấu hình A / B / C**

Cả ba dùng cùng corpus, cùng model, cùng store, metric cosine và lấy top-3.

- **A:** cửa sổ cố định 500 ký tự, overlap 50, cắt trong phạm vi từng trang, không lọc.
- **B:** chia theo đoạn (khoản/điểm), gom tối đa 500 ký tự. Mỗi tiêu đề Chương/Mục/Điều mở một chunk mới. Đoạn dài hơn 500 ký tự được tách tại dấu `.`, `;` hoặc `:`. Không lọc.
- **C:** dùng **đúng index của B**, chỉ thêm `WHERE chuong = …` cho những câu hỏi có filter.

Như vậy A và B chỉ khác nhau ở cách chunk; B và C chỉ khác nhau ở việc lọc. Lý do chọn 500 ký tự là model chỉ nhận 128 token; ước lượng ban đầu khoảng 4 ký tự/token hóa ra quá lạc quan (xem phần Hạn chế).

**Benchmark 20 câu**

- Tập dev 15 câu, tập test 5 câu. File: [benchmark/questions.jsonl](../../benchmark/questions.jsonl).
- Các loại câu: trực tiếp, diễn đạt lại, có điều kiện/ngoại lệ, và câu cần metadata.
- Có 4 câu dùng filter `chuong`: dev gồm d13 (VIII) và d14 (XI); test gồm t04 (VI) và t05 (XIV). t05 chấp nhận hai nguồn gold hợp lệ là Điều 190 và Điều 194.
- Kiểm chứng bằng script [verify_benchmark.py](../../starter/scripts/verify_benchmark.py), kiểm tra các điểm sau:
  - evidence nằm nguyên văn trên trang gold sau khi chuẩn hóa khoảng trắng và thuộc đúng `gold_dieu`;
  - giá trị filter khớp với chương của gold;
  - câu hỏi không làm lộ "Điều N" hay "trang N".
- Script đã được thử với dữ liệu sai cố ý và bắt được lỗi.
- Bộ câu hỏi chốt ngày 2026-11-13, trước khi chạy pipeline.

**Tiêu chí chọn chiến lược, chốt trước khi xem test**

Tiêu chí ghi trong [benchmark/README.md](../../benchmark/README.md), áp dụng theo thứ tự:
1. Chọn cấu hình có Evidence Hit@3 trên dev cao nhất.
2. Nếu chênh lệch không quá 1 câu, chọn cấu hình có Hit@1 dev cao hơn.
3. Nếu vẫn hòa, ưu tiên coherence cao hơn, rồi đến số chunk ít hơn.

Tập test chỉ chạy một lần.

## Kết quả

Định nghĩa hit: chunk phải thuộc đúng (nguồn, trang) gold **và** chứa đủ toàn bộ evidence, so khớp sau khi chuẩn hóa khoảng trắng.

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian | Chi phí |
|---|---|---|---|---|---|---|
| A | dev | 5/15 | 9/15 | 457 | index 11,8 s; 19 ms/truy vấn | 0 |
| B | dev | 7/15 | 11/15 | 574 | index 12,2 s; 19 ms/truy vấn | 0 |
| C | dev | **8/15** | **12/15** | 574 (dùng chung index B) | không tốn thêm thời gian index; 23 ms/truy vấn | 0 |
| A | test | 4/5 | 4/5 | 457 | index 12,5 s; 27 ms/truy vấn | 0 |
| B | test | 2/5 | 4/5 | 574 | index 11,8 s; 20 ms/truy vấn | 0 |
| C | test | 3/5 | 4/5 | 574 | 36 ms/truy vấn | 0 |

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N hoặc N/A) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---|---|---|---|
| A | 0,80 (n=10; 0/1/2 = 2/8/0) | 15/15 | N/A (không lọc) | 1 / 0 / 4 → 1,6 |
| B | 1,80 (n=10; 0/1/2 = 0/2/8) | 15/15 | N/A (không lọc) | 1 / 0 / 4 → 1,6 |
| C | 1,80 (n=10; cùng chunk với B) | 15/15 | test 2/2 (dev 2/2) | 1 / 0 / 4 → 1,6 |

Ngoài ra, trên các câu có filter, Hit@3 là: dev A 1/2, B 1/2, C 2/2; test cả ba đều 2/2.

**Đường dẫn trace và nhãn thủ công, cách chọn mẫu**

- Trace top-3 đầy đủ (text, score, metadata, kết quả hit): [traces_dev.jsonl](../../starter/results/traces_dev.jsonl), [traces_test.jsonl](../../starter/results/traces_test.jsonl).
- Bảng tổng hợp: [summary_dev.csv](../../starter/results/summary_dev.csv), [summary_test.csv](../../starter/results/summary_test.csv).
- Thống kê chunk, thời gian, phiên bản: [stats_dev.json](../../starter/results/stats_dev.json), [stats_test.json](../../starter/results/stats_test.json).
- Log ingest: [ingest_log.json](../../starter/results/ingest_log.json).
- Nhãn audit: [coherence_labels.csv](../../starter/results/audit/coherence_labels.csv), [metadata_labels_test.csv](../../starter/results/audit/metadata_labels_test.csv), [grounding_labels_test.csv](../../starter/results/audit/grounding_labels_test.csv).
- Cấu hình A/B/C: [experiment_log.csv](../../artifacts/experiment_log.csv) và hằng `INDEXES` / `STRATEGIES` trong [run.py](../../starter/src/run.py); code chunking ở [chunking.py](../../starter/src/chunking.py).
- **Coherence:** chọn 10 trang cách đều nhau (5, 14, 23, …, 86) và trên mỗi trang lấy đoạn gần giữa trang nhất. Danh sách vị trí được cố định trong `run.py` trước khi xem bất kỳ điểm số nào. Với mỗi cấu hình, chấm chunk chứa vị trí đó theo quy tắc:
  - 2 điểm: đoạn ở vị trí audit nguyên vẹn, chunk tự hiểu được, không lẫn mảnh câu bị cắt;
  - 1 điểm: đoạn nguyên vẹn nhưng thiếu ngữ cảnh (điểm a/b/c đứng một mình không có câu dẫn) hoặc lẫn mảnh bị cắt của Điều khác;
  - 0 điểm: chính đoạn ở vị trí audit bị cắt ngang giữa câu hoặc giữa từ.
- **Metadata:** kiểm tra toàn bộ 45 bản ghi (5 câu × top-3 × 3 cấu hình). Đối chiếu bằng cách đọc lại PDF bằng một regex độc lập với code ingest: định vị chunk trong text thô, rồi suy ra trang, Chương và các Điều mà chunk chứa. Sau đó đọc tay các trường hợp biên.
- **Grounding:** chấm top-3 của 5 câu test. Phần này chỉ đánh giá **evidence truy xuất được**, không phải độ chính xác câu trả lời của LLM.
- **Người chấm:** các nhãn do Claude (LLM) chấm nháp, có ghi rõ lý do và cột `labeled_by` ở từng dòng. Sau đó học viên đọc lại và xác nhận ở cột `student_review`. Vì người chấm cũng biết kết quả tự động, có nguy cơ thiên lệch (xem phần Hạn chế).

## Phân tích và kết luận

**So sánh A với B (chỉ khác cách chunk)**

- Trên dev, B hơn A: Hit@3 11/15 so với 9/15, Hit@1 7/15 so với 5/15.
- Coherence của B cao hơn hẳn: 1,8 so với 0,8.
- Về cấu trúc: 188/457 chunk của A trộn từ hai Điều trở lên, trong khi B không có chunk nào như vậy.
- A trượt các câu d03, d04 và d10 vì cửa sổ cố định cắt ngang evidence:
  - **d10** (Điều 139, trang 57): cả top-3 đều đúng trang gold, nhưng chunk hạng 1 bắt đầu ở giữa câu evidence ("sản trước và sau khi sinh…"); phần đầu "1. Lao động nữ được nghỉ thai" nằm ở chunk trước.
  - **d04** (Điều 25, trang 11): chunk chứa tiêu đề Điều 25 bị cắt ngang ngay trong khoản 2 ("…chức danh nghề nghiệp cần tr"), nên mất đoạn "từ cao đẳng trở lên".
- B cũng có điểm yếu: 8 chunk rất ngắn (dưới 60 ký tự, ví dụ "3. Cách chức. 4. Sa thải.") và những chunk bắt đầu bằng điểm c/d đứng một mình không có câu dẫn (vị trí pos07, pos09). Hai vị trí này B chỉ được 1 điểm coherence.
- Trên test, Hit@3 của A và B bằng nhau (4/5), nhưng Hit@1 thì A cao hơn (4/5 so với 2/5).
  - **t03:** B xếp chunk ngắn "Điều 106. Giờ làm việc ban đêm" ở hạng 1, vì giống chữ "ban đêm" trong câu hỏi.
  - **t04:** B xếp một câu thuộc Điều 129 (có nhắc "khấu trừ hằng tháng vào lương") lên trên khoản 3 Điều 102.
  - Chunk ngắn và trọn ý giúp tăng độ chính xác của nội dung, nhưng cũng dễ bị kéo lên đầu chỉ vì trùng từ khóa.

**So sánh B với C (chỉ khác filter)**

- Hai cấu hình chỉ khác nhau ở các câu có filter.
- Ví dụ **d13** ("Thời hiệu là bao lâu…", ngữ cảnh: kỷ luật lao động, Chương VIII):
  - B lấy về Điều 194 (trang 81) và Điều 190 (trang 79), là thời hiệu giải quyết tranh chấp ở Chương XIV.
  - C lọc theo `chuong = VIII` và lấy được Điều 123 (trang 51) ở hạng 2.
- Ví dụ **t04** (Chương VI): C đưa khoản 3 Điều 102 (trang 43) từ hạng 2 lên hạng 1.
- Tuân thủ filter đạt 2/2 ở cả dev và test.
- Lọc không tốn thêm chi phí index; truy vấn chậm hơn vài mili giây. Đây là đo trên một máy, nên độ chênh nằm trong mức nhiễu.

**Hai ví dụ trượt, có ID câu và nguồn**

1. **t02** ("Nghỉ việc sau vài năm… mỗi năm làm việc được trả trợ cấp bao nhiêu?"; gold là Điều 46, trang 21).
   - Cả ba cấu hình đều trả về Điều 97 "Kỳ hạn trả lương" (trang 41) và các điều về tiền lương thử việc hoặc chuyển việc (trang 12–13).
   - Câu hỏi dùng ngôn ngữ đời thường ("nghỉ việc", "trả trợ cấp"), trong khi luật dùng thuật ngữ "trợ cấp thôi việc". Model nhỏ khớp theo các từ về "tiền lương".
   - Grounding = 0. Lỗi này nằm ở model embedding, đổi cách chunk không sửa được.
2. **d08** ("Hợp đồng lao động xác định thời hạn có thời hạn tối đa bao lâu?"; gold là Điều 20, trang 9).
   - B và C trả về toàn bộ chunk thuộc Điều 35 và Điều 36 (trang 16–17), có lặp lại cụm "hợp đồng lao động xác định thời hạn có thời hạn…" nhưng nói về thời hạn báo trước.
   - A chỉ tìm được Điều 20 ở hạng 3.
   - Khi nhiều điều luật lặp cùng một cụm thuật ngữ, cosine trên câu ngắn không phân biệt được ý chính.

Ngoài ra, d06 và d07 trượt ở cả ba cấu hình:
- d06: câu hỏi nói "cưới vợ", văn bản gốc dùng "nghỉ việc riêng" (Điều 115).
- d07: evidence gồm 2 câu trích, và top-1 rơi vào định nghĩa ở Điều 3.

**Chiến lược được chọn, đánh đổi và điều kiện áp dụng**

- Theo tiêu chí đã chốt, chọn **C**: Hit@3 dev 12/15 là cao nhất; C chỉ hơn B 1 câu nên xét tiếp Hit@1 dev, C 8/15 so với B 7/15.
- Test không xác nhận được lợi thế này:
  - Hit@3 của cả ba bằng nhau (4/5).
  - A có Hit@1 cao nhất trên test (4/5).
  - Grounding giống nhau ở cả ba (1,6/2).
- Với N = 5, mỗi câu là 20%, nên không thể kết luận cấu hình nào tốt hơn trên test. Mình không đổi lựa chọn sau khi xem test.
- Lợi ích rõ nhất của B/C là coherence (1,8 so với 0,8) và metadata `dieu_list` sạch hơn, nhờ đó truy vết về đúng một Điều.
- Đánh đổi: B/C có nhiều chunk hơn (574 so với 457) và có các chunk rất ngắn, dễ được xếp hạng cao chỉ vì trùng từ khóa.
- Filter chỉ có ích khi người dùng hoặc ngữ cảnh đã cho biết chương. Nếu cho sai chương, kết quả đúng sẽ bị loại hoàn toàn.
- Mọi kết luận ở đây chỉ áp dụng cho corpus này và model này.

**Hạn chế**

- **Mẫu nhỏ:** dev 15 câu, test 5 câu, chỉ có 4 câu dùng filter. Chênh lệch 1–2 câu chưa đủ để kết luận.
- **Model bị cắt input:** 202/457 chunk của A và 26/574 chunk của B dài hơn 128 token, nên phần đuôi không được embed. Điều này gây bất lợi nhiều hơn cho A. Mình không sửa tham số sau khi phát hiện.
- **Nhãn chấm tay:**
  - Do LLM chấm nháp và một người duyệt, không có người chấm thứ hai độc lập.
  - Người chấm đã biết kết quả tự động, nên có nguy cơ thiên lệch.
  - Coherence chỉ dựa trên 10 vị trí.
  - Do C dùng chung chunk với B, điểm coherence và metadata của C trùng với B theo cấu trúc, đó không phải hai lần đo độc lập.
- **Metadata:** cột `dieu` chỉ lưu Điều tại vị trí đầu chunk. Ví dụ chunk A chứa cả Điều 96 và 97 sẽ chỉ có `dieu = 96`, nên lọc theo `dieu = 97` sẽ bỏ sót chunk này. Muốn lọc theo Điều thì cần dùng `dieu_list`.
- **Định nghĩa hit:** so khớp nguyên văn sau chuẩn hóa nên khá nghiêm. Nếu evidence bị tách sang hai chunk, câu đó bị tính là trượt dù hai chunk gộp lại vẫn đủ thông tin (ví dụ d10 ở cấu hình A).
- **Thời gian:** đo trên một máy CPU, chỉ một lần chạy; độ trễ truy vấn dao động vài chục mili giây. Chi phí bằng 0 vì chạy local; con số này không phản ánh chi phí khi dùng API.
- **Corpus:** chỉ là văn bản gốc năm 2019, không có các lần sửa đổi sau đó.

**Nếu làm lại hoặc mở rộng**

- Dùng model có ngữ cảnh dài hơn và hiểu tiếng Việt tốt hơn (ví dụ dòng multilingual-e5 hoặc bge-m3), để hết bị cắt ở 128 token và xử lý tốt hơn các câu diễn đạt đời thường như t02, d06.
- Ở B, gắn tiêu đề Điều và câu dẫn của khoản vào từng chunk (contextual header), để điểm a/b/c không đứng một mình; gộp các chunk dưới 60 ký tự vào chunk liền kề.
- Thử hybrid retrieval, kết hợp BM25 với dense search, để bắt các thuật ngữ như "trợ cấp thôi việc".
- Mở rộng benchmark lên khoảng 50 câu và tạo một tập test mới, chưa từng xem, để kiểm chứng lại kết quả.
- Lưu `dieu_list` thành cột mảng có chỉ mục để lọc chính xác theo Điều.

**Công cụ AI và cách kiểm tra**

- Claude (Claude Code) hỗ trợ viết code pipeline, soạn nháp benchmark, chấm nháp nhãn và soạn nháp báo cáo.
- Cách kiểm tra:
  - `verify_benchmark.py` kiểm tra evidence nguyên văn trên trang gold.
  - Học viên đọc duyệt từng câu benchmark.
  - Chạy pipeline hai lần và so sánh, top-3 giống hệt nhau; DB không bị nhân đôi.
  - Metadata được đối chiếu bằng một bộ parse PDF độc lập.
  - Học viên đọc lại các nhãn chấm tay, xác nhận ở cột `student_review`.
- Mọi số liệu trong báo cáo lấy từ các file trong `starter/results/`.
