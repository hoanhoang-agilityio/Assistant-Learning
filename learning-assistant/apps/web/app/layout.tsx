import "@copilotkit/react-core/v2/styles.css";
import "@/app/globals.css";

import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import {
  DARK_SCHEME_QUERY,
  DARK_THEME_CLASS,
  SETTINGS_STORAGE_KEY,
} from "@/constants/settings";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Learning Assistant",
  description:
    "Research a topic, turn it into learning material, take a quiz and get personalised feedback.",
};

/**
 * Applies the saved theme before first paint, so a dark-mode user never sees
 * a light flash. Reads the settings store's persisted JSON directly; no saved
 * theme, or `system`, follows the device.
 */
const THEME_SCRIPT = `(function(){try{var s=JSON.parse(localStorage.getItem(${JSON.stringify(
  SETTINGS_STORAGE_KEY,
)})||"{}");var t=s&&s.state&&s.state.settings&&s.state.settings.theme;if(t==="dark"||(t!=="light"&&matchMedia(${JSON.stringify(
  DARK_SCHEME_QUERY,
)}).matches)){document.documentElement.classList.add(${JSON.stringify(
  DARK_THEME_CLASS,
)})}}catch(e){}})()`;

const RootLayout = ({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) => {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className={`${geistSans.variable} ${geistMono.variable}`}>
        {children}
      </body>
    </html>
  );
};

export default RootLayout;
