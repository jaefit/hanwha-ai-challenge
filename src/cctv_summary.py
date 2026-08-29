#!/usr/bin/env python3
"""CCTV 수집 로그 창 요약: 카메라별 프레임 성공률·밝기·count·점유율·등급·플래그 분포. 야간 테스트·리허설 판정용.

  .venv/bin/python src/cctv_summary.py --from 20:00 --minutes 60 [--date 20260829]
판정 기준(임시): 밝기 중앙값 <40 이면 저조도 구간 · count 가 0 근처면 야간 검출 실패 · bg_fail 비율 높으면 배경모델 불안정.
"""
import sys, json, pathlib, datetime, statistics, collections

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIVE = ROOT / "data" / "live"


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main():
    date = arg("--date", datetime.datetime.now().strftime("%Y%m%d"))
    hh, mm = map(int, arg("--from", "00:00").split(":")); minutes = int(arg("--minutes", "1440"))
    t0 = datetime.datetime(int(date[:4]), int(date[4:6]), int(date[6:]), hh, mm); t1 = t0 + datetime.timedelta(minutes=minutes)
    fn = LIVE / f"cctv_{date}.jsonl"
    if not fn.exists(): sys.exit(f"no log {fn}")
    rows = [json.loads(l) for l in fn.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [r for r in rows if t0 <= datetime.datetime.fromisoformat(r["ts"]) < t1]
    if not rows: sys.exit(f"창 {t0:%H:%M}~{t1:%H:%M} 레코드 없음")
    by = collections.defaultdict(list)
    for r in rows: by[r["name"]].append(r)
    print(f"창 {t0:%m-%d %H:%M}~{t1:%H:%M} · 레코드 {len(rows)} · 카메라 {len(by)}")
    print(f"{'카메라':<12}{'n':>4}{'ok%':>5}{'밝기중앙':>7}{'count중앙':>9}{'count최대':>9}{'점유중앙':>8}  등급분포 · 플래그")
    for name, rs in sorted(by.items(), key=lambda x: -len(x[1])):
        ok = [r for r in rs if r.get("ok")]
        br = [r["brightness"] for r in ok if r.get("brightness") is not None]
        cn = [r["count"] for r in ok if r.get("count") is not None]
        oc = [r["occupancy"] for r in ok if r.get("occupancy") is not None]
        lv = collections.Counter(r.get("level") for r in ok); fl = collections.Counter(f for r in ok for f in r.get("flags", []))
        print(f"{name:<12}{len(rs):>4}{100*len(ok)/len(rs):>5.0f}{(statistics.median(br) if br else float('nan')):>7.0f}{(statistics.median(cn) if cn else float('nan')):>9.1f}{(max(cn) if cn else float('nan')):>9.1f}{(statistics.median(oc) if oc else float('nan')):>8.2f}  {dict(lv)} · {dict(fl) or '-'}")
    errs = collections.Counter((r["name"], r.get("error", "")[:40]) for r in rows if not r.get("ok"))
    if errs: print("오류:", dict(errs))
    dark = [n for n, rs in by.items() if (b := [r["brightness"] for r in rs if r.get("brightness") is not None]) and statistics.median(b) < 40]
    print(f"\n저조도(중앙 밝기<40) 카메라 {len(dark)}/{len(by)}: {dark}")


if __name__ == "__main__":
    main()
