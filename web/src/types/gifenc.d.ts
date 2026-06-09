declare module "gifenc" {
  export function GIFEncoder(): {
    writeFrame(
      data: ImageData,
      width: number,
      height: number,
      opts: { palette: number[][]; delay: number },
    ): void;
    finish(): void;
    bytes(): ArrayBuffer;
  };
  export function quantize(
    data: ImageData | Uint8ClampedArray,
    maxColors: number,
    opts?: { format?: string; oneBitAlpha?: number | boolean; clearAlpha?: boolean; clearAlphaThreshold?: number },
  ): number[][];
  export function applyPalette(
    data: ImageData | Uint8ClampedArray,
    palette: number[][],
    format?: string,
  ): ImageData;
}
