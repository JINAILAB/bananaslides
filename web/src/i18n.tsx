import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type Locale = "ko" | "en" | "zh-CN";

type TranslationParams = Record<string, string | number>;

type I18nContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  finalizeLocaleSelection: () => void;
  isLocaleBannerVisible: boolean;
  localeOptions: Array<{ value: Locale; label: string }>;
  t: (key: string, params?: TranslationParams) => string;
};

const STORAGE_KEY = "bananaslides.locale";

const LOCALE_LABELS: Record<Locale, string> = {
  ko: "한국어",
  en: "English",
  "zh-CN": "简体中文",
};

const TRANSLATIONS: Record<Locale, Record<string, string>> = {
  en: {
    "language.banner.message": "Choose your language for bananaslides.",
    "language.banner.continue": "Continue",
    "language.banner.selectAria": "Choose language",
    "language.banner.closeAria": "Close language banner",
    "common.removeFile": "Remove {{name}}",
    "common.secondsCount": "{{count}} seconds",
    "mode.auto": "Auto",
    "mode.review": "Review",
    "status.uploaded": "Uploaded",
    "status.prepared": "Prepared",
    "status.processing": "Processing",
    "status.awaiting_review": "Awaiting Review",
    "status.rebuilding_slide": "Rebuilding Slide",
    "status.building_deck": "Building PPTX",
    "status.completed": "Completed",
    "status.failed": "Failed",
    "boxType.text": "Text",
    "boxType.image": "Image",
    "source.base": "Base",
    "source.manual": "Manual",
    "upload.title.idle": "Convert Slides.",
    "upload.title.completed": "PPTX Ready.",
    "upload.subtitle.completed": "The current job is complete and ready to download.",
    "upload.title.failed": "Conversion Failed.",
    "upload.subtitle.failed": "The job stopped before completion. Review the error and start again.",
    "upload.title.processing": "Processing PPTX.",
    "upload.error.loadJob": "Failed to load job.",
    "upload.error.startConversion": "Failed to start conversion.",
    "upload.dropZone.title": "Drop your files here",
    "upload.dropZone.support": "Supports PDF, JPG, PNG, TIFF, WEBP, and BMP",
    "upload.dropZone.browse": "Browse Local Storage",
    "upload.selectedFiles": "Selected Files",
    "upload.stagedCount": "{{count}} staged",
    "upload.emptySelectedFiles": "Selected files will appear here.",
    "upload.strategy.title": "Conversion Strategy",
    "upload.strategy.description":
      "Choose the conversion path first, then drop source assets on the right. The whole default flow starts and finishes on this page.",
    "upload.strategy.auto.title": "Auto Mode",
    "upload.strategy.auto.description":
      "Upload, process, and download directly. Best when the OCR does not need manual review.",
    "upload.strategy.review.title": "Review Mode",
    "upload.strategy.review.description":
      "Stop before final PPTX generation, inspect OCR boxes, and rebuild after manual review.",
    "upload.estimatedTime": "Estimated processing time:",
    "upload.start": "Start Conversion",
    "upload.starting": "Starting…",
    "upload.currentJob.title": "Current Job",
    "upload.currentJob.description": "Job {{jobId}} is running in {{mode}} mode.",
    "upload.processingSteps.uploaded.label": "Uploaded",
    "upload.processingSteps.uploaded.description": "The job exists and the raw assets are stored.",
    "upload.processingSteps.prepared.label": "Prepared",
    "upload.processingSteps.prepared.description": "Images and PDF pages have been normalized into ordered slide assets.",
    "upload.processingSteps.processing.label": "Processing",
    "upload.processingSteps.processing.description":
      "OCR, masking, inpainting, and editable PPT reconstruction are running.",
    "upload.processingSteps.building_deck.label": "Building PPTX",
    "upload.processingSteps.building_deck.description":
      "The final PPTX is being assembled from the current slide artifacts.",
    "upload.processingSteps.completed.label": "Completed",
    "upload.processingSteps.completed.description": "The PPTX is ready to download.",
    "upload.failure.title": "Conversion failed",
    "upload.failure.unknown": "Unknown error.",
    "upload.summary.title": "Job Summary",
    "upload.summary.uploads": "Uploads",
    "upload.summary.slides": "Slides",
    "upload.summary.mode": "Mode",
    "upload.summary.status": "Status",
    "upload.download.title": "Download PPTX",
    "upload.download.description": "The editable PPTX has been assembled from the current slide artifacts.",
    "upload.download.button": "Download PPTX",
    "upload.next.title": "What happens next?",
    "upload.next.description":
      "Auto Mode stays on this page until the final PPTX is ready. Review Mode will move into the OCR review workspace once baseline artifacts are prepared.",
    "review.error.loadJob": "Failed to load review job.",
    "review.error.loadEditor": "Failed to load editor state.",
    "review.error.buildPptx": "Failed to build PPTX.",
    "review.error.saveEdits": "Failed to save OCR edits.",
    "review.aria.closePanel": "Close review panel",
    "review.aria.collapsePanel": "Collapse review panel",
    "review.aria.openPanel": "Open review panel",
    "review.loadingCanvas": "Loading review canvas…",
    "review.canvasAlt": "Slide under review",
    "review.workspace": "Review Workspace",
    "review.titleFallback": "OCR Review",
    "review.slideProgress": "Slide {{current}} of {{total}}. Review boxes only when the automatic OCR needs correction.",
    "review.mode.select": "Select Mode",
    "review.mode.newBox": "New Box Mode",
    "review.help.insert": "Choose the box type first, then drag on the slide to keep adding boxes.",
    "review.help.select": "Click to select, or drag on empty space to select multiple boxes.",
    "review.help.shortcuts": "Shortcuts: `T` Text box, `I` Image box, `S` Select, `Esc` back to Select.",
    "review.boxType.title": "Box Type",
    "review.boxType.new": "Applies to new boxes",
    "review.boxType.selected": "Applies to selected box",
    "review.build": "Build PPTX",
    "review.building": "Building…",
    "review.selection.none": "No box selected",
    "review.selection.multiple": "{{count}} boxes selected",
    "review.selection.single": "Box {{index}} • {{category}} • {{source}}",
    "review.selection.multipleNotice":
      "Multiple boxes are selected. Box type editing is available only when a single box is selected.",
    "review.delete.single": "Delete Box",
    "review.delete.multiple": "Delete Boxes",
    "review.emptySelectionHelp":
      "Select a box to edit its box type, drag in Select Mode to pick multiple boxes, or press Backspace to delete the current selection.",
  },
  ko: {
    "language.banner.message": "bananaslides에서 사용할 언어를 선택하세요.",
    "language.banner.continue": "계속",
    "language.banner.selectAria": "언어 선택",
    "language.banner.closeAria": "언어 선택 배너 닫기",
    "common.removeFile": "{{name}} 제거",
    "common.secondsCount": "{{count}}초",
    "mode.auto": "자동",
    "mode.review": "검토",
    "status.uploaded": "업로드됨",
    "status.prepared": "준비됨",
    "status.processing": "처리 중",
    "status.awaiting_review": "검토 대기",
    "status.rebuilding_slide": "슬라이드 재생성 중",
    "status.building_deck": "PPTX 생성 중",
    "status.completed": "완료",
    "status.failed": "실패",
    "boxType.text": "텍스트",
    "boxType.image": "이미지",
    "source.base": "기본",
    "source.manual": "수동",
    "upload.title.idle": "슬라이드 변환.",
    "upload.title.completed": "PPTX 준비 완료.",
    "upload.subtitle.completed": "현재 작업이 완료되어 바로 다운로드할 수 있습니다.",
    "upload.title.failed": "변환 실패.",
    "upload.subtitle.failed": "작업이 완료 전에 중단되었습니다. 오류를 확인한 뒤 다시 시작하세요.",
    "upload.title.processing": "PPTX 처리 중.",
    "upload.error.loadJob": "작업을 불러오지 못했습니다.",
    "upload.error.startConversion": "변환을 시작하지 못했습니다.",
    "upload.dropZone.title": "파일을 여기에 놓으세요",
    "upload.dropZone.support": "PDF, JPG, PNG, TIFF, WEBP, BMP를 지원합니다",
    "upload.dropZone.browse": "로컬 저장소에서 찾기",
    "upload.selectedFiles": "선택된 파일",
    "upload.stagedCount": "{{count}}개 대기 중",
    "upload.emptySelectedFiles": "선택한 파일이 여기에 표시됩니다.",
    "upload.strategy.title": "변환 전략",
    "upload.strategy.description":
      "먼저 변환 경로를 선택한 뒤 오른쪽에 원본 파일을 놓으세요. 기본 흐름은 이 페이지에서 시작하고 끝납니다.",
    "upload.strategy.auto.title": "자동 모드",
    "upload.strategy.auto.description": "업로드 후 바로 처리하고 다운로드합니다. OCR 검토가 거의 필요 없을 때 적합합니다.",
    "upload.strategy.review.title": "검토 모드",
    "upload.strategy.review.description": "최종 PPTX 생성 전에 멈추고 OCR 박스를 검토한 뒤 수동 수정 후 다시 생성합니다.",
    "upload.estimatedTime": "예상 처리 시간:",
    "upload.start": "변환 시작",
    "upload.starting": "시작 중…",
    "upload.currentJob.title": "현재 작업",
    "upload.currentJob.description": "작업 {{jobId}}가 {{mode}} 모드로 실행 중입니다.",
    "upload.processingSteps.uploaded.label": "업로드됨",
    "upload.processingSteps.uploaded.description": "작업이 생성되었고 원본 자산이 저장되었습니다.",
    "upload.processingSteps.prepared.label": "준비됨",
    "upload.processingSteps.prepared.description": "이미지와 PDF 페이지가 순서가 있는 슬라이드 자산으로 정리되었습니다.",
    "upload.processingSteps.processing.label": "처리 중",
    "upload.processingSteps.processing.description": "OCR, 마스킹, 인페인팅, 편집 가능한 PPT 재구성이 진행 중입니다.",
    "upload.processingSteps.building_deck.label": "PPTX 생성 중",
    "upload.processingSteps.building_deck.description": "현재 슬라이드 결과물을 기준으로 최종 PPTX를 조립하고 있습니다.",
    "upload.processingSteps.completed.label": "완료",
    "upload.processingSteps.completed.description": "PPTX를 다운로드할 수 있습니다.",
    "upload.failure.title": "변환 실패",
    "upload.failure.unknown": "알 수 없는 오류입니다.",
    "upload.summary.title": "작업 요약",
    "upload.summary.uploads": "업로드",
    "upload.summary.slides": "슬라이드",
    "upload.summary.mode": "모드",
    "upload.summary.status": "상태",
    "upload.download.title": "PPTX 다운로드",
    "upload.download.description": "현재 슬라이드 결과물을 기준으로 편집 가능한 PPTX가 조립되었습니다.",
    "upload.download.button": "PPTX 다운로드",
    "upload.next.title": "다음 단계",
    "upload.next.description": "자동 모드는 최종 PPTX가 준비될 때까지 이 페이지에 머뭅니다. 검토 모드는 baseline 결과물이 준비되면 OCR 검토 화면으로 이동합니다.",
    "review.error.loadJob": "검토 작업을 불러오지 못했습니다.",
    "review.error.loadEditor": "편집 상태를 불러오지 못했습니다.",
    "review.error.buildPptx": "PPTX를 생성하지 못했습니다.",
    "review.error.saveEdits": "OCR 편집 내용을 저장하지 못했습니다.",
    "review.aria.closePanel": "검토 패널 닫기",
    "review.aria.collapsePanel": "검토 패널 접기",
    "review.aria.openPanel": "검토 패널 열기",
    "review.loadingCanvas": "검토 캔버스를 불러오는 중…",
    "review.canvasAlt": "검토 중인 슬라이드",
    "review.workspace": "검토 작업공간",
    "review.titleFallback": "OCR 검토",
    "review.slideProgress": "슬라이드 {{current}} / {{total}}. 자동 OCR에 수정이 필요할 때만 박스를 검토하세요.",
    "review.mode.select": "선택 모드",
    "review.mode.newBox": "새 박스 모드",
    "review.help.insert": "먼저 박스 타입을 고른 뒤 슬라이드에서 드래그해 계속 박스를 추가하세요.",
    "review.help.select": "클릭해서 선택하거나 빈 공간을 드래그해 여러 박스를 선택하세요.",
    "review.help.shortcuts": "단축키: `T` 텍스트 박스, `I` 이미지 박스, `S` 선택, `Esc` 선택으로 돌아가기.",
    "review.boxType.title": "박스 타입",
    "review.boxType.new": "새 박스에 적용",
    "review.boxType.selected": "선택한 박스에 적용",
    "review.build": "PPTX 생성",
    "review.building": "생성 중…",
    "review.selection.none": "선택된 박스 없음",
    "review.selection.multiple": "{{count}}개 박스 선택됨",
    "review.selection.single": "박스 {{index}} • {{category}} • {{source}}",
    "review.selection.multipleNotice": "여러 박스가 선택되었습니다. 박스 타입 편집은 단일 박스를 선택했을 때만 가능합니다.",
    "review.delete.single": "박스 삭제",
    "review.delete.multiple": "박스들 삭제",
    "review.emptySelectionHelp":
      "박스를 선택해 타입을 바꾸고, 선택 모드에서 드래그해 여러 박스를 고르거나, Backspace로 현재 선택을 삭제하세요.",
  },
  "zh-CN": {
    "language.banner.message": "请选择 bananaslides 的显示语言。",
    "language.banner.continue": "继续",
    "language.banner.selectAria": "选择语言",
    "language.banner.closeAria": "关闭语言选择横幅",
    "common.removeFile": "移除 {{name}}",
    "common.secondsCount": "{{count}} 秒",
    "mode.auto": "自动",
    "mode.review": "校对",
    "status.uploaded": "已上传",
    "status.prepared": "已准备",
    "status.processing": "处理中",
    "status.awaiting_review": "等待校对",
    "status.rebuilding_slide": "正在重建幻灯片",
    "status.building_deck": "正在生成 PPTX",
    "status.completed": "已完成",
    "status.failed": "失败",
    "boxType.text": "文本",
    "boxType.image": "图片",
    "source.base": "基础",
    "source.manual": "手动",
    "upload.title.idle": "转换幻灯片。",
    "upload.title.completed": "PPTX 已准备好。",
    "upload.subtitle.completed": "当前任务已完成，可以直接下载。",
    "upload.title.failed": "转换失败。",
    "upload.subtitle.failed": "任务在完成前停止。请检查错误后重新开始。",
    "upload.title.processing": "正在处理 PPTX。",
    "upload.error.loadJob": "无法加载任务。",
    "upload.error.startConversion": "无法开始转换。",
    "upload.dropZone.title": "将文件拖放到这里",
    "upload.dropZone.support": "支持 PDF、JPG、PNG、TIFF、WEBP 和 BMP",
    "upload.dropZone.browse": "浏览本地文件",
    "upload.selectedFiles": "已选择的文件",
    "upload.stagedCount": "已暂存 {{count}} 个",
    "upload.emptySelectedFiles": "已选择的文件会显示在这里。",
    "upload.strategy.title": "转换策略",
    "upload.strategy.description": "先选择转换路径，再把源文件拖到右侧。默认流程会在这个页面开始并完成。",
    "upload.strategy.auto.title": "自动模式",
    "upload.strategy.auto.description": "上传后直接处理并下载。适合几乎不需要手动校对 OCR 的情况。",
    "upload.strategy.review.title": "校对模式",
    "upload.strategy.review.description": "在最终生成 PPTX 前暂停，检查 OCR 框，并在手动校对后重新生成。",
    "upload.estimatedTime": "预计处理时间：",
    "upload.start": "开始转换",
    "upload.starting": "正在开始…",
    "upload.currentJob.title": "当前任务",
    "upload.currentJob.description": "任务 {{jobId}} 正在以 {{mode}} 模式运行。",
    "upload.processingSteps.uploaded.label": "已上传",
    "upload.processingSteps.uploaded.description": "任务已创建，原始资源已存储。",
    "upload.processingSteps.prepared.label": "已准备",
    "upload.processingSteps.prepared.description": "图片和 PDF 页面已整理为有序的幻灯片资源。",
    "upload.processingSteps.processing.label": "处理中",
    "upload.processingSteps.processing.description": "OCR、蒙版、修补和可编辑 PPT 重建正在进行。",
    "upload.processingSteps.building_deck.label": "正在生成 PPTX",
    "upload.processingSteps.building_deck.description": "正在根据当前幻灯片结果组装最终 PPTX。",
    "upload.processingSteps.completed.label": "已完成",
    "upload.processingSteps.completed.description": "PPTX 已可下载。",
    "upload.failure.title": "转换失败",
    "upload.failure.unknown": "未知错误。",
    "upload.summary.title": "任务摘要",
    "upload.summary.uploads": "上传数",
    "upload.summary.slides": "幻灯片",
    "upload.summary.mode": "模式",
    "upload.summary.status": "状态",
    "upload.download.title": "下载 PPTX",
    "upload.download.description": "可编辑的 PPTX 已根据当前幻灯片结果组装完成。",
    "upload.download.button": "下载 PPTX",
    "upload.next.title": "接下来会发生什么？",
    "upload.next.description": "自动模式会停留在此页面，直到最终 PPTX 准备完成。校对模式会在 baseline 结果准备好后进入 OCR 校对工作区。",
    "review.error.loadJob": "无法加载校对任务。",
    "review.error.loadEditor": "无法加载编辑状态。",
    "review.error.buildPptx": "无法生成 PPTX。",
    "review.error.saveEdits": "无法保存 OCR 编辑内容。",
    "review.aria.closePanel": "关闭校对面板",
    "review.aria.collapsePanel": "收起校对面板",
    "review.aria.openPanel": "打开校对面板",
    "review.loadingCanvas": "正在加载校对画布…",
    "review.canvasAlt": "正在校对的幻灯片",
    "review.workspace": "校对工作区",
    "review.titleFallback": "OCR 校对",
    "review.slideProgress": "第 {{current}} / {{total}} 张幻灯片。仅在自动 OCR 需要修正时检查这些框。",
    "review.mode.select": "选择模式",
    "review.mode.newBox": "新建框模式",
    "review.help.insert": "先选择框类型，然后在幻灯片上拖拽，持续添加新框。",
    "review.help.select": "点击进行选择，或在空白区域拖拽以选择多个框。",
    "review.help.shortcuts": "快捷键：`T` 文本框，`I` 图片框，`S` 选择，`Esc` 返回选择。",
    "review.boxType.title": "框类型",
    "review.boxType.new": "应用于新框",
    "review.boxType.selected": "应用于当前选中框",
    "review.build": "生成 PPTX",
    "review.building": "生成中…",
    "review.selection.none": "未选择任何框",
    "review.selection.multiple": "已选择 {{count}} 个框",
    "review.selection.single": "框 {{index}} • {{category}} • {{source}}",
    "review.selection.multipleNotice": "当前选择了多个框。只有在选中单个框时才能编辑框类型。",
    "review.delete.single": "删除框",
    "review.delete.multiple": "删除多个框",
    "review.emptySelectionHelp": "选择一个框来编辑类型，在选择模式下拖拽以选中多个框，或按 Backspace 删除当前选择。",
  },
};

