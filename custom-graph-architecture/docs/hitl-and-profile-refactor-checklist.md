# HITL Middleware + User-Agent Profile Ownership — Refactor Checklist

Tracking doc cho loạt quyết định kiến trúc đã chốt trong buổi review context-bloat + node/agent/tool
+ hitl_agent naming. Cập nhật trạng thái (`[ ]` → `[x]`) khi từng mục được code xong.

## Quyết định đã chốt

| # | Quyết định | Lý do |
|---|---|---|
| D1 | `user_agent` dùng `HumanInTheLoopMiddleware` để duyệt ghi đè field, không qua `hitl_agent` nữa | Approval là 1 tool call cụ thể (`update_user_profile`), khớp tự nhiên với middleware chính thức |
| D2 | `hitl_agent` đổi tên thành `plan_approval` (bỏ hậu tố `_agent`, không dùng `create_agent`), chỉ còn phục vụ duyệt plan của `coach_agent` | Đúng quy ước đặt tên hiện có; nhánh `user_agent` đã chuyển sang D1 |
| D3 | `draft_profile` + `collect_profile` giữ nguyên code, chuyển vị trí sang nhánh `user_agent` | `user_agent` là nguồn sự thật duy nhất cho profile; giảm logic điều khiển ở supervisor |
| D4 | `coach_agent` thiếu profile → trả quyền về `supervisor` (qua `summarize`), **không** đi thẳng `user_agent` | Coach không cần biết `user_agent` tồn tại; mọi điều hướng agent-tới-agent đi qua supervisor, đúng pattern các nhánh khác đã dùng |
| D5 | Supervisor **không** tự tính `missing_profile_fields`; chỉ đọc field `profile_status` do coach/user_agent set sẵn | Tránh 2 nơi cùng tính 1 business rule |
| D6 | Giữ thêm field `profile_required_for` (không bỏ như đề xuất tạm thời trước đó) | Ngăn form onboarding bật lên khi `user_agent` chỉ được gọi cho câu hỏi vặt, không liên quan tới 1 plan đang chờ |
| D7 | ~~Gộp 5 node terminal-formatter~~ — **tạm hoãn**, giữ nguyên 5 node riêng như thiết kế hiện tại | Cân nhắc lại; xem "Việc đã rà, xác nhận đúng" bên dưới |

## Hai state field mới — ngữ nghĩa chính xác

```
profile_required_for: Literal["plan"] | None
```
- Set bởi `coach_agent()` = `"plan"` khi nó phát hiện thiếu field bắt buộc, ngay trước khi bounce về supervisor.
- Đọc bởi `route_after_user_agent` để quyết định có **bắt buộc** kiểm tra completeness sau lượt chạy của `user_agent` hay không. Nếu `None` (user_agent được gọi vì lý do khác, vd hỏi vặt) → luôn đi `summarize`, không đụng tới form, bất kể profile đủ hay thiếu.
- Clear về `None` khi đã tiêu thụ xong: bởi `collect_profile()` lúc lưu thành công, hoặc bởi `user_agent()`/router khi phát hiện profile đã đủ ngay sau lượt ad-hoc (không cần qua form).

```
profile_status: Literal["ready", "need_input"] | None
```
- Set bởi `coach_agent()` = `"need_input"` cùng lúc với `profile_required_for = "plan"`.
- Set bởi `user_agent()` **chỉ khi** `profile_required_for == "plan"` (không tính completeness một cách vô ích ở lượt ad-hoc) = `"ready"` hoặc `"need_input"` tùy `missing_profile_fields()`.
- Set bởi `collect_profile()` = `"ready"` không cần tính lại (đúng lúc thoát vòng validate nghĩa là đã đủ).
- Đọc bởi `supervisor()` (đưa vào context, không tính lại) để quyết định route `user_agent` (`need_input`) hay tiếp tục `coach_agent` (`ready`).
- Đọc bởi `route_after_user_agent` cùng với `profile_required_for` để quyết định `DRAFT_PROFILE` hay `SUMMARIZE`.

