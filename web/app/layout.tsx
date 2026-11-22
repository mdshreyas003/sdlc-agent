import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Suspense } from "react";
import Shell from "@/components/Shell";
import { AuthProvider } from "@/lib/auth";
import { DataProvider } from "@/lib/data";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Engineering Memory",
  description: "Evidence-grounded answers to “why is this code the way it is?”",
  alternates: { canonical: "/" },
  openGraph: {
    title: "Engineering Memory",
    description: "Evidence-grounded answers to “why is this code the way it is?”",
    type: "website",
  },
};

// Set the theme before first paint (stored choice, else system) to avoid a flash.
const themeInit = `try{var t=localStorage.getItem("wb-theme")||(matchMedia("(prefers-color-scheme: light)").matches?"light":"dark");document.documentElement.dataset.theme=t;var d=document.documentElement,a=localStorage.getItem("wb-accent"),c=localStorage.getItem("wb-contrast"),f=localStorage.getItem("wb-font");if(a&&a!=="blue")d.dataset.accent=a;if(c==="high")d.dataset.contrast="high";if(f==="system")d.dataset.font="system"}catch(e){document.documentElement.dataset.theme="dark"}`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable}`} data-theme="dark" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: themeInit }} /></head>
      {/* The shell reads the URL (usePathname) and live data on the client, so it streams in behind this boundary. */}
      <body><Suspense fallback={null}><AuthProvider><DataProvider><Shell>{children}</Shell></DataProvider></AuthProvider></Suspense></body>
    </html>
  );
}
