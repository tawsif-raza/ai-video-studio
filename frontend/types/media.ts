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
