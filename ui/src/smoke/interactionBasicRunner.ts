type InteractionStatus = 'Pass' | 'Partial' | 'Fail';

type InteractionCaseResult = {
  expectedBySpec: string;
  actualCurrentBehavior: string;
  status: InteractionStatus;
  exactReason: string | null;
  changedFiles: string[];
  reproductionNote: string;
};

type InteractionReport = {
  pass: boolean;
  results: Record<string, InteractionCaseResult>;
  targetUrl: string;
};

type AppContext = {
  frameDocument: Document;
  frameWindow: Window;
  targetUrl: string;
};

type RestoreEvidence = {
  mode: string;
  direction: string;
};

const statusNode = document.getElementById('interaction-basic-status');
const jsonNode = document.getElementById('interaction-basic-json');
const frame = document.getElementById('interaction-basic-frame') as HTMLIFrameElement | null;

if (!statusNode || !jsonNode || !frame) {
  throw new Error('Interaction basic runner is missing required DOM nodes.');
}

function writeReport(report: InteractionReport) {
  statusNode.textContent = JSON.stringify(report, null, 2);
  jsonNode.textContent = JSON.stringify(report);

  const firstResult = Object.values(report.results)[0];
  document.title = `CCUT Interaction Basic Spec Runner | undoHybrid=${firstResult?.status || 'Fail'} | ${firstResult?.actualCurrentBehavior || 'runner-failed'}`;
}

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function textOf(node: Element | null) {
  return node?.textContent?.replace(/\s+/g, ' ').trim() || '';
}

async function waitForFrameReady(frameDocument: Document) {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    const shell = frameDocument.querySelector('.ccut-shell');
    const board = frameDocument.querySelector('.fragment-map-board');
    const hold = frameDocument.querySelector('.hold-board');
    if (shell && board && hold) {
      return;
    }
    await wait(150);
  }

  throw new Error('CCUT shell did not finish mounting in time.');
}

async function loadFreshApp(): Promise<AppContext> {
  const target = new URL('/', window.location.origin);
  target.searchParams.set('ts', String(Date.now()));
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

  const frameDocument = frame.contentDocument;
  const frameWindow = frame.contentWindow;
  if (!frameDocument || !frameWindow) {
    throw new Error('Failed to access iframe content.');
  }

  await waitForFrameReady(frameDocument);
  return {
    frameDocument,
    frameWindow,
    targetUrl: target.toString()
  };
}

function getShell(frameDocument: Document) {
  return frameDocument.querySelector('.ccut-shell') as HTMLElement | null;
}

function getRestoreEvidence(frameDocument: Document): RestoreEvidence {
  const shell = getShell(frameDocument);
  return {
    mode: shell?.dataset.lastRestoreMode || 'none',
    direction: shell?.dataset.lastRestoreDirection || 'none'
  };
}

function getEditTile(frameDocument: Document, fragmentId: string) {
  return frameDocument.querySelector(
    `.fragment-map-board .fragment-tile--edit[data-fragment-id="${fragmentId}"]`
  ) as HTMLElement | null;
}

function getReservedTile(frameDocument: Document, fragmentId: string) {
  return frameDocument.querySelector(
    `.hold-board .fragment-tile--reserved[data-fragment-id="${fragmentId}"]`
  ) as HTMLElement | null;
}

function getReservedItem(frameDocument: Document, fragmentId: string) {
  return getReservedTile(frameDocument, fragmentId)?.closest('.hold-board__item') as HTMLElement | null;
}

function getReplaceHandle(frameDocument: Document, fragmentId: string) {
  return frameDocument.querySelector(
    `.hold-board__replace-handle[aria-label="Drag ${fragmentId} to replace an edit fragment"]`
  ) as HTMLButtonElement | null;
}

function getBoundaryNode(frameDocument: Document, leftId: string, rightId: string) {
  return frameDocument.querySelector(
    `.boundary-handle[aria-label="Resize boundary between ${leftId} and ${rightId}"]`
  ) as HTMLButtonElement | null;
}

