declare module "gifuct-js" {
  export function parseGIF(buffer: ArrayBuffer): unknown;
  export function decompressFrames(gifData: unknown, buildPatch: boolean): Array<{
    dims: { width: number; height: number; top: number; left: number };
    patch: Uint8ClampedArray;
    delay: number;
    disposalType: number;
  }>;
}
