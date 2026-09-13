import type { Metadata, Viewport } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Trợ lý Sức khỏe Vinmec | ReAct Agent + MCP',
  description:
    'Trợ lý AI đặt lịch khám tại Vinmec — tra cứu bác sĩ, ghi nhớ tiền sử và gợi ý bác sĩ phù hợp nhất.',
  icons: { icon: '/icon.svg' },
}

export const viewport: Viewport = { colorScheme: 'light' }

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    // suppressHydrationWarning: một số extension trình duyệt (trình quản lý mật khẩu,
    // phần mềm diệt virus…) chèn thuộc tính như `bis_skin_checked` vào DOM trước khi
    // React kịp hydrate, gây cảnh báo lệch HTML không liên quan tới mã nguồn.
    <html lang="vi" suppressHydrationWarning>
      <body className="antialiased" suppressHydrationWarning>
        {children}
      </body>
    </html>
  )
}
