"""Run inside D:\\SlothShelf\\slothshelf:  python prepare_github.py
Creates LICENSE, docs/index.html (a static demo for GitHub Pages) and docs/.nojekyll."""
import os, re

html = open(os.path.join("app", "static", "index.html"), encoding="utf-8").read()

# The stock sloth picture is not ours to publish; hide it in the public demo.
html = re.sub(r'<img class="sloth[^>]*>', '', html)

MOCK = r"""<script>
(() => {
  const mk = (i, v, t, q) => ({_id: String(i), url: 'https://example.com/' + i, status: 'carded', user: {state: 'unread'}, source_quality: q || 'full',
    title: ['Python tricks every beginner misses','Ten AI tools worth trying this term','Why your RAG pipeline is slow','Ten productivity hacks (listicle)'][i % 4],
    card: {verdict: v, topic: t, tags: ['python', 'tips', 'ai'], summary: 'Five built-in features that replace common loops.',
      overview: 'The reel walks through five built-in Python features that replace common loops. It starts with enumerate, then zip, then f-string format specs, and ends with a tip on merging dictionaries. Each one is shown on a short example.',
      key_points: ['enumerate replaces range(len(x)) and gives index and item together.', 'zip pairs two lists and stops at the shorter one.', 'f-strings accept format specs such as :.2f.', 'dict1 | dict2 merges dictionaries in Python 3.9+.'],
      terms: ['enumerate: built-in that yields (index, item)', 'zip: pairs items from several iterables'], try_this: 'Rewrite one loop in your last project with enumerate.', reason: 'Matches your goal of learning Python.'}});
  const links = [mk(0,'read','Python'), mk(1,'read','AI tools','caption'), mk(2,'skim','RAG','note'), mk(3,'skip','Misc')];
  const data = {
    '/api/links': links,
    '/api/stats': {links_in: 42, status: {carded: 38, new: 3, failed: 1}, verdicts: {read: 14, skim: 16, skip: 8}, states: {}, agreement: {checked: 9, agreed: 7, rate: 0.778}},
    '/api/digest/latest': {week: '2026-W43', stats: {links_in: 42, carded: 38, picked: 2}, picks: links.slice(0, 2)},
    '/api/goals': {goals: ['learn Python for ML', 'find useful AI tools']},
    '/api/health': {mongo: true, ollama: true, models: {'gemma2:2b': true}},
    '/api/search': links.slice(0, 2),
  };
  const real = window.fetch;
  window.fetch = async (url, opts) => {
    const path = String(url).split('?')[0];
    if (path === '/api/digest/pdf') return new Response(JSON.stringify({detail: 'The PDF digest works in the local app. This page is a demo.'}), {status: 400});
    const body = data[path] ?? (path === '/api/digest' ? data['/api/digest/latest'] : {ok: true, inserted: 0, duplicates: 0, invalid: 0, processed: 0, carded: 0, failed: 0, remaining: 0, queued: 0, goals: data['/api/goals'].goals});
    return new Response(JSON.stringify(body), {status: 200, headers: {'Content-Type': 'application/json'}});
  };
})();
</script>
<div style="position:relative;z-index:5;background:#16211b;color:#e6eee8;text-align:center;padding:9px 14px;font:14px system-ui">
Demo with sample data. The real SlothShelf runs on your laptop with Gemma and MongoDB Atlas.
<a href="https://github.com/hiyalukka/slothshelf" style="color:#6fcf9b">Get the code</a></div>
"""
html = html.replace("<body>", "<body>\n" + MOCK, 1)

os.makedirs("docs", exist_ok=True)
open(os.path.join("docs", "index.html"), "w", encoding="utf-8").write(html)
open(os.path.join("docs", ".nojekyll"), "w").write("")
open("LICENSE", "w").write("""MIT License

Copyright (c) 2026 Hiya

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
associated documentation files (the "Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the
following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial
portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT
LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO
EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE
USE OR OTHER DEALINGS IN THE SOFTWARE.
""")
print("Created LICENSE, docs/index.html, docs/.nojekyll")