function getSeamNode(frameDocument: Document) {
  return frameDocument.querySelector('.synthetic-seam') as HTMLButtonElement | null;
}

function getPrecisionBoundaryNode(frameDocument: Document, leftId: string, rightId: string) {
  return frameDocument.querySelector(
    `.precision-overlay__boundary[aria-label="Adjust internal boundary between ${leftId} and ${rightId}"]`
  ) as HTMLButtonElement | null;
}

function getVisibleEditIds(frameDocument: Document) {
  return Array.from(frameDocument.querySelectorAll('.fragment-map-board .fragment-tile--edit')).map(
    (node) => (node as HTMLElement).dataset.fragmentId || ''
  );
}

function getReservedIds(frameDocument: Document) {
  return Array.from(frameDocument.querySelectorAll('.hold-board .fragment-tile--reserved')).map(
    (node) => (node as HTMLElement).dataset.fragmentId || ''
  );
}

function getDurationText(frameDocument: Document, fragmentId: string, scope: 'edit' | 'reserved' = 'edit') {
  const tile =
    scope === 'edit'
      ? getEditTile(frameDocument, fragmentId)
      : getReservedTile(frameDocument, fragmentId);
  return textOf(tile?.querySelector('.fragment-tile__duration') || null);
}

function getOverlayCount(frameDocument: Document) {
  return frameDocument.querySelectorAll('.precision-overlay').length;
}

function getOverlayChain(frameDocument: Document) {
  return Array.from(frameDocument.querySelectorAll('.precision-overlay .precision-overlay__segment')).map(
    (segment) => {
      const tile = segment.querySelector('.fragment-tile') as HTMLElement | null;
      const id = tile?.dataset.fragmentId || '?';
      const duration = textOf(segment.querySelector('.fragment-tile__duration'));
      return `${id}:${duration}`;
    }
  );
}

function getHoldPosition(frameDocument: Document, fragmentId: string) {
  const item = getReservedItem(frameDocument, fragmentId);
  return item ? `${item.style.left || '0px'},${item.style.top || '0px'}` : 'missing';
}

function getActionButton(frameDocument: Document, label: string) {
  return frameDocument.querySelector(`[aria-label="${label}"]`) as HTMLButtonElement | null;
}

function clickNode(node: HTMLElement) {
  node.dispatchEvent(
    new MouseEvent('click', {
      bubbles: true,
      cancelable: true
    })
  );
}

function dispatchPointerEvent(
  target: EventTarget,
  type: string,
  ownerWindow: Window,
  pointerId: number,
  clientX: number,
  clientY: number
) {
  const eventWindow = ownerWindow as Window & typeof globalThis;
  target.dispatchEvent(
    new eventWindow.PointerEvent(type, {
      bubbles: true,
      cancelable: true,
      pointerId,
      pointerType: 'mouse',
      isPrimary: true,
      button: 0,
      buttons: type === 'pointerup' || type === 'pointercancel' ? 0 : 1,
      clientX,
      clientY
    })
  );
}

function dispatchMouseEvent(
  target: EventTarget,
  type: string,
  ownerWindow: Window,
  clientX: number,
  clientY: number
) {
  const eventWindow = ownerWindow as Window & typeof globalThis;
  target.dispatchEvent(
    new eventWindow.MouseEvent(type, {
      bubbles: true,
      cancelable: true,
      button: 0,
      buttons: type === 'mouseup' ? 0 : 1,
      clientX,
      clientY
    })
  );
}

function dispatchDragEvent(
  target: EventTarget,
  type: string,
  ownerWindow: Window,
  dataTransfer: DataTransfer,
  clientX: number,
  clientY: number
) {
  const eventWindow = ownerWindow as Window & typeof globalThis;
  target.dispatchEvent(
    new eventWindow.DragEvent(type, {
      bubbles: true,
      cancelable: true,
      dataTransfer,
      clientX,
      clientY
    })
  );
}

