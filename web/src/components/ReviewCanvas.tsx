import { useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";

import { useI18n } from "../i18n";
import type { EditorBox, EditorCategory, SlideSize } from "../lib/types";

type ResizeHandle = "top-left" | "top-right" | "bottom-left" | "bottom-right";

type PointerAction =
  | {
      type: "move";
      boxIds: string[];
      startPointerX: number;
      startPointerY: number;
      startBoxes: Array<{ boxId: string; startBox: EditorBox }>;
    }
  | {
      type: "resize";
      handle: ResizeHandle;
      boxId: string;
      startPointerX: number;
      startPointerY: number;
      startBox: EditorBox;
    }
  | null;

type DraftBox = {
  startX: number;
  startY: number;
  startClientX: number;
  startClientY: number;
  x: number;
  y: number;
  width: number;
  height: number;
} | null;

type SelectionMarquee = {
  startX: number;
  startY: number;
  startClientX: number;
  startClientY: number;
  x: number;
  y: number;
  width: number;
  height: number;
} | null;

const BOX_CREATE_DRAG_THRESHOLD_PX = 6;
const BOX_HIT_PADDING_PX = 8;

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function sanitizeBox(box: EditorBox, slideSize: SlideSize): EditorBox {
  const width = clamp(Number(box.width) || 1, 1, slideSize.width_px);
  const height = clamp(Number(box.height) || 1, 1, slideSize.height_px);
  const x = clamp(Number(box.x) || 0, 0, slideSize.width_px - width);
  const y = clamp(Number(box.y) || 0, 0, slideSize.height_px - height);
  return { ...box, x, y, width, height };
}

function intersectsSelection(box: EditorBox, marquee: NonNullable<SelectionMarquee>) {
  return (
    box.x < marquee.x + marquee.width &&
    box.x + box.width > marquee.x &&
    box.y < marquee.y + marquee.height &&
    box.y + box.height > marquee.y
  );
}

export function ReviewCanvas({
  slideSize,
  imageUrl,
  boxes,
  selectedIds,
  setSelectedIds,
  setBoxes,
  activeCategory,
  isInsertMode,
  setInsertMode,
}: {
  slideSize: SlideSize;
  imageUrl: string;
  boxes: EditorBox[];
  selectedIds: string[];
  setSelectedIds: Dispatch<SetStateAction<string[]>>;
  setBoxes: Dispatch<SetStateAction<EditorBox[]>>;
  activeCategory: EditorCategory;
  isInsertMode: boolean;
  setInsertMode: Dispatch<SetStateAction<boolean>>;
}) {
  const { t } = useI18n();
  const imageRef = useRef<HTMLImageElement | null>(null);
  const overlayRef = useRef<HTMLDivElement | null>(null);
  const [draftBox, setDraftBox] = useState<DraftBox>(null);
  const [selectionMarquee, setSelectionMarquee] = useState<SelectionMarquee>(null);
  const [pointerAction, setPointerAction] = useState<PointerAction>(null);
  const [viewportVersion, setViewportVersion] = useState(0);

  const scale = useMemo(() => {
    const width = imageRef.current?.clientWidth || slideSize.width_px;
    const height = imageRef.current?.clientHeight || slideSize.height_px;
    return {
      x: width / slideSize.width_px,
      y: height / slideSize.height_px,
    };
  }, [slideSize, viewportVersion]);

  useEffect(() => {
    const observer = new ResizeObserver(() => setViewportVersion((value) => value + 1));
    if (imageRef.current) {
      observer.observe(imageRef.current);
    }
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (isInsertMode) {
      setPointerAction(null);
      setSelectionMarquee(null);
      return;
    }
    setDraftBox(null);
  }, [isInsertMode]);

  useEffect(() => {
    function overlayPoint(clientX: number, clientY: number) {
      const rect = overlayRef.current?.getBoundingClientRect();
      if (!rect) {
        return { x: 0, y: 0 };
      }
      return {
        x: clamp((clientX - rect.left) / scale.x, 0, slideSize.width_px),
        y: clamp((clientY - rect.top) / scale.y, 0, slideSize.height_px),
      };
    }

    function onPointerMove(event: PointerEvent) {
      if (pointerAction) {
        const point = overlayPoint(event.clientX, event.clientY);
        setBoxes((current) =>
          current.map((box) => {
            const startEntry = pointerAction.type === "move"
              ? pointerAction.startBoxes.find((entry) => entry.boxId === box.box_id)
              : null;

            if (pointerAction.type === "move") {
              if (!startEntry) {
                return box;
              }
              return sanitizeBox(
                {
                  ...box,
                  x: startEntry.startBox.x + (point.x - pointerAction.startPointerX),
                  y: startEntry.startBox.y + (point.y - pointerAction.startPointerY),
                },
                slideSize,
              );
            }

            if (box.box_id !== pointerAction.boxId) {
              return box;
            }

            const fixedLeft = pointerAction.startBox.x;
            const fixedTop = pointerAction.startBox.y;
            const fixedRight = pointerAction.startBox.x + pointerAction.startBox.width;
            const fixedBottom = pointerAction.startBox.y + pointerAction.startBox.height;

            if (pointerAction.handle === "bottom-right") {
              return sanitizeBox(
                {
                  ...box,
                  width: point.x - fixedLeft,
                  height: point.y - fixedTop,
                },
                slideSize,
              );
            }

            if (pointerAction.handle === "top-left") {
              const x = clamp(Math.min(point.x, fixedRight - 1), 0, slideSize.width_px - 1);
              const y = clamp(Math.min(point.y, fixedBottom - 1), 0, slideSize.height_px - 1);
              return sanitizeBox(
                {
                  ...box,
                  x,
                  y,
                  width: fixedRight - x,
                  height: fixedBottom - y,
                },
                slideSize,
              );
            }

            if (pointerAction.handle === "top-right") {
              const y = clamp(Math.min(point.y, fixedBottom - 1), 0, slideSize.height_px - 1);
              return sanitizeBox(
                {
                  ...box,
                  y,
                  width: point.x - fixedLeft,
                  height: fixedBottom - y,
                },
                slideSize,
              );
            }

            const x = clamp(Math.min(point.x, fixedRight - 1), 0, slideSize.width_px - 1);
            return sanitizeBox(
              {
                ...box,
                x,
                width: fixedRight - x,
                height: point.y - fixedTop,
              },
              slideSize,
            );
          }),
        );
        return;
      }

      if (draftBox) {
        const point = overlayPoint(event.clientX, event.clientY);
        setDraftBox({
          ...draftBox,
          x: Math.min(draftBox.startX, point.x),
          y: Math.min(draftBox.startY, point.y),
          width: Math.abs(point.x - draftBox.startX),
          height: Math.abs(point.y - draftBox.startY),
        });
        return;
      }

      if (selectionMarquee) {
        const point = overlayPoint(event.clientX, event.clientY);
        setSelectionMarquee({
          ...selectionMarquee,
          x: Math.min(selectionMarquee.startX, point.x),
          y: Math.min(selectionMarquee.startY, point.y),
          width: Math.abs(point.x - selectionMarquee.startX),
          height: Math.abs(point.y - selectionMarquee.startY),
        });
      }
    }

    function onPointerUp(event: PointerEvent) {
      if (pointerAction) {
        setPointerAction(null);
        return;
      }
      if (draftBox) {
        const draggedDistance = Math.hypot(
          event.clientX - draftBox.startClientX,
          event.clientY - draftBox.startClientY,
        );
        if (draggedDistance < BOX_CREATE_DRAG_THRESHOLD_PX) {
          setDraftBox(null);
          setSelectedIds([]);
          return;
        }
        const newBox = sanitizeBox(
          {
            box_id: `box-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
            x: draftBox.x,
            y: draftBox.y,
            width: draftBox.width,
            height: draftBox.height,
            category: activeCategory,
            source: "manual",
            source_box_id: null,
          },
          slideSize,
        );
        setBoxes((current) => [...current, newBox]);
        setSelectedIds([newBox.box_id]);
        setDraftBox(null);
        return;
      }

      if (selectionMarquee) {
        const draggedDistance = Math.hypot(
          event.clientX - selectionMarquee.startClientX,
          event.clientY - selectionMarquee.startClientY,
        );
        if (draggedDistance < BOX_CREATE_DRAG_THRESHOLD_PX) {
          setSelectionMarquee(null);
          setSelectedIds([]);
          return;
        }
        setSelectedIds(boxes.filter((box) => intersectsSelection(box, selectionMarquee)).map((box) => box.box_id));
        setSelectionMarquee(null);
      }
    }

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
    };
  }, [activeCategory, boxes, draftBox, pointerAction, scale.x, scale.y, selectionMarquee, setBoxes, setSelectedIds, slideSize]);

  return (
    <div>
      <div className="overflow-hidden border border-slate-200 bg-[linear-gradient(180deg,#f8fafc_0%,#eef2f7_100%)]">
        <div className="relative mx-auto w-fit">
          <img
            ref={imageRef}
            src={imageUrl}
            alt={t("review.canvasAlt")}
            className="block max-h-[76vh] max-w-full"
            onLoad={() => setViewportVersion((value) => value + 1)}
          />
          <div
            ref={overlayRef}
            className={`absolute inset-0 ${isInsertMode ? "cursor-crosshair" : "cursor-default"}`}
            onPointerDown={(event) => {
              if (event.target !== overlayRef.current) {
                return;
              }
              if (!isInsertMode) {
                const rect = overlayRef.current?.getBoundingClientRect();
                if (!rect) {
                  return;
                }
                const x = clamp((event.clientX - rect.left) / scale.x, 0, slideSize.width_px);
                const y = clamp((event.clientY - rect.top) / scale.y, 0, slideSize.height_px);
                setSelectionMarquee({
                  startX: x,
                  startY: y,
                  startClientX: event.clientX,
                  startClientY: event.clientY,
                  x,
                  y,
                  width: 0,
                  height: 0,
                });
                return;
              }
              const rect = overlayRef.current?.getBoundingClientRect();
              if (!rect) {
                return;
              }
              const x = clamp((event.clientX - rect.left) / scale.x, 0, slideSize.width_px);
              const y = clamp((event.clientY - rect.top) / scale.y, 0, slideSize.height_px);
              setSelectedIds([]);
              setDraftBox({
                startX: x,
                startY: y,
                startClientX: event.clientX,
                startClientY: event.clientY,
                x,
                y,
                width: 0,
                height: 0,
              });
            }}
          >
            {boxes.map((box, index) => {
              const isSelected = selectedIds.includes(box.box_id);
              const colorClass =
                box.category === "figure"
                  ? "border-sky-500 bg-sky-500/10"
                  : box.source === "manual"
                    ? "border-amber-500 bg-amber-500/10"
                    : "border-emerald-500 bg-emerald-500/10";
              const renderedWidth = box.width * scale.x;
              const renderedHeight = box.height * scale.y;

              return (
                <div
                  key={box.box_id}
                  className={`absolute touch-none ${isInsertMode ? "cursor-pointer" : "cursor-move"}`}
                  style={{
                    left: `${box.x * scale.x - BOX_HIT_PADDING_PX}px`,
                    top: `${box.y * scale.y - BOX_HIT_PADDING_PX}px`,
                    width: `${renderedWidth + BOX_HIT_PADDING_PX * 2}px`,
                    height: `${renderedHeight + BOX_HIT_PADDING_PX * 2}px`,
                    zIndex: isSelected ? boxes.length + 1 : index + 1,
                  }}
                  onPointerDown={(event) => {
                    if (isInsertMode) {
                      if (event.target === event.currentTarget) {
                        return;
                      }
                      event.preventDefault();
                      event.stopPropagation();
                      setDraftBox(null);
                      setSelectionMarquee(null);
                      setPointerAction(null);
                      setSelectedIds([box.box_id]);
                      setInsertMode(false);
                      return;
                    }
                    event.preventDefault();
                    event.stopPropagation();
                    const rect = overlayRef.current?.getBoundingClientRect();
                    if (!rect) {
                      return;
                    }
                    const point = {
                      x: clamp((event.clientX - rect.left) / scale.x, 0, slideSize.width_px),
                      y: clamp((event.clientY - rect.top) / scale.y, 0, slideSize.height_px),
                    };
                    const handle = (event.target as HTMLElement).dataset.handle as ResizeHandle | undefined;
                    if (handle) {
                      setSelectedIds([box.box_id]);
                      setPointerAction({
                        type: "resize",
                        handle,
                        boxId: box.box_id,
                        startPointerX: point.x,
                        startPointerY: point.y,
                        startBox: { ...box },
                      });
                      return;
                    }
                    const moveBoxIds = selectedIds.length > 1 && selectedIds.includes(box.box_id) ? selectedIds : [box.box_id];
                    setSelectedIds(moveBoxIds);
                    setPointerAction({
                      type: "move",
                      boxIds: moveBoxIds,
                      startPointerX: point.x,
                      startPointerY: point.y,
                      startBoxes: boxes
                        .filter((candidate) => moveBoxIds.includes(candidate.box_id))
                        .map((candidate) => ({ boxId: candidate.box_id, startBox: { ...candidate } })),
                    });
                  }}
                >
                  <div
                    className={`absolute ${colorClass} ${isSelected ? "border-2 ring-1 ring-primary/40" : "border"}`}
                    style={{
                      left: `${BOX_HIT_PADDING_PX}px`,
                      top: `${BOX_HIT_PADDING_PX}px`,
                      width: `${renderedWidth}px`,
                      height: `${renderedHeight}px`,
                    }}
                  />
                  {isSelected ? (
                    <>
                      <div
                        data-handle="top-left"
                        className="absolute left-2 top-2 flex h-5 w-5 -translate-x-1/2 -translate-y-1/2 cursor-nwse-resize items-center justify-center"
                      >
                        <div className="pointer-events-none h-3 w-3 rounded-full border border-white bg-primary" />
                      </div>
                      <div
                        data-handle="top-right"
                        className="absolute right-2 top-2 flex h-5 w-5 translate-x-1/2 -translate-y-1/2 cursor-nesw-resize items-center justify-center"
                      >
                        <div className="pointer-events-none h-3 w-3 rounded-full border border-white bg-primary" />
                      </div>
                      <div
                        data-handle="bottom-left"
                        className="absolute bottom-2 left-2 flex h-5 w-5 -translate-x-1/2 translate-y-1/2 cursor-nesw-resize items-center justify-center"
                      >
                        <div className="pointer-events-none h-3 w-3 rounded-full border border-white bg-primary" />
                      </div>
                      <div
                        data-handle="bottom-right"
                        className="absolute bottom-2 right-2 flex h-5 w-5 translate-x-1/2 translate-y-1/2 cursor-nwse-resize items-center justify-center"
                      >
                        <div className="pointer-events-none h-3 w-3 rounded-full border border-white bg-primary" />
                      </div>
                    </>
                  ) : null}
                </div>
              );
            })}

            {selectionMarquee ? (
              <div
                className="pointer-events-none absolute border border-dashed border-slate-900/55 bg-slate-900/8"
                style={{
                  left: `${selectionMarquee.x * scale.x}px`,
                  top: `${selectionMarquee.y * scale.y}px`,
                  width: `${selectionMarquee.width * scale.x}px`,
                  height: `${selectionMarquee.height * scale.y}px`,
                }}
              />
            ) : null}

            {draftBox ? (
              <div
                className="absolute border border-primary bg-primary/10"
                style={{
                  left: `${draftBox.x * scale.x}px`,
                  top: `${draftBox.y * scale.y}px`,
                  width: `${draftBox.width * scale.x}px`,
                  height: `${draftBox.height * scale.y}px`,
                }}
              />
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
