# Day 06 · Data Ingestion Engineering

**Lab cá nhân** · **4 giờ** · **Dữ liệu tự chọn**

Biến tài liệu thành kho tri thức có thể truy xuất cho AI agent, rồi đo xem cách chuẩn bị dữ liệu nào hiệu quả nhất.

| 📄 Dữ liệu | 🧩 Chiến lược | 🎯 Benchmark |
|---|---|---|
| Tối thiểu **30 trang nội dung** | Tối thiểu **3 cấu hình** | Tối thiểu **20 câu hỏi** |

## Bài làm của học viên: setup và chạy

Học viên: Nguyễn Thị Duyên (2A202603698). Corpus: Bộ luật Lao động 2019, bản Công báo. Báo cáo: [report/individual/2A202603698_NguyenThiDuyen.md](report/individual/2A202603698_NguyenThiDuyen.md).

| Thành phần | Đường dẫn |
|---|---|
| PDF nguồn (93 trang nội dung) và manifest | `starter/data/bo-luat-lao-dong-2019.pdf`, [data/manifest.json](data/manifest.json) |
| Benchmark 20 câu (15 dev / 5 test, 4 câu filter) | [benchmark/questions.jsonl](benchmark/questions.jsonl), [benchmark/README.md](benchmark/README.md) |
| Code pipeline | `starter/src/` (`ingestion`, `chunking`, `embeddings`, `store`, `evaluation`, `run`) |
| Trace top-3, bảng kết quả, thống kê, log ingest | `starter/results/` (`traces_*.jsonl`, `summary_*.csv/json`, `stats_*.json`, `ingest_log.json`) |
| Nhãn audit thủ công | `starter/results/audit/` |
| Cấu hình A/B/C | [artifacts/experiment_log.csv](artifacts/experiment_log.csv) |

Môi trường đã chạy: Windows 10, Python 3.11, Docker Desktop. Embedding chạy local trên CPU nên không cần API key và chi phí bằng 0. Lần đầu chạy sẽ tải model khoảng 470 MB từ Hugging Face.

Chạy các lệnh dưới đây trong thư mục `starter/`:

```bash
docker compose up -d
```

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
```

```bash
cp .env.example .env
```

```bash
.venv/Scripts/python -m src.ingestion
```

```bash
.venv/Scripts/python scripts/verify_benchmark.py
```

```bash
.venv/Scripts/python -m src.run --split dev
```

```bash
.venv/Scripts/python -m src.run --split test
```

Ghi chú về các lệnh:

- Trên Linux hoặc macOS, thay `.venv/Scripts/` bằng `.venv/bin/`.
- `src.ingestion` đọc PDF rồi ghi ra `results/pages.jsonl`, `results/ingest_log.json` và `data/manifest.json`.
- `verify_benchmark.py` kiểm tra evidence có nằm nguyên văn trên trang gold, kiểm tra cách chia split và các filter.
- `src.run --split dev` dựng index A và B trong pgvector (bảng `chunks`, upsert theo `chunk_id`, kèm bước kiểm tra nạp lại không nhân đôi), sau đó chạy A/B/C trên tập dev.
- `src.run --split test` chỉ chạy sau khi đã chốt cấu hình. Các file nhãn đã có trong `results/audit/` sẽ không bị ghi đè.

## Bắt đầu nhanh

Dùng [starter PostgreSQL + pgvector](starter/README.md) để dựng database và hoàn thiện các hàm TODO, hoặc tự chọn vector store tương đương. Starter chỉ là khung: **bạn tự hiện thực pipeline và benchmark**.

## 1. Xây pipeline

![Đọc tài liệu, chuẩn hóa, chia chunk, tạo vector, lưu và kiểm tra](assets/ingestion-pipeline.svg)

Chọn tài liệu được phép sử dụng; giữ **ID tài liệu, nguồn, trang/vị trí** và metadata phù hợp. Dùng embedding model thật qua API hoặc chạy local; lưu và truy xuất bằng pgvector, Qdrant, Chroma hoặc một store tương đương.

## 2. So sánh và đánh giá

![Ba chiến lược được đánh giá trên cùng corpus và benchmark dev/test](assets/benchmark-workflow.svg)

Dùng cùng dữ liệu, model và câu hỏi cho cả ba cấu hình. Tách **15 câu dev / 5 câu test** trước khi chạy; chọn cấu hình trên dev, rồi đánh giá test sau khi cố định. Mỗi câu hỏi cần có đoạn bằng chứng và trang nguồn; thiết kế bộ câu hỏi và đánh giá theo [BENCHMARK.md](BENCHMARK.md).

Đánh giá theo năm khía cạnh: **độ chính xác truy xuất**, **tính mạch lạc của chunk**, **tính hữu dụng của metadata**, **chất lượng grounding** và **tác động của chiến lược dữ liệu**. Giải thích lựa chọn bằng kết quả, ví dụ lỗi và các đánh đổi.

## 3. Chuẩn bị bài nộp

1. Chạy pipeline và lưu cấu hình, kết quả top-3, trace cùng nhãn đánh giá thủ công.
2. Điền [thông tin học viên](STUDENT.md), [nhật ký thí nghiệm](artifacts/experiment_log.csv) và bản sao [mẫu báo cáo cá nhân](report/individual/MSSV_HoTen.md).
3. Kiểm tra mã nguồn, cách chạy, manifest dữ liệu và checklist trong [SUBMISSION.md](SUBMISSION.md).

## Tài liệu hướng dẫn

| Bạn cần tìm | Tài liệu |
|---|---|
| Setup baseline PostgreSQL + pgvector | [starter/README.md](starter/README.md) |
| Các bước làm và cách tính chỉ số | [GUIDE.md](GUIDE.md) |
| Tiến độ trong 4 giờ | [CHECKPOINTS.md](CHECKPOINTS.md) |
| Năm tiêu chí benchmark và bộ câu hỏi | [BENCHMARK.md](BENCHMARK.md) |
| Tiêu chí chấm điểm | [RUBRIC.md](RUBRIC.md) |
| Quy tắc sử dụng dữ liệu, AI và API | [RULES.md](RULES.md) |
| Cách nộp bài | [SUBMISSION.md](SUBMISSION.md) |

[data/format-example.json](data/format-example.json) chỉ minh họa định dạng, không phải corpus đủ điều kiện. Phần xử lý và benchmark do bạn tự hiện thực; không bắt buộc xây chatbot.
