import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import DOMPurify from 'dompurify'

const escapeHtml = (input) => {
  if (!input) return ''
  return input
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
  highlight: (code, lang) => {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(code, { language: lang }).value
    }
    return escapeHtml(code)
  }
})

md.renderer.rules.fence = (tokens, idx, options, env, self) => {
  const token = tokens[idx]
  const langInfo = (token.info || '').trim()
  const lang = langInfo.split(/\s+/)[0] || 'text'
  const highlighted = options.highlight
    ? options.highlight(token.content, lang)
    : escapeHtml(token.content)
  const langLabel = langInfo || 'text'

  return `
    <div class="code-block">
      <div class="code-header">
        <span class="code-lang">${escapeHtml(langLabel)}</span>
        <button class="code-copy-btn" type="button">复制</button>
      </div>
      <pre><code class="hljs language-${escapeHtml(lang)}">${highlighted}</code></pre>
    </div>
  `
}

const renderMarkdown = (raw) => {
  if (!raw) return ''
  const html = md.render(raw)
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: [
      'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
      'p', 'br', 'strong', 'em', 'code', 'pre', 'span', 'div', 'blockquote',
      'ul', 'ol', 'li', 'a', 'button'
    ],
    ALLOWED_ATTR: ['href', 'target', 'rel', 'class', 'type']
  })
}

const isPlainMarkdownRequest = (input) => {
  if (!input) return false
  const text = input.toLowerCase()
  return (
    text.includes('只输出markdown') ||
    text.includes('输出markdown') ||
    text.includes('原始markdown') ||
    text.includes('纯markdown') ||
    text.includes('不要渲染') ||
    text.includes('raw markdown') ||
    text.includes('plain markdown') ||
    text.includes('markdown文本')
  )
}

export { renderMarkdown, isPlainMarkdownRequest }
