import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildArchiveBundleExplorer,
  buildDirectoryTreeExplorer,
  buildDocumentPagesExplorer,
  buildPagedCollectionExplorer
} from '../src/utils/agentArtifactInteractions.js'

test('buildDirectoryTreeExplorer keeps matching descendants visible and selectable', () => {
  const explorer = buildDirectoryTreeExplorer({
    nodes: [
      {
        name: 'src',
        path: 'src',
        node_type: 'directory',
        children: [
          {
            name: 'components',
            path: 'src/components',
            node_type: 'directory',
            children: [
              {
                name: 'AgentArtifactPanel.vue',
                path: 'src/components/AgentArtifactPanel.vue',
                node_type: 'file',
                size_bytes: 2048
              }
            ]
          }
        ]
      }
    ]
  }, {
    query: 'artifactpanel'
  })

  assert.deepEqual(
    explorer.rows.map((row) => row.path),
    ['src', 'src/components', 'src/components/AgentArtifactPanel.vue']
  )
  assert.equal(explorer.selectedNode?.path, 'src/components/AgentArtifactPanel.vue')
})

test('buildDocumentPagesExplorer filters pages by content and preserves page selection semantics', () => {
  const explorer = buildDocumentPagesExplorer({
    pages: [
      { page_number: 1, title: 'Overview', text: 'Catalog summary' },
      { page_number: 2, title: 'Hydration', text: 'Complex replay boundary' }
    ]
  }, {
    query: 'replay'
  })

  assert.equal(explorer.items.length, 1)
  assert.equal(explorer.selectedPage?.page_number, 2)
})

test('buildPagedCollectionExplorer and buildArchiveBundleExplorer filter and select matching items', () => {
  const paged = buildPagedCollectionExplorer({
    columns: ['name', 'status'],
    items: [
      { name: 'catalog', status: 'ready' },
      { name: 'hydration', status: 'needs-review' }
    ]
  }, {
    query: 'review'
  })
  const archive = buildArchiveBundleExplorer({
    files: [
      { name: 'dist/app.js', path: 'dist/app.js' },
      { name: 'logs/replay.txt', path: 'logs/replay.txt', checksum: 'abc123' }
    ]
  }, {
    query: 'replay'
  })

  assert.equal(paged.items.length, 1)
  assert.equal(paged.selectedItem?.name, 'hydration')
  assert.equal(archive.items.length, 1)
  assert.equal(archive.selectedItem?.path, 'logs/replay.txt')
})
