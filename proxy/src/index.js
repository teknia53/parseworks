const PREFIX = '/pw';
const LEGACY_PREFIX = '/parseworks';

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    let path = url.pathname;

    const prefix = path === LEGACY_PREFIX || path.startsWith(LEGACY_PREFIX + '/')
      ? LEGACY_PREFIX
      : PREFIX;

    if (path === prefix) {
      return Response.redirect(url.origin + prefix + '/' + url.search, 301);
    }

    if (!path.startsWith(prefix + '/')) {
      return new Response('Not found', { status: 404 });
    }
    path = path.slice(prefix.length);

    const targetUrl = env.PAGES_URL + path + url.search;
    const proxyReq = new Request(targetUrl, {
      method: request.method,
      headers: request.headers,
      body: request.body,
      redirect: 'follow',
    });
    return fetch(proxyReq);
  },
};
