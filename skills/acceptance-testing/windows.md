# Windows 10/11 — Claude Code native (Git Bash): command equivalents

Commands in these skills are bash. Claude Code on Windows runs them in **Git Bash**. The left column does not
exist or behaves differently there — use the right column.

| Linux / macOS | Windows (Git Bash) |
|---|---|
| `python3 -I <script.py>` | `python3` may be the Microsoft Store stub (exit 9009, prints nothing) → `py -3 -I <script.py>` or `python -I <script.py>`. `qa.py` re-runs itself under `~/.claude/skills/acceptance-testing/.venv` (PyYAML) by itself. |
| `ss -ltnp` / `lsof -nP -iTCP -sTCP:LISTEN` | `netstat -ano -p tcp \| grep LISTENING` (last column = PID) |
| `… \| grep :<port>` | `netstat -ano -p tcp \| grep LISTENING \| grep ":<port> "` |
| `ps -o pid,etime,cmd -u $USER` | `powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" \| Select ProcessId,ParentProcessId,CommandLine \| Format-List"` |
| `pkill -f <pattern>` / `pgrep -f <pattern>` | find the PID (netstat / Get-CimInstance above), then `taskkill //F //T //PID <pid>` |
| `kill -TERM -<pgid>` (whole process group) | `taskkill //F //T //PID <root pid>` (`//T` = the whole tree) |
| `setsid nohup <cmd> > log 2>&1 &` | `nohup <cmd> > log 2>&1 &` then record `$!`; stop it by the PID netstat shows on its port + `taskkill //F //T` |
| `/tmp/...` | the session scratchpad directory, or `$TEMP` |

Rules that have broken runs on Windows:

- **MSYS path conversion.** Git Bash rewrites arguments that look like `/x` into `C:\...` for Windows programs.
  Write `taskkill //F //T //PID <pid>` (double slash), or prefix the command with `MSYS_NO_PATHCONV=1`.
- **Process trees.** Killing an `npm` / `pnpm` / `npx` wrapper leaves `node.exe` children alive and the port
  stays taken. Always `taskkill //T` on the tree root, then re-check the port with netstat.
- **`timeout`** must be Git Bash's `/usr/bin/timeout`, not `C:\Windows\System32\timeout.exe` (that one only
  waits). Check once per session: `type -a timeout` — the first line must be `/usr/bin/timeout`.
- **`bash` in PATH can be WSL** (`C:\Windows\System32\bash.exe`). Claude Code must use Git Bash:
  `CLAUDE_CODE_GIT_BASH_PATH=C:\Program Files\Git\bin\bash.exe` (install.cmd sets it).
- **CRLF.** Keep `.sh` files LF. `$'\r': command not found` → `sed -i 's/\r$//' <file>`.
- **Paths.** Use forward slashes (`C:/Users/...`); never pass an unquoted backslash path to bash.
- **Long paths.** `.qa/node_modules` (Playwright) can pass 260 characters; install.cmd checks
  `LongPathsEnabled` and `git config core.longpaths`.
- **Encoding.** The skill scripts print UTF-8. Other tools that print Vietnamese: write to a file, then Read it.
- **PowerShell 5.1** strips `"` inside arguments passed to native programs (`python -c "print(\"x\")"` arrives
  as `print(x)`). Use single quotes inside `-c` code, or a script file.