## Sơ đồ luồng

```
supervisor ──(profile_status=need_input hoặc user hỏi/sửa profile)──> user_agent
                                                                          │
                                                (ad-hoc Q&A/edit; HumanInTheLoopMiddleware
                                                 chặn khi ghi đè field đã có giá trị)
                                                                          │
                                          route_after_user_agent đọc profile_required_for + profile_status
                                          ┌──────────────────────┴───────────────────────┐
                                   required_for="plan" và need_input                required_for=None
                                   hoặc required_for="plan" và ready                 (luôn tới summarize)
                                          │                        │
                                   draft_profile              summarize
                                   collect_profile (interrupt)     │
                                   → profile_status="ready"     supervisor
                                   → profile_required_for=None
                                          │
                                      summarize
                                          │
                                      supervisor ──(profile_status=ready)──> coach_agent

coach_agent ──(thiếu field)──> set profile_required_for="plan", profile_status="need_input"
                                          │
                                      summarize
                                          │
                                      supervisor ──> user_agent (theo nhánh trên)

coach_agent ──(sẵn sàng)──> deterministic_verification ──> present_plan ──> plan_approval (đổi tên hitl_agent) ──> commit_plan
```

## Checklist theo file

### Nhóm A — `user_agent` + `HumanInTheLoopMiddleware` (D1)
- [x] `src/tools/profile.py` — `update_user_profile`: bỏ nhánh trả `"status": "pending_approval"`; luôn `save_profile` khi tool thực sự chạy.
- [x] `src/agents/user.py` — thêm `HumanInTheLoopMiddleware(interrupt_on={"update_user_profile": InterruptOnConfig(allowed_decisions=["approve","reject"], when=<đọc profile hiện tại qua `load_user_context`, chỉ True nếu field đã có giá trị>)})` vào middleware list. Triển khai: `user_agent()` gọi `load_user_context` một lần ở đầu node (không phải trong `when`, vì `when` bắt buộc đồng bộ) và truyền kết quả qua `UserAgentContext.profile` (field mới); `when=_overwrites_a_stored_value` chỉ đọc lại giá trị đã tải sẵn đó.
- [x] `src/agents/user.py` — bỏ `_pending_approval`, `_tool_artifact(update_user_profile...)`, field `pending_approval` khỏi `UserAgentUpdate`.
- [x] `src/schemas/graph.py` — `PendingApproval.source` chỉ còn `"coach_agent"` (bỏ `"user_agent"` khỏi `ApprovalSource`); tương tự thu hẹp `ApprovalKind` về chỉ `"plan"` (giá trị `"profile_update"` không còn nơi nào tạo ra).
- [x] `src/nodes/commit_profile_update.py` — xóa file (write đã nằm trong tool khi approve). Hệ quả bắt buộc đi kèm (không xóa sẽ vỡ graph): bỏ đăng ký node/edge trong `src/graph.py` và import trong `src/nodes/__init__.py`; bỏ `Node.COMMIT_PROFILE_UPDATE` (`src/enums/graph.py`); bỏ nhánh `source == "user_agent"` (đã bất khả thi từ D1) khỏi `route_after_hitl` cùng hai outcome `HitlAgentRoute.USER_APPROVE`/`USER_REJECT` và hai dòng tương ứng trong `HITL_AGENT_ROUTES` — phần đổi tên còn lại (`hitl_agent`→`plan_approval`, v.v.) vẫn để dành cho Nhóm B.
- [x] `src/runtime/facade.py` — `_interrupt_text`/`_graph_input`: thêm nhánh hiểu payload `{"action_requests": [...], "review_configs": [...]}` của middleware và dựng `Command(resume={"decisions": [...]})` từ free-text reply, giữ UI không đổi. Thêm hàm `_is_hitl_request`, `_hitl_decision`, `_resume_value`.
- [x] Test: viết lại `tests/test_update_user_profile.py` (tool giờ luôn ghi khi chạy); thêm `tests/test_user_agent.py` (predicate `_overwrites_a_stored_value`, node tải profile mới trước khi gọi agent); bỏ 3 test `*_user_agent_*` đã lỗi thời trong `tests/test_hitl_agent.py`; thêm test resume cho HITL request trong `tests/test_turn_reply.py`.