const I18nContext = createContext<I18nContextValue | null>(null);

function normalizeLocale(value: string | null | undefined): Locale | null {
  if (!value) {
    return null;
  }
  const normalized = value.toLowerCase();
  if (normalized.startsWith("ko")) {
    return "ko";
  }
  if (normalized.startsWith("zh")) {
    return "zh-CN";
  }
  if (normalized.startsWith("en")) {
    return "en";
  }
  return null;
}

function readStoredLocale(): Locale | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    return normalizeLocale(window.localStorage.getItem(STORAGE_KEY));
  } catch {
    return null;
  }
}

function detectBrowserLocale(): Locale {
  if (typeof navigator === "undefined") {
    return "en";
  }
  const candidates = Array.isArray(navigator.languages) && navigator.languages.length
    ? navigator.languages
    : [navigator.language];
  for (const candidate of candidates) {
    const locale = normalizeLocale(candidate);
    if (locale) {
      return locale;
    }
  }
  return "en";
}

function interpolate(template: string, params?: TranslationParams) {
  if (!params) {
    return template;
  }
  return template.replace(/\{\{(\w+)\}\}/g, (_, key: string) => String(params[key] ?? ""));
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocale] = useState<Locale>(() => readStoredLocale() ?? detectBrowserLocale());
  const [isLocaleBannerVisible, setIsLocaleBannerVisible] = useState<boolean>(() => readStoredLocale() === null);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const finalizeLocaleSelection = useCallback(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, locale);
    } catch {
      // Ignore storage write failures and continue with the in-memory locale.
    }
    setIsLocaleBannerVisible(false);
  }, [locale]);

  const t = useCallback(
    (key: string, params?: TranslationParams) => {
      const template = TRANSLATIONS[locale][key] ?? TRANSLATIONS.en[key] ?? key;
      return interpolate(template, params);
    },
    [locale],
  );

  const value = useMemo<I18nContextValue>(
    () => ({
      locale,
      setLocale,
      finalizeLocaleSelection,
      isLocaleBannerVisible,
      localeOptions: (Object.keys(LOCALE_LABELS) as Locale[]).map((value) => ({
        value,
        label: LOCALE_LABELS[value],
      })),
      t,
    }),
    [finalizeLocaleSelection, isLocaleBannerVisible, locale, t],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error("useI18n must be used inside I18nProvider.");
  }
  return context;
}
