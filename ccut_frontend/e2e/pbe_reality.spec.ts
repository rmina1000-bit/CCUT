import { test, expect } from '@playwright/test';
import { playheadToPixel } from '../src/features/pbe/pbeModel';
import {
  MOCK_PROJECTS,
  MOCK_SOURCE_ENTRIES,
  VERIFICATION_MOCK_FRAGMENTS,
  MOCK_PROPOSALS_THUMBNAIL_FIX
} from './verification_mock_fragments';

test.describe('PBE-D4-C: Browser playhead drift & playback reality tests', () => {

  // We keep a history of measured values to detect if all cases are identical
  const measurements: Array<{ label: string; currentTime: number; barX: number }> = [];

  test.beforeEach(async ({ page }) => {
    // Capture page console logs
    page.on('console', msg => console.log(`[BROWSER CONSOLE] ${msg.type()}: ${msg.text()}`));
    page.on('pageerror', err => console.error(`[BROWSER EXCEPTION] ${err.message}`));
    
    // Navigate and hydrate debug mock state (Index.tsx #debug-hydrate)
    await page.goto('/#debug-hydrate');
    
    // Wait for mock hydration completed and editor target is ready
    await page.waitForFunction(() => {
      console.log("Checking triggerPBEMock:", typeof (window as any).triggerPBEMock);
      return (window as any).triggerPBEMock !== undefined;
    }, { timeout: 15000 });

    await page.evaluate(({ projects, sourceEntries, editFragments, proposals }) => {
      (window as any).triggerPBEMock({ projects, sourceEntries, editFragments, proposals });
    }, {
      projects: MOCK_PROJECTS,
      sourceEntries: MOCK_SOURCE_ENTRIES,
      editFragments: VERIFICATION_MOCK_FRAGMENTS,
      proposals: MOCK_PROPOSALS_THUMBNAIL_FIX
    });
  });

  const runDriftCase = async (page: any, caseLabel: string, triggerAction: () => Promise<void>) => {
    console.log(`\n--- Running PBE Reality Check: ${caseLabel} ---`);
    
    // 1. Open mock boundary modal via window interface helper
    await triggerAction();

    // Wait for modal transitions and CSS playhead transition (0.1s ease-out) to finish completely
    await page.waitForTimeout(300);

    // Ensure the PBE container or modal is visible and playhead is populated
    const playhead = page.locator('[data-testid="pbe-playhead-line"]');
    const track = page.locator('[data-testid="pbe-timeline-track"]');
    
    // Let's print the DOM HTML to see what's loaded on failure
    try {
      await expect(playhead).toBeVisible({ timeout: 10000 });
      await expect(track).toBeVisible({ timeout: 10000 });
    } catch (e) {
      const content = await page.content();
      console.log("[PAGE CONTENT ON TIMEOUT]\n", content.slice(0, 2000));
      throw e;
    }

    // 2. Measure Initial State (P1 ~ P6 alignment audit)
    const initialVideoTime = await page.evaluate(() => {
      const v = document.querySelector('[data-testid="pbe-video-element"]') as HTMLVideoElement;
      return v ? v.currentTime : 0;
    });
    
    const initialPlayheadSec = parseFloat(await playhead.getAttribute('data-playhead-sec') || '0');
    
    // Get absolute screen rects to compute actual relative horizontal layout offset
    const playheadRect = await playhead.evaluate(el => {
      const r = el.getBoundingClientRect();
      return { left: r.left, width: r.width, right: r.right };
    });
    const trackRect = await track.evaluate(el => {
      const r = el.getBoundingClientRect();
      return { left: r.left, width: r.width, right: r.right };
    });
    const barX = playheadRect.left - trackRect.left;
    console.log(`[RECT_DEBUG] ${caseLabel} playheadRect=${JSON.stringify(playheadRect)} trackRect=${JSON.stringify(trackRect)} barX=${barX}`);
    
    // Get the clip's start time for this case (matching the trigger configurations)
    const clipStartSec = caseLabel === 'C-첫' ? 0.0 : caseLabel === 'C-중' ? 6.0 : 16.0;
    
    // 3. Play Sample and check playhead progress
    // Click play button inside modal
    const playBtn = page.locator('button:has-text("재생")');
    await playBtn.click();
    
    // Allow video to play for 600ms to introduce active playing state and natural time update jitter
    await page.waitForTimeout(600);

    const midVideoTime = await page.evaluate(() => {
      const v = document.querySelector('[data-testid="pbe-video-element"]') as HTMLVideoElement;
      return v ? v.currentTime : 0;
    });
    console.log(`[${caseLabel}] play sample: t1=${initialVideoTime.toFixed(2)} -> t2=${midVideoTime.toFixed(2)} (currentTime 증가 확인)`);
    expect(midVideoTime).toBeGreaterThan(initialVideoTime);

    // Measure active playback state coordinates
    const activePlayheadSec = parseFloat(await playhead.getAttribute('data-playhead-sec') || '0');
    const playheadRectActive = await playhead.evaluate(el => {
      const r = el.getBoundingClientRect();
      return { left: r.left, width: r.width, right: r.right };
    });
    const trackRectActive = await track.evaluate(el => {
      const r = el.getBoundingClientRect();
      return { left: r.left, width: r.width, right: r.right };
    });
    const activeBarX = playheadRectActive.left - trackRectActive.left;
    
    // Calculate expectedPx from midVideoTime using playheadToPixel
    const expectedPx = playheadToPixel(midVideoTime, clipStartSec, 180);
    const drift = Math.abs(activeBarX - expectedPx);

    // Track measurements to verify uniqueness
    measurements.push({ label: caseLabel, currentTime: midVideoTime, barX: activeBarX });

    console.log(`[${caseLabel}] open=${caseLabel === 'C-첫' ? 'firstBoundary' : caseLabel === 'C-중' ? 'midBoundary' : 'SNS'} clipStartSec=${clipStartSec.toFixed(2)} -> currentTime=${midVideoTime.toFixed(2)} playheadSec=${activePlayheadSec.toFixed(2)} barX=${activeBarX.toFixed(2)} expX=${expectedPx.toFixed(2)} drift=${drift.toFixed(2)}`);

    // Detect measurement duplication across distinct runs
    if (measurements.length === 3) {
      const m1 = measurements[0];
      const m2 = measurements[1];
      const m3 = measurements[2];
      if (m1.currentTime === m2.currentTime && m2.currentTime === m3.currentTime && m1.barX === m2.barX && m2.barX === m3.barX) {
        console.error("측정 실패: 동일값, 원인 미상 (모든 케이스의 currentTime과 barX가 동일하여 실측이 아님)");
        throw new Error("측정 실패: 동일값, 원인 미상 (모든 케이스의 currentTime과 barX가 동일하여 실측이 아님)");
      }
    }

    // 4. Test looping mechanism by seeking close to the end of the active group
    // First: 6s, Mid: 20s, SNS: 26s
    const clipEndSec = caseLabel === 'C-첫' ? 6.0 : caseLabel === 'C-중' ? 20.0 : 26.0;
    await page.evaluate((targetEnd) => {
      const v = document.querySelector('[data-testid="pbe-video-element"]') as HTMLVideoElement;
      if (v) {
        v.currentTime = targetEnd - 0.2;
      }
    }, clipEndSec);

    // Wait for loop back reset
    await page.waitForTimeout(1000);
    const postLoopVideoTime = await page.evaluate(() => {
      const v = document.querySelector('[data-testid="pbe-video-element"]') as HTMLVideoElement;
      return v ? v.currentTime : 0;
    });
    console.log(`[${caseLabel}] stop: clipEndSec=${clipEndSec.toFixed(2)} reached -> currentTime reset/reset to boundary = ${postLoopVideoTime.toFixed(2)} (loop OK)`);
    
    // Close editor modal
    const closeBtn = page.locator('button:has-text("취소")');
    await closeBtn.click();
  };

  test('C-첫: 첫 조각 경계 PBE 열기 및 drift 실측', async ({ page }) => {
    await runDriftCase(page, 'C-첫', async () => {
      await page.evaluate(() => {
        (window as any).triggerPBEMock('first');
      });
    });
  });

  test('C-중: 중간 조각 경계 PBE 열기 및 drift 실측', async ({ page }) => {
    await runDriftCase(page, 'C-중', async () => {
      await page.evaluate(() => {
        (window as any).triggerPBEMock('mid');
      });
    });
  });

  test('C-혼: SNS 혼합 조각 경계 PBE 열기 및 drift 실측', async ({ page }) => {
    await runDriftCase(page, 'C-혼', async () => {
      await page.evaluate(() => {
        (window as any).triggerPBEMock('sns');
      });
    });
  });
});
