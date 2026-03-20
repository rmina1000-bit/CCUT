type BrowserSanityResult = {
  pass: boolean;
  rootNotEmpty: boolean;
  shellExists: boolean;
  consoleErrorCount: number;
  pageErrorCount: number;
  consoleErrors: string[];
  pageErrors: string[];
  targetUrl: string;
};

const statusNode = document.getElementById('browser-sanity-status');
const jsonNode = document.getElementById('browser-sanity-json');
const frame = document.getElementById('browser-sanity-frame') as HTMLIFrameElement | null;

if (!statusNode || !jsonNode || !frame) {
  throw new Error('Browser sanity runner is missing required DOM nodes.');
}

function writeStatus(result: BrowserSanityResult) {
  statusNode.textContent = JSON.stringify(result, null, 2);
  jsonNode.textContent = JSON.stringify(result);
}

function readFrameResult(targetUrl: string): BrowserSanityResult {
  const frameWindow = frame?.contentWindow;
  const frameDocument = frameWindow?.document;
  const sanity = frameWindow?.__CCUT_SANITY__;
  const root = frameDocument?.getElementById('root');

  const rootNotEmpty = !!root && (root.children.length > 0 || (root.textContent || '').trim().length > 0);
  const shellExists = !!frameDocument?.querySelector('.ccut-shell');
  const consoleErrorCount = sanity?.consoleErrorCount ?? 0;
  const pageErrorCount = sanity?.pageErrorCount ?? 0;
  const consoleErrors = sanity?.consoleErrors ?? [];
  const pageErrors = sanity?.pageErrors ?? [];

  return {
    pass: rootNotEmpty && shellExists && consoleErrorCount === 0 && pageErrorCount === 0,
    rootNotEmpty,
    shellExists,
    consoleErrorCount,
    pageErrorCount,
    consoleErrors,
    pageErrors,
    targetUrl
  };
}

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function runBrowserSanity() {
  const target = new URL('/', window.location.origin);
  target.searchParams.set('__sanity', '1');
  target.searchParams.set('ts', String(Date.now()));

  statusNode.textContent = `Loading ${target.toString()} ...`;
  frame.src = target.toString();

  await new Promise<void>((resolve, reject) => {
    const timeout = window.setTimeout(() => reject(new Error('Iframe load timed out.')), 5000);

    frame.addEventListener(
      'load',
      () => {
        window.clearTimeout(timeout);
        resolve();
      },
      { once: true }
    );
  });

  for (let attempt = 0; attempt < 30; attempt += 1) {
    await wait(150);
    const result = readFrameResult(target.toString());
    if (result.rootNotEmpty || result.shellExists || result.pageErrorCount > 0 || result.consoleErrorCount > 0) {
      writeStatus(result);
      return;
    }
  }

  writeStatus(readFrameResult(target.toString()));
}

runBrowserSanity().catch((error: Error) => {
  writeStatus({
    pass: false,
    rootNotEmpty: false,
    shellExists: false,
    consoleErrorCount: 0,
    pageErrorCount: 1,
    consoleErrors: [],
    pageErrors: [`${error.name}: ${error.message}`],
    targetUrl: frame.src
  });
});

export {};
