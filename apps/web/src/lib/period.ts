export const PERIODS = [7, 30, 90] as const;
export type Period = (typeof PERIODS)[number];
