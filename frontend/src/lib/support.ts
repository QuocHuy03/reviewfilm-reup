/** Trang hỗ trợ / liên hệ — mở bằng trình duyệt mặc định (Electron chuyển link cửa sổ mới ra ngoài). */
export const SUPPORT_URL = "https://taothaoai.com"

export function openSupport() {
  window.open(SUPPORT_URL, "_blank", "noopener")
}
