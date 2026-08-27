# Persona Attribute Dependency Extraction & Visualizer

Hệ thống phân tích và trích xuất các **thuộc tính Persona phụ thuộc (Persona Attribute Dependencies)** cho từng câu hỏi trong bài khảo sát (Survey Task) bằng phương pháp **Hierarchical Tree Pruning** (cắt tỉa cây phân cấp 4 tầng) từ cây Persona Taxonomy toàn cục (1,290 thuộc tính), đồng thời cung cấp giao diện trực quan hóa tương tác (D3.js Visualizer Dashboard).

---

## 📂 Cấu trúc thư mục

```
application/playground/attribute_dependency/
├── __init__.py                # Package exports
├── constants.py               # Các hằng số đường dẫn & cache
├── llm_client.py              # LLM Client wrapper (hỗ trợ OpenAI, vLLM, LiteLLM, Ollama)
├── load_tree.py               # Đọc và phân tầng cây taxonomy 4 lớp
├── prompts.py                 # Prompt templates phân tích từng tầng (Layer 1 -> 4)
├── dependency_extractor.py    # Core logic Hierarchical Attribute Pruner
├── task_processor.py          # Script xử lý trích xuất tự động cho 1 task survey
├── visualize_dependency.py    # Script sinh Dashboard HTML trực quan hóa tương tác
└── README.md                  # Tài liệu hướng dẫn sử dụng
```

---

## ⚙️ 1. Cấu hình môi trường (LLM Endpoint)

Hệ thống tự động đọc cấu hình từ file `.env` hoặc `.env.local` ở thư mục gốc hoặc `application/playground/`.

### Sử dụng Local LLM (vLLM, LiteLLM, Ollama, SGLang - vd: Qwen3-14B):
```env
LOCAL_LLM_MODEL=Qwen3-14B
LOCAL_LLM_BASE_URL=http://localhost:8000/v1
LOCAL_LLM_AUTH_HEADER=Bearer your-optional-token
```

