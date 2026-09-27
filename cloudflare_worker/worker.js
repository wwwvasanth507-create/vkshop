/**
 * VKShop Permanent Public Gateway Cloudflare Worker
 * Permanent Gateway URL: https://home.vkshop.workers.dev
 *
 * Description:
 * Proxies incoming HTTP/HTTPS traffic from home.vkshop.workers.dev to the
 * active VPS/backend origin server configured via the ORIGIN_URL environment variable.
 */

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // 1. Configurable Origin Server (Defaults to local/VPS origin if env var is unset)
    const originBase = (env.ORIGIN_URL || "http://127.0.0.1:5000").replace(/\/+$/, "");
    const targetUrl = new URL(`${originBase}${url.pathname}${url.search}`);

    // 2. Handle CORS preflight OPTIONS requests for mobile and web clients
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

    // 3. Construct proxy request headers
    const proxyHeaders = new Headers(request.headers);
    proxyHeaders.set("X-Forwarded-Host", url.host);
    proxyHeaders.set("X-Forwarded-Proto", url.protocol.replace(":", ""));
    proxyHeaders.set("X-Via-Gateway", "VKShop-Cloudflare-Worker-Gateway");

    // Pass client IP address to backend
    const clientIp = request.headers.get("cf-connecting-ip") || request.headers.get("x-real-ip");
    if (clientIp) {
      proxyHeaders.set("X-Forwarded-For", clientIp);
    }

    // 4. Execute fetch proxy call to current VPS origin
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

      // Set CORS headers on API requests
      if (url.pathname.startsWith("/api/")) {
        responseHeaders.set("Access-Control-Allow-Origin", "*");
        responseHeaders.set("Access-Control-Allow-Credentials", "true");
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
