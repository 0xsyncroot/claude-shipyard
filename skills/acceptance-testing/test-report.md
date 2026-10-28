# Test completion report (T6) — for the test lead

`qa.py report <slug>` → `.qa/<slug>/report.html` (self-contained page; evidence images linked relatively, `--embed` inlines evidence images — can reach tens of MB on a large suite (68 TCs ≈ 80 MB); share the folder instead). `--plan` renders the design only (basis, cases, coverage) before execution. Publish as an Artifact only when the user asks; otherwise give the local path.

## What the page contains (ISO/IEC/IEEE 29119-3 §7.4 mapping)

| Section on the page | 29119-3 element | Source |
|---|---|---|
| Kết luận + verdict "SẴN SÀNG BÀN GIAO" / "CHƯA ĐẠT" | completion evaluation | exit criteria evaluated by the script |
| Tiêu chí kết thúc (each ✓/✗ with the measured value) | completion evaluation | results + defects + lint |
| Quy trình (SVG flow with counts) | summary of testing performed | runs + defects |
| Số liệu: by status / priority / type / surface; coverage basis → TC | test measures | testcases.yml + latest results |
| Lỗi (BUG list with lifecycle, owner, reopen count); "Gửi team thi công" (open ones) | incident reports | defects/*.md |
| Lịch sử chạy + trước/sau sửa (screenshots side by side) | summary / confirmation testing | runs/*/results.json |
| Chi tiết test case (filterable cards: steps, expected, result per viewport, error, evidence) | test case specification + execution log | testcases.yml + results |
| Thi công (wave mode: stage log, AC board, `git diff --stat BASE..HEAD`) | — (the user asked for build + test in one report) | .wave/<slug>/STATUS.md + git |
| Sai lệch so với kế hoạch · Yếu tố cản trở · Rủi ro còn lại · Bài học | deviations · blocking factors · residual risks · lessons learned | sections of `.qa/<slug>/STATUS.md` the lead writes |
| Fact / Assumption / Unknown | — (user's review rule) | STATUS section |
| Nguồn | test deliverables / reusable assets | file list |

## Lead checklist before generating

- [ ] Final full run done on the hand-over build; its run id is the latest.
- [ ] Every BUG has a current status and history line; deferred ones carry the user's verbatim OK.
- [ ] STATUS sections Deviations / Blocking factors / Residual risks / Lessons learned / Fact-Assumption-Unknown filled (one line "none" is fine).
- [ ] You opened the P0 screenshots yourself.
- [ ] Test data cleaned (0 prefixed rows).

Then tell the user in their language: verdict, P0/total pass counts, open defects by severity, residual risks, report path.
