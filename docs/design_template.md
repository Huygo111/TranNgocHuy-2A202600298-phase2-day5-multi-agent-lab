# Design Template

## Problem

Hệ thống cần nhận một câu hỏi nghiên cứu tương đối mở, sau đó:

- tìm nguồn liên quan,
- tổng hợp ghi chú nghiên cứu,
- phân tích các ý chính,
- viết câu trả lời cuối cùng có cấu trúc rõ ràng.

Task này phù hợp với bài lab vì có nhiều pha xử lý khác nhau: tìm thông tin, phân tích, và tổng hợp câu trả lời. Nếu dồn toàn bộ vào một lần gọi model duy nhất thì rất khó quan sát từng bước và khó kiểm soát chất lượng handoff.

## Why Multi-Agent?

Single-agent baseline có ưu điểm là nhanh và rẻ hơn, nhưng có ba hạn chế chính:

1. Không tách riêng pha tìm nguồn và pha phân tích, nên khó biết lỗi đến từ đâu.
2. Không có shared state trung gian để debug hoặc benchmark từng bước.
3. Khó gắn guardrails cho từng nhiệm vụ chuyên biệt.

Multi-agent workflow giúp chia nhỏ trách nhiệm:

- `Researcher` tập trung tìm nguồn và tạo `research_notes`
- `Analyst` chuyển ghi chú nghiên cứu thành `analysis_notes`
- `Writer` dùng hai lớp ngữ cảnh trên để viết `final_answer`
- `Supervisor` giữ vai trò router, bảo đảm workflow đi đúng thứ tự và dừng đúng lúc

Trade-off là multi-agent tốn thêm latency và cost, nhưng bù lại trace rõ hơn và chất lượng lập luận/citation tốt hơn.

## Agent Roles

| Agent | Responsibility | Input | Output | Failure mode |
|---|---|---|---|---|
| Supervisor | Quyết định bước kế tiếp dựa trên shared state và giới hạn iteration | `ResearchState` hiện tại | route tiếp theo trong `route_history` | route sai thứ tự, không dừng, hoặc bỏ qua bước cần thiết |
| Researcher | Tìm nguồn, chuẩn hóa nguồn và tạo ghi chú nghiên cứu ban đầu | `request.query`, `request.max_sources` | `sources`, `research_notes`, `agent_results` | search key thiếu, query rỗng, nguồn nghèo nàn, LLM fail |
| Analyst | Phân tích `research_notes`, rút ra insight, trade-off, risk | `research_notes`, `sources`, `request.query` | `analysis_notes`, `agent_results` | thiếu `research_notes`, phân tích hời hợt, LLM fail |
| Writer | Viết câu trả lời cuối cùng từ research + analysis | `research_notes`, `analysis_notes`, `sources`, `request.query` | `final_answer`, `agent_results` | thiếu context đầu vào, câu trả lời không nhất quán, LLM fail |

## Shared State

Shared state nằm trong `ResearchState` và là nguồn dữ liệu duy nhất đi qua toàn workflow.

| Field | Vai trò |
|---|---|
| `request` | Chứa `query`, `max_sources`, `audience`; mọi agent đều cần biết đầu bài |
| `iteration` | Đếm số vòng lặp supervisor-routing để chặn loop vô hạn |
| `route_history` | Ghi lại thứ tự route để debug và benchmark |
| `sources` | Danh sách nguồn tìm được từ `Researcher`; dùng lại cho `Analyst` và `Writer` |
| `research_notes` | Ghi chú tổng hợp từ nguồn; là đầu vào chính cho `Analyst` |
| `analysis_notes` | Phân tích trung gian; là đầu vào chính cho `Writer` |
| `final_answer` | Kết quả cuối cùng trả về cho người dùng |
| `critic_notes` | Nhận xét hậu kiểm của `CriticAgent` trong bonus extension |
| `quality_score` | Điểm chất lượng 0-10 do `CriticAgent` sinh ra |
| `citation_coverage` | Tỷ lệ nguồn được nhắc lại trong câu trả lời cuối; dùng cho benchmark |
| `agent_results` | Lưu output + metadata của từng agent để ước lượng cost và kiểm tra từng bước |
| `trace` | Event-level trace cục bộ để export JSON/Markdown và đối chiếu với Langfuse |
| `errors` | Thu thập lỗi logic hoặc lỗi runtime nếu muốn mở rộng fallback trong tương lai |

Lý do thiết kế như vậy là để mỗi handoff đều có dữ liệu cụ thể, dễ benchmark và không phụ thuộc vào hidden context bên trong model.

