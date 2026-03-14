import type { Source } from "fumadocs-core/source";
import { loader } from "fumadocs-core/source";
import { createMDXSource } from "fumadocs-mdx";
import { docs } from "@/.source";

const mdxSource = createMDXSource(docs.docs, docs.meta);

// Resolve lazy files getter to an array for compatibility
const resolvedSource: Source<typeof mdxSource extends Source<infer C> ? C : never> = {
	files:
		typeof mdxSource.files === "function" ? (mdxSource.files as () => any[])() : mdxSource.files,
};

export const source = loader({
	baseUrl: "/",
	source: resolvedSource,
});
