# Day 3 Same-Corpus New-Question Check

## Conclusion

**Completed.** Eight frozen, newly authored questions were evaluated once through the current production BM25 retrieval and generation path. All eight completed. The six answerable questions were factually complete and cited supporting evidence; the two insufficient-evidence questions correctly refused without unsupported claims.

This is a small new-question check on the same corpus. It is not tuning, does not establish generalization to new documents, and is not whole-domain accuracy.

## Frozen Inputs And Runtime

- Execution date/time zone: 2026-10-26, Asia/Shanghai.
- HEAD: `8e0035f`.
- Frozen at: `2026-10-26T15:47:05+08:00`.
- Question count: 8 (6 answerable, 2 insufficient-evidence).
- Canonical question-set SHA-256: `ef8c2c26bd0526abfe6500731584dbbac3b31589e98e8831e1f3517b6dfeb032`.
- Question-file SHA-256: `64edcb85b9711137dc92f41b2bedf12ff62a3249bcf8511b39f8e6b9deec9686`.
- Corpus: `geoexplore-v1`, fingerprint `07931977ad3ff8a5ae743b5ed96ea92d0c87f0b4a8fb6a1aaa1be7e72ef2575f`; 6 documents and 1006 chunks.
- Documents represented by answerable items: `geo-1996-21`, `geo-fs11503`, `geo-report-1989-4195`, `geo-s10950-021-10042-z`, and `geo-of12-1191`.
- Retrieval: production BM25, `top_k=5`, production predecessor expansion, at most 4 context chunks, at most 900 characters per chunk.
- Generation: `deepseek-flash`, temperature `0.0`, `llm_max_retries=1` (`max_attempts=1`), and the existing parser repair policy (at most one repair).
- Runtime storage: in-memory SQLite; Redis disabled.

Questions were authored from source PDFs and parsed chunks before running retrieval. Their evidence notes and overlap checks are frozen in `questions.json`. They do not reuse prior Acceptance questions or use retrieval ranking to select questions.

## Per-Question Review

| ID | Expected | Retrieval / final context | Actual result and manual review | Citation, filter, usage / latency |
| --- | --- | --- | --- | --- |
| `geo-day3-001` | Answer | Gold `_22`: rank 1, seed/expanded/final present. | Correct: BLIMP is completely insensitive to overall seismic-data scale, while recursion is not. | `geo-1996-21_22`, PDF p. 7; filter compliant. 864 tokens, 1723.723 ms. |
| `geo-day3-002` | Answer | Gold `_38`: rank 1, seed/expanded/final present. | Correct: about 23 percent, or 5 of 23 miles, with likely bedrock reflectors correlated to logs. | `geo-fs11503_38`, PDF p. 6; filter compliant. 981 tokens, 1325.753 ms. |
| `geo-day3-003` | Answer | Gold `_52`: rank 1, seed/expanded/final present. | Correct: navigation fix marks were generally placed every 60 seconds. | `geo-report-1989-4195_52`, PDF p. 16; filter compliant. 966 tokens, 1102.392 ms. |
| `geo-day3-004` | Answer | Gold `_28`: rank 1, seed/expanded/final present. | Correct: a plus/minus 10 percent refraction-velocity error was estimated from first-break-picking sensitivity analysis. | `geo-s10950-021-10042-z_28`, PDF p. 4; filter compliant. 879 tokens, 838.819 ms. |
| `geo-day3-005` | Answer | Gold `_47`: rank 1, seed/expanded/final present. | Correctly listed the rapid-pulse source, hydrophone/streamer, processor, graphic recorder, and retained raw unfiltered magnetic-tape recording. | `geo-report-1989-4195_47`, PDF p. 14; filter compliant. 978 tokens, 1159.415 ms. |
| `geo-day3-006` | Answer | `_61`: rank 6, not a top-5 seed but brought in by predecessor expansion; `_62`: rank 1. Both final. | Correctly gave Line A 385-470 ft, Line B 375-415 ft, and an approximately north-northwest trend. | `geo-of12-1191_61` and `_62`, PDF p. 14; filter compliant. 1084 tokens, 1739.806 ms. |
| `geo-day3-007` | Refuse | Technical-report-only context had no New River setting evidence; no gold evidence applies. | Correctly returned insufficient evidence. It did not substitute Nebraska settings for excluded New River-report settings. | No citation; filter compliant. 952 tokens, 1571.868 ms. |
| `geo-day3-008` | Refuse | Filtered New River context had no support for an exact survey fuel total; no gold evidence applies. | Correctly returned insufficient evidence. It did not misstate the unrelated Camp Lejeune groundwater-withdrawal figure as fuel use. | No citation; filter compliant. 892 tokens, 818.397 ms. |