function dispatchKey(frameDocument: Document, ownerWindow: Window, key: string, options?: { ctrlKey?: boolean; shiftKey?: boolean }) {
  const eventWindow = ownerWindow as Window & typeof globalThis;
  frameDocument.dispatchEvent(
    new eventWindow.KeyboardEvent('keydown', {
      bubbles: true,
      cancelable: true,
      key,
      ctrlKey: options?.ctrlKey,
      shiftKey: options?.shiftKey
    })
  );
}

async function triggerUndo(frameDocument: Document, frameWindow: Window) {
  dispatchKey(frameDocument, frameWindow, 'z', { ctrlKey: true });
  await wait(180);
}

async function triggerRedo(frameDocument: Document, frameWindow: Window) {
  dispatchKey(frameDocument, frameWindow, 'z', { ctrlKey: true, shiftKey: true });
  await wait(180);
}

function getDropMarkerEvidence(frameDocument: Document) {
  const slots = Array.from(frameDocument.querySelectorAll('.fragment-map-board .fragment-map-slot')) as HTMLElement[];

  for (let index = 0; index < slots.length; index += 1) {
    const slot = slots[index];
    const fragmentId =
      (slot.querySelector('.fragment-tile--edit') as HTMLElement | null)?.dataset.fragmentId || `slot-${index}`;

    if (slot.classList.contains('is-drop-before')) {
      return { index, marker: `before:${fragmentId}` };
    }

    if (slot.classList.contains('is-drop-after')) {
      return { index: index + 1, marker: `after:${fragmentId}` };
    }
  }

  return { index: null as number | null, marker: 'none' };
}

async function runReorderCase() {
  const { frameDocument, frameWindow } = await loadFreshApp();
  const sourceTile = getEditTile(frameDocument, 'E1');
  const b1Tile = getEditTile(frameDocument, 'B1');
  const c1Tile = getEditTile(frameDocument, 'C1');

  if (!sourceTile || !b1Tile || !c1Tile) {
    throw new Error('Reorder nodes are missing.');
  }

  const before = getVisibleEditIds(frameDocument).join(',');
  const sourceRect = sourceTile.getBoundingClientRect();
  const b1Rect = b1Tile.getBoundingClientRect();
  const c1Rect = c1Tile.getBoundingClientRect();
  const startX = sourceRect.left + sourceRect.width / 2;
  const startY = sourceRect.top + sourceRect.height / 2;
  const gapX = (b1Rect.right + c1Rect.left) / 2;
  const gapY = (b1Rect.top + b1Rect.height / 2 + c1Rect.top + c1Rect.height / 2) / 2;

  dispatchPointerEvent(sourceTile, 'pointerdown', frameWindow, 41, startX, startY);
  await wait(24);
  dispatchPointerEvent(frameDocument, 'pointermove', frameWindow, 41, gapX, gapY);
  await wait(60);
  const during = getDropMarkerEvidence(frameDocument);
  dispatchPointerEvent(frameDocument, 'pointerup', frameWindow, 41, gapX, gapY);
  await wait(220);

  const afterAction = getVisibleEditIds(frameDocument).join(',');
  await triggerUndo(frameDocument, frameWindow);
  const afterUndo = getVisibleEditIds(frameDocument).join(',');
  const undoRestore = getRestoreEvidence(frameDocument);
  await triggerRedo(frameDocument, frameWindow);
  const afterRedo = getVisibleEditIds(frameDocument).join(',');
  const redoRestore = getRestoreEvidence(frameDocument);

  const expected = 'A2,A3,B1,E1,C1,C3,D1,D4';
  return {
    pass:
      before === 'A2,A3,B1,C1,C3,D1,D4,E1' &&
      during.index === 3 &&
      during.marker === 'after:B1' &&
      afterAction === expected &&
      afterUndo === before &&
      afterRedo === expected &&
      undoRestore.mode === 'op' &&
      undoRestore.direction === 'undo' &&
      redoRestore.mode === 'op' &&
      redoRestore.direction === 'redo',
    evidence:
      `reorder before=${before} during=${during.index ?? 'none'}(${during.marker}) ` +
      `afterAction=${afterAction} undo=${afterUndo}[${undoRestore.mode}/${undoRestore.direction}] ` +
      `redo=${afterRedo}[${redoRestore.mode}/${redoRestore.direction}]`
  };
}

