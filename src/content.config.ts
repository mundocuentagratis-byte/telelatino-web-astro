import { glob } from "astro/loaders";
import { defineCollection, z } from "astro:content";

const articleSchema = z.object({
  title: z.string(),
  description: z.string(),
  pubDate: z.coerce.date(),
  category: z.string(),
  author: z.string().default("TELELATINO"),
  tags: z.array(z.string()).default([]),
  draft: z.boolean().default(false),

  sourceName: z.string().optional(),
  sourceUrl: z.string().url().optional(),

  image: z.string().optional(),
  imageAlt: z.string().optional(),

  youtubeVideoId: z.string().optional(),
  youtubeVideoTitle: z.string().optional(),
});

const blog = defineCollection({
  loader: glob({
    base: "./src/content/blog",
    pattern: "**/*.{md,mdx}",
  }),
  schema: articleSchema,
});

const noticias = defineCollection({
  loader: glob({
    base: "./src/content/noticias",
    pattern: "**/*.{md,mdx}",
  }),
  schema: articleSchema,
});

export const collections = {
  blog,
  noticias,
};