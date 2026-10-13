import { Moon, Sun } from "lucide-react"
import { ThemeProvider as NextThemes, useTheme } from "next-themes"
import { useEffect, type ReactNode } from "react"
import { Button } from "@/components/ui/button"

/** Đồng bộ màu thanh tiêu đề Windows (nút thu nhỏ/đóng) theo theme. */
function TitleBarSync() {
  const { resolvedTheme } = useTheme()
  useEffect(() => {
    if (resolvedTheme === "dark" || resolvedTheme === "light") window.rf?.setTheme(resolvedTheme)
  }, [resolvedTheme])
  return null
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  return (
    <NextThemes attribute="class" defaultTheme="dark" enableSystem disableTransitionOnChange storageKey="rf-theme">
      <TitleBarSync />
      {children}
    </NextThemes>
  )
}

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme()
  const dark = resolvedTheme === "dark"
  return (
    <Button variant="ghost" size="icon-sm" className="no-drag" title={dark ? "Chuyển sang giao diện sáng" : "Chuyển sang giao diện tối"}
      onClick={() => setTheme(dark ? "light" : "dark")}>
      {dark ? <Sun /> : <Moon />}
    </Button>
  )
}
