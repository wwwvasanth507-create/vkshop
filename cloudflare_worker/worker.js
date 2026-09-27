/**
 * VKShop Permanent Public Gateway Cloudflare Worker
 * Permanent Gateway URL: https://home.vkshop.workers.dev
 *
 * Description:
 * Proxies incoming HTTP/HTTPS traffic from home.vkshop.workers.dev to the
 * active VPS/backend origin server configured via the ORIGIN_URL environment variable.
 * Includes native edge SEO support (Google Verification, robots.txt, sitemap.xml).
 */

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // 1. Google Site Verification File Handler (Strict Exact Match)
    if (url.pathname === "/google7eb473ec0eff88a6.html") {
      return new Response("google-site-verification: google7eb473ec0eff88a6.html", {
        status: 200,
        headers: {
          "Content-Type": "text/html; charset=utf-8",
          "Cache-Control": "public, max-age=86400",
        },
      });
    }

    // 2. SEO robots.txt Handler
    if (url.pathname === "/robots.txt") {
      const robotsTxt = `User-agent: *
Allow: /

Sitemap: ${url.origin}/sitemap.xml
`;
      return new Response(robotsTxt, {
        status: 200,
        headers: {
          "Content-Type": "text/plain; charset=utf-8",
          "Cache-Control": "public, max-age=86400",
        },
      });
    }

    // 3. SEO sitemap.xml Handler
    if (url.pathname === "/sitemap.xml") {
      const defaultSitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>${url.origin}/</loc>
  </url>
</urlset>`;
      return new Response(defaultSitemap, {
        status: 200,
        headers: {
          "Content-Type": "application/xml; charset=utf-8",
          "Cache-Control": "public, max-age=86400",
        },
      });
    }

    // 4. Configurable Origin Server
    const originBase = (env.ORIGIN_URL || "https://vkshop.dpdns.org").replace(/\/+$/, "");
    const targetUrl = new URL(`${originBase}${url.pathname}${url.search}`);

    // 5. Handle CORS preflight OPTIONS requests for mobile and web clients
    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, PATCH, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With, X-CSRF-Token",
          "Access-Control-Max-Age": "86400",
        },
      });
    }

    // 6. Construct proxy request headers
    const proxyHeaders = new Headers(request.headers);
    proxyHeaders.set("X-Forwarded-Host", url.host);
    proxyHeaders.set("X-Forwarded-Proto", url.protocol.replace(":", ""));
    proxyHeaders.set("X-Via-Gateway", "VKShop-Cloudflare-Worker-Gateway");

    // Pass client IP address to backend
    const clientIp = request.headers.get("cf-connecting-ip") || request.headers.get("x-real-ip");
    if (clientIp) {
      proxyHeaders.set("X-Forwarded-For", clientIp);
    }

    // 7. Execute fetch proxy call to current VPS origin
    const init = {
      method: request.method,
      headers: proxyHeaders,
      body: ["GET", "HEAD"].includes(request.method) ? null : request.body,
      redirect: "manual",
    };

    try {
      const response = await fetch(targetUrl.toString(), init);

      // Clone response headers & set gateway metadata
      const responseHeaders = new Headers(response.headers);
      responseHeaders.set("X-Gateway-Domain", "home.vkshop.workers.dev");

      // Add SEO Headers for indexing public pages
      if (!url.pathname.startsWith("/admin") && !url.pathname.startsWith("/checkout")) {
        responseHeaders.set("X-Robots-Tag", "index, follow");
      }

      // Set CORS headers on API requests
      if (url.pathname.startsWith("/api/")) {
        responseHeaders.set("Access-Control-Allow-Origin", "*");
        responseHeaders.set("Access-Control-Allow-Credentials", "true");
      }

      // Set CORS & Edge Caching for static assets (/static/*, CSS, JS, fonts, images)
      if (
        url.pathname.startsWith("/static/") ||
        url.pathname.match(/\.(css|js|jpeg|jpg|png|webp|ttf|woff|woff2|svg|ico)$/i)
      ) {
        responseHeaders.set("Access-Control-Allow-Origin", "*");
        responseHeaders.set("Cache-Control", "public, max-age=31536000, immutable");
      }

      // Inject Google Verification & Core SEO Meta Tags into HTML pages at Edge
      const contentType = responseHeaders.get("content-type") || "";
      if (contentType.includes("text/html") && url.pathname === "/") {
        let html = await response.text();
        const seoTags = `
    <title>VKShop - Online Shopping</title>
    <meta name="description" content="VKShop - Shop electronics, fashion, groceries and more online.">
    <meta name="keywords" content="VKShop, VK Shop, online shopping, ecommerce, shopping">
    <meta name="robots" content="index, follow">
    <link rel="canonical" href="https://home.vkshop.workers.dev/">
    <meta name="google-site-verification" content="g17FdWOZ4SxlTr1CEwiQ6jAR876aPZnrYqgf4-CjfKk" />`;
        
        if (html.includes("<title>")) {
          html = html.replace(/<title>.*?<\/title>/i, `<title>VKShop - Online Shopping</title>`);
        }
        if (!html.includes('name="description"')) {
          html = html.replace("<head>", `<head>${seoTags}`);
        }
        return new Response(html, {
          status: response.status,
          statusText: response.statusText,
          headers: responseHeaders,
        });
      }

      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: responseHeaders,
      });
    } catch (err) {
      return new Response(
        JSON.stringify({
          success: false,
          error: "Gateway Bad Gateway (502)",
          message: "Unable to reach active VKShop origin server.",
          gateway: "https://home.vkshop.workers.dev",
          details: err.message,
        }),
        {
          status: 502,
          headers: {
            "Content-Type": "application/json",
            "X-Gateway-Domain": "home.vkshop.workers.dev",
          },
        }
      );
    }
  },
};