async function runReplaceCase() {
  const { frameDocument, frameWindow } = await loadFreshApp();
  const replaceHandle = getReplaceHandle(frameDocument, 'F1');
  const targetTile = getEditTile(frameDocument, 'A2');

  if (!replaceHandle || !targetTile) {
    throw new Error('Replace nodes are missing.');
  }

  const beforeEdit = getVisibleEditIds(frameDocument).join(',');
  const beforeHold = getReservedIds(frameDocument).join(',');
  const sourcePos = getHoldPosition(frameDocument, 'F1');
  const dt = new (frameWindow as Window & typeof globalThis).DataTransfer();
  const handleRect = replaceHandle.getBoundingClientRect();
  const targetRect = targetTile.getBoundingClientRect();
  const x = targetRect.left + targetRect.width / 2;
  const y = targetRect.top + targetRect.height / 2;

  dispatchDragEvent(replaceHandle, 'dragstart', frameWindow, dt, handleRect.left + 8, handleRect.top + 8);
  await wait(40);
  dispatchDragEvent(targetTile, 'dragenter', frameWindow, dt, x, y);
  dispatchDragEvent(targetTile, 'dragover', frameWindow, dt, x, y);
  await wait(40);
  dispatchDragEvent(targetTile, 'drop', frameWindow, dt, x, y);
  dispatchDragEvent(replaceHandle, 'dragend', frameWindow, dt, x, y);
  await wait(220);

  const afterActionEdit = getVisibleEditIds(frameDocument).join(',');
  const afterActionHold = getReservedIds(frameDocument).join(',');
  const inheritedPos = getHoldPosition(frameDocument, 'A2');

  await triggerUndo(frameDocument, frameWindow);
  const afterUndoEdit = getVisibleEditIds(frameDocument).join(',');
  const afterUndoHold = getReservedIds(frameDocument).join(',');
  const undoRestore = getRestoreEvidence(frameDocument);

  await triggerRedo(frameDocument, frameWindow);
  const afterRedoEdit = getVisibleEditIds(frameDocument).join(',');
  const afterRedoHold = getReservedIds(frameDocument).join(',');
  const redoRestore = getRestoreEvidence(frameDocument);

  return {
    pass:
      beforeEdit === 'A2,A3,B1,C1,C3,D1,D4,E1' &&
      beforeHold === 'F1,G2' &&
      afterActionEdit === 'F1,A3,B1,C1,C3,D1,D4,E1' &&
      afterActionHold === 'G2,A2' &&
      inheritedPos === sourcePos &&
      afterUndoEdit === beforeEdit &&
      afterUndoHold === beforeHold &&
      afterRedoEdit === afterActionEdit &&
      afterRedoHold === afterActionHold &&
      undoRestore.mode === 'op' &&
      redoRestore.mode === 'op',
    evidence:
      `replace beforeEdit=${beforeEdit} beforeHold=${beforeHold} sourcePos=${sourcePos} ` +
      `afterAction=${afterActionEdit}/${afterActionHold}@${inheritedPos} ` +
      `undo=${afterUndoEdit}/${afterUndoHold}[${undoRestore.mode}/${undoRestore.direction}] ` +
      `redo=${afterRedoEdit}/${afterRedoHold}[${redoRestore.mode}/${redoRestore.direction}]`
  };
}

