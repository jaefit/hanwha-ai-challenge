"""run_all.sh 종료 경로 검증 — 2026-09-02 T7 드라이런에서 찾은 L5.

`Ctrl+C` 를 눌러도 워치독 루프의 `sleep $WD_POLL` 이 끝나야 트랩이 돈다. 실측 38초·13초가 걸렸다.
9/5 밤 현장에서 반응이 없다고 한 번 더 누르면 zsh 가 트랩을 버리고 수집기와 `caffeinate -dims` 가
고아로 남는다 — 맥이 밤새 깨어 있고 API 도 계속 나간다.

셸은 pytest 로 직접 못 돌리므로(메모리: shell-heredoc-untested) 둘로 나눠 본다.
  ① zsh 에서 그 관용구가 실제로 트랩을 즉시 돌리는지 — 동작 검증
  ② run_all.sh 의 워치독 루프가 그 관용구를 쓰는지 — 회귀 방지
"""
import pathlib, shutil, subprocess, time

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
RUN_ALL = ROOT / "run_all.sh"

BODY = """
trap 'print -r -- stopped >&2; exit 0' INT TERM
print -r -- ready >&2
while true; do
  {SLEEP}
done
"""


def _latency(sleep_stmt, tmp_path):
    """스크립트를 띄우고 ready 를 본 뒤 INT 를 보내, stopped 가 찍히기까지 걸린 초."""
    zsh = shutil.which("zsh")
    if not zsh:
        pytest.skip("zsh 없음")
    f = tmp_path / "probe.sh"
    f.write_text(BODY.replace("{SLEEP}", sleep_stmt), encoding="utf-8")
    p = subprocess.Popen([zsh, str(f)], stderr=subprocess.PIPE, text=True)
    assert p.stderr.readline().strip() == "ready"
    t0 = time.monotonic()
    p.send_signal(subprocess.signal.SIGINT)
    line = p.stderr.readline().strip()
    dt = time.monotonic() - t0
    p.wait(timeout=20)
    assert line == "stopped", f"트랩이 안 돌았다: {line!r}"
    return dt


def test_bare_sleep_swallows_the_trap(tmp_path):
    """맨 `sleep N` 은 잠이 끝나야 트랩이 돈다 — 이게 L5 의 기전이다."""
    assert _latency("sleep 5", tmp_path) > 3.0


def test_backgrounded_sleep_lets_the_trap_run_at_once(tmp_path):
    """`sleep N & wait $!` 는 wait 가 시그널에 깨므로 즉시 트랩이 돈다."""
    assert _latency("sleep 5 & wait $!", tmp_path) < 2.0


def test_run_all_watchdog_sleep_is_interruptible():
    """워치독 루프가 맨 sleep 을 쓰면 현장에서 Ctrl+C 가 최대 WD_POLL 초 먹힌다."""
    lines = RUN_ALL.read_text(encoding="utf-8").splitlines()
    hits = [l.strip() for l in lines if "sleep $WD_POLL" in l or "sleep ${WD_POLL" in l]
    assert hits, "워치독 루프의 sleep 을 찾지 못했다 — 구조가 바뀌었으면 이 검사를 고쳐야 한다"
    for h in hits:
        assert "&" in h and "wait" in h, f"트랩이 막히는 맨 sleep 이다: {h!r} — 배경으로 돌리고 wait 해야 한다"
