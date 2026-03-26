import React, { useEffect } from 'react';
import ReactDOM from 'react-dom/client';
import '../index.css';
import { BoundaryPrecisionOverlay } from '../components/BoundaryPrecisionOverlay';
import { FragmentMap } from '../components/FragmentMap';
import { FragmentTile } from '../components/FragmentTile';
import { OriginalPanorama } from '../components/OriginalPanorama';
import { ReservedFragments } from '../components/ReservedFragments';
import { buildSmokeFixtures, noopFragmentHandler } from './smokeFixtures';

type SmokeStatus = 'pending' | 'pass' | 'fail';

const smokeState = window.__CCUT_COMPONENT_SMOKE__;

if (!smokeState) {
  throw new Error('Component smoke state is not initialized.');
}

function setComponentResult(name: string, status: SmokeStatus, message?: string) {
  smokeState.components[name] = { status, message };
}

class SmokeBoundary extends React.Component<
  { name: string; children: React.ReactNode },
  { hasError: boolean }
> {
  constructor(props: { name: string; children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
    setComponentResult(props.name, 'pending');
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error) {
    setComponentResult(this.props.name, 'fail', `${error.name}: ${error.message}`);
  }

  render() {
    if (this.state.hasError) {
      return (
        <section className="panel-card" data-smoke-component={this.props.name}>
          <strong>{this.props.name}</strong>
          <p>Mount failed.</p>
        </section>
      );
    }

    return this.props.children;
  }
}

function MountProbe({ name, children }: { name: string; children: React.ReactNode }) {
  useEffect(() => {
    if (smokeState.components[name]?.status !== 'fail') {
      setComponentResult(name, 'pass');
    }
  }, [name]);

  return (
    <section className="panel-card" data-smoke-component={name}>
      <div className="panel-header">
        <span className="eyebrow">Component Smoke</span>
        <span className="panel-chip">{name}</span>
      </div>
      <div style={{ marginTop: 12 }}>{children}</div>
    </section>
  );
}

function SmokeApp() {
  const { board, sourceFragments, visibleFragment, reservedFragment, overlay } = buildSmokeFixtures();

  return (
    <div style={{ padding: 12, display: 'grid', gap: 12 }}>
      <SmokeBoundary name="FragmentTile">
        <MountProbe name="FragmentTile">
          <FragmentTile
            fragment={visibleFragment}
            variant="edit"
            isSelected={false}
            isFocusExpanded={false}
            isTimeLens={false}
            isDimmed={false}
            isPlaying={false}
            playProgress={0}
            onSingleClick={() => undefined}
            onDoubleClick={() => undefined}
          />
        </MountProbe>
      </SmokeBoundary>

      <SmokeBoundary name="OriginalPanorama">
        <MountProbe name="OriginalPanorama">
          <OriginalPanorama
            sources={board.sourceVideos}
            fragments={sourceFragments}
            activeSource={visibleFragment.source_video}
            selectedFragmentId={visibleFragment.fragment_id}
            highlightedFragmentId={visibleFragment.fragment_id}
            focusExpandedId={null}
            playingFragmentId={null}
            playProgress={0}
            fragmentOverrides={new Map()}
            onSourceChange={() => undefined}
            onFragmentSelect={noopFragmentHandler}
          />
        </MountProbe>
      </SmokeBoundary>

      <SmokeBoundary name="FragmentMap">
        <MountProbe name="FragmentMap">
          <FragmentMap
            editFragments={board.editFragments}
            selectedFragmentId={visibleFragment.fragment_id}
            pairSelectedFragmentIds={[]}
            focusExpandedId={null}
            timeLensId={null}
            playingFragmentId={null}
            playProgress={0}
            boundaryHighlightIds={[]}
            isBoundaryDragging={false}
            fragmentOverrides={new Map()}
            dragOrigin={null}
            dragTargetVisibleIndex={null}
            replaceTargetId={null}
            onFragmentSingleClick={noopFragmentHandler}
            onFragmentDoubleClick={noopFragmentHandler}
            onPairSelectionToggle={noopFragmentHandler}
            onPrecisionEntryOpen={() => undefined}
            onDragStart={() => undefined}
            onDragTargetIndexChange={() => undefined}
            onReplaceTargetChange={() => undefined}
            onReplaceDrop={() => undefined}
            onDragDrop={() => undefined}
            onDragEnd={() => undefined}
          />
        </MountProbe>
      </SmokeBoundary>

      <SmokeBoundary name="ReservedFragments">
        <MountProbe name="ReservedFragments">
          <ReservedFragments
            fragments={board.reservedFragments}
            positions={board.holdAreaPositions}
            selectedFragmentId={reservedFragment.fragment_id}
            focusExpandedId={null}
            timeLensId={null}
            playingFragmentId={null}
            playProgress={0}
            onSelect={noopFragmentHandler}
            onRepositionStart={() => undefined}
          />
        </MountProbe>
      </SmokeBoundary>

      <SmokeBoundary name="BoundaryPrecisionOverlay">
        <MountProbe name="BoundaryPrecisionOverlay">
          <BoundaryPrecisionOverlay
            overlay={overlay}
            editFragments={board.editFragments}
            playingFragmentId={null}
            playProgress={0}
            onClose={() => undefined}
            onCommit={() => undefined}
            onPreviewChange={() => undefined}
            onPreviewClear={() => undefined}
            onSourceRecall={() => undefined}
          />
        </MountProbe>
      </SmokeBoundary>
    </div>
  );
}

function finalizeSmokeResult() {
  const requiredComponents = [
    'ReservedFragments',
    'FragmentMap',
    'OriginalPanorama',
    'FragmentTile',
    'BoundaryPrecisionOverlay'
  ];

  requiredComponents.forEach((name) => {
    if (!smokeState.components[name]) {
      setComponentResult(name, 'fail', 'No result was recorded.');
      return;
    }

    if (smokeState.components[name].status === 'pending') {
      setComponentResult(name, 'fail', 'Mount did not complete before timeout.');
    }
  });

  const pass =
    smokeState.consoleErrorCount === 0 &&
    smokeState.pageErrorCount === 0 &&
    requiredComponents.every((name) => smokeState.components[name]?.status === 'pass');

  const result = {
    pass,
    consoleErrorCount: smokeState.consoleErrorCount,
    pageErrorCount: smokeState.pageErrorCount,
    consoleErrors: smokeState.consoleErrors,
    pageErrors: smokeState.pageErrors,
    components: smokeState.components
  };

  const jsonNode = document.getElementById('component-smoke-json');
  if (jsonNode) {
    jsonNode.textContent = JSON.stringify(result);
  }
}

ReactDOM.createRoot(document.getElementById('smoke-root') as HTMLElement).render(
  <React.StrictMode>
    <SmokeApp />
  </React.StrictMode>
);

window.setTimeout(finalizeSmokeResult, 600);
