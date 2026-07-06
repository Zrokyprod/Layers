const DEFAULT_ZROKY_API_BASE_URL = "https://api.zroky.com";
const ACTION_RECEIPT_PUBLIC_KEY_PATH = "/.well-known/zroky/action-receipt-signing-key";

export function zrokyPublicApiBaseUrl(): string {
  return (process.env.NEXT_PUBLIC_ZROKY_API_BASE_URL ?? DEFAULT_ZROKY_API_BASE_URL).replace(/\/+$/, "");
}

export function actionReceiptPublicKeyUrl(): string {
  return `${zrokyPublicApiBaseUrl()}${ACTION_RECEIPT_PUBLIC_KEY_PATH}`;
}