### Nhóm B — `hitl_agent` đổi tên thành `plan_approval`, thu hẹp chỉ phục vụ coach (D2)
- [x] Chốt tên cuối cùng: `plan_approval`.
- [x] Xác nhận môi trường không có checkpoint Postgres đang treo phiên approval thật — kiểm tra trực tiếp trên `coaching-db` (cổng 5433, 28 thread): không thread nào có `state.next == (Node.HITL_AGENT,)`. 3 thread có `next` khác rỗng đều dừng ở `coach_agent`/`qa_agent` (phiên crash/restart giữa chừng, không liên quan đến `hitl_agent`). An toàn để đổi tên.
- [x] `src/nodes/hitl_agent.py` → đổi tên file thành `plan_approval.py`, hàm `hitl_agent` → `plan_approval`, `Node.HITL_AGENT` → `Node.PLAN_APPROVAL`. (Nhánh `source == "user_agent"` và `HitlAgentRoute.USER_APPROVE`/`USER_REJECT` đã bị xóa từ Nhóm A vì bất khả thi sau D1 — chỉ còn phần đổi tên thuần túy ở đây.)
- [x] `HitlAgentInterrupt` → `PlanApprovalInterrupt`; `HITL_AGENT_INTERRUPT` → `PLAN_APPROVAL_INTERRUPT` (giá trị `"plan_approval"`). `HitlAgentUpdate` → `PlanApprovalUpdate` (không nằm trong checklist gốc nhưng đổi theo cho nhất quán, chỉ dùng nội bộ file).
- [x] `route_after_hitl` → đổi tên `route_after_plan_approval` — còn đúng 4 outcome: `COACH_APPROVE/COACH_REVISE/COACH_NO_FEEDBACK/COACH_EXHAUSTED`.
- [x] `HitlAgentRoute` → đổi tên `PlanApprovalRoute`.
- [x] `src/graph.py`, `src/constants/routes.py` (`HITL_AGENT_ROUTES` → `PLAN_APPROVAL_ROUTES`), `src/enums/graph.py`, `src/enums/routes.py`, `src/nodes/__init__.py` — cập nhật import/tên theo trên. `USER_AGENT_ROUTES[PENDING_APPROVAL]` (vẫn còn tồn tại, sẽ dọn ở Nhóm C) cũng đổi target sang `Node.PLAN_APPROVAL` để graph còn compile được.
- [x] `tests/test_hitl_agent.py` → đổi tên file thành `tests/test_plan_approval.py`, viết lại theo scope mới (chỉ còn coach, bỏ tham số `source`/`kind` giờ luôn cố định). Cập nhật thêm các chỗ tham chiếu tên cũ ở `tests/test_form_frames.py`, `tests/test_graph_state.py` (docstring), `tests/test_node_observability.py`, `tests/test_supervisor_loop.py`, và tài liệu sống `docs/state-design.md` (không đụng các log lịch sử đã có ngày tháng `Done` trong `supervisor-migration.md`/`implementation-plan.md`).

