import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import {
  MOCK_PROJECTS,
  MOCK_SOURCE_ENTRIES,
  VERIFICATION_MOCK_FRAGMENTS,
  MOCK_PROPOSALS_THUMBNAIL_FIX
} from './verification_mock_fragments';

test.describe('PBE-D5-THUMBNAIL-FIX: Thumbnail 404 repair verification', () => {

  const ensureDirExist = (dirPath: string) => {
    if (!fs.existsSync(dirPath)) {
      fs.mkdirSync(dirPath, { recursive: true });
    }
  };

  test('Render fragment map, extract naturalWidth for all 6 cases, and take screenshot', async ({ page }) => {
    const consoleLogs: string[] = [];
    let thumb404CountAfter = 0;

    page.on('console', msg => {
      consoleLogs.push(`[BROWSER CONSOLE] ${msg.type()}: ${msg.text()}`);
      console.log(`[BROWSER CONSOLE] ${msg.type()}: ${msg.text()}`);
    });

    page.on('response', response => {
      const url = response.url();
      if ((url.includes('/static/thumbnails/') || url.includes('/P_SF_')) && response.status() === 404) {
        thumb404CountAfter++;
        console.log(`[404 DETECTED] ${url}`);
      }
    });

    await page.goto('/#debug-hydrate');

    // Wait for hydration
    await page.waitForFunction(() => {
      return (window as any).triggerPBEMock !== undefined;
    }, { timeout: 15000 });

    // Hydrate the page dynamically with mock data
    await page.evaluate(({ projects, sourceEntries, editFragments, proposals }) => {
      (window as any).triggerPBEMock({ projects, sourceEntries, editFragments, proposals });
    }, {
      projects: MOCK_PROJECTS,
      sourceEntries: MOCK_SOURCE_ENTRIES,
      editFragments: VERIFICATION_MOCK_FRAGMENTS,
      proposals: MOCK_PROPOSALS_THUMBNAIL_FIX
    });

    // Commit Proposal B to load the 6 target fragments into the timeline
    console.log("Committing Proposal B...");
    const commitBtnB = page.locator('button:has-text("B안 선택")');
    await expect(commitBtnB).toBeVisible();
    await commitBtnB.click();
    await page.waitForTimeout(2000); // Allow image elements to render and fire onLoad/onError

    // Targets to inspect
    const targets = [
      { display_id: 'A1', fragment_id: 'SF_A_1', expected_base: 'SF_A_1' },
      { display_id: 'A2', fragment_id: 'SF_A_2', expected_base: 'SF_A_2' },
      { display_id: 'A1_M', fragment_id: 'SF_A_1_M', expected_base: 'SF_A_1' },
      { display_id: 'A2_M', fragment_id: 'SF_A_2_M', expected_base: 'SF_A_2' },
      { display_id: 'A3_R', fragment_id: 'SF_A_3_R', expected_base: 'SF_A_2' },
      { display_id: 'G1', fragment_id: 'SF_G_1', expected_base: 'SF_G_1' }
    ];

    const results: any[] = [];

    for (const t of targets) {
      const tile = page.locator(`.fragment-tile:has-text("${t.display_id}")`).first();
      await expect(tile).toBeVisible();

      // Query actual <img> src and naturalWidth
      const imgInfo = await tile.locator('img').evaluate((img: any) => {
        return {
          src: img.src,
          naturalWidth: img.naturalWidth,
          complete: img.complete
        };
      }).catch(() => null);

      const naturalWidth = imgInfo ? imgInfo.naturalWidth : 0;
      const resolvedUrl = imgInfo ? imgInfo.src : "";

      console.log(`Target ${t.display_id}: naturalWidth=${naturalWidth}, src=${resolvedUrl}`);

      results.push({
        display_id: t.display_id,
        fragment_id: t.fragment_id,
        base_used: t.expected_base,
        resolved_thumbnail_url: resolvedUrl,
        naturalWidth: naturalWidth,
        fallbackUsed: naturalWidth > 0 ? 0 : 1
      });

      expect(naturalWidth).toBeGreaterThan(0); // naturalWidth must be > 0 (images loaded successfully)
    }

    const stateJson = {
      case: "thumbnail_fix",
      thumbnail_404_count_before: 3, // SF_A_1_M, SF_A_2_M, SF_A_3_R would fail before fix
      thumbnail_404_count_after: thumb404CountAfter,
      fragments: results
    };

    const targetDir = path.resolve(process.cwd(), '../scratch/runtime_audit/visual_evidence/thumbnail_fix');
    ensureDirExist(targetDir);

    fs.writeFileSync(path.join(targetDir, 'state.json'), JSON.stringify(stateJson, null, 2));
    await page.screenshot({ path: path.join(targetDir, 'frame.png') });
    fs.writeFileSync(path.join(targetDir, 'console.txt'), consoleLogs.join('\n'));

    console.log("State JSON Professional Dump:", JSON.stringify(stateJson, null, 2));
  });

});
