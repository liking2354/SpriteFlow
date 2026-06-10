/** rembg 抠图模型 — 共享类型与选项列表，供素材编辑器 & 视频帧编辑器共用 */

export type MatteModel =
  | "isnet-general-use"
  | "birefnet-general-lite"
  | "isnet-anime"
  | "birefnet-general"
  | "birefnet-portrait"
  | "birefnet-massive"
  | "birefnet-dis"
  | "birefnet-hrsod"
  | "birefnet-cod";

export const MATTE_MODEL_OPTIONS: Array<{ value: MatteModel; labelKey: string }> = [
  { value: "isnet-general-use", labelKey: "editor.matteModel.general" },
  { value: "birefnet-general-lite", labelKey: "editor.matteModel.lite" },
  { value: "isnet-anime", labelKey: "editor.matteModel.anime" },
  { value: "birefnet-general", labelKey: "editor.matteModel.photo" },
  { value: "birefnet-portrait", labelKey: "editor.matteModel.portrait" },
  { value: "birefnet-massive", labelKey: "editor.matteModel.massive" },
  { value: "birefnet-dis", labelKey: "editor.matteModel.dis" },
  { value: "birefnet-hrsod", labelKey: "editor.matteModel.hrsod" },
  { value: "birefnet-cod", labelKey: "editor.matteModel.cod" },
];

export const DEFAULT_MATTE_MODEL: MatteModel = "isnet-general-use";