### Nhóm C — `draft_profile`/`collect_profile` chuyển sang nhánh `user_agent` (D3, D4, D5, D6)
- [x] `src/schemas/graph.py` — thêm `profile_required_for: NotRequired[Literal["plan"] | None]` và `profile_status: NotRequired[Literal["ready","need_input"] | None]` vào `GraphState`. Đặt tên 2 alias `ProfileRequiredFor`/`ProfileStatus` (export qua `src/schemas/__init__.py`) để coach/user_agent/collect_profile khai báo `TypedDict` update mà không lặp lại `Literal`.
- [x] `src/agents/coach.py` — `coach_agent()`: nhánh `missing_profile_fields` set thêm `profile_required_for: "plan"`, `profile_status: "need_input"`.
- [x] `src/constants/routes.py` — `COACH_ROUTES[CoachRoute.NEEDS_PROFILE]` → `Node.SUMMARIZE` (không phải `USER_AGENT` hay `DRAFT_PROFILE`).
- [x] `src/agents/user.py` — `user_agent()`: nếu `profile_required_for == "plan"`, tính và set `profile_status` (`"ready"`/`"need_input"`) từ `missing_profile_fields` (tách ra helper `_profile_completion_update`, dùng chung cho cả nhánh thành công lẫn nhánh `except`); nếu không, không đụng field này.
- [x] `src/agents/user.py` — `route_after_user_agent()`: viết lại theo bảng quyết định ở trên (đọc `profile_required_for` + `profile_status`, không tính lại).
- [x] `src/enums/routes.py` — `UserAgentRoute`: bỏ `PENDING_APPROVAL`, thêm `NEEDS_MORE_INFO`, giữ `DONE`.
- [x] `src/constants/routes.py` — `USER_AGENT_ROUTES = {NEEDS_MORE_INFO: Node.DRAFT_PROFILE, DONE: Node.SUMMARIZE}`.
- [x] `src/nodes/collect_profile.py` — thêm vào return: `profile_status: "ready"`, `profile_required_for: None`. Không đổi gì khác trong logic form/validate/save.
- [x] `src/nodes/draft_profile.py` — không đổi (xác nhận: đúng là không cần đổi gì).
- [x] `src/graph.py` — đổi `add_edge(Node.COLLECT_PROFILE, Node.COACH_AGENT)` thành `add_edge(Node.COLLECT_PROFILE, Node.SUMMARIZE)`.
- [x] `src/agents/supervisor.py` — `supervisor()`: đọc `state.get("profile_status")`, đưa 1 dòng (`_profile_status_line`) vào context cho LLM qua một `SystemMessage` phụ, không tính toán lại.
- [x] `src/agents/supervisor.py` — sửa Rule 2 trong `SUPERVISOR_SYSTEM`: bỏ câu "coach collects its own missing fields"; thay bằng "khi `profile_status` là `need_input`, route `user_agent`; khi `ready`, tiếp tục plan đang chờ với `coach_agent`".
- [x] `src/ui/components/profile_form.py`, `PROFILE_FORM_INTERRUPT`, `facade.py` `_pending_form` — không đổi, payload/shape giữ nguyên (xác nhận).
- [x] Test: cập nhật `tests/test_coach_agent.py` (2 test mới cho `profile_required_for`/`profile_status`), `tests/test_collect_profile.py` (assertion mới), `tests/test_user_agent.py` (`_profile_completion_update` + `route_after_user_agent` decision table), `tests/test_supervisor.py` (2 test mới cho `_profile_status_line`); viết lại toàn bộ `tests/test_profile_collection_loop.py` (flow giờ đi qua `user_agent`, cần supervisor stub đọc `profile_status` từ message thay vì luôn chọn coach).