All final contexts had at most four chunks. No final chunk exceeded 900 characters, and no item had a filter violation or context truncation.

## Metrics

| Metric | Result | Definition |
| --- | ---: | --- |
| Execution completion | 8 / 8 | A final production response was recorded. |
| Primary Provider calls | 8 | One per frozen question. |
| Repair calls | 0 | No parser repair was triggered. |
| Provider retries observed | 0 | `llm_max_retries=1` means one allowed attempt. |
| Answerable gold chunks in raw top-5 seeds | 6 / 7 | `geo-day3-006_61` ranked 6; all other preannotated chunks were top-5 seeds. |
| Answerable gold chunks in expanded candidates | 7 / 7 | Production expansion supplied `_61`. |
| Answerable gold chunks in final bounded context | 7 / 7 | All frozen evidence chunks reached the model context. |
| Final-context complete fact coverage | 6 / 6 answerable questions | Every answerable item's required evidence set was in final context. |
| Correct and complete answer | 6 / 6 answerable questions | Manual fact, numerical-unit, and completeness review. |
| Status accuracy | 8 / 8 | `answered` for six answerable items; `insufficient_evidence` for two refusals. |
| Correct refusal | 2 / 2 refusal questions | No unsupported answer was produced. |
| Citation support and physical-page correctness | 6 / 6 answered questions | Each response cited direct supporting evidence on the annotated physical page. |
| Filter violations | 0 / 8 | Final retrieval context respected every frozen filter. |
| Context-budget violations | 0 / 8 | At most four chunks and 900 characters per chunk. |
| Known usage | 8 / 8 responses | Missing usage would have been reported as unknown. |

Aggregate Provider usage was 6,635 prompt tokens, 961 completion tokens, and 7,596 total tokens. Aggregate Provider elapsed time was 10,280.173 ms; these are sum-of-call measurements, not user-visible end-to-end latency.

## Failure Attribution And Limits

No execution, Provider, citation, filter, or answer-quality failure was observed in this frozen set. The sole retrieval observation is that `geo-day3-006_61` ranked sixth in raw BM25 but was retained by the current production predecessor expansion; it is an observation, not a request or justification to tune retrieval.

The refusal findings demonstrate only the two specified scope boundaries. The results do not resolve known historical Acceptance retrieval/context deficiencies, do not represent a blind benchmark after their source corpus was inspected, and do not show performance on new documents or the wider geoscience domain.

## File And Workspace Record

New artifacts in this directory:

- `questions.json`: frozen question labels, source evidence, and overlap checks.
- `run-manifest.json`: environment, corpus identity, runtime, and pre-run record.
- `retrieval-results.json`: production retrieval-stage evidence audit.
- `generation-results.json`: actual responses, citations, call events, usage, and latency.
- `report.md`: this manual review.

The initial tracked worktree changes were retained in `README.md`, `docs/02-getting-started.md`, `eval/geological_generation.py`, `frontend/README.md`, `frontend/vite.config.ts`, `scripts/diagnose_generation_retrieval.py`, and `tests/unit/test_geological_generation_eval.py`. Historical result files remained unmodified. Historical SHA-256 checks before and after the run:

- First-run Acceptance: `b2ff15f990203b48deb71c02a91fda4b9fca8c44c7a2ed26d252683ec1a30200`.
- After-egress-fix Acceptance: `31a0b791bea3e34aff38747b6fe092f23b733b4c0cc7550c44d1dcbf5da989c0`.

No production code, prompt, frozen legacy question set, corpus, index, configuration, or `.env` file was changed. No service was started or stopped. No legacy Acceptance, browser validation, or extra Provider smoke test was run.
