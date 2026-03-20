const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const uiRoot = path.resolve(__dirname, '..');
const npmCommand = process.platform === 'win32' ? 'npm.cmd' : 'npm';

function runScript(scriptName) {
  const result = spawnSync(npmCommand, ['run', scriptName], {
    cwd: uiRoot,
    stdio: 'inherit'
  });

  if (typeof result.status === 'number' && result.status !== 0) {
    process.exit(result.status);
  }

  if (typeof result.status !== 'number') {
    process.exit(1);
  }
}

const typeScriptBin = path.join(uiRoot, 'node_modules', 'typescript', 'bin', 'tsc');
if (!fs.existsSync(typeScriptBin)) {
  console.error('[gate] Failed: TypeScript is not installed locally, so `npm run typecheck` cannot run yet.');
  console.error('[gate] Install `typescript`, `@types/react`, and `@types/react-dom` before using phase completion gates.');
  process.exit(1);
}

console.log('[gate] Running typecheck...');
runScript('typecheck');

console.log('[gate] Running lint (or skipping if unavailable)...');
runScript('lint');

console.log('[gate] Running production build...');
runScript('build');

console.log('[gate] Build gates passed.');