### Nhóm D — Context bloat trong `coach_agent` (từ phần đầu buổi review, vẫn còn mở)
- [x] `src/tools/load_exercise.py` — áp `@tool(response_format="content_and_artifact")`: `content` chỉ còn `slot_id → [{id, name}]`, `artifact` giữ full metadata (`{"exercises": [...6 field...], "slots": {...}}` như cũ). Viết lại phần lớn `tests/test_load_exercise.py` vì invoke bằng plain-args giờ chỉ trả `content`; thêm helper `_invoke()` dựng full tool-call dict để đọc `.artifact` ở các test cần metadata đầy đủ.
- [x] `src/agents/coach.py` / `src/prompts/coach_agent.py` — vá gap: `_slots_to_fix_block()` giờ nhận thêm `feedback` (từ `state.get("approval_feedback")`); khi không có `verification_result` nhưng có `feedback`, trả về hằng số mới `REVIEWER_SLOTS_TO_FIX` — một câu hướng dẫn model tự xác định slot từ `<reviewer_feedback>` + plan hiện tại, thay vì để trống hoàn toàn khiến Rule 9 ("gọi `load_exercise` cho mọi slot còn phải điền") áp dụng tràn lan. Rule 8 trong `COACH_AGENT_SYSTEM` cập nhật theo. Test mới: `tests/test_coach_context.py`.
- [x] **Phát hiện phụ khi làm mục trên — đã sửa luôn:** `approval_feedback`/`approval_decision`/`pending_approval`/`approval_retry_count` không được reset sau khi 1 vòng review kết thúc. State được checkpoint theo thread, nên `<reviewer_feedback>` (và giờ cả `REVIEWER_SLOTS_TO_FIX`) rò rỉ từ 1 lần bị từ chối cũ sang 1 lần build plan hoàn toàn mới trong cùng thread; `approval_retry_count` cũng vậy, khiến plan mới bắt đầu với budget đã tiêu một phần và có thể rơi vào `hitl_exhausted` sớm.
  - Thêm `ApprovalCycleReset` (TypedDict) + `cleared_approval()` vào `src/schemas/graph.py`, export qua `src/schemas/__init__.py`.
  - 3 node kết thúc vòng review — `commit_plan`, `hitl_rejected_no_feedback`, `hitl_exhausted` — kế thừa `ApprovalCycleReset` và spread `cleared_approval()` vào return.
  - **Không** reset ở nhánh `COACH_REVISE`: nhánh đó quay lại `coach_agent` và cần chính `approval_feedback` để sửa plan. Test mới `tests/test_approval_cycle_reset.py` chốt cả 3 nhánh terminal lẫn ràng buộc "revise không phải terminal".
- [ ] **Chưa xác minh được — cần input từ người review:** `data/input.json` không tồn tại trong working tree lẫn git history của repo này (`find`/`git log --all` đều rỗng). Có thể là file tạm/export cục bộ từ phiên review gốc, chưa từng được commit. Không thể xác minh nguồn gốc 3 block tool-schema cuối nếu không có file — cần người review cung cấp lại file hoặc làm rõ nó nằm ở đâu trước khi mục này có thể đóng.

### Test cần viết/sửa
- [x] `tests/test_hitl_agent.py` → đổi tên `tests/test_plan_approval.py`, viết lại (Nhóm B).
- [x] `tests/test_coach_agent.py` (Nhóm C).
- [x] `tests/test_collect_profile.py` (Nhóm C).
- [x] `tests/test_supervisor_loop.py` (Nhóm B: tên node đổi trong assertion `.next`).
- [x] `tests/test_form_frames.py` (Nhóm B: `HITL_AGENT_INTERRUPT` → `PLAN_APPROVAL_INTERRUPT`).

## Việc đã rà, xác nhận đúng — không cần sửa

- `trim_history`, `summarize` node (đã dùng đúng pattern `RemoveMessage` + `trim_messages` chính thức của LangGraph).
- `_narrowed_plan`/`_merge_revised_days` trong `coach.py` — partial-update giữa verification-retry và HITL-revise không chồng lấn.
- `hitl_agent` gộp 2 nguồn approval trước đây — đúng trục gộp (cùng cơ chế, khác dữ liệu); giờ tách lại chỉ vì `user_agent` đổi cơ chế (D1), không phải vì gộp sai.
- 5 node terminal-formatter (`blocked`, `notify_fail`, `hitl_rejected_no_feedback`, `hitl_exhausted`, `qa_fallback`) — **giữ nguyên, không gộp** (D7 tạm hoãn). Mỗi node có span Langfuse riêng phục vụ observability theo chủ đích đã ghi trong `graph.py`; ngoài ra `blocked` đi thẳng `END` còn 4 node kia qua `SUMMARIZE`, và `notify_fail`/`qa_fallback` có logic dựng message riêng từ state khác nhau — gộp cần thêm 1 field discriminator (`terminal_reason`) + tách predicate dùng chung với router, nếu sau này muốn làm lại thì tham khảo lại điểm này.
- `supervisor`, `draft_profile`, `verify_faithfulness` — đúng khi là node thường (1 lệnh LLM) thay vì `create_agent`.
