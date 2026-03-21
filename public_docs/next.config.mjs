import { createMDX } from "fumadocs-mdx/next";

const withMDX = createMDX();

/** @type {import('next').NextConfig} */
const config = {
	basePath: "/docs",
	async redirects() {
		return [
			{
				source: "/",
				destination: "/docs",
				permanent: true,
				basePath: false,
			},
		];
	},
};

export default withMDX(config);
