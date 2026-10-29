/** Ngôn ngữ lồng tiếng / phụ đề đầu ra — khớp backend core/langs.py. */
export const LANGS: { code: string; name: string }[] = [
  { code: "vi", name: "Tiếng Việt" }, { code: "en", name: "Tiếng Anh" }, { code: "zh", name: "Tiếng Trung" },
  { code: "ja", name: "Tiếng Nhật" }, { code: "ko", name: "Tiếng Hàn" }, { code: "id", name: "Tiếng Indonesia" },
  { code: "th", name: "Tiếng Thái" }, { code: "es", name: "Tiếng Tây Ban Nha" }, { code: "pt", name: "Tiếng Bồ Đào Nha" },
  { code: "fr", name: "Tiếng Pháp" }, { code: "de", name: "Tiếng Đức" }, { code: "it", name: "Tiếng Ý" },
  { code: "ru", name: "Tiếng Nga" }, { code: "ar", name: "Tiếng Ả Rập" }, { code: "tr", name: "Tiếng Thổ Nhĩ Kỳ" },
  { code: "ms", name: "Tiếng Mã Lai" }, { code: "fil", name: "Tiếng Philippines" },
]
export const langName = (code?: string) => LANGS.find((l) => l.code === (code || "vi"))?.name ?? code ?? "Tiếng Việt"

/** Giọng đọc được ngôn ngữ này: đúng ngôn ngữ, hoặc giọng CapCut đa ngôn ngữ (chỉ khi không phải tiếng Việt). */
export const voiceFits = (v: { lang?: string }, lang = "vi") => (v.lang || "vi") === lang || (lang !== "vi" && v.lang === "multi")

/** Câu mẫu để tạo thử giọng theo ngôn ngữ. */
export const DEMO_TEXT: Record<string, string> = {
  vi: "Xin chào các bạn, hôm nay chúng ta sẽ cùng xem một bộ phim cực kỳ hấp dẫn.",
  en: "Hello everyone, today we are watching an amazing movie together.",
  zh: "大家好，今天我们一起来看一部非常精彩的电影。",
  ja: "皆さん、こんにちは。今日は一緒にとても面白い映画を見ましょう。",
  ko: "안녕하세요 여러분, 오늘은 함께 정말 재미있는 영화를 보겠습니다.",
  id: "Halo semuanya, hari ini kita akan menonton film yang sangat seru.",
  th: "สวัสดีทุกคน วันนี้เราจะมาดูหนังที่สนุกมากด้วยกัน",
  es: "Hola a todos, hoy vamos a ver juntos una película increíble.",
  pt: "Olá a todos, hoje vamos assistir juntos a um filme incrível.",
  fr: "Bonjour à tous, aujourd'hui nous regardons ensemble un film incroyable.",
  de: "Hallo zusammen, heute schauen wir gemeinsam einen großartigen Film.",
  it: "Ciao a tutti, oggi guardiamo insieme un film incredibile.",
  ru: "Всем привет, сегодня мы вместе посмотрим потрясающий фильм.",
  ar: "مرحبا بالجميع، اليوم سنشاهد معا فيلما رائعا.",
  tr: "Herkese merhaba, bugün birlikte harika bir film izleyeceğiz.",
  ms: "Hai semua, hari ini kita akan menonton filem yang sangat menarik.",
  fil: "Kumusta kayong lahat, manonood tayo ngayon ng isang napakagandang pelikula.",
}

/** Ký tự / giây khi đọc (đo tiếng Việt ~17; ngôn ngữ khác quy đổi theo backend core/langs.py). */
const CPS: Record<string, number> = { vi: 17, zh: 5.1, ja: 8.5, ko: 7.9, th: 13.6, de: 15.9, ru: 15.9, tr: 15.9, ar: 14.7 }
export const dubCps = (lang?: string) => CPS[lang || "vi"] ?? 17
