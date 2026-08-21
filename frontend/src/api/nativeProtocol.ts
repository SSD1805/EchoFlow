export type NativeProtocolCommand =
  | "desktop_request"
  | "transcript_tools_request"
  | "lifecycle_request";

interface NativeProtocolError {
  code: string;
  message: string;
}

export interface NativeProtocolResponse<T> {
  protocol_version: 1;
  request_id: string;
  ok: boolean;
  result: T | null;
  error: NativeProtocolError | null;
}

export interface NativeProtocolMessages {
  invalid: string;
  incompatible: string;
  failure: string;
}

export function parseNativeProtocolResponse<T>(
  value: unknown,
  messages: NativeProtocolMessages,
): NativeProtocolResponse<T> {
  if (!value || typeof value !== "object") {
    throw new Error(messages.invalid);
  }
  const candidate = value as Partial<NativeProtocolResponse<T>>;
  if (
    candidate.protocol_version !== 1 ||
    typeof candidate.request_id !== "string" ||
    typeof candidate.ok !== "boolean"
  ) {
    throw new Error(messages.incompatible);
  }
  return candidate as NativeProtocolResponse<T>;
}

export async function invokeNativeProtocol<T>(
  command: NativeProtocolCommand,
  method: string,
  params: Record<string, unknown>,
  messages: NativeProtocolMessages,
): Promise<T> {
  const { invoke } = await import("@tauri-apps/api/core");
  const response = parseNativeProtocolResponse<T>(
    await invoke<unknown>(command, {
      request: {
        protocol_version: 1,
        request_id: crypto.randomUUID(),
        method,
        params,
      },
    }),
    messages,
  );
  if (!response.ok || response.result === null) {
    throw new Error(response.error?.message ?? messages.failure);
  }
  return response.result;
}
