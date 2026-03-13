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

const sanitizeMarkdownHtml = (html) => DOMPurify.sanitize(html, {
  ALLOWED_TAGS: [
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'p', 'br', 'strong', 'em', 'code', 'pre', 'span', 'div', 'blockquote',
    'ul', 'ol', 'li', 'a', 'button', 'hr',
    'table', 'thead', 'tbody', 'tr', 'th', 'td'
  ],
  ALLOWED_ATTR: ['href', 'target', 'rel', 'class', 'type']
})

const highlightCode = (code, lang) => {
  if (lang && hljs.getLanguage(lang)) {
    return hljs.highlight(code, { language: lang }).value
  }
  return escapeHtml(code)
}

const renderMarkdown = (raw) => {
  if (!raw) return ''
  return sanitizeMarkdownHtml(md.render(raw))
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

const getBlockType = (token) => {
  switch (token.type) {
    case 'fence':
      return 'code'
    case 'heading_open':
      return 'heading'
    case 'blockquote_open':
      return 'blockquote'
    case 'bullet_list_open':
    case 'ordered_list_open':
      return 'list'
    case 'hr':
      return 'hr'
    case 'table_open':
      return 'table'
    case 'paragraph_open':
      return 'paragraph'
    default:
      return 'html'
  }
}

const collectTopLevelBlocks = (tokens) => {
  const groups = []

  for (let index = 0; index < tokens.length;) {
    const token = tokens[index]

    if (token.level !== 0 || token.type.endsWith('_close')) {
      index += 1
      continue
    }

    if (token.type === 'fence' || token.nesting === 0) {
      groups.push(tokens.slice(index, index + 1))
      index += 1
      continue
    }

    let depth = token.nesting
    let cursor = index + 1

    while (cursor < tokens.length && depth > 0) {
      depth += tokens[cursor].nesting
      cursor += 1
    }

    groups.push(tokens.slice(index, cursor))
    index = cursor
  }

  return groups
}

const renderTokenBlock = (tokens, blockIndex) => {
  const firstToken = tokens[0]
  const blockType = getBlockType(firstToken)

  if (blockType === 'code' && firstToken.type === 'fence') {
    const langInfo = (firstToken.info || '').trim()
    const language = langInfo.split(/\s+/)[0] || 'text'
    return {
      id: `code-${blockIndex}`,
      type: 'code',
      language,
      languageLabel: langInfo || 'text',
      code: firstToken.content || '',
      highlightedCode: highlightCode(firstToken.content || '', language)
    }
  }

  return {
    id: `${blockType}-${blockIndex}`,
    type: blockType,
    html: sanitizeMarkdownHtml(md.renderer.render(tokens, md.options, {}))
  }
}

const renderMarkdownBlocks = (raw) => {
  if (!raw) return []
  const tokens = md.parse(raw, {})
  return collectTopLevelBlocks(tokens).map((group, index) => renderTokenBlock(group, index))
}

const getFenceInfo = (line) => {
  const match = line.trimStart().match(/^(`{3,}|~{3,})/)
  if (!match) return null
  return {
    char: match[1][0],
    length: match[1].length
  }
}

const splitMarkdownForStreaming = (raw) => {
  if (!raw) {
    return {
      stableContent: '',
      previewContent: ''
    }
  }

  let cursor = 0
  let lastStableBoundary = 0
  let inFence = false
  let activeFence = null

  while (cursor < raw.length) {
    const nextLineBreak = raw.indexOf('\n', cursor)
    const lineEnd = nextLineBreak === -1 ? raw.length : nextLineBreak + 1
    const line = raw.slice(cursor, lineEnd)
    const fence = getFenceInfo(line)

    if (fence) {
      if (!inFence) {
        inFence = true
        activeFence = fence
      } else if (activeFence && fence.char === activeFence.char && fence.length >= activeFence.length) {
        inFence = false
        activeFence = null
        lastStableBoundary = lineEnd
      }
    } else if (!inFence && line.trim() === '') {
      lastStableBoundary = lineEnd
    }

    cursor = lineEnd
  }

  const stableContent = raw.slice(0, lastStableBoundary)
  const previewContent = raw.slice(lastStableBoundary).replace(/^\n+/, '')

  return {
    stableContent,
    previewContent
  }
}

const readLine = (raw, cursor) => {
  const nextLineBreak = raw.indexOf('\n', cursor)
  const end = nextLineBreak === -1 ? raw.length : nextLineBreak + 1
  return {
    line: raw.slice(cursor, end),
    end
  }
}

const isBlankLine = (line) => line.trim() === ''

const isHeadingLine = (line) => /^ {0,3}#{1,6}\s+\S+/.test(line)

const isHorizontalRuleLine = (line) => /^ {0,3}((\*\s*){3,}|(-\s*){3,}|(_\s*){3,})$/.test(line.trim())

const isBlockquoteLine = (line) => /^ {0,3}>/.test(line)

const isListLine = (line) => /^ {0,3}([-+*]|\d+\.)\s+/.test(line)

const isListContinuationLine = (line) => {
  if (isBlankLine(line)) return false
  if (isListLine(line)) return true
  return /^\s{2,}\S+/.test(line) || /^\t+\S+/.test(line)
}

const isTableSeparatorLine = (line) => /^ {0,3}\|?( *:?-+:? *\|)+ *:?-+:? *\|?$/.test(line.trim())

const isTableRowLine = (line) => line.includes('|')

const looksLikeTableSeparatorLine = (line) => {
  const trimmed = line.trim()
  return Boolean(trimmed) && /^[\s|:-]+$/.test(trimmed) && trimmed.includes('-')
}

const countTableCells = (line) => line
  .replace(/\n$/, '')
  .trim()
  .replace(/^\|/, '')
  .replace(/\|$/, '')
  .split('|')
  .filter((cell) => cell !== '')
  .length

const isTableStart = (currentLine, nextLine) => {
  if (!isTableRowLine(currentLine) || countTableCells(currentLine) < 2) {
    return false
  }
  return isTableSeparatorLine(nextLine || '') || looksLikeTableSeparatorLine(nextLine || '')
}

const isBlockStarterLine = (line, nextLine = '') => {
  return Boolean(
    getFenceInfo(line) ||
    isHeadingLine(line) ||
    isHorizontalRuleLine(line) ||
    isBlockquoteLine(line) ||
    isListLine(line) ||
    isTableStart(line, nextLine)
  )
}

const isEscapedCharacter = (raw, index) => {
  let slashCount = 0
  for (let cursor = index - 1; cursor >= 0 && raw[cursor] === '\\'; cursor -= 1) {
    slashCount += 1
  }
  return slashCount % 2 === 1
}

const isWordCharacter = (char) => /[0-9A-Za-z\u00C0-\u024F\u4E00-\u9FFF]/.test(char || '')

const canToggleSingleMarker = (raw, index) => {
  const prev = raw[index - 1] || ''
  const next = raw[index + 1] || ''
  return !(isWordCharacter(prev) && isWordCharacter(next))
}

const closeInlineToken = (type) => {
  switch (type) {
    case 'strong':
      return '</strong>'
    case 'em':
      return '</em>'
    case 'strike':
      return '</del>'
    case 'code':
      return '</code>'
    default:
      return ''
  }
}

const openInlineToken = (type) => {
  switch (type) {
    case 'strong':
      return '<strong>'
    case 'em':
      return '<em>'
    case 'strike':
      return '<del>'
    case 'code':
      return '<code>'
    default:
      return ''
  }
}

const sanitizeHref = (href) => {
  const value = (href || '').trim()
  if (!value) return ''
  if (/^(https?:\/\/|mailto:|\/)/i.test(value)) {
    return escapeHtml(value)
  }
  return ''
}

const renderPendingLink = (label) => {
  const labelHtml = renderInlineMarkdown(label || '')
  return `<span class="streaming-link-pending">${labelHtml}</span>`
}

const findClosingBracket = (raw, start) => {
  let depth = 0
  for (let index = start; index < raw.length; index += 1) {
    if (isEscapedCharacter(raw, index)) continue
    if (raw[index] === '[') {
      depth += 1
      continue
    }
    if (raw[index] === ']') {
      depth -= 1
      if (depth === 0) {
        return index
      }
    }
  }
  return -1
}

const findClosingParen = (raw, start) => {
  let depth = 0
  for (let index = start; index < raw.length; index += 1) {
    if (isEscapedCharacter(raw, index)) continue
    if (raw[index] === '(') {
      depth += 1
      continue
    }
    if (raw[index] === ')') {
      depth -= 1
      if (depth === 0) {
        return index
      }
    }
  }
  return -1
}

const renderInlineMarkdown = (raw) => {
  if (!raw) return ''

  let html = ''
  const stack = []

  const toggleToken = (type, marker) => {
    const top = stack[stack.length - 1]
    if (top && top.type === type && top.marker === marker) {
      stack.pop()
      html += closeInlineToken(type)
      return
    }
    stack.push({ type, marker })
    html += openInlineToken(type)
  }

  for (let index = 0; index < raw.length;) {
    const char = raw[index]

    if (char === '\n') {
      html += '<br>'
      index += 1
      continue
    }

    if (char === '[' && !isEscapedCharacter(raw, index)) {
      const labelEnd = findClosingBracket(raw, index)
      if (labelEnd !== -1 && raw[labelEnd + 1] === '(') {
        const urlEnd = findClosingParen(raw, labelEnd + 1)
        if (urlEnd !== -1) {
          const label = raw.slice(index + 1, labelEnd)
          const href = sanitizeHref(raw.slice(labelEnd + 2, urlEnd))
          const labelHtml = renderInlineMarkdown(label)
          html += href
            ? `<a href="${href}" target="_blank" rel="noreferrer noopener">${labelHtml}</a>`
            : labelHtml
          index = urlEnd + 1
          continue
        }

        html += renderPendingLink(raw.slice(index + 1, labelEnd))
        index = raw.length
        continue
      }

      if (labelEnd !== -1) {
        html += renderPendingLink(raw.slice(index + 1, labelEnd))
        index = labelEnd + 1
        continue
      }

      html += renderPendingLink(raw.slice(index + 1))
      break
    }

    const pair = raw.slice(index, index + 2)
    if (!isEscapedCharacter(raw, index) && (pair === '**' || pair === '__')) {
      toggleToken('strong', pair)
      index += 2
      continue
    }

    if (!isEscapedCharacter(raw, index) && pair === '~~') {
      toggleToken('strike', pair)
      index += 2
      continue
    }

    if (!isEscapedCharacter(raw, index) && char === '`') {
      toggleToken('code', char)
      index += 1
      continue
    }

    if (!isEscapedCharacter(raw, index) && (char === '*' || char === '_') && canToggleSingleMarker(raw, index)) {
      toggleToken('em', char)
      index += 1
      continue
    }

    html += escapeHtml(char)
    index += 1
  }

  while (stack.length > 0) {
    html += closeInlineToken(stack.pop().type)
  }

  return html
}

const normalizeBlockText = (raw) => raw.replace(/\n$/, '')

const buildStreamingHtmlBlock = (blockIndex, blockType, html) => ({
  id: `${blockType}-${blockIndex}`,
  type: blockType,
  html
})

const renderStreamingParagraphBlock = (raw, blockIndex) => {
  const content = normalizeBlockText(raw)
  return buildStreamingHtmlBlock(blockIndex, 'paragraph', `<p>${renderInlineMarkdown(content)}</p>`)
}

const renderStreamingHeadingBlock = (raw, blockIndex) => {
  const line = normalizeBlockText(raw)
  const match = line.match(/^\s{0,3}(#{1,6})\s+(.*)$/)
  if (!match) {
    return renderStreamingParagraphBlock(raw, blockIndex)
  }
  const level = match[1].length
  const content = match[2].trim()
  return buildStreamingHtmlBlock(
    blockIndex,
    'heading',
    `<h${level}>${renderInlineMarkdown(content)}</h${level}>`
  )
}

const renderStreamingHrBlock = (blockIndex) => buildStreamingHtmlBlock(blockIndex, 'hr', '<hr>')

const stripBlockquotePrefix = (line) => line.replace(/^\s{0,3}>\s?/, '').replace(/\n$/, '')

const renderStreamingBlockquoteBlock = (raw, blockIndex) => {
  const content = raw
    .split('\n')
    .filter((line) => line.length > 0)
    .map(stripBlockquotePrefix)
    .join('\n')
  return buildStreamingHtmlBlock(blockIndex, 'blockquote', `<blockquote><p>${renderInlineMarkdown(content)}</p></blockquote>`)
}

const parseListItems = (raw) => {
  const lines = raw.split('\n').filter((line) => line.length > 0)
  const items = []
  let currentItem = null

  lines.forEach((line) => {
    const match = line.match(/^\s{0,3}(([-+*])|(\d+\.))\s*(.*)$/)
    if (match) {
      if (currentItem) {
        items.push(currentItem)
      }
      currentItem = {
        ordered: Boolean(match[3]),
        content: match[4] || ''
      }
      return
    }

    if (!currentItem) {
      currentItem = {
        ordered: false,
        content: line.trim()
      }
      return
    }

    currentItem.content += `\n${line.trim()}`
  })

  if (currentItem) {
    items.push(currentItem)
  }

  return items
}

const renderStreamingListBlock = (raw, blockIndex) => {
  const items = parseListItems(raw)
  const ordered = items[0]?.ordered
  const tag = ordered ? 'ol' : 'ul'
  const body = items
    .map((item) => `<li>${renderInlineMarkdown(item.content)}</li>`)
    .join('')
  return buildStreamingHtmlBlock(blockIndex, 'list', `<${tag}>${body}</${tag}>`)
}

const splitTableCells = (line) => line
  .replace(/\n$/, '')
  .trim()
  .replace(/^\|/, '')
  .replace(/\|$/, '')
  .split('|')
  .map((cell) => cell.trim())

const renderStreamingTableBlock = (raw, blockIndex) => {
  const lines = raw.split('\n').filter((line) => line.trim() !== '')
  const [headerLine = '', , ...bodyLines] = lines
  const headers = splitTableCells(headerLine)
  const rows = bodyLines.map(splitTableCells)
  const headerHtml = headers.map((cell) => `<th>${renderInlineMarkdown(cell)}</th>`).join('')
  const bodyHtml = rows
    .map((row) => `<tr>${row.map((cell) => `<td>${renderInlineMarkdown(cell)}</td>`).join('')}</tr>`)
    .join('')

  return buildStreamingHtmlBlock(
    blockIndex,
    'table',
    `<table><thead><tr>${headerHtml}</tr></thead><tbody>${bodyHtml}</tbody></table>`
  )
}

const renderStreamingCodeBlock = (raw, blockIndex) => {
  const [firstLine = ''] = raw.split('\n')
  const langInfo = (firstLine.trimStart().match(/^(`{3,}|~{3,})(.*)$/)?.[2] || '').trim()
  const language = langInfo.split(/\s+/)[0] || 'text'
  const body = raw
    .split('\n')
    .slice(1)
    .filter((line, index, lines) => {
      if (index !== lines.length - 1) return true
      return !getFenceInfo(line)
    })
    .join('\n')

  return {
    id: `code-${blockIndex}`,
    type: 'code',
    language,
    languageLabel: langInfo || 'text',
    code: body,
    highlightedCode: highlightCode(body, language)
  }
}

const renderStreamingMarkdownBlocks = (raw) => {
  if (!raw) return []

  const blocks = []

  for (let cursor = 0; cursor < raw.length;) {
    const current = readLine(raw, cursor)
    const upcoming = current.end < raw.length ? readLine(raw, current.end) : null

    if (isBlankLine(current.line)) {
      cursor = current.end
      continue
    }

    const fence = getFenceInfo(current.line)
    if (fence) {
      let end = current.end
      while (end < raw.length) {
        const next = readLine(raw, end)
        end = next.end
        const nextFence = getFenceInfo(next.line)
        if (nextFence && nextFence.char === fence.char && nextFence.length >= fence.length) {
          break
        }
      }
      blocks.push(renderStreamingCodeBlock(raw.slice(cursor, end), blocks.length))
      cursor = end
      continue
    }

    if (isHeadingLine(current.line)) {
      blocks.push(renderStreamingHeadingBlock(current.line, blocks.length))
      cursor = current.end
      continue
    }

    if (isHorizontalRuleLine(current.line)) {
      blocks.push(renderStreamingHrBlock(blocks.length))
      cursor = current.end
      continue
    }

    if (isTableStart(current.line, upcoming?.line || '')) {
      let end = current.end
      while (end < raw.length) {
        const next = readLine(raw, end)
        if (isBlankLine(next.line) || !isTableRowLine(next.line)) {
          break
        }
        end = next.end
      }
      blocks.push(renderStreamingTableBlock(raw.slice(cursor, end), blocks.length))
      cursor = end
      continue
    }

    if (isBlockquoteLine(current.line)) {
      let end = current.end
      while (end < raw.length) {
        const next = readLine(raw, end)
        if (isBlankLine(next.line) || !isBlockquoteLine(next.line)) {
          break
        }
        end = next.end
      }
      blocks.push(renderStreamingBlockquoteBlock(raw.slice(cursor, end), blocks.length))
      cursor = end
      continue
    }

    if (isListLine(current.line)) {
      let end = current.end
      while (end < raw.length) {
        const next = readLine(raw, end)
        if (!isListContinuationLine(next.line)) {
          break
        }
        end = next.end
      }
      blocks.push(renderStreamingListBlock(raw.slice(cursor, end), blocks.length))
      cursor = end
      continue
    }

    let end = current.end
    while (end < raw.length) {
      const next = readLine(raw, end)
      const nextAfter = next.end < raw.length ? readLine(raw, next.end) : null
      if (isBlankLine(next.line) || isBlockStarterLine(next.line, nextAfter?.line || '')) {
        break
      }
      end = next.end
    }
    blocks.push(renderStreamingParagraphBlock(raw.slice(cursor, end), blocks.length))
    cursor = end
  }

  return blocks
}

export {
  renderMarkdown,
  renderMarkdownBlocks,
  renderStreamingMarkdownBlocks,
  isPlainMarkdownRequest,
  sanitizeMarkdownHtml,
  splitMarkdownForStreaming
}
