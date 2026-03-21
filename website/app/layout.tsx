import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { LayoutContent } from "@/components/layout-content";
import { AuthProvider } from "@/lib/auth-context";

const geistSans = Geist({
	variable: "--font-geist-sans",
	subsets: ["latin"],
});

const geistMono = Geist_Mono({
	variable: "--font-geist-mono",
	subsets: ["latin"],
});

export const metadata: Metadata = {
	title: "Reflexio - The Learning Layer for AI Agents",
	description:
		"Turn static AI agents into self-improving systems. Reflexio autonomously reflects on interactions, corrects mistakes, and learns new skills from user feedback.",
	icons: {
		icon: { url: "/reflexio_fav.svg", type: "image/svg+xml" },
		shortcut: { url: "/reflexio_fav.svg", type: "image/svg+xml" },
		apple: "/reflexio_fav.svg",
	},
};

export default function RootLayout({
	children,
}: Readonly<{
	children: React.ReactNode;
}>) {
	return (
		<html lang="en" suppressHydrationWarning>
			<body
				className={`${geistSans.variable} ${geistMono.variable} antialiased`}
				suppressHydrationWarning
			>
				<AuthProvider>
					<LayoutContent>{children}</LayoutContent>
				</AuthProvider>
			</body>
		</html>
	);
}
