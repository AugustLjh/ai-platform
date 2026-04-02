const normalizeQuery = (value) => String(value || '').trim().toLowerCase()

const itemKey = (item, fallback) => String(item || '').trim() || fallback

const stringIncludes = (value, query) => String(value || '').toLowerCase().includes(query)

const objectIncludes = (value, query) => {
  if (!query) return true
  if (value === null || value === undefined) return false
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return stringIncludes(value, query)
  }
  if (Array.isArray(value)) {
    return value.some((entry) => objectIncludes(entry, query))
  }
  if (typeof value === 'object') {
    return Object.values(value).some((entry) => objectIncludes(entry, query))
  }
  return false
}

const pickSelectedKey = (items, preferredKey, keyBuilder) => {
  if (!Array.isArray(items) || items.length === 0) {
    return ''
  }
  const keys = items.map((item, index) => keyBuilder(item, index))
  if (preferredKey && keys.includes(preferredKey)) {
    return preferredKey
  }
  return keys[0]
}

const collectTreeRows = (nodes, query, expandedSet, rows, ancestors = []) => {
  let matchedInSubtree = false

  for (const node of Array.isArray(nodes) ? nodes : []) {
    const path = itemKey(node?.path || node?.name, `node-${rows.length + 1}`)
    const searchable = [node?.name, node?.path, node?.uri, node?.mime_type, node?.metadata]
    const selfMatch = !query || searchable.some((value) => objectIncludes(value, query))
    const children = Array.isArray(node?.children) ? node.children : []
    const forcedExpand = query && children.length > 0
    const expanded = forcedExpand || expandedSet.has(path)
    const childRows = []
    const childMatch = collectTreeRows(children, query, expandedSet, childRows, [...ancestors, path])
    const visible = selfMatch || childMatch || (!query && (ancestors.length === 0 || expandedSet.has(ancestors[ancestors.length - 1])))

    if (visible) {
      rows.push({
        key: path,
        path,
        depth: ancestors.length,
        name: node?.name || path,
        isDirectory: node?.node_type === 'directory',
        expanded,
        hasChildren: children.length > 0,
        node,
        isMatch: selfMatch
      })
      if ((expanded || query) && childRows.length > 0) {
        rows.push(...childRows)
      }
    }

    matchedInSubtree = matchedInSubtree || selfMatch || childMatch
  }

  return matchedInSubtree
}

export const buildDirectoryTreeExplorer = (payload = {}, state = {}) => {
  const query = normalizeQuery(state.query)
  const expandedSet = new Set(Array.isArray(state.expandedPaths) ? state.expandedPaths : [])
  const rows = []
  collectTreeRows(payload.nodes || [], query, expandedSet, rows)
  const selectableRows = rows.filter((row) => row.node?.node_type !== 'directory' || row.hasChildren)
  const preferredRows = query
    ? selectableRows.filter((row) => row.isMatch)
    : selectableRows
  const fallbackSelectedKey = pickSelectedKey(selectableRows, state.selectedPath, (row) => row.key)
  const selectedKey = query && !state.selectedPath
    ? pickSelectedKey(preferredRows, '', (row) => row.key)
    : fallbackSelectedKey
  return {
    query,
    rows,
    selectedKey,
    selectedNode: selectableRows.find((row) => row.key === selectedKey)?.node || null,
    matchCount: rows.filter((row) => row.isMatch).length
  }
}

const filterSelectableItems = (items, query, matcher) => {
  const filtered = (Array.isArray(items) ? items : []).filter((item) => !query || matcher(item, query))
  return {
    items: filtered,
    query,
    totalCount: Array.isArray(items) ? items.length : 0
  }
}