async function runBoundaryCase() {
  const { frameDocument, frameWindow } = await loadFreshApp();
  const boundary = getBoundaryNode(frameDocument, 'A2', 'A3');

  if (!boundary) {
    throw new Error('Boundary node is missing.');
  }

  const beforeLeft = getDurationText(frameDocument, 'A2');
  const beforeRight = getDurationText(frameDocument, 'A3');
  boundary.dispatchEvent(
    new ((frameWindow as Window & typeof globalThis).KeyboardEvent)('keydown', {
      bubbles: true,
      cancelable: true,
      key: 'ArrowRight',
      shiftKey: true
    })
  );
  await wait(180);

  const afterActionLeft = getDurationText(frameDocument, 'A2');
  const afterActionRight = getDurationText(frameDocument, 'A3');
  await triggerUndo(frameDocument, frameWindow);
  const undoLeft = getDurationText(frameDocument, 'A2');
  const undoRight = getDurationText(frameDocument, 'A3');
  const undoRestore = getRestoreEvidence(frameDocument);
  await triggerRedo(frameDocument, frameWindow);
  const redoLeft = getDurationText(frameDocument, 'A2');
  const redoRight = getDurationText(frameDocument, 'A3');
  const redoRestore = getRestoreEvidence(frameDocument);

  return {
    pass:
      beforeLeft === '2.8s' &&
      beforeRight === '2.3s' &&
      afterActionLeft === '3.0s' &&
      afterActionRight === '2.1s' &&
      undoLeft === beforeLeft &&
      undoRight === beforeRight &&
      redoLeft === afterActionLeft &&
      redoRight === afterActionRight &&
      undoRestore.mode === 'op' &&
      redoRestore.mode === 'op' &&
      getOverlayCount(frameDocument) === 0,
    evidence:
      `boundary before=${beforeLeft}/${beforeRight} afterAction=${afterActionLeft}/${afterActionRight} ` +
      `undo=${undoLeft}/${undoRight}[${undoRestore.mode}/${undoRestore.direction}] ` +
      `redo=${redoLeft}/${redoRight}[${redoRestore.mode}/${redoRestore.direction}] overlay=${getOverlayCount(frameDocument)}`
  };
}

async function runPrecisionCase() {
  const { frameDocument, frameWindow } = await loadFreshApp();
  const seam = getSeamNode(frameDocument);
  if (!seam) {
    throw new Error('Seam node is missing.');
  }

  clickNode(seam);
  await wait(180);
  const beforeChain = getOverlayChain(frameDocument).join(',');
  const internalBoundary = getPrecisionBoundaryNode(frameDocument, 'C1', 'C2');
  if (!internalBoundary) {
    throw new Error('Precision boundary node is missing.');
  }

  const rect = internalBoundary.getBoundingClientRect();
  const startX = rect.left + rect.width / 2;
  const y = rect.top + rect.height / 2;
  dispatchMouseEvent(internalBoundary, 'mousedown', frameWindow, startX, y);
  await wait(24);
  dispatchMouseEvent(frameDocument, 'mousemove', frameWindow, startX + 14, y);
  await wait(120);
  const duringChain = getOverlayChain(frameDocument).join(',');
  dispatchMouseEvent(frameDocument, 'mouseup', frameWindow, startX + 14, y);
  await wait(180);

  const afterActionBoard = getDurationText(frameDocument, 'C1');
  const afterActionChain = getOverlayChain(frameDocument).join(',');
  const closeButton = frameDocument.querySelector('.precision-overlay .ghost-button') as HTMLButtonElement | null;
  closeButton?.click();
  await wait(120);

  await triggerUndo(frameDocument, frameWindow);
  const undoBoard = getDurationText(frameDocument, 'C1');
  const undoRestore = getRestoreEvidence(frameDocument);
  const undoSeam = getSeamNode(frameDocument);
  if (!undoSeam) {
    throw new Error('Seam node missing after precision undo.');
  }
  clickNode(undoSeam);
  await wait(180);
  const undoChain = getOverlayChain(frameDocument).join(',');
  (frameDocument.querySelector('.precision-overlay .ghost-button') as HTMLButtonElement | null)?.click();
  await wait(120);

  await triggerRedo(frameDocument, frameWindow);
  const redoBoard = getDurationText(frameDocument, 'C1');
  const redoRestore = getRestoreEvidence(frameDocument);
  const redoSeam = getSeamNode(frameDocument);
  if (!redoSeam) {
    throw new Error('Seam node missing after precision redo.');
  }
  clickNode(redoSeam);
  await wait(180);
  const redoChain = getOverlayChain(frameDocument).join(',');
  (frameDocument.querySelector('.precision-overlay .ghost-button') as HTMLButtonElement | null)?.click();
  await wait(120);

  return {
    pass:
      beforeChain === 'C1:2.8s,C2:1.4s,C3:3.0s' &&
      duringChain === 'C1:3.3s,C2:0.9s,C3:3.0s' &&
      afterActionBoard === '3.3s' &&
      afterActionChain === 'C1:3.3s,C2:0.9s,C3:3.0s' &&
      undoBoard === '2.8s' &&
      undoChain === beforeChain &&
      redoBoard === '3.3s' &&
      redoChain === afterActionChain &&
      undoRestore.mode === 'op' &&
      redoRestore.mode === 'op',
    evidence:
      `precision before=${beforeChain} during=${duringChain} afterAction=${afterActionBoard}/${afterActionChain} ` +
      `undo=${undoBoard}/${undoChain}[${undoRestore.mode}/${undoRestore.direction}] ` +
      `redo=${redoBoard}/${redoChain}[${redoRestore.mode}/${redoRestore.direction}] close=${getOverlayCount(frameDocument)}`
  };
}

