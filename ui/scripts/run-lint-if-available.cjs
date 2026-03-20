const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const uiRoot = path.resolve(__dirname, '..');

const configCandidates = [
  'eslint.config.js',
  'eslint.config.cjs',
  'eslint.config.mjs',
  '.eslintrc',
  '.eslintrc.js',
  '.eslintrc.cjs',
  '.eslintrc.json',
  '.eslintrc.yml',
  '.eslintrc.yaml'
];

const eslintBin = path.join(uiRoot, 'node_modules', 'eslint', 'bin', 'eslint.js');
const hasEslint = fs.existsSync(eslintBin);
const hasConfig = configCandidates.some((candidate) => fs.existsSync(path.join(uiRoot, candidate)));

if (!hasEslint) {
  console.log('[lint] Skipped: eslint is not installed in ui/node_modules.');
  process.exit(0);
}

if (!hasConfig) {
  console.log('[lint] Skipped: no ESLint config was found.');
  process.exit(0);
}

const result = spawnSync(
  process.execPath,
  [eslintBin, '--ext', '.js,.jsx,.ts,.tsx', 'src', 'main.jsx'],
  {
    cwd: uiRoot,
    stdio: 'inherit'
  }
);

if (typeof result.status === 'number') {
  process.exit(result.status);
}

process.exit(1);