export const buildDocumentPagesExplorer = (payload = {}, state = {}) => {
  const query = normalizeQuery(state.query)
  const filtered = filterSelectableItems(payload.pages || [], query, (item, normalizedQuery) => (
    objectIncludes(item?.title, normalizedQuery) ||
    objectIncludes(item?.text, normalizedQuery) ||
    objectIncludes(item?.source, normalizedQuery)
  ))
  const selectedKey = pickSelectedKey(filtered.items, state.selectedPage, (item, index) => String(item?.page_number || index + 1))
  return {
    ...filtered,
    selectedKey,
    selectedPage: filtered.items.find((item, index) => String(item?.page_number || index + 1) === selectedKey) || null
  }
}

export const buildMediaGalleryExplorer = (payload = {}, state = {}) => {
  const query = normalizeQuery(state.query)
  const filtered = filterSelectableItems(payload.items || [], query, (item, normalizedQuery) => (
    objectIncludes(item?.title, normalizedQuery) ||
    objectIncludes(item?.alt, normalizedQuery) ||
    objectIncludes(item?.uri, normalizedQuery) ||
    objectIncludes(item?.mime_type, normalizedQuery)
  ))
  const selectedKey = pickSelectedKey(filtered.items, state.selectedItem, (item, index) => itemKey(item?.uri || item?.path || item?.title, `media-${index + 1}`))
  return {
    ...filtered,
    selectedKey,
    selectedItem: filtered.items.find((item, index) => itemKey(item?.uri || item?.path || item?.title, `media-${index + 1}`) === selectedKey) || null
  }
}

export const buildFileBundleExplorer = (payload = {}, state = {}) => {
  const query = normalizeQuery(state.query)
  const filtered = filterSelectableItems(payload.files || [], query, (item, normalizedQuery) => (
    objectIncludes(item?.name, normalizedQuery) ||
    objectIncludes(item?.path, normalizedQuery) ||
    objectIncludes(item?.description, normalizedQuery) ||
    objectIncludes(item?.preview_text, normalizedQuery) ||
    objectIncludes(item?.mime_type, normalizedQuery)
  ))
  const selectedKey = pickSelectedKey(filtered.items, state.selectedItem, (item, index) => itemKey(item?.uri || item?.path || item?.name, `bundle-${index + 1}`))
  return {
    ...filtered,
    selectedKey,
    selectedItem: filtered.items.find((item, index) => itemKey(item?.uri || item?.path || item?.name, `bundle-${index + 1}`) === selectedKey) || null
  }
}

export const buildArchiveBundleExplorer = (payload = {}, state = {}) => {
  const query = normalizeQuery(state.query)
  const filtered = filterSelectableItems(payload.files || [], query, (item, normalizedQuery) => (
    objectIncludes(item?.name, normalizedQuery) ||
    objectIncludes(item?.path, normalizedQuery) ||
    objectIncludes(item?.description, normalizedQuery) ||
    objectIncludes(item?.checksum, normalizedQuery) ||
    objectIncludes(item?.mime_type, normalizedQuery)
  ))
  const selectedKey = pickSelectedKey(filtered.items, state.selectedItem, (item, index) => itemKey(item?.path || item?.name, `archive-${index + 1}`))
  return {
    ...filtered,
    selectedKey,
    selectedItem: filtered.items.find((item, index) => itemKey(item?.path || item?.name, `archive-${index + 1}`) === selectedKey) || null
  }
}

export const buildPagedCollectionExplorer = (payload = {}, state = {}) => {
  const query = normalizeQuery(state.query)
  const columns = Array.isArray(payload.columns) ? payload.columns : []
  const filtered = filterSelectableItems(payload.items || [], query, (item, normalizedQuery) => objectIncludes(item, normalizedQuery))
  const selectedKey = pickSelectedKey(filtered.items, state.selectedItem, (item, index) => itemKey(item?.id || item?.key || item?.path || item?.name || item?.title, `row-${index + 1}`))
  return {
    ...filtered,
    columns,
    selectedKey,
    selectedItem: filtered.items.find((item, index) => itemKey(item?.id || item?.key || item?.path || item?.name || item?.title, `row-${index + 1}`) === selectedKey) || null
  }
}