## Routing Policy

Workflow hiện dùng policy rule-based thay vì để supervisor tự quyết hoàn toàn bằng LLM. Lý do là lab này ưu tiên tính ổn định và dễ kiểm chứng.

Luật route:

1. Nếu `iteration >= max_iterations` thì route `done`
2. Nếu chưa có `research_notes` thì route `researcher`
3. Nếu chưa có `analysis_notes` thì route `analyst`
4. Nếu chưa có `final_answer` thì route `writer`
5. Nếu đã có đủ output thì route `done`

Graph thực tế:

```text
START
  |
  v
Supervisor
  |----> Researcher ----|
  |----> Analyst -------|----> Supervisor
  |----> Writer --------|
  |
  v
 DONE
```

Flow chạy thực tế của benchmark:

```text
supervisor -> researcher -> analyst -> writer -> done
```

Bonus flow:

```text
supervisor -> researcher -> analyst -> writer -> critic -> done
```

## Guardrails

- Max iterations: dùng `MAX_ITERATIONS`, mặc định `6`
- Timeout: dùng `TIMEOUT_SECONDS`, mặc định `60s`
- Retry: `LLMClient` retry cho `APIConnectionError`, `APITimeoutError`, `RateLimitError`
- Fallback:
  - nếu chưa có `TAVILY_API_KEY` thì `SearchClient` fallback sang mock search results để lab vẫn chạy
  - nếu Langfuse không cấu hình đúng thì trace fallback về local trace thay vì làm workflow crash
- Validation:
  - chặn prompt rỗng ở `LLMClient`
  - chặn query rỗng hoặc `max_results < 1` ở `SearchClient`
  - `Analyst` yêu cầu phải có `research_notes`
  - `Writer` yêu cầu phải có `research_notes` và `analysis_notes`
  - `Critic` yêu cầu phải có `final_answer`
- Observability:
  - trace cục bộ ghi vào `state.trace`
  - export artifact tại `reports/traces/*.json` và `reports/traces/*.md`
  - trace cloud trên Langfuse để xem timeline model calls
- Bonus control:
  - `ENABLE_CRITIC=false` theo mặc định để không làm thay đổi flow cơ bản
  - bonus chỉ bật khi gọi `multi-agent --enable-critic` hoặc `benchmark --include-critic`

## Benchmark Plan

### Queries

Benchmark dùng 3 query trong `configs/lab_default.yaml`:

1. `Research GraphRAG state-of-the-art and write a 500-word summary`
2. `Compare single-agent and multi-agent workflows for customer support`
3. `Summarize production guardrails for LLM agents`

### Metrics

- Latency: wall-clock time cho mỗi run
- Estimated cost: tổng `cost_usd` từ baseline trace hoặc `agent_results`
- Citation coverage: tỷ lệ nguồn được nhắc lại trong câu trả lời cuối
- Failure rate: số run fail / tổng run
- Quality score: do `CriticAgent` sinh ra ở biến thể bonus; baseline và multi-agent cơ bản để trống

### Expected Outcome

- `baseline` nhanh hơn và rẻ hơn
- `multi-agent` chậm hơn và tốn thêm cost vì có nhiều lần gọi model
- `multi-agent` có citation coverage tốt hơn do có bước `Researcher` chuyên trách và shared state rõ ràng
- trace của `multi-agent` giàu thông tin hơn, phù hợp để debug hơn baseline

### Actual Outcome

Kết quả benchmark thật cuối cùng:

- `baseline`: latency trung bình `14.54s`, cost trung bình `0.0005 USD`, citation coverage `0.00`
- `multi-agent`: latency trung bình `23.73s`, cost trung bình `0.0013 USD`, citation coverage `0.56`
- `multi-agent-critic`: latency trung bình `29.02s`, cost trung bình `0.0015 USD`, quality score trung bình `7.00`, citation coverage `0.33`
- failure rate của cả ba biến thể: `0.00`

Diễn giải:

- `multi-agent` cải thiện citation coverage so với baseline và vẫn giữ cost/latency ở mức chấp nhận được.
- `multi-agent-critic` thêm một lớp đánh giá chất lượng, nhưng vì hiện tại `CriticAgent` chỉ review chứ chưa tự sửa lại câu trả lời nên bonus này tăng observability hơn là cải thiện trực tiếp citation coverage.

Artifact liên quan:

- benchmark report: `reports/benchmark_report.md`
- benchmark metrics: `reports/benchmark_metrics.json`
- Langfuse screenshot: `reports/traces/screenshot_trace.png`
- trace summary cục bộ: `reports/traces/*.md`
