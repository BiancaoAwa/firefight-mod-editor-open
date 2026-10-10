// Read-only snapshot helper: write the remote bytes of the given paths at a ref
// into a local directory, so `git diff --no-index` can compare them.
// Usage: node fetch-remote.mjs <owner/repo> <ref> <outDir> <path> [path...]
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';

const cred = readFileSync('C:/Users/BC_aw/.dsh/.credentials.yaml', 'utf8');
const token = /^\s{2}GITHUB_TOKEN:\s*(\S+)\s*$/m.exec(cred)?.[1];
if (!token) throw new Error('no token in credentials');
const headers = { authorization: `Bearer ${token}`, accept: 'application/vnd.github+json', 'user-agent': 'dsh-fetch-remote' };

const [repo, ref, outDir, ...paths] = process.argv.slice(2);
if (!repo || !ref || !outDir || paths.length === 0) throw new Error('usage: node fetch-remote.mjs <owner/repo> <ref> <outDir> <path>...');

for (const path of paths) {
    const res = await fetch(`https://api.github.com/repos/${repo}/contents/${path}?ref=${ref}`, { headers });
    if (!res.ok) throw new Error(`${path}: ${res.status} ${await res.text()}`);
    const body = await res.json();
    const buf = Buffer.from(body.content, 'base64');
    const target = join(outDir, path);
    mkdirSync(dirname(target), { recursive: true });
    writeFileSync(target, buf);
    console.log(`${String(buf.length).padStart(7)}  ${path}  (git blob sha ${body.sha.slice(0, 12)})`);
}
