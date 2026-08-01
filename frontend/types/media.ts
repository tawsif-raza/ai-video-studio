/** Mirrors shared_core/contracts/asset_manifest.py's ScannedMediaFile /
 * ImportedMediaManifest - the exact shape GET /projects/{id}/media returns. */
export interface ScannedMediaFile {
  filename: string;
  path: string;
  size_bytes: number;
  sha256: string;
}

export interface ImportedMediaManifest {
  images: ScannedMediaFile[];
  videos: ScannedMediaFile[];
  audio: ScannedMediaFile[];
}

/** Mirrors web_api/models.py's MediaUploadResponse. */
export interface MediaUploadResponse {
  filename: string;
  path: string;
  size_bytes: number;
}

/** Mirrors web_api/models.py's MediaCategory - the filesystem-side names
 * ("video" singular), not ImportedMediaManifest's field names ("videos"
 * plural) - see that model's docstring for why the two differ. */
export type MediaCategory = "images" | "video" | "audio";

/** Mirrors web_api/models.py's MediaDeleteItem/BulkMediaDeleteRequest. */
export interface MediaDeleteItem {
  category: MediaCategory;
  filename: string;
}

/** Mirrors web_api/models.py's MediaDeleteResult. */
export interface MediaDeleteResult {
  category: MediaCategory;
  filename: string;
  success: boolean;
  error?: string | null;
}

/** Mirrors web_api/models.py's BulkMediaDeleteResponse. */
export interface BulkMediaDeleteResponse {
  results: MediaDeleteResult[];
}

/** Maps ImportedMediaManifest's field name to the MediaCategory (and real
 * media/ subdirectory name) it corresponds to - manifest.videos holds
 * MediaCategory "video", not "videos". */
export const MEDIA_MANIFEST_FIELD_TO_CATEGORY: Record<"images" | "videos" | "audio", MediaCategory> = {
  images: "images",
  videos: "video",
  audio: "audio",
};
