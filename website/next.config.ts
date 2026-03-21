import type { NextConfig } from "next";

const nextConfig: NextConfig = {
	async rewrites() {
		// Use environment variable or default to localhost:8081 for local development
		const apiUrl = process.env.API_BACKEND_URL || "http://localhost:8081";
		const docsPort = process.env.DOCS_PORT || "8082";
		const rewrites = [
			{
				source: "/api/:path*",
				destination: `${apiUrl}/api/:path*`,
			},
			{
				source: "/token",
				destination: `${apiUrl}/token`,
			},
		];
		// In local dev, proxy /docs to the docs Next.js app.
		// In production, ALB routes /docs/* to port 8082 before reaching this app.
		if (process.env.NODE_ENV === "development") {
			rewrites.push(
				{
					source: "/docs",
					destination: `http://localhost:${docsPort}/docs`,
				},
				{
					source: "/docs/:path*",
					destination: `http://localhost:${docsPort}/docs/:path*`,
				},
			);
		}
		return rewrites;
	},
};

export default nextConfig;
