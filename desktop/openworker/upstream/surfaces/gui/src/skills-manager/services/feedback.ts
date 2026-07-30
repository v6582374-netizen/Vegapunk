import { invoke } from "@tauri-apps/api/core";
import { FeedbackRequest } from "@skills-manager/types";

export async function submitFeedback(request: FeedbackRequest): Promise<void> {
  await invoke("submit_feedback", { request });
}
