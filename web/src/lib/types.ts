export type JobMode = "auto" | "review";

export type JobStatus =
  | "uploaded"
  | "prepared"
  | "processing"
  | "awaiting_review"
  | "rebuilding_slide"
  | "building_deck"
  | "completed"
  | "failed";

export type EditorCategory = "text" | "figure";

export interface JobOutputMap {
  deck_pptx: string | null;
}

export interface SlideSize {
  width_px: number;
  height_px: number;
}

export interface SlideRecord {
  slide_number: number;
  label: string;
  source_type: string;
  source_name: string;
  page_number: number | null;
  image_relpath: string;
  slide_size: SlideSize;
  status: string;
  artifacts: Record<string, string> | null;
}

export interface JobRecord {
  job_id: string;
  mode: JobMode;
  status: JobStatus;
  created_at: string;
  updated_at: string;
  error: string | null;
  uploads: Array<{
    upload_id: string;
    original_name: string;
    stored_relpath: string;
    content_type: string;
    kind: string;
  }>;
  slides: SlideRecord[];
  outputs: JobOutputMap;
}

export interface EditorBox {
  box_id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  category: EditorCategory;
  source: string;
  source_box_id: string | null;
}

export interface EditorState {
  job_id: string;
  slide_number: number;
  slide_size: SlideSize;
  image_url: string;
  boxes: EditorBox[];
  ocr_edits_json: string;
}

export interface ChangedItem {
  label: string;
  path: string;
}
