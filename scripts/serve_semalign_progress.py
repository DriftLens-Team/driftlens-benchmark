"""Show actual local acceptance progress; no model calls or editable controls."""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PAGE = """<!doctype html><html lang="ko"><meta charset="utf-8"><title>SemAlign 실행 검증</title>
<style>body{font:17px 'Malgun Gothic',sans-serif;color:#14243a;background:#f5f7fa;margin:0}main{max-width:1160px;margin:32px auto;padding:28px 36px;background:white}h1{font-size:30px;margin:0 0 12px}h2{font-size:21px;margin:30px 0 12px}.sub{color:#586678}.row{display:flex;gap:20px;flex-wrap:wrap}.box{flex:1;border:1px solid #d8e0e8;padding:18px;min-width:130px}.num{font-size:32px;font-weight:bold;margin-top:10px}.bar{height:14px;background:#e5eaf0;margin:20px 0}.bar>div{background:#237265;height:100%}table{width:100%;border-collapse:collapse;font-size:14px}td,th{text-align:left;padding:10px;border-bottom:1px solid #dce3ea}th{background:#edf1f6}code{font-family:Consolas,monospace;white-space:pre-wrap;word-break:break-all;font-size:12px}.ok{color:#167145}.bad{color:#b3382a}.running{color:#154d96}footer{margin-top:22px;color:#596676;font-size:13px}</style>
<main><h1>SemAlign 실행 검증</h1><p class="sub">7개 지표 · 52주 · 생성 검수와 의미 변화 평가</p><div id="content">실행 기록을 읽는 중입니다.</div><footer>화면은 실행 로그와 manifest에서 읽은 실제 진행 상태입니다. 5초마다 갱신합니다.</footer></main>
<script>const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const names={'benchmark-tests':'Benchmark 자동 테스트','benchmark-lint':'코드 검사','benchmark-build':'Benchmark 패키지 빌드','agent-tests':'SQL 에이전트 자동 테스트','agent-build':'SQL 에이전트 패키지 빌드','data-tests':'데이터 회귀 테스트','data-counterexamples':'데이터 반례 검사','data-independent-reference':'728개 독립 참조값 비교','data-generate':'개선된 데이터 생성','data-validate':'생성 데이터 정합성 검사','live-generation':'실제 AI 전체 생성','original-generation':'원본 SQL 재검수','regenerated-generation':'수정 SQL 검수','fake-generation':'모의 에이전트 전체 생성'};async function update(){try{const d=await(await fetch('/status.json',{cache:'no-store'})).json();let m=d.run||{};const running=d.execution.steps.findLast(x=>x.status==='running');document.querySelector('#content').innerHTML=`<p><b>전체 상태</b> ${esc(d.execution.status)}　<b>현재 단계</b> ${esc(names[running?.name]||running?.name||'기록 완료')}</p><div class="row">${[['계획',m.planned??364],['시도',m.attempted??0],['검수 통과',m.validated??0],['거절',m.rejected??0],['미검증 / 실패',`${m.unverified??0} / ${m.failed??0}`]].map(([k,v])=>`<div class="box">${esc(k)}<div class="num">${esc(v)}</div></div>`).join('')}</div><div class="bar"><div style="width:${100*(m.attempted||0)/(m.planned||364)}%"></div></div><p>모델: <b>${esc(m.model_id||'설정된 Upstage 모델')}</b>　검수: ${esc(m.validation_policy||'behavioral')}　${m.elapsed_seconds?`소요 ${esc(m.elapsed_seconds)}초`:''}</p><h2>실행 단계</h2><table><tr><th>단계</th><th>상태</th><th>종료 코드</th><th>소요 시간</th></tr>${d.execution.steps.slice(-12).map(s=>`<tr><td>${esc(names[s.name]||s.name)}</td><td class="${s.status==='passed'?'ok':s.status==='failed'?'bad':'running'}">${esc(s.status)}</td><td>${esc(s.exit_code??'진행 중')}</td><td>${s.elapsed_seconds??'-'}초</td></tr>`).join('')}</table>${running?`<h2>현재 실행 명령</h2><code>${esc(running.command.map(x=>x.replaceAll(d.workspace,'<workspace>')).join(' '))}</code>`:''}<p class="sub">갱신 시각 ${esc(new Date().toLocaleString('ko-KR'))}</p>`;}catch(e){document.querySelector('footer').textContent='새 기록을 기다리고 있습니다. 기존 실행 상태는 유지됩니다.'}}update();setInterval(update,5000);</script></html>"""


def main():
    """Bind only localhost and expose two read-only routes for one chosen run."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    run = args.run.resolve()
    cached = {"execution": {"steps": [], "status": "waiting"}, "workspace": str(run.parents[2])}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                payload, kind = PAGE.encode("utf-8"), "text/html; charset=utf-8"
            elif self.path == "/status.json":
                try:
                    cached["execution"] = json.loads((run / "execution.json").read_text(encoding="utf-8"))
                    steps = cached["execution"]["steps"]
                    last = next(
                        (
                            s["name"].removesuffix("-generation")
                            for s in reversed(steps)
                            if s["name"].endswith("-generation")
                        ),
                        None,
                    )
                    if last:
                        cached["run"] = json.loads(
                            (run / last / "private/manifest.json").read_text(encoding="utf-8")
                        )
                        cached["run"] = {
                            k: cached["run"].get(k)
                            for k in (
                                "planned",
                                "attempted",
                                "validated",
                                "rejected",
                                "unverified",
                                "failed",
                                "model_id",
                                "validation_policy",
                                "elapsed_seconds",
                            )
                        }
                except (OSError, ValueError):
                    pass
                payload, kind = (
                    json.dumps(cached, ensure_ascii=False).encode("utf-8"),
                    "application/json; charset=utf-8",
                )
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    print(f"http://127.0.0.1:{args.port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