async function runSnapshotFallbackCase() {
  const { frameDocument, frameWindow } = await loadFreshApp();
  const exclude = getActionButton(frameDocument, 'Exclude B1');
  if (!exclude) {
    throw new Error('Exclude button is missing.');
  }

  const before = getVisibleEditIds(frameDocument).join(',');
  clickNode(exclude);
  await wait(180);
  const afterAction = getVisibleEditIds(frameDocument).join(',');
  await triggerUndo(frameDocument, frameWindow);
  const afterUndo = getVisibleEditIds(frameDocument).join(',');
  const undoRestore = getRestoreEvidence(frameDocument);
  await triggerRedo(frameDocument, frameWindow);
  const afterRedo = getVisibleEditIds(frameDocument).join(',');
  const redoRestore = getRestoreEvidence(frameDocument);

  return {
    pass:
      before === 'A2,A3,B1,C1,C3,D1,D4,E1' &&
      afterAction === 'A2,A3,C1,C3,D1,D4,E1' &&
      afterUndo === before &&
      afterRedo === afterAction &&
      undoRestore.mode === 'snapshot' &&
      redoRestore.mode === 'snapshot',
    evidence:
      `snapshot exclude before=${before} afterAction=${afterAction} ` +
      `undo=${afterUndo}[${undoRestore.mode}/${undoRestore.direction}] ` +
      `redo=${afterRedo}[${redoRestore.mode}/${redoRestore.direction}]`
  };
}

