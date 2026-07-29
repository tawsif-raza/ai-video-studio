import { apiGet } from "@/api/client";
import type { ProducerPackage, ProductionPackage } from "@/types/package";

/** GET /projects/{id}/production-package (W7.5) */
export const getProductionPackage = (projectId: string): Promise<ProductionPackage> =>
  apiGet<ProductionPackage>(`/projects/${projectId}/production-package`);

/** GET /projects/{id}/producer-package (W7.5) */
export const getProducerPackage = (projectId: string): Promise<ProducerPackage> =>
  apiGet<ProducerPackage>(`/projects/${projectId}/producer-package`);
