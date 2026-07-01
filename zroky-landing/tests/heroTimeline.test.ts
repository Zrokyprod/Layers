import { describe, expect, it } from 'vitest';
import {
  HERO_SIGNATURE_HEX,
  getHeroTimelineState,
  isHeroStageComplete,
} from '../src/lib/heroTimeline';

describe('heroTimeline', () => {
  it('advances through the control-loop stages at the expected times', () => {
    expect(getHeroTimelineState(0.7).activeStage).toBe('proposed');
    expect(getHeroTimelineState(1.2).activeStage).toBe('held');
    expect(getHeroTimelineState(1.9).activeStage).toBe('approved');
    expect(getHeroTimelineState(2.6).activeStage).toBe('executed');
    expect(getHeroTimelineState(3.4).activeStage).toBe('verified');
    expect(getHeroTimelineState(3.9).activeStage).toBe('receipt');
  });

  it('tracks completed stages and typed signature progress', () => {
    const early = getHeroTimelineState(1.2);
    expect(isHeroStageComplete(early, 'held')).toBe(true);
    expect(isHeroStageComplete(early, 'approved')).toBe(false);
    expect(early.receiptVisible).toBe(false);

    const receipt = getHeroTimelineState(4.8);
    expect(receipt.receiptVisible).toBe(true);
    expect(receipt.signatureChars).toBeGreaterThan(0);
    expect(receipt.signatureChars).toBeLessThanOrEqual(HERO_SIGNATURE_HEX.length);
  });

  it('derives rail token position and line fill from loop progress', () => {
    const start = getHeroTimelineState(0.6);
    expect(start.tokenX).toBe(0);
    expect(start.lineFill).toBe(0);

    const middle = getHeroTimelineState(2.5);
    expect(middle.tokenX).toBeCloseTo(0.75);
    expect(middle.lineFill).toBe(middle.tokenX);

    const verified = getHeroTimelineState(3.3);
    expect(verified.tokenX).toBe(1);
    expect(verified.lineFill).toBe(1);
  });

  it('returns the final receipt state for reduced motion', () => {
    const state = getHeroTimelineState(0, true);
    expect(state.activeStage).toBe('receipt');
    expect(state.receiptVisible).toBe(true);
    expect(state.signatureChars).toBe(HERO_SIGNATURE_HEX.length);
    expect(state.tokenX).toBe(1);
    expect(state.lineFill).toBe(1);
    expect(state.completedStages).toEqual(['proposed', 'held', 'approved', 'executed', 'verified', 'receipt']);
  });
});