async function runSnapshotLegacyCase() {
  const moveApp = await loadFreshApp();
  const moveButton = getActionButton(moveApp.frameDocument, 'Move A2 to Hold Area');
  if (!moveButton) {
    throw new Error('Move-to-hold button is missing.');
  }

  clickNode(moveButton);
  await wait(180);
  const moveAfter = `${getVisibleEditIds(moveApp.frameDocument).join(',')}|${getReservedIds(moveApp.frameDocument).join(',')}`;
  await triggerUndo(moveApp.frameDocument, moveApp.frameWindow);
  const moveUndo = `${getVisibleEditIds(moveApp.frameDocument).join(',')}|${getReservedIds(moveApp.frameDocument).join(',')}`;
  const moveUndoRestore = getRestoreEvidence(moveApp.frameDocument);
  await triggerRedo(moveApp.frameDocument, moveApp.frameWindow);
  const moveRedo = `${getVisibleEditIds(moveApp.frameDocument).join(',')}|${getReservedIds(moveApp.frameDocument).join(',')}`;
  const moveRedoRestore = getRestoreEvidence(moveApp.frameDocument);

  const restoreApp = await loadFreshApp();
  const restoreButton = getActionButton(restoreApp.frameDocument, 'Restore F1 to edit structure');
  if (!restoreButton) {
    throw new Error('Restore-from-hold button is missing.');
  }

  clickNode(restoreButton);
  await wait(180);
  const restoreAfter = `${getVisibleEditIds(restoreApp.frameDocument).join(',')}|${getReservedIds(restoreApp.frameDocument).join(',')}`;
  await triggerUndo(restoreApp.frameDocument, restoreApp.frameWindow);
  const restoreUndo = `${getVisibleEditIds(restoreApp.frameDocument).join(',')}|${getReservedIds(restoreApp.frameDocument).join(',')}`;
  const restoreUndoRestore = getRestoreEvidence(restoreApp.frameDocument);
  await triggerRedo(restoreApp.frameDocument, restoreApp.frameWindow);
  const restoreRedo = `${getVisibleEditIds(restoreApp.frameDocument).join(',')}|${getReservedIds(restoreApp.frameDocument).join(',')}`;
  const restoreRedoRestore = getRestoreEvidence(restoreApp.frameDocument);

  const repositionApp = await loadFreshApp();
  const holdItem = getReservedItem(repositionApp.frameDocument, 'F1');
  if (!holdItem) {
    throw new Error('Hold item F1 is missing.');
  }

  const beforePos = getHoldPosition(repositionApp.frameDocument, 'F1');
  const rect = holdItem.getBoundingClientRect();
  const startX = rect.left + rect.width / 2;
  const startY = rect.top + rect.height / 2;
  dispatchMouseEvent(holdItem, 'mousedown', repositionApp.frameWindow, startX, startY);
  await wait(24);
  dispatchMouseEvent(repositionApp.frameDocument, 'mousemove', repositionApp.frameWindow, startX + 20, startY + 16);
  await wait(40);
  dispatchMouseEvent(repositionApp.frameDocument, 'mouseup', repositionApp.frameWindow, startX + 20, startY + 16);
  await wait(180);
  const afterPos = getHoldPosition(repositionApp.frameDocument, 'F1');
  await triggerUndo(repositionApp.frameDocument, repositionApp.frameWindow);
  const undoPos = getHoldPosition(repositionApp.frameDocument, 'F1');
  const repositionUndoRestore = getRestoreEvidence(repositionApp.frameDocument);
  await triggerRedo(repositionApp.frameDocument, repositionApp.frameWindow);
  const redoPos = getHoldPosition(repositionApp.frameDocument, 'F1');
  const repositionRedoRestore = getRestoreEvidence(repositionApp.frameDocument);

  return {
    pass:
      moveAfter === 'A3,B1,C1,C3,D1,D4,E1|F1,G2,A2' &&
      moveUndo === 'A2,A3,B1,C1,C3,D1,D4,E1|F1,G2' &&
      moveRedo === moveAfter &&
      moveUndoRestore.mode === 'snapshot' &&
      moveRedoRestore.mode === 'snapshot' &&
      restoreAfter === 'A2,A3,B1,C1,C3,D1,D4,E1,F1|G2' &&
      restoreUndo === 'A2,A3,B1,C1,C3,D1,D4,E1|F1,G2' &&
      restoreRedo === restoreAfter &&
      restoreUndoRestore.mode === 'snapshot' &&
      restoreRedoRestore.mode === 'snapshot' &&
      afterPos !== beforePos &&
      undoPos === beforePos &&
      redoPos === afterPos &&
      repositionUndoRestore.mode === 'snapshot' &&
      repositionRedoRestore.mode === 'snapshot',
    evidence:
      `legacy move=${moveAfter}|undo=${moveUndo}[${moveUndoRestore.mode}]|redo=${moveRedo}[${moveRedoRestore.mode}] ` +
      `restore=${restoreAfter}|undo=${restoreUndo}[${restoreUndoRestore.mode}]|redo=${restoreRedo}[${restoreRedoRestore.mode}] ` +
      `holdPos=${beforePos}->${afterPos}->${undoPos}[${repositionUndoRestore.mode}]->${redoPos}[${repositionRedoRestore.mode}]`
  };
}

