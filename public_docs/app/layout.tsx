import "./global.css";
import { DocsLayout } from "fumadocs-ui/layouts/docs";
import { RootProvider } from "fumadocs-ui/provider";
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import type { ReactNode } from "react";
import { source } from "@/lib/source";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
	title: {
		template: "%s | Reflexio Docs",
		default: "Reflexio Docs",
	},
	description:
		"Official documentation for Reflexio - A powerful framework for building AI agents with memory and user profiling capabilities",
	icons: "/docs/assets/reflexio_fav.svg",
};

export default function Layout({ children }: { children: ReactNode }) {
	return (
		<html lang="en" suppressHydrationWarning>
			<body className={inter.className} suppressHydrationWarning>
				<RootProvider search={{ options: { api: "/docs/api/search" } }}>
					<DocsLayout
						tree={source.pageTree}
						nav={{
							title: "Reflexio Docs",
						}}
					>
						{children}
					</DocsLayout>
				</RootProvider>
			</body>
		</html>
	);
}
