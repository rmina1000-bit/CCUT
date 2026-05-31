import { test, expect } from '@playwright/test';
import {
  MOCK_PROJECTS,
  MOCK_SOURCE_ENTRIES,
  VERIFICATION_MOCK_FRAGMENTS,
  MOCK_PROPOSALS_THUMBNAIL_FIX
} from './verification_mock_fragments';

test.describe('PBE-APPLY-AUDIT: 3-way ID trace', () => {

  test('Trace ID and state after PBE apply', async ({ page }) => {
    // Capture page console logs
    page.on('console', msg => {
      console.log(`[BROWSER CONSOLE] ${msg.type()}: ${msg.text()}`);
    });
    page.on('pageerror', err => {
      console.error(`[BROWSER EXCEPTION] ${err.message}`);
    });
    
    await page.goto('/#debug-hydrate');
    
    // Wait for triggerPBEMock to be defined
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

    // Select Proposal A to make committedProposalId = "A"
    const commitBtn = page.locator('button:has-text("A안 선택")');
    await expect(commitBtn).toBeVisible({ timeout: 5000 });
    console.log("Clicking 'A안 선택' to commit Proposal A...");
    await commitBtn.click();

    console.log("Triggering PBE Mock...");
    await page.evaluate(() => {
      (window as any).triggerPBEMock('mid');
    });

    // Wait for PBE modal and applying
    const applyBtn = page.locator('button:has-text("적용하기")');
    await expect(applyBtn).toBeVisible({ timeout: 5000 });

    console.log("Clicking '적용하기'...");
    await applyBtn.click();

    // Wait some time for re-renders and logging to complete
    await page.waitForTimeout(2000);
    console.log("PBE audit scenario finished successfully.");
  });

});
