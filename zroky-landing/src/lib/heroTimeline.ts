export type HeroTone = 'neutral' | 'warning' | 'accent' | 'success';

export type HeroStageId = 'proposed' | 'held' | 'approved' | 'executed' | 'verified' | 'receipt';

export interface HeroStageDefinition {
  id: HeroStageId;
  label: string;
  startsAt: number;
  tone: HeroTone;
  status: string;
}

export interface HeroTimelineState {
  activeStage: HeroStageId;
  completedStages: HeroStageId[];
  receiptVisible: boolean;
  signatureChars: number;
  tokenX: number;
  lineFill: number;
  loopProgress: number;
}

export const HERO_LOOP_SECONDS = 6;

export const HERO_SIGNATURE_HEX = '7f3a9e10c2d4b6a8d92c';

export const HERO_STAGES: HeroStageDefinition[] = [
  { id: 'proposed', label: 'Proposed', startsAt: 0.6, tone: 'neutral', status: 'Rec' },
  { id: 'held', label: 'Held', startsAt: 1.1, tone: 'warning', status: 'Hold' },
  { id: 'approved', label: 'Approved', startsAt: 1.8, tone: 'accent', status: 'OK' },
  { id: 'executed', label: 'Executed', startsAt: 2.5, tone: 'accent', status: 'Run' },
  { id: 'verified', label: 'Verified', startsAt: 3.3, tone: 'success', status: 'Match' },
  { id: 'receipt', label: 'Receipt', startsAt: 3.8, tone: 'success', status: 'Signed' },
];

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function railProgress(loopProgress: number) {
  const railStages = HERO_STAGES.filter((stage) => stage.id !== 'receipt');
  const first = railStages[0];
  const last = railStages[railStages.length - 1];
  if (loopProgress <= first.startsAt) return 0;
  if (loopProgress >= last.startsAt) return 1;

  for (let index = 0; index < railStages.length - 1; index += 1) {
    const current = railStages[index];
    const next = railStages[index + 1];
    if (loopProgress >= current.startsAt && loopProgress <= next.startsAt) {
      const segment = (loopProgress - current.startsAt) / (next.startsAt - current.startsAt);
      return clamp((index + segment) / (railStages.length - 1), 0, 1);
    }
  }

  return 0;
}

export function getHeroTimelineState(elapsedSeconds: number, reducedMotion = false): HeroTimelineState {
  if (reducedMotion) {
    return {
      activeStage: 'receipt',
      completedStages: HERO_STAGES.map((stage) => stage.id),
      receiptVisible: true,
      signatureChars: HERO_SIGNATURE_HEX.length,
      tokenX: 1,
      lineFill: 1,
      loopProgress: 1,
    };
  }

  const loopProgress = ((elapsedSeconds % HERO_LOOP_SECONDS) + HERO_LOOP_SECONDS) % HERO_LOOP_SECONDS;
  const visibleStages = HERO_STAGES.filter((stage) => loopProgress >= stage.startsAt);
  const activeStage = visibleStages.length > 0 ? visibleStages[visibleStages.length - 1].id : 'proposed';
  const receiptVisible = loopProgress >= 3.8;
  const typingProgress = clamp((loopProgress - 4.2) / 1.1, 0, 1);
  const tokenX = railProgress(loopProgress);

  return {
    activeStage,
    completedStages: visibleStages.map((stage) => stage.id),
    receiptVisible,
    signatureChars: Math.round(HERO_SIGNATURE_HEX.length * typingProgress),
    tokenX,
    lineFill: tokenX,
    loopProgress,
  };
}

export function isHeroStageComplete(state: HeroTimelineState, stageId: HeroStageId) {
  return state.completedStages.includes(stageId);
}
