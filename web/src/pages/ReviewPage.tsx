import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { ReviewCanvas } from "../components/ReviewCanvas";
import { Shell } from "../components/Shell";
import { useI18n } from "../i18n";
import {
  apiFileUrl,
  buildDeck,
  fetchEditorState,
  fetchJob,
  saveEditorState,
} from "../lib/api";
import type { EditorBox, EditorCategory, EditorState, JobRecord, SlideRecord } from "../lib/types";

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function shouldIgnoreBackspace(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  return target.isContentEditable || Boolean(target.closest("input, textarea, select, [contenteditable='true']"));
}

function categoryButtonClass(active: boolean) {
  return active
    ? "border-primary bg-primary text-white"
    : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50";
}

export function ReviewPage() {
  const { t } = useI18n();
  const { jobId = "" } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [job, setJob] = useState<JobRecord | null>(null);
  const [editorState, setEditorState] = useState<EditorState | null>(null);
  const [boxes, setBoxes] = useState<EditorBox[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [isInsertMode, setIsInsertMode] = useState(true);
  const [activeCategory, setActiveCategory] = useState<EditorCategory>("text");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<"build" | "navigating" | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  const selectedSlideNumber = Number(searchParams.get("slide") || 1);
  const slides = job?.slides ?? [];
  const currentSlide = slides.find((slide) => slide.slide_number === selectedSlideNumber) || null;
  const selectedBox = useMemo(
    () => (selectedIds.length === 1 ? boxes.find((box) => box.box_id === selectedIds[0]) || null : null),
    [boxes, selectedIds],
  );
  const selectedBoxIndex = selectedBox ? boxes.findIndex((box) => box.box_id === selectedBox.box_id) : -1;

  useEffect(() => {
    async function loadJob() {
      try {
        const nextJob = await fetchJob(jobId);
        setJob(nextJob);
        if (nextJob.status === "completed") {
          navigate(`/?job=${jobId}`, { replace: true });
        }
      } catch (nextError) {
        setError(nextError instanceof Error ? nextError.message : t("review.error.loadJob"));
      }
    }
    void loadJob();
  }, [jobId, navigate, t]);

  useEffect(() => {
    async function loadEditor() {
      if (!job || !job.slides.length) {
        return;
      }
      try {
        const safeSlideNumber = clamp(selectedSlideNumber, 1, job.slides.length);
        if (safeSlideNumber !== selectedSlideNumber) {
          setSearchParams({ slide: String(safeSlideNumber) }, { replace: true });
          return;
        }
        const nextState = await fetchEditorState(jobId, safeSlideNumber);
        setEditorState(nextState);
        setBoxes(nextState.boxes);
        setSelectedIds([]);
        setError(null);
      } catch (nextError) {
        setError(nextError instanceof Error ? nextError.message : t("review.error.loadEditor"));
      }
    }
    void loadEditor();
  }, [job, jobId, selectedSlideNumber, setSearchParams, t]);

  useEffect(() => {
    if (selectedBox?.category) {
      setActiveCategory(selectedBox.category);
    }
  }, [selectedBox]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (shouldIgnoreBackspace(event.target)) {
        return;
      }

      if (event.code === "KeyT") {
        event.preventDefault();
        setSelectedIds([]);
        setActiveCategory("text");
        setIsInsertMode(true);
        return;
      }

      if (event.code === "KeyI") {
        event.preventDefault();
        setSelectedIds([]);
        setActiveCategory("figure");
        setIsInsertMode(true);
        return;
      }

      if (event.code === "KeyS") {
        event.preventDefault();
        setIsInsertMode(false);
        return;
      }

      if (event.key === "Escape" && isInsertMode) {
        event.preventDefault();
        setIsInsertMode(false);
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isInsertMode]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Backspace" || selectedIds.length === 0 || shouldIgnoreBackspace(event.target)) {
        return;
      }
      event.preventDefault();
      setBoxes((current) => current.filter((box) => !selectedIds.includes(box.box_id)));
      setSelectedIds([]);
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [selectedIds]);

  function updateSelectedBox(patch: Partial<EditorBox>) {
    if (!selectedBox || !editorState) {
      return;
    }
    setBoxes((current) =>
      current.map((box) => {
        if (box.box_id !== selectedBox.box_id) {
          return box;
        }
        const next = { ...box, ...patch };
        return {
          ...next,
          x: clamp(Number(next.x) || 0, 0, editorState.slide_size.width_px - (Number(next.width) || 1)),
          y: clamp(Number(next.y) || 0, 0, editorState.slide_size.height_px - (Number(next.height) || 1)),
          width: clamp(Number(next.width) || 1, 1, editorState.slide_size.width_px),
          height: clamp(Number(next.height) || 1, 1, editorState.slide_size.height_px),
        };
      }),
    );
  }

  async function handleBuildDeck() {
    if (!editorState) {
      return;
    }
    setBusyAction("build");
    setMessage(null);
    setError(null);
    try {
      await saveEditorState(jobId, editorState.slide_number, boxes);
      await buildDeck(jobId);
      navigate(`/?job=${jobId}`);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : t("review.error.buildPptx"));
    } finally {
      setBusyAction(null);
    }
  }

  async function handleSelectSlide(nextSlideNumber: number) {
    if (nextSlideNumber === selectedSlideNumber || busyAction !== null) {
      return;
    }
    setError(null);
    if (!editorState) {
      setSearchParams({ slide: String(nextSlideNumber) });
      return;
    }
    setBusyAction("navigating");
    try {
      await saveEditorState(jobId, editorState.slide_number, boxes);
      setSearchParams({ slide: String(nextSlideNumber) });
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : t("review.error.saveEdits"));
    } finally {
      setBusyAction(null);
    }
  }

  const selectionSummary = selectedBox
    ? t("review.selection.single", {
        index: selectedBoxIndex + 1,
        category: selectedBox.category === "figure" ? t("boxType.image") : t("boxType.text"),
        source: selectedBox.source === "manual" ? t("source.manual") : t("source.base"),
      })
    : selectedIds.length > 1
      ? t("review.selection.multiple", { count: selectedIds.length })
      : t("review.selection.none");
  const sidebarWidth = "min(88vw, 22rem)";
  const mainContentStyle = {
    "--review-main-pr": `calc(${sidebarWidth} + 1.25rem)`,
  } as CSSProperties;

  return (
    <Shell contentWidth="full" contentPadding="flush-left">
      <section className="relative min-w-0 px-6 pb-10 lg:px-10">
        {isSidebarOpen ? (
          <button
            type="button"
            aria-label={t("review.aria.closePanel")}
            className="fixed inset-0 z-30 bg-slate-900/12 backdrop-blur-[1px] lg:hidden"
            onClick={() => setIsSidebarOpen(false)}
          />
        ) : null}

        <button
          type="button"
          aria-expanded={isSidebarOpen}
          aria-label={isSidebarOpen ? t("review.aria.collapsePanel") : t("review.aria.openPanel")}
          className="fixed top-24 z-50 inline-flex h-14 w-11 items-center justify-center rounded-l-xl rounded-r-none border border-r-0 border-slate-200 bg-white text-slate-900 shadow-[-12px_18px_40px_-30px_rgba(15,23,42,0.35)] transition-all duration-300 hover:bg-slate-50 lg:hidden"
          style={{ right: isSidebarOpen ? sidebarWidth : "0" }}
          onClick={() => setIsSidebarOpen((current) => !current)}
        >
          <span className="material-symbols-outlined text-[28px]">
            {isSidebarOpen ? "chevron_right" : "chevron_left"}
          </span>
        </button>

        <section
          className="min-w-0 space-y-4 pr-0 transition-[padding-right] duration-300 ease-out lg:pr-[var(--review-main-pr)]"
          style={mainContentStyle}
        >
          <div>
            {editorState ? (
              <ReviewCanvas
                slideSize={editorState.slide_size}
                imageUrl={editorState.image_url}
                boxes={boxes}
                selectedIds={selectedIds}
                setSelectedIds={setSelectedIds}
                setBoxes={setBoxes}
                activeCategory={activeCategory}
                isInsertMode={isInsertMode}
                setInsertMode={setIsInsertMode}
              />
            ) : (
              <div className="p-8 text-sm text-muted">{t("review.loadingCanvas")}</div>
            )}
          </div>

          <div className="pt-2">
            <div className="flex gap-2 overflow-x-auto pb-2">
              {slides.map((slide: SlideRecord) => (
                <button
                  key={slide.slide_number}
                  onClick={() => void handleSelectSlide(slide.slide_number)}
                  disabled={busyAction !== null}
                  className={`min-w-[120px] overflow-hidden border text-left transition ${
                    slide.slide_number === selectedSlideNumber
                      ? "border-primary bg-primary-soft"
                      : "border-slate-200 bg-surface-low hover:border-slate-300"
                  }`}
                >
                  <img
                    src={apiFileUrl(`/jobs/${jobId}/files/${slide.image_relpath}`)}
                    alt={slide.label}
                    className="h-20 w-full object-cover"
                  />
                </button>
              ))}
            </div>
          </div>
        </section>

        <aside
          className={`fixed bottom-0 right-0 top-16 z-40 overflow-hidden border-l border-slate-200 bg-white/96 shadow-[-20px_0_48px_-38px_rgba(15,23,42,0.32)] backdrop-blur-xl transition-transform duration-300 ease-out lg:translate-x-0 ${
            isSidebarOpen ? "translate-x-0" : "translate-x-full"
          }`}
          style={{ width: sidebarWidth }}
        >
          <div className="h-full space-y-5 overflow-y-auto p-6">
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-3">
                <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-muted">{t("review.workspace")}</p>
              </div>
              <h1 className="font-headline text-2xl font-extrabold tracking-tight text-slate-900">
                {currentSlide?.label || t("review.titleFallback")}
              </h1>
              <p className="text-sm leading-7 text-muted">
                {t("review.slideProgress", {
                  current: selectedSlideNumber,
                  total: slides.length || 1,
                })}
              </p>
            </div>

            <div className="space-y-3">
              <button
                onClick={() => {
                  setSelectedIds([]);
                  setIsInsertMode((current) => !current);
                }}
                className={`w-full rounded-full px-5 py-2.5 text-sm font-semibold transition ${
                  isInsertMode
                    ? "bg-primary text-white"
                    : "border border-slate-200 bg-white text-slate-800 hover:bg-slate-50"
                }`}
              >
                {isInsertMode ? t("review.mode.select") : t("review.mode.newBox")}
              </button>
              {isInsertMode ? (
                <div className="space-y-3">
                  <div className="text-sm leading-6 text-muted">{t("review.help.insert")}</div>
                  <div className="text-xs leading-5 text-muted">{t("review.help.shortcuts")}</div>
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="text-sm leading-6 text-muted">{t("review.help.select")}</div>
                  <div className="text-xs leading-5 text-muted">{t("review.help.shortcuts")}</div>
                </div>
              )}
            </div>

            {isInsertMode || selectedBox ? (
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-700">{t("review.boxType.title")}</p>
                  <span className="text-xs text-muted">
                    {isInsertMode ? t("review.boxType.new") : t("review.boxType.selected")}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setActiveCategory("text");
                      if (!isInsertMode && selectedBox) {
                        updateSelectedBox({ category: "text" });
                      }
                    }}
                    className={`rounded-xl border px-3 py-2 text-sm font-semibold transition ${categoryButtonClass(
                      isInsertMode ? activeCategory === "text" : selectedBox?.category === "text",
                    )}`}
                  >
                    {t("boxType.text")}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setActiveCategory("figure");
                      if (!isInsertMode && selectedBox) {
                        updateSelectedBox({ category: "figure" });
                      }
                    }}
                    className={`rounded-xl border px-3 py-2 text-sm font-semibold transition ${categoryButtonClass(
                      isInsertMode ? activeCategory === "figure" : selectedBox?.category === "figure",
                    )}`}
                  >
                    {t("boxType.image")}
                  </button>
                </div>
              </div>
            ) : null}

            <div className="space-y-3">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-700">{selectionSummary}</p>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={handleBuildDeck}
                  disabled={busyAction !== null}
                  className="w-full rounded-full bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white transition disabled:opacity-50"
                >
                  {busyAction === "build" ? t("review.building") : t("review.build")}
                </button>
              </div>
            </div>

            {selectedIds.length > 1 ? (
              <div className="text-sm leading-6 text-muted">
                {t("review.selection.multipleNotice")}
              </div>
            ) : selectedIds.length === 0 ? (
              <div className="text-sm leading-7 text-muted">
                {t("review.emptySelectionHelp")}
              </div>
            ) : null}

            {message ? <div className="text-sm font-medium text-emerald-700">{message}</div> : null}
            {error ? <div className="text-sm font-medium text-rose-700">{error}</div> : null}
          </div>
        </aside>
      </section>
    </Shell>
  );
}
