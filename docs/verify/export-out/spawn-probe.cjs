const { spawn } = require("node:child_process");
const which = process.argv[2];
const cmd = which === "python"
  ? "C:\\Users\\BC_aw\\.dsh\\dsh-runtimes\\dsh-primary-runtime\\dependencies\\python\\python.exe"
  : process.execPath;
const args = which === "python" ? ["-c", "import time; time.sleep(0.3)"] : ["-v"];
const child = spawn(cmd, args, { stdio: ["ignore", "pipe", "pipe"], windowsHide: true });
child.on("error", (e) => console.log(which, "ERROR", e.code, e.syscall));
child.on("close", (code) => console.log(which, "CLOSE", code));
setTimeout(() => process.exit(0), 4000);
