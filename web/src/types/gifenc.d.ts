declare module "gifenc" {
  export interface GifFrameOpts {
    transparent?: boolean;
    transparentIndex?: number;
    delay?: number;
    palette?: number[][] | null;
    repeat?: number;
    colorDepth?: number;
    dispose?: number;
  }

  export function GIFEncoder(opt?: { initialCapacity?: number; auto?: boolean }): {
    writeFrame(
      index: Uint8Array,
      width: number,
      height: number,
      opts?: GifFrameOpts,
    ): void;
    finish(): void;
    bytes(): Uint8Array;
    reset(): void;
    bytesView(): Uint8Array;
    readonly buffer: ArrayBuffer;
    readonly stream: unknown;
  };
  export function quantize(
    data: Uint8Array | Uint8ClampedArray,
    maxColors: number,
    opts?: { format?: string; oneBitAlpha?: number | boolean; clearAlpha?: boolean; clearAlphaThreshold?: number },
  ): number[][];
  export function applyPalette(
    data: Uint8Array | Uint8ClampedArray,
    palette: number[][],
    format?: string,
  ): Uint8Array;
}
