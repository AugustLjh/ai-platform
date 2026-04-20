export const collectRunEventPages = async (fetchPage, {
  afterSequence = 0,
  limit = 500,
  exhaustive = afterSequence <= 0,
  maxPages = 100
} = {}) => {
  const events = []
  let cursor = Number(afterSequence || 0)
  let pageCount = 0

  while (pageCount < maxPages) {
    const page = await fetchPage(cursor, limit)
    if (!Array.isArray(page) || page.length === 0) {
      break
    }

    events.push(...page)
    pageCount += 1

    const nextCursor = Math.max(cursor, ...page.map((event) => Number(event?.sequence || 0)))
    if (!exhaustive || page.length < limit || nextCursor <= cursor) {
      break
    }
    cursor = nextCursor
  }

  return events
}
