import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
export type Json =
  | null
  | boolean
  | number
  | string
  | Json[]
  | { [key: string]: Json };
export type RecordData = Record<string, any>;
export interface Client {
  request(operation: string, payload?: RecordData): Promise<RecordData>;
  selectPath(kind: string): Promise<string | null>;
  onClose(handler: () => void): Promise<() => void>;
  onHandoff(handler: (request: RecordData) => void): Promise<() => void>;
  onProgress(handler: (progress: RecordData) => void): Promise<() => void>;
  close(): Promise<void>;
}
export const nativeClient: Client = {
  request: (operation, payload = {}) =>
    invoke("launcher_request", { operation, payload }),
  selectPath: (kind) => invoke("select_path", { kind }),
  onClose: async (handler) => {
    const stop = await listen("launcher-close-requested", handler);
    try {
      await invoke("frontend_ready");
    } catch (error) {
      stop();
      throw error;
    }
    return stop;
  },
  onHandoff: async (handler) => {
    const stop = await listen<RecordData>("launcher-handoff", (event) =>
      handler(event.payload),
    );
    try {
      const pending = await invoke<RecordData | null>("initial_handoff");
      if (pending) handler(pending);
    } catch (error) {
      stop();
      throw error;
    }
    return stop;
  },
  onProgress: (handler) =>
    listen<RecordData>("launcher-progress", (event) => handler(event.payload)),
  close: () => invoke("close_launcher"),
};
