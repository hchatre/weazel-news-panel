import "./globals.css";
import type { Metadata } from "next";
import { I18nProvider } from "@/lib/i18n";
import { AuthProvider } from "@/lib/auth";

export const metadata: Metadata = { title: "Weazel Newsroom", description: "Newsroom operations and editorial intelligence" };

// Sets the theme class before paint so there is no light/dark flash.
const themeScript = `try{var t=localStorage.getItem('wz_theme');if(t==='light'){document.documentElement.classList.remove('dark')}else{document.documentElement.classList.add('dark')}}catch(e){document.documentElement.classList.add('dark')}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: themeScript }} /></head>
      <body><I18nProvider><AuthProvider>{children}</AuthProvider></I18nProvider></body>
    </html>
  );
}
