/** Apple keyboards paste with ⌘V; everyone else — most employees, on Windows — with Ctrl+V. */
export function isApple(): boolean {
  if (typeof navigator === "undefined") return false;
  const data = (navigator as Navigator & { userAgentData?: { platform?: string } }).userAgentData;
  const platform = data?.platform || navigator.platform || navigator.userAgent;
  return /mac|iphone|ipad|ipod/i.test(platform);
}

export function pasteKeys(): string {
  return isApple() ? "⌘V" : "Ctrl+V";
}
