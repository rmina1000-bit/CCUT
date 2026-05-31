import { test, expect } from '@playwright/test';
import {
  MOCK_PROJECTS,
  MOCK_SOURCE_ENTRIES,
  VERIFICATION_MOCK_FRAGMENTS,
  MOCK_PROPOSALS_THUMBNAIL_FIX
} from './verification_mock_fragments';

test.describe('PROPOSAL-IDENTITY-AUDIT: A/B identity & source mismatch trace', () => {

  test('Trace A/B proposals and playback details', async ({ page }) => {
    page.on('console', msg => {
      console.log(`[BROWSER CONSOLE] ${msg.type()}: ${msg.text()}`);
    });
    page.on('pageerror', err => {
      console.error(`[BROWSER EXCEPTION] ${err.message}`);
    });
    
    await page.goto('/#debug-hydrate');
    
    // Wait for mock hydration completed
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

    console.log("\n--- (A) Proposal A/B Original Dump ---");
    const proposals = await page.evaluate(() => {
      // Find the React state or DOM elements representing the proposals
      // Or we can retrieve them by evaluating the window or page variables
      // Let's print the proposals state if exposed, or extract them via DOM/elements
      return (window as any).debugProposals || null;
    });
    console.log("PROPOSALS_DUMP:", JSON.stringify(proposals));

    console.log("\n--- (B) Front-end Fragment Map Render Arrays ---");
    // We can evaluate resolvedFragments or filteredFragments
    const resolvedFrags = await page.evaluate(() => {
      return (window as any).debugResolvedFragments || null;
    });
    console.log("RESOLVED_FRAGMENTS_DUMP:", JSON.stringify(resolvedFrags));

    console.log("\n--- (C) Click Play Video Src Comparison ---");
    // Click on A/B proposals and measure the player variables
    console.log("Clicking 'A안 선택' to commit Proposal A...");
    const commitBtnA = page.locator('button:has-text("A안 선택")');
    await expect(commitBtnA).toBeVisible();
    await commitBtnA.click();
    await page.waitForTimeout(500);

    // Click on B proposal card to preview it
    console.log("Clicking B proposal card to preview...");
    // Let's find B card
    const bCard = page.locator('button:has-text("B안 선택"), div:has-text("사용자형")');
    if (await bCard.count() > 0) {
      await bCard.first().click();
    }
    await page.waitForTimeout(500);

    console.log("Audit scenario finished.");
  });

});
