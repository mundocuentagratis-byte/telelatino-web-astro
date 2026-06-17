import rss from "@astrojs/rss";
import { getCollection } from "astro:content";

export async function GET(context) {
  const blogPosts = await getCollection("blog", ({ data }) => !data.draft);
  const newsPosts = await getCollection("noticias", ({ data }) => !data.draft);

  const items = [
    ...blogPosts.map((post) => ({
      title: post.data.title,
      description: post.data.description,
      pubDate: post.data.pubDate,
      link: `/blog/${post.id}/`,
    })),

    ...newsPosts.map((post) => ({
      title: post.data.title,
      description: post.data.description,
      pubDate: post.data.pubDate,
      link: `/noticias/${post.id}/`,
    })),
  ].sort((a, b) => b.pubDate.valueOf() - a.pubDate.valueOf());

  return rss({
    title: "TeleLatino Oficial",
    description:
      "Noticias, guías y novedades sobre entretenimiento digital, televisión online y deportes.",
    site: context.site,
    items,
  });
}