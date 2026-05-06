# Hướng Dẫn Làm Bài - Multi-Agent Research Lab

Tài liệu này tóm tắt cách làm bài lab theo đúng yêu cầu trong `README.md`,
`docs/lab_guide.md`, `docs/design_template.md`, `docs/peer_review_rubric.md`,
`CONTRIBUTING.md` và `notebooks/README.md`.

## 1. Mục Tiêu Bài Lab

Cần xây dựng một **research assistant** có 2 chế độ:

1. **Single-agent baseline**: một agent tự tìm hiểu, phân tích và viết câu trả lời.
2. **Multi-agent workflow**: `Supervisor` điều phối `Researcher`, `Analyst`, `Writer`.

Sau đó benchmark để so sánh hai cách tiếp cận theo metric cụ thể, không chỉ nhìn
output bằng cảm tính.

## 2. Quy Tắc Quan Trọng

- Không thêm agent nếu không có lý do rõ ràng.
- Mỗi agent phải có responsibility riêng, hạn chế overlap.
- Shared state phải đủ rõ để debug và handoff.
- Phải có trace hoặc log cho từng bước.
- Phải có benchmark single-agent vs multi-agent.
- Không commit `.env`, API key, secret.
- Production code nằm trong `src/`; notebook chỉ nên dùng để demo hoặc thử nghiệm.

## 3. Setup Môi Trường

Repo yêu cầu Python `>=3.11`.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev,llm]"
copy .env.example .env
```

Nếu dùng Git Bash/macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,llm]"
cp .env.example .env
```

Mở `.env` và điền các key cần thiết:

```bash
OPENAI_API_KEY=...
# optional
LANGSMITH_API_KEY=...
TAVILY_API_KEY=...
```

Chạy smoke test:

```bash
make test
python -m multi_agent_research_lab.cli --help
```

Ghi chú về `mypy` trên máy này:

```bash
make typecheck
# hoặc chạy trực tiếp
mypy src tests --cache-dir .mypy_cache_local --no-sqlite-cache
```

Lý do là môi trường Windows hiện tại có thể lỗi `disk I/O error` nếu `mypy` dùng
SQLite cache mặc định.

## 4. Thứ Tự Làm Bài Khuyến Nghị

### Bước 1: Implement LLM Client

File: `src/multi_agent_research_lab/services/llm_client.py`

Việc cần làm:

- Kết nối OpenAI SDK hoặc provider khác.
- Implement `LLMClient.complete(system_prompt, user_prompt)`.
- Trả về `LLMResponse(content, input_tokens, output_tokens, cost_usd)`.
- Đặt retry, timeout và token/cost logging trong client, không rải rác trong agents.

Ví dụ với OpenAI SDK mới (`openai>=1.40`):

```python
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from multi_agent_research_lab.core.config import get_settings


class LLMClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.client = OpenAI(api_key=settings.openai_api_key, timeout=settings.timeout_seconds)
        self.model = settings.openai_model

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        usage = response.usage
        return LLMResponse(
            content=response.choices[0].message.content or "",
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
        )
```

Ghi chú: có thể dùng provider khác, miễn là giữ interface `LLMClient` để agents
không import SDK trực tiếp.

### Bước 2: Implement Search Client

File: `src/multi_agent_research_lab/services/search_client.py`

Việc cần làm:

- Option A: dùng Tavily, Bing, SerpAPI hoặc search provider khác.
- Option B: dùng mock/local source để có workflow chạy nhanh trong lab.
- Trả về `list[SourceDocument]`.

Mock tối thiểu:

```python
def search(self, query: str, max_results: int = 5) -> list[SourceDocument]:
    return [
        SourceDocument(
            title=f"Source {i + 1}: {query}",
            url=f"https://example.com/source-{i + 1}",
            snippet=f"Relevant information about {query}.",
        )
        for i in range(min(max_results, 3))
    ]
```

### Bước 3: Implement Single-Agent Baseline

File: `src/multi_agent_research_lab/cli.py`

Mục tiêu milestone 1 là thay placeholder baseline bằng một LLM call thật.

Việc cần làm:

- Tạo `ResearchState` từ query.
- Gọi `LLMClient.complete(...)`.
- Ghi `state.final_answer`.
- Đo latency và token/cost nếu có.
- Lưu metric để benchmark sau này.
- Nếu thiếu `OPENAI_API_KEY` hoặc provider lỗi, CLI nên báo lỗi rõ ràng thay vì in
  placeholder.

Chạy thử:

```bash
python -m multi_agent_research_lab.cli baseline --query "Research GraphRAG state-of-the-art and write a 500-word summary"
```

### Bước 4: Implement Supervisor / Routing Policy

Files:

- `src/multi_agent_research_lab/agents/supervisor.py`
- `src/multi_agent_research_lab/graph/workflow.py`

Routing policy tối thiểu:

1. Nếu đạt `max_iterations` thì route `done`.
2. Nếu chưa có `research_notes` thì route `researcher`.
3. Nếu có `research_notes` nhưng chưa có `analysis_notes` thì route `analyst`.
4. Nếu có `analysis_notes` nhưng chưa có `final_answer` thì route `writer`.
5. Nếu đã có `final_answer` thì route `done`.

Giá trị `max_iterations` và `timeout_seconds` nên lấy từ config/env. Config mặc định
hiện tại là `max_iterations=6` và `timeout_seconds=60`, không nên hard-code trong
nhiều file.

Ví dụ:

```python
def run(self, state: ResearchState) -> ResearchState:
    settings = get_settings()

    if state.iteration >= settings.max_iterations:
        next_route = "done"
    elif not state.research_notes:
        next_route = "researcher"
    elif not state.analysis_notes:
        next_route = "analyst"
    elif not state.final_answer:
        next_route = "writer"
    else:
        next_route = "done"

    state.record_route(next_route)
    state.add_trace_event(
        "supervisor_route",
        {"next": next_route, "iteration": state.iteration},
    )
    return state
```

Nâng cao: có thể để LLM quyết định route, nhưng vẫn phải có guardrail để dừng vòng
lặp và fallback khi lỗi.

### Bước 5: Implement Worker Agents

Files:

- `src/multi_agent_research_lab/agents/researcher.py`
- `src/multi_agent_research_lab/agents/analyst.py`
- `src/multi_agent_research_lab/agents/writer.py`

`Researcher`:

- Gọi `SearchClient.search(...)`.
- Tổng hợp source thành `research_notes`.
- Cập nhật `state.sources` và `state.research_notes`.
- Ghi trace event.

`Analyst`:

- Đọc `state.research_notes`.
- Rút ra key claims, insight, contradiction, evidence gap.
- Cập nhật `state.analysis_notes`.
- Ghi trace event.

`Writer`:

- Đọc `state.research_notes`, `state.analysis_notes`, `state.sources`.
- Viết câu trả lời cuối cùng có citation/source reference.
- Cập nhật `state.final_answer`.
- Ghi trace event.

Trong repo có `agents/critic.py` là optional bonus. Chỉ thêm vào workflow nếu có lý
do rõ ràng, vì rubric ưu tiên role clarity và không thêm agent thừa.

### Bước 6: Build LangGraph Workflow

File: `src/multi_agent_research_lab/graph/workflow.py`

Việc cần làm:

- Tạo `StateGraph` với nodes: `supervisor`, `researcher`, `analyst`, `writer`.
- Entry point là `supervisor`.
- Conditional edge từ `supervisor` dựa trên route mới nhất trong `route_history`.
- Mỗi worker chạy xong quay về `supervisor`.
- Khi route là `done` thì kết thúc graph.
- `run(...)` cần trả về `ResearchState`; nếu LangGraph trả về dict thì convert lại.

Skeleton logic:

```python
from langgraph.graph import END, StateGraph


class MultiAgentWorkflow:
    def build(self):
        graph = StateGraph(ResearchState)

        graph.add_node("supervisor", SupervisorAgent().run)
        graph.add_node("researcher", ResearcherAgent().run)
        graph.add_node("analyst", AnalystAgent().run)
        graph.add_node("writer", WriterAgent().run)

        graph.set_entry_point("supervisor")

        def router(state: ResearchState) -> str:
            last_route = state.route_history[-1] if state.route_history else "done"
            return END if last_route == "done" else last_route

        graph.add_conditional_edges(
            "supervisor",
            router,
            {
                "researcher": "researcher",
                "analyst": "analyst",
                "writer": "writer",
                END: END,
            },
        )

        for node in ["researcher", "analyst", "writer"]:
            graph.add_edge(node, "supervisor")

        return graph.compile()
```

### Bước 7: Trace / Observability

Files:

- `src/multi_agent_research_lab/observability/tracing.py`
- `src/multi_agent_research_lab/observability/logging.py`
- `src/multi_agent_research_lab/core/state.py`

Yêu cầu tối thiểu:

- Mỗi agent ghi `state.add_trace_event(...)`.
- Trace cho biết agent nào làm gì, route nào được chọn, tốn bao nhiêu latency/token
  nếu có.
- Nếu dùng LangSmith/Langfuse/OpenTelemetry thì thêm link trace vào report.
- Nếu không dùng tracing provider, xuất trace JSON/local log vẫn chấp nhận được nếu
  giải thích rõ.

Tích hợp Langfuse trong repo hiện tại:

- Điền các biến sau vào `.env`:

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_ENABLED=true
```

- Cài dependency:

```bash
pip install -e ".[llm]"
```

- Khi đã cấu hình đúng, `baseline` và `multi-agent` sẽ tự:
  - gửi trace lên Langfuse
  - in `langfuse_trace_url` ra console
  - vẫn lưu trace cục bộ vào `reports/traces/*.json` và `reports/traces/*.md`

Yêu cầu ảnh chụp trace:

- Mở `langfuse_trace_url` sau khi chạy lệnh.
- Chụp màn hình trang trace trong Langfuse.
- Đưa ảnh đó vào report hoặc nộp kèm như deliverable.

### Bước 8: Benchmark

Files:

- `src/multi_agent_research_lab/evaluation/benchmark.py`
- `src/multi_agent_research_lab/evaluation/report.py`
- `configs/lab_default.yaml`
- `reports/benchmark_report.md`

Chạy benchmark với ít nhất 3 query trong `configs/lab_default.yaml`.

Metric tối thiểu:

| Metric | Cách đo gợi ý |
|---|---|
| Latency | wall-clock time / `perf_counter()` |
| Cost | token usage hoặc provider usage |
| Quality | điểm 0-10 theo peer review/rubric |
| Citation coverage | số claims có source / tổng claims chính |
| Failure rate | số query fail / tổng query |

Report cần so sánh single-agent vs multi-agent bằng metric cụ thể, kèm nhận xét
ưu/nhược điểm và failure mode.

### Bước 9: Điền Design Template

File: `docs/design_template.md`

Cần điền:

- `Problem`: task cụ thể hệ thống cần xử lý.
- `Why multi-agent`: tại sao single-agent baseline chưa đủ trong task này.
- `Agent roles`: responsibility, input, output, failure mode của từng agent.
- `Shared state`: các field trong `ResearchState` và lý do cần field đó.
- `Routing policy`: mô tả graph/route policy.
- `Guardrails`: max iterations, timeout, retry, fallback, validation.
- `Benchmark plan`: query, metric, expected outcome.

### Bước 10: Viết Benchmark Report

File: `reports/benchmark_report.md`

Nội dung nên có:

- Bảng kết quả single-agent vs multi-agent.
- Latency, cost/token, quality, citation coverage, failure rate.
- Screenshot trace hoặc link trace.
- Giải thích agent nào làm gì trong trace.
- Một failure mode cụ thể và cách fix.
- Nhận xét khi nào nên và không nên dùng multi-agent.

## 5. Làm Bonus

Phần bonus hiện phù hợp nhất với repo này là dùng `agents/critic.py` như một agent
kiểm tra chất lượng đầu ra sau `Writer`.

Mục tiêu bonus:

- Kiểm tra factual risk hoặc hallucination risk trong `final_answer`.
- Đánh giá citation coverage: claim nào có source, claim nào thiếu source.
- Đề xuất sửa hoặc yêu cầu quay lại bước phân tích/viết nếu chất lượng chưa đạt.

Files liên quan:

- `src/multi_agent_research_lab/agents/critic.py`
- `src/multi_agent_research_lab/graph/workflow.py`
- `src/multi_agent_research_lab/core/state.py`
- `src/multi_agent_research_lab/evaluation/benchmark.py`
- `reports/benchmark_report.md`

Cách làm bonus khuyến nghị:

1. Implement `CriticAgent.run(state)` để đọc `final_answer`, `sources`,
   `research_notes`, `analysis_notes`.
2. Cho `Critic` trả ra nhận xét có cấu trúc, ví dụ:
   - Các claim mạnh và có hỗ trợ từ source
   - Các claim thiếu bằng chứng
   - Các chỗ nên viết lại rõ hơn
   - Kết luận `pass` hoặc `needs_revision`
3. Mở rộng `ResearchState` nếu cần thêm field như:
   - `critic_notes`
   - `quality_score`
   - `citation_coverage`
4. Nối `critic` vào workflow theo một trong hai cách:
   - Cách đơn giản: `writer -> critic -> done`
   - Cách tốt hơn: `writer -> critic`, nếu `needs_revision` thì quay lại `writer`
     hoặc `analyst`, nếu `pass` thì `done`
5. Ghi trace rõ ràng để khi peer review có thể giải thích vì sao `critic` cho qua
   hoặc yêu cầu sửa.

Ví dụ routing bonus:

```python
if last_route == "writer":
    return "critic"
if last_route == "critic" and state.quality_score is not None and state.quality_score >= 8:
    return END
if last_route == "critic":
    return "writer"
```

Lưu ý khi làm bonus:

- Chỉ thêm `Critic` nếu bạn giải thích được vì sao role này không overlap quá nhiều
  với `Analyst`.
- Phải có guardrail để tránh loop `writer <-> critic` vô hạn.
- Bonus chỉ có giá trị nếu benchmark hoặc trace cho thấy nó cải thiện chất lượng,
  citation coverage, hoặc giảm failure mode.

Cách viết vào report:

- Nêu rõ đây là `bonus extension`.
- So sánh `multi-agent cơ bản` với `multi-agent + critic`.
- Chỉ ra tradeoff: thường tăng latency/cost nhưng có thể tăng quality hoặc giảm
  hallucination risk.

## 6. Checklist Trước Khi Nộp

- [ ] Tạo branch riêng cho bài làm.
- [ ] LLM client hoạt động.
- [ ] Search client hoạt động hoặc có mock source hợp lý.
- [ ] Single-agent baseline chạy được.
- [ ] Supervisor có routing policy rõ ràng.
- [ ] Researcher, Analyst, Writer có responsibility riêng.
- [ ] LangGraph workflow chạy end-to-end.
- [ ] Có trace/log cho từng bước.
- [ ] Benchmark report nằm ở `reports/benchmark_report.md`.
- [ ] `docs/design_template.md` đã điền đầy đủ.
- [ ] Không commit `.env`, API key, secret.
- [ ] Chạy `make lint`.
- [ ] Chạy `make typecheck`.
- [ ] Chạy `make test`.
- [ ] Trả lời exit ticket:
  - Case nào nên dùng multi-agent? Vì sao?
  - Case nào không nên dùng multi-agent? Vì sao?

## 7. Tiêu Chí Peer Review

Mỗi nhóm review repo/trace của một nhóm khác trong 8 phút.

| Tiêu chí | Câu hỏi | Điểm |
|---|---|---:|
| Role clarity | Mỗi agent có nhiệm vụ rõ, không overlap quá nhiều không? | 0-2 |
| State design | Shared state có đủ thông tin để handoff mà không mất context không? | 0-2 |
| Failure guard | Có max iterations, timeout, retry/fallback, validation không? | 0-2 |
| Benchmark | Có so sánh single vs multi-agent bằng metric cụ thể không? | 0-2 |
| Trace explanation | Nhóm giải thích được trace: ai làm gì, tốn bao nhiêu, sai ở đâu không? | 0-2 |
| **Tổng** |  | **0-10** |

Feedback format:

```text
Strength:
Risk / failure mode:
One concrete improvement:
Score:
```

## 8. Deliverables Cuối Cùng

1. GitHub repo cá nhân.
2. Screenshot trace hoặc link trace.
3. `reports/benchmark_report.md` so sánh single-agent vs multi-agent.
4. Một đoạn giải thích failure mode và cách fix.
5. Câu trả lời exit ticket trong report hoặc file riêng.
