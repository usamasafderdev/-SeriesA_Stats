"""Read-only acceptance of the supplied snapshot; browser mutations use a copy."""
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from contextlib import closing
from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError
import html
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def run_acceptance():
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "python": sys.version.split()[0], "authenticated_provider_requests": 0}
    with tempfile.TemporaryDirectory(prefix="serie-a-acceptance-") as folder:
        temporary = Path(folder)
        database = temporary / "serie_a.db"
        with closing(sqlite3.connect(ROOT / "serie_a.db")) as source, closing(sqlite3.connect(database)) as target:
            source.backup(target)
        port = free_port()
        base = f"http://127.0.0.1:{port}"
        environment = dict(os.environ, SERIE_A_PORT=str(port), SERIE_A_DATABASE=str(database),
                           X_API_KEY="", FOOTBALL_DATA_TOKEN="", BBS_API_KEY="", STRIKER_API_KEY="")
        log = (temporary / "server.log").open("w", encoding="utf-8")
        process = subprocess.Popen([sys.executable, "main.py"], cwd=ROOT, env=environment,
            stdout=log, stderr=log, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        server = None
        try:
            def get(path):
                with urlopen(base + path, timeout=10) as response:
                    return json.load(response)
            for _ in range(100):
                try:
                    if get("/api/health")["status"] == "ok":
                        break
                except OSError:
                    time.sleep(.1)
            else:
                raise AssertionError("python main.py did not start.")
            all_matches = get("/api/matches?source=live")
            finished = get("/api/matches?source=live&status=finished")
            standings = get("/api/standings?season=2026")
            assert len(all_matches) == 380
            assert len(finished) == 110 and len({match["id"] for match in finished}) == 110
            assert len(standings) == 20
            assert all_matches == sorted(all_matches, key=lambda row: row["match_date"], reverse=True)
            for match in finished:
                details = get(f"/api/matches/{match['id']}")
                assert details["id"] == match["id"]
            for team in standings:
                matches = [match for match in finished if team["team_name"] in
                           (match["home_team_name"], match["away_team_name"])]
                wins = draws = losses = goals = conceded = 0
                for match in matches:
                    home = team["team_name"] == match["home_team_name"]
                    own = match["home_score"] if home else match["away_score"]
                    opponent = match["away_score"] if home else match["home_score"]
                    wins += own > opponent
                    draws += own == opponent
                    losses += own < opponent
                    goals += own
                    conceded += opponent
                assert (len(matches), wins, draws, losses, goals, conceded) == (
                    team["played"], team["wins"], team["draws"], team["losses"],
                    team["goals_for"], team["goals_against"])
            coverage = get("/api/data-coverage")
            assert coverage["completed_fixtures"] == 110
            with closing(sqlite3.connect(database)) as connection:
                assert connection.execute("pragma integrity_check").fetchone()[0] == "ok"
                assert not connection.execute("pragma foreign_key_check").fetchall()
                assert connection.execute("select count(*) from lineup_players").fetchone()[0] == 44
            preserved = next(match for match in finished if "Fiorentina" in match["home_team_name"])
            assert preserved["statistics"]["home_possession"] == 41
            assert preserved["statistics"]["away_possession"] == 59
            report.update(launch="python main.py", official_fixtures=len(all_matches),
                          completed_match_details_checked=len(finished),
                          teams_reconciled_with_standings=len(standings), coverage=coverage)
            ids = {}
            for token in ("Internazionale", "Genoa", "Fiorentina"):
                ids[token] = next(match["id"] for match in finished if token in match["home_team_name"])
            driver = (ROOT / "tools" / "browser_acceptance.js").read_text(encoding="utf-8")
            driver = driver.replace("__MATCH_IDS__", json.dumps(ids))

            class Proxy(BaseHTTPRequestHandler):
                def do_GET(self):
                    if self.path == "/?mobile=1":
                        # Headless Windows Chrome enforces a minimum window width.
                        # A same-origin 390px frame tests the real mobile viewport.
                        wrapper = '''<!doctype html><html><head><link rel="icon" href="data:,"></head><body style="margin:0">
                        <iframe id="mobile" src="/?frame=1" style="width:390px;height:1000px;border:0"></iframe>
                        <script>(async()=>{for(let i=0;i<290;i++){
                          let result=document.getElementById('mobile').contentDocument?.getElementById('acceptance-result');
                          if(result){let p=document.createElement('pre');p.id='acceptance-result';p.textContent=result.textContent;document.body.append(p);return;}
                          await new Promise(r=>setTimeout(r,100));
                        }})();</script></body></html>'''.encode()
                        self.send_response(200)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(wrapper)
                        return
                    try:
                        with urlopen(base + self.path, timeout=15) as response:
                            body = response.read()
                            content_type = response.headers.get("Content-Type", "")
                    except HTTPError as error:
                        self.send_error(error.code)
                        return
                    if self.path in ("/", "/?frame=1"):
                        body = body.replace(b"</body>", b"<script>" + driver.encode() + b"</script></body>")
                    self.send_response(200)
                    self.send_header("Content-Type", content_type)
                    self.end_headers()
                    self.wfile.write(body)

                def do_POST(self):
                    # Only the read-only planner is exposed to the browser driver.
                    if self.path != "/api/highlightly/plan":
                        self.send_error(405)
                        return
                    from urllib.request import Request
                    body = self.rfile.read(int(self.headers["Content-Length"]))
                    request = Request(base + self.path, body, {"Content-Type": "application/json"})
                    with urlopen(request, timeout=15) as response:
                        result = response.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(result)

                def log_message(self, *_args):
                    pass

            server = ThreadingHTTPServer(("127.0.0.1", 0), Proxy)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            browser = next((path for path in (
                Path(os.getenv("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe",
                Path(os.getenv("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
            ) if path.exists()), None)
            if browser is None:
                raise AssertionError("Install Chrome or Edge for the browser acceptance check.")
            for width, height in ((1440, 1100), (390, 1000)):
                profile = temporary / f"browser-{width}"
                result = subprocess.run([str(browser), "--headless=new", "--disable-gpu", "--no-first-run",
                    f"--user-data-dir={profile}", f"--window-size={width},{height}",
                    "--dump-dom", "--virtual-time-budget=30000", "--timeout=35000",
                    f"http://127.0.0.1:{server.server_port}/" + ("?mobile=1" if width == 390 else "")],
                    capture_output=True, encoding="utf-8", errors="replace", timeout=45)
                found = re.search(r'<pre id="acceptance-result">(.*?)</pre>', result.stdout, re.S)
                assert found, "Browser driver did not finish."
                outcome = json.loads(html.unescape(found[1]))
                report[f"browser_{width}"] = outcome
                assert not outcome.get("error"), outcome
                if width == 390:
                    assert outcome["viewport"]["width"] == 390
            with closing(sqlite3.connect(database)) as connection:
                assert connection.execute("select coalesce(sum(attempts),0) from highlightly_requests").fetchone()[0] == coverage["requests_used"]
            report["status"] = "passed"
        finally:
            if server:
                server.shutdown()
                server.server_close()
            process.terminate()
            process.wait(timeout=10)
            log.close()
    target = ROOT / "docs" / "ACCEPTANCE.json"
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    run_acceptance()
