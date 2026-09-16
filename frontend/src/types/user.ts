export interface User {
  id: number;
  name: string;
  username?: string | null;
  email?: string | null;
  phone?: string | null;
  website?: string | null;
  company_name?: string | null;
}

export interface FailedUserDetail {
  user_id: number;
  status_code?: number | null;
  reason: string;
}

export interface BatchMetadata {
  total: number;
  success_count: number;
  failed_count: number;
  execution_time_ms: number;
}

export interface UserBatchResponse {
  users: User[];
  failed: number[];
  errors: FailedUserDetail[];
  meta: BatchMetadata;
  total_requested?: number;
  total_success?: number;
  total_failed?: number;
  duration_ms?: number | null;
}

export interface UserFetchRequest {
  user_ids: number[];
}

export interface SystemHealth {
  status: string;
  service: string;
  version: string;
  environment: string;
  concurrency_limit: number;
}