async function runNonRegressionGuard() {
  const { frameDocument } = await loadFreshApp();
  const a2 = getEditTile(frameDocument, 'A2');
  const b1 = getEditTile(frameDocument, 'B1');
  const summary = frameDocument.querySelector('.panel-card--summary .summary-card') as HTMLElement | null;

  if (!a2 || !b1 || !summary) {
    throw new Error('Non-regression nodes are missing.');
  }

  clickNode(a2);
  await wait(280);
  const focusChip = textOf(frameDocument.querySelector('.panel-card--detail .panel-chip'));
  const focusTitle = textOf(frameDocument.querySelector('.panel-card--detail .detail-copy h2'));

  clickNode(b1);
  await wait(80);
  clickNode(b1);
  await wait(280);
  const timeLensChip = textOf(frameDocument.querySelector('.panel-card--detail .panel-chip'));
  const timeLensTitle = textOf(frameDocument.querySelector('.panel-card--detail .detail-copy h2'));

  summary.dispatchEvent(
    new ((frameDocument.defaultView || window) as Window & typeof globalThis).PointerEvent('pointerdown', {
      bubbles: true,
      cancelable: true,
      pointerId: 83,
      pointerType: 'mouse',
      isPrimary: true,
      button: 0
    })
  );
  await wait(120);

  const clearedChip = textOf(frameDocument.querySelector('.panel-card--detail .panel-chip'));
  return {
    pass:
      focusChip === 'Focus Expanded' &&
      focusTitle === 'A2' &&
      timeLensChip === 'Time Lens' &&
      timeLensTitle === 'B1' &&
      clearedChip === 'Idle',
    evidence: `nonRegression focus=${focusChip}/${focusTitle} timeLens=${timeLensChip}/${timeLensTitle} clear=${clearedChip}`
  };
}

async function runInteractionChecks(): Promise<InteractionReport> {
  const reorder = await runReorderCase();
  const replace = await runReplaceCase();
  const boundary = await runBoundaryCase();
  const precision = await runPrecisionCase();
  const snapshotFallback = await runSnapshotFallbackCase();
  const snapshotLegacy = await runSnapshotLegacyCase();
  const nonRegression = await runNonRegressionGuard();

  const pass =
    reorder.pass &&
    replace.pass &&
    boundary.pass &&
    precision.pass &&
    snapshotFallback.pass &&
    snapshotLegacy.pass &&
    nonRegression.pass;

  const actualCurrentBehavior = [
    reorder.evidence,
    replace.evidence,
    boundary.evidence,
    precision.evidence,
    snapshotFallback.evidence,
    snapshotLegacy.evidence,
    nonRegression.evidence
  ].join(' || ');

  const results: Record<string, InteractionCaseResult> = {
    undoOpFirstRestoreOnly: {
      expectedBySpec:
        'Undo/redo should use op-first restore for reorder, replace-fragment, boundary-resize, and precision-boundary, fall back silently to snapshot restore where no op exists, preserve snapshot-only legacy paths, and leave the locked interaction baseline intact.',
      actualCurrentBehavior,
      status: pass ? 'Pass' : 'Fail',
      exactReason: pass
        ? null
        : 'Expected exact undo/redo round trips for reorder, replace, boundary, precision, snapshot fallback on exclude, snapshot-only legacy paths, and no regression in click/Time Lens baseline.',
      changedFiles: [],
      reproductionNote:
        'Used fresh app loads per case. Verified reorder, replace, normal boundary resize, and precision-boundary commit with action -> undo -> redo; verified snapshot fallback on exclude and snapshot-only move-to-hold / restore-from-hold / hold-area-reposition; then rechecked single-click focus, double-click Time Lens, and outside clear.'
    }
  };

  return {
    pass,
    results,
    targetUrl: window.location.href
  };
}

runInteractionChecks()
  .then((report) => {
    writeReport(report);
  })
  .catch((error: Error) => {
    writeReport({
      pass: false,
      targetUrl: frame.src,
      results: {
        runnerFailure: {
          expectedBySpec: 'Interaction spec runner should load the app and execute the scripted checks.',
          actualCurrentBehavior: `${error.name}: ${error.message}`,
          status: 'Fail',
          exactReason: `${error.name}: ${error.message}`,
          changedFiles: [],
          reproductionNote: 'The verification runner itself failed before undo verification completed.'
        }
      }
    });
  });

export {};
