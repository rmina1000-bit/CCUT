import { describe, it, expect } from 'vitest';
import { generateProposals } from './proposalOrchestrator';
import { createInitialSnapshot } from './directionSnapshot';
import { Fragment } from '@/data/fragmentData';

describe('strategyEngine capture', () => {
    it('should log A/B sequence during analysis initialization', () => {
        // Mock fragments
        const mockFragments: Fragment[] = [
            { fragment_id: 'F1', start_frame: 100, intelligence: { hook: 0.9 } } as any,
            { fragment_id: 'F2', start_frame: 200, intelligence: { hook: 0.5 } } as any,
            { fragment_id: 'F3', start_frame: 300, intelligence: { hook: 0.7 } } as any,
        ];

        const snapshot = createInitialSnapshot();
        const pair = generateProposals(mockFragments, snapshot);

        const keyA = pair.A.key_fragments;
        const keyB = pair.B.key_fragments;
        const isFirstDiff = keyA[0] !== keyB[0];

        // This is what would be logged in the browser console
        console.log(`[strategyEngine] A안 순서:`, keyA);
        console.log(`[strategyEngine] B안 순서:`, keyB);
        console.log(`[strategyEngine] A/B 첫 조각 다름: ${isFirstDiff}`);

        expect(keyA).toBeDefined();
        expect(keyB).toBeDefined();
    });
});