### Sử dụng OpenAI API:
```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

---

## 🚀 2. Trích xuất Attribute Dependency cho một Job / Task

Lệnh `task_processor` sẽ đọc file câu hỏi (`questionnaire.yaml` / `.json`) và ngữ cảnh (`context.md`) từ thư mục `input/` của task, tiến hành duyệt cắt tỉa cây taxonomy 4 tầng qua LLM và lưu kết quả vào `attribute_dependencies.json`, đồng thời **tự động sinh kèm file `attribute_dependencies_visualizer.html`**.

### Cú pháp:
```powershell
python -m application.playground.attribute_dependency.task_processor <TÊN_TASK_HOẶC_ĐƯỜNG_DẪN>
```

### Ví dụ thực tế:

1. **Chạy theo tên task:**
   ```powershell
   python -m application.playground.attribute_dependency.task_processor survey_price-sensitivity-hasbro-gaming-candy-land
   ```

2. **Chạy theo đường dẫn thư mục task:**
   ```powershell
   python -m application.playground.attribute_dependency.task_processor application/tasks/survey_price-sensitivity-hasbro-gaming-candy-land
   ```

3. **Chỉ định model cụ thể:**
   ```powershell
   python -m application.playground.attribute_dependency.task_processor survey_price-sensitivity-hasbro-gaming-candy-land --model Qwen3-14B
   ```

4. **Chạy ở chế độ Mock (Test nhanh không gọi LLM API, không tốn token):**
   ```powershell
   python -m application.playground.attribute_dependency.task_processor survey_price-sensitivity-hasbro-gaming-candy-land --mock
   ```

### Kết quả đầu ra:
Sau khi chạy xong, trong thư mục `input/` của task sẽ có:
* `input/attribute_dependencies.json`: Dữ liệu JSON chứa toàn bộ thuộc tính phụ thuộc, mức độ liên quan (`high`/`medium`), lý do nhân quả (`reason`) và tập giá trị (`values`).
* `input/attribute_dependencies_visualizer.html`: File giao diện trực quan hóa HTML độc lập.

---

## 📊 3. Sinh file Visualizer & Mở Dashboard quan sát

Nếu bạn đã có sẵn file `attribute_dependencies.json` và muốn tạo lại hoặc mở ngay giao diện trực quan hóa trên trình duyệt web:

### Cú pháp:
```powershell
python -m application.playground.attribute_dependency.visualize_dependency <ĐƯỜNG_DẪN_FILE_JSON> [--open]
```

### Ví dụ:
```powershell
python -m application.playground.attribute_dependency.visualize_dependency application/tasks/survey_price-sensitivity-hasbro-gaming-candy-land/input/attribute_dependencies.json --open
```

*(Hoặc bạn chỉ cần vào Windows Explorer và click đúp chuột mở trực tiếp file `attribute_dependencies_visualizer.html` bằng bất kỳ trình duyệt nào Chrome/Edge/Firefox).*

---

## 🧭 4. Hướng dẫn sử dụng giao diện Visualizer Dashboard

Giao diện HTML trực quan hóa gồm 3 khu vực chính:

```
┌───────────────────────────┬──────────────────────────────────────────┬───────────────────────────┐
│ 1. Survey Questions (Tabs)│ 2. Interactive Tree Canvas (D3.js)       │ 3. Attribute Inspector    │
│                           │                                          │                           │
│  [🌐 GLOBAL OVERVIEW]     │  [Toolbar: Focus Active | Full Tree]     │  [Node Name & Breadcrumb] │
│                           │  [Search Box] [Zoom + / - / ↺]           │                           │
│  [Q1] q_price_matters     │                                          │  [Causal Reasoning Box]   │
│  [Q2] q_too_expensive     │  Root ──> L1 ──> L2 ──> L3 ──> [Leaf]    │                           │
│  [Q3] q_price_acceptable  │                                          │  [Allowed Values (Pills)] │
│  [Q4] q_price_vs_quality  │  (Đường đi tới các lá phụ thuộc          │                           │
│                           │   sẽ phát sáng Xanh/Cam)                 │  [Quick Attribute List]   │
└───────────────────────────┴──────────────────────────────────────────┴───────────────────────────┘
```

1. **Cột bên trái (Survey Questions):**
   - Click chọn câu hỏi bất kỳ (hoặc tab **GLOBAL OVERVIEW** để xem toàn bộ thuộc tính của survey).
   - Xem chi tiết nội dung câu hỏi, construct và loại câu hỏi.
2. **Khu vực trung tâm (Tree Canvas):**
   - Tự động làm sáng đường đi từ **Root $\rightarrow$ Leaf** của các thuộc tính liên quan đến câu hỏi đang chọn.
   - Nút **"Focus Active"**: Thu gọn các nhánh không liên quan để tập trung quan sát.
   - Nút **"Full Tree"**: Mở rộng toàn cảnh cây taxonomy.
   - **Hover vào nút lá (Leaf)**: Tooltip hiển thị ngay sát node gồm: Tên thuộc tính, Category, Mức độ liên quan (*HIGH/MED*), Lý do nhân quả (*Reasoning*), và Tập giá trị (*Values*).
   - Hỗ trợ Pan / Zoom chuột, nút **Fit Screen (⛶)**, **Expand All (+)**, **Collapse All (-)**.
   - **Ô tìm kiếm (Search box)**: Nhập tên thuộc tính để tự động tìm kiếm, mở nhánh và zoom đến node tương ứng.
3. **Cột bên phải (Attribute Inspector):**
   - Hiển thị chi tiết đường dẫn phân cấp (*Breadcrumb path*), đoạn giải thích chi tiết (*Reasoning*), và danh sách đầy đủ các giá trị (*Value pills*).
   - Danh sách **Quick Pick Chips**: Click vào bất kỳ chip thuộc tính nào để camera tự động lướt đến node đó trên cây.
4. **Nút "Load JSON" (Góc trên bên phải):**
   - Cho phép tải lên hoặc kéo thả file `attribute_dependencies.json` của bất kỳ bài khảo sát nào khác để quan sát ngay trên giao diện.

---

## 🛠️ 5. Lệnh kiểm tra và Debug bổ trợ

* **Kiểm tra kết nối LLM Client (Free text & JSON mode):**
  ```powershell
  python -m application.playground.attribute_dependency.llm_client
  ```

* **Chạy thử kịch bản mẫu cắt tỉa cây phân cấp (Console Demo):**
  ```powershell
  python -m application.playground.attribute_dependency.demo_dependency
  ```

