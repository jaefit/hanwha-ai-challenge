#!/usr/bin/env python3
"""사전 예측표 → 챗봇 시스템 프롬프트 생성 (T4)

  .venv/bin/python src/build_prompt.py
입력: prompt/exit_navi.md (템플릿) + data/derived/exit_forecast_2026.json + nowcast 도보 모델
출력: prompt/exit_navi.generated.md — 데이터가 갱신되면 이 스크립트만 다시 돌리면 프롬프트가 따라온다.
"""
import json, sys, pathlib, datetime
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import nowcast as N

HOURS = ["19", "20", "21", "22", "23"]
LVL = lambda x: "심각" if x >= 1 else "경계" if x >= 0.8 else "주의" if x >= 0.5 else "여유"

def main():
    ef = json.loads((ROOT / "data/derived/exit_forecast_2026.json").read_text(encoding="utf-8"))
    ex = ef["exits"]
    # 부하율 표
    head = "| 출구 | " + " | ".join(h + "시" for h in HOURS) + " |\n|---|" + "---|" * len(HOURS)
    rows = []
    for st in ex:
        cells = []
        for h in HOURS:
            v = ex[st][h]
            cells.append("통제" if v["closed"] else f"{v['load']:.2f} [{v['load_lo']:.2f}–{v['load_hi']:.2f}] {LVL(v['load'])}" + (f" 대기{v['wait_min']}분" if v.get("wait_min") else ""))
        rows.append(f"| {st}{'†' if v.get('estimated_capacity') else ''} | " + " | ".join(cells) + " |")
    table = head + "\n" + "\n".join(rows) + "\n† = 처리량 추정(9호선·도보·1호선 합산)"
    # 순위
    rank = "\n".join(f"- {h}시: " + " < ".join(f"{st} {l:.2f}" for st, l, w in ef["ranking_by_hour"][h]) for h in HOURS)
    # 도보 (이벤트광장 기준, 한산 1.5명/m² vs 혼잡 4.0명/m²)
    walk = "\n".join(f"- {ex_}: 약 {N.travel_min('이벤트광장', ex_, 1.5):.0f}분 (혼잡 시 ~{N.travel_min('이벤트광장', ex_, 4.0):.0f}분)" for ex_ in N.EXIT_LL)
    tpl = (ROOT / "prompt/exit_navi.md").read_text(encoding="utf-8")
    out = (tpl.replace("{{GENERATED}}", datetime.date.today().isoformat() + f" (사전표 {ef['generated'][:10]})")
              .replace("{{FORECAST_TABLE}}", table).replace("{{RANKING}}", rank).replace("{{WALK}}", walk))
    out = out.split("<!--")[0] + out.split("-->")[1] if "<!--" in out else out
    assert all(st in out for st in ex) and all(h + "시" in out for h in HOURS) and "통제" in out
    (ROOT / "prompt/exit_navi.generated.md").write_text(out, encoding="utf-8")
    print("→ prompt/exit_navi.generated.md", len(out), "자")
    print(rank)

if __name__ == "__main__":
    main()
