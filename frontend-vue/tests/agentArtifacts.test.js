import test from 'node:test'
import assert from 'node:assert/strict'

import {
  describeArtifact,
  filterArtifacts,
  buildArtifactsFromToolResult,
  buildRunArtifactsFromToolCalls,
  buildArtifactsFromStructuredResult,
  getRunAnswerText,
  mergeArtifacts,
  normalizeRunResult,
  normalizeArtifact,
  summarizeArtifactFilters
} from '../src/utils/agentArtifacts.js'

test('buildArtifactsFromStructuredResult derives task_plan from steps-only payload', () => {
  const artifacts = buildArtifactsFromStructuredResult({
    steps: [
      { title: 'Audit compatibility drift', status: 'in_progress' },
      { title: 'Backfill replay coverage', status: 'pending' }
    ],
    decisions: ['Prefer structure-first compatibility over markdown-only fallback.']
  })

  assert.equal(artifacts[0].artifactType, 'answer')
  assert.equal(artifacts[0].payload.text, 'Audit compatibility drift\nBackfill replay coverage')

  const taskPlan = artifacts.find((artifact) => artifact.artifactType === 'task_plan')
  assert.ok(taskPlan)
  assert.equal(taskPlan.payload.steps[0].title, 'Audit compatibility drift')
  assert.equal(taskPlan.payload.decisions[0], 'Prefer structure-first compatibility over markdown-only fallback.')
})

test('normalizeRunResult derives readable answer text from nested structured payloads', () => {
  const result = normalizeRunResult({
    final_output_json: {
      document_excerpt: [
        {
          title: 'Runtime Notes',
          text: 'Structured results should remain readable after hydration.'
        }
      ]
    }
  })

  assert.equal(result.finalOutputText, 'Structured results should remain readable after hydration.')
  assert.equal(result.artifacts[0].artifactType, 'answer')
  assert.equal(result.artifacts[1].artifactType, 'document_excerpt')
})

test('normalizeRunResult merges explicit artifacts with derived answer and task plan surfaces', () => {
  const result = normalizeRunResult({
    final_output_json: {
      steps: [
        { title: 'Audit compatibility drift', status: 'in_progress' },
        { title: 'Backfill replay coverage', status: 'pending' }
      ],
      citations: [
        {
          title: 'Runtime Plan',
          url: 'https://example.com/runtime-plan',
          snippet: 'Prefer structure-first hydration.'
        }
      ]
    },
    artifacts: [
      {
        artifact_type: 'citations',
        name: 'Runtime Sources',
        payload: {
          items: [
            {
              title: 'Runtime Plan',
              url: 'https://example.com/runtime-plan',
              snippet: 'Prefer structure-first hydration.'
            }
          ]
        }
      }
    ]
  })

  assert.equal(result.finalOutputText, 'Audit compatibility drift\nBackfill replay coverage')
  assert.deepEqual(
    result.artifacts.map((artifact) => artifact.artifactType),
    ['answer', 'citations', 'task_plan']
  )
  assert.equal(result.artifacts[1].name, 'Runtime Sources')
})

test('normalizeRunResult preserves richer artifact types from structured final output', () => {
  const result = normalizeRunResult({
    final_output_json: {
      document_pages: {
        title: 'Deployment Checklist',
        pages: [
          { page: 1, text: 'Validate schema migrations.' },
          { page: 2, text: 'Verify workspace hydration.' }
        ]
      },
      archive_bundle: {
        name: 'release-bundle.zip',
        format: 'zip',
        entries: [
          { path: 'dist/app.js', size_bytes: 2048, compressed_size_bytes: 512 }
        ]
      }
    }
  })

  assert.equal(result.finalOutputText, 'Validate schema migrations.')
  assert.ok(result.artifacts.find((artifact) => artifact.artifactType === 'document_pages'))
  assert.ok(result.artifacts.find((artifact) => artifact.artifactType === 'archive_bundle'))
})

test('getRunAnswerText falls back to step titles when no explicit answer fields exist', () => {
  const answer = getRunAnswerText({
    finalOutputJson: {
      steps: [
        { title: 'Review the persisted run payload' },
        { title: 'Rebuild missing artifacts from structured JSON' }
      ]
    }
  })

  assert.equal(answer, 'Review the persisted run payload\nRebuild missing artifacts from structured JSON')
})

test('buildArtifactsFromToolResult promotes structured MCP payloads without duplicating answer artifacts', () => {
  const artifacts = buildArtifactsFromToolResult({
    structured_content: {
      answer: 'Found the matching documents.',
      citations: [
        { title: 'Runtime Plan', url: 'https://example.com/runtime-plan', snippet: 'Use structured artifacts.' }
      ],
      table: {
        columns: ['name', 'status'],
        rows: [{ name: 'catalog', status: 'ready' }]
      }
    },
    text: 'Found the matching documents.'
  }, {
    id: 'tool-call-1',
    stepId: 'step-1',
    toolName: 'search_docs',
    toolKind: 'mcp'
  }, {
    includeAnswer: false
  })

  assert.equal(artifacts.find((artifact) => artifact.artifactType === 'answer'), undefined)
  assert.equal(artifacts.find((artifact) => artifact.artifactType === 'citations')?.name, 'search_docs - Citations')
  assert.equal(artifacts.find((artifact) => artifact.artifactType === 'table')?.metadata.tool_call_id, 'tool-call-1')
})

test('buildArtifactsFromToolResult promotes workspace status and file info payloads', () => {
  const statusArtifacts = buildArtifactsFromToolResult({
    workspace: {
      id: 'tenant/run',
      root: '/workspace',
      status: 'ready',
      source: { type: 'upload_bundle' },
      snapshot: {
        file_count: 2,
        total_size_bytes: 42,
        snapshot_at: '2026-05-13T00:00:00+00:00'
      }
    }
  }, {
    id: 'tool-1',
    toolName: 'workspace_status',
    toolKind: 'workspace',
    status: 'completed'
  })

  assert.equal(statusArtifacts[0].artifactType, 'workspace_summary')
  assert.equal(statusArtifacts[0].payload.source.type, 'upload_bundle')

  const infoArtifacts = buildArtifactsFromToolResult({
    path: 'src/app.py',
    type: 'file',
    size_bytes: 12,
    sha256: 'abc'
  }, {
    id: 'tool-2',
    toolName: 'workspace_file_info',
    toolKind: 'workspace',
    status: 'completed'
  })

  assert.equal(infoArtifacts[0].artifactType, 'file_bundle')
  assert.equal(infoArtifacts[0].payload.files[0].metadata.sha256, 'abc')
})

test('buildArtifactsFromToolResult surfaces empty git diff as an artifact', () => {
  const artifacts = buildArtifactsFromToolResult({
    command: ['git', 'diff'],
    exit_code: 0,
    stdout: '',
    stderr: '',
    truncated: false
  }, {
    id: 'tool-3',
    toolName: 'git_diff',
    toolKind: 'workspace',
    status: 'completed'
  })

  assert.equal(artifacts[0].artifactType, 'document_excerpt')
  assert.equal(artifacts[0].payload.items[0].text, 'No changes.')
})

test('buildArtifactsFromToolResult promotes workspace patch artifacts', () => {
  const artifacts = buildArtifactsFromToolResult({
    status: 'applied',
    path: 'src/app.py',
    operation: 'modify',
    dry_run: false,
    changed: true,
    before_sha256: 'before',
    after_sha256: 'after',
    diff: '--- a/src/app.py\n+++ b/src/app.py\n@@\n-old\n+new\n',
    artifacts: [{
      artifact_type: 'code_patch',
      name: 'Workspace Patch',
      payload: {
        operation: 'modify',
        status: 'applied',
        dry_run: false,
        files: [{
          path: 'src/app.py',
          operation: 'modify',
          before_sha256: 'before',
          after_sha256: 'after',
          changed: true
        }],
        diff: '--- a/src/app.py\n+++ b/src/app.py\n@@\n-old\n+new\n'
      }
    }]
  }, {
    id: 'tool-4',
    toolName: 'workspace_apply_patch',
    toolKind: 'workspace',
    status: 'completed'
  })

  assert.equal(artifacts[0].artifactType, 'code_patch')
  assert.equal(artifacts[0].payload.files[0].path, 'src/app.py')
  assert.equal(artifacts[0].payload.files[0].beforeSha256, 'before')
  assert.equal(artifacts[0].metadata.tool_call_id, 'tool-4')
})

test('buildArtifactsFromToolResult promotes sandbox execution into verification report', () => {
  const artifacts = buildArtifactsFromToolResult({
    status: 'failed',
    exit_code: 1,
    command: ['python', '-m', 'pytest'],
    cwd: '.',
    duration_ms: 123,
    timeout_seconds: 300,
    purpose: 'test',
    failure_category: 'non_zero_exit',
    stdout: 'FAILED tests/test_app.py::test_app',
    stderr: '',
    truncated: false,
    runner: { backend: 'docker', image: 'python:3.12-slim' },
    structured_report: {
      schema_version: 'verification_report.v1',
      summary: { report_count: 1 },
      reports: [
        {
          kind: 'test',
          format: 'pytest_text',
          summary: { failed: 1 },
          failures: [{ title: 'tests/test_app.py::test_app', severity: 'error' }]
        }
      ]
    }
  }, {
    id: 'tool-verify-1',
    toolName: 'run_tests',
    toolKind: 'sandbox-exec',
    status: 'completed'
  })

  assert.equal(artifacts[0].artifactType, 'verification_report')
  assert.equal(artifacts[0].name, 'run_tests - Test Verification')
  assert.equal(artifacts[0].payload.kind, 'test')
  assert.equal(artifacts[0].payload.status, 'failed')
  assert.equal(artifacts[0].payload.exitCode, 1)
  assert.equal(artifacts[0].payload.logs.stdout, 'FAILED tests/test_app.py::test_app')
  assert.equal(artifacts[0].payload.structuredReport.schema_version, 'verification_report.v1')
  assert.equal(artifacts[0].payload.structuredReport.reports[0].summary.failed, 1)
  assert.equal(artifacts[0].metadata.failure_category, 'non_zero_exit')
})

test('buildArtifactsFromToolResult promotes specialized verification tools', () => {
  const artifacts = buildArtifactsFromToolResult({
    status: 'completed',
    exit_code: 0,
    command: ['python', '-m', 'pyright', '.'],
    cwd: '.',
    duration_ms: 42,
    timeout_seconds: 300,
    purpose: 'typecheck',
    stdout: '0 errors',
    stderr: '',
    truncated: false,
    ecosystem: 'python',
    report_format: 'plain_text'
  }, {
    id: 'tool-typecheck-1',
    toolName: 'typecheck_run',
    toolKind: 'sandbox-exec',
    status: 'completed'
  })

  assert.equal(artifacts[0].artifactType, 'verification_report')
  assert.equal(artifacts[0].name, 'typecheck_run - Typecheck Verification')
  assert.equal(artifacts[0].payload.kind, 'typecheck')
  assert.equal(artifacts[0].payload.ecosystem, 'python')
  assert.equal(artifacts[0].payload.reportFormat, 'plain_text')
})

test('buildArtifactsFromToolResult promotes web search and page results', () => {
  const searchArtifacts = buildArtifactsFromToolResult({
    query: 'runtime',
    items: [
      {
        title: 'Runtime Plan',
        url: 'https://docs.example.com/runtime',
        snippet: 'Use structured web artifacts.'
      }
    ],
    fetched_at: '2026-05-14T00:00:00+00:00',
    source: 'web_search'
  }, {
    id: 'tool-web-1',
    toolName: 'web_search',
    toolKind: 'web',
    status: 'completed'
  })

  assert.equal(searchArtifacts[0].artifactType, 'citations')
  assert.equal(searchArtifacts[0].payload.items[0].url, 'https://docs.example.com/runtime')
  assert.equal(searchArtifacts[0].metadata.query, 'runtime')

  const pageArtifacts = buildArtifactsFromToolResult({
    url: 'https://docs.example.com/runtime',
    requested_url: 'https://docs.example.com/runtime',
    status: 200,
    title: 'Runtime Plan',
    text: 'Use structured web artifacts.',
    fetched_at: '2026-05-14T00:00:00+00:00',
    truncated: false
  }, {
    id: 'tool-web-2',
    toolName: 'open_page',
    toolKind: 'web',
    status: 'completed'
  })

  assert.equal(pageArtifacts[0].artifactType, 'document_excerpt')
  assert.equal(pageArtifacts[0].payload.items[0].source, 'https://docs.example.com/runtime')
  assert.equal(pageArtifacts[0].payload.items[0].metadata.status, 200)

  const downloadArtifacts = buildArtifactsFromToolResult({
    url: 'https://docs.example.com/runtime.pdf',
    requested_url: 'https://docs.example.com/runtime.pdf',
    status: 200,
    filename: 'runtime.pdf',
    content_type: 'application/pdf',
    bytes: 12,
    sha256: 'hash',
    truncated: false,
    files: [{
      name: 'runtime.pdf',
      path: 'runtime.pdf',
      mime_type: 'application/pdf',
      size_bytes: 12,
      data: 'ZmFrZSBwZGY=',
      source_url: 'https://docs.example.com/runtime.pdf',
      metadata: { sha256: 'hash' }
    }]
  }, {
    id: 'tool-web-3',
    toolName: 'download_file',
    toolKind: 'web',
    status: 'completed'
  })

  assert.equal(downloadArtifacts[0].artifactType, 'file_bundle')
  assert.equal(downloadArtifacts[0].payload.files[0].name, 'runtime.pdf')
  assert.equal(downloadArtifacts[0].payload.files[0].uri, 'data:application/pdf;base64,ZmFrZSBwZGY=')
  assert.equal(downloadArtifacts[0].payload.files[0].source, 'https://docs.example.com/runtime.pdf')
  assert.equal(downloadArtifacts[0].metadata.sha256, 'hash')
})

test('buildArtifactsFromToolResult promotes delete patch review metadata', () => {
  const artifacts = buildArtifactsFromToolResult({
    status: 'dry_run',
    path: 'src/obsolete.py',
    operation: 'delete',
    dry_run: true,
    changed: true,
    before_sha256: 'before',
    after_sha256: null,
    diff: '--- a/src/obsolete.py\n+++ b/src/obsolete.py\n@@\n-old\n',
    artifacts: [{
      artifact_type: 'code_patch',
      name: 'Workspace Patch',
      payload: {
        operation: 'delete',
        status: 'dry_run',
        dry_run: true,
        files: [{
          path: 'src/obsolete.py',
          operation: 'delete',
          before_sha256: 'before',
          after_sha256: null,
          changed: true
        }],
        diff: '--- a/src/obsolete.py\n+++ b/src/obsolete.py\n@@\n-old\n',
        review_notes: ['Deletion requires review.'],
        merge_policy: 'manual_review_required'
      }
    }]
  }, {
    id: 'tool-5',
    toolName: 'workspace_delete_path',
    toolKind: 'workspace',
    status: 'completed'
  })

  assert.equal(artifacts[0].artifactType, 'code_patch')
  assert.equal(artifacts[0].payload.operation, 'delete')
  assert.deepEqual(artifacts[0].payload.reviewNotes, ['Deletion requires review.'])
  assert.equal(artifacts[0].payload.mergePolicy, 'manual_review_required')
})

test('buildArtifactsFromStructuredResult promotes implicit result lists into table artifacts', () => {
  const artifacts = buildArtifactsFromStructuredResult({
    answer: 'Found two matching records.',
    results: [
      { path: '/docs/runtime', status: 'ready' },
      { path: '/docs/mcp', status: 'stale' }
    ]
  })

  assert.equal(artifacts[0].artifactType, 'answer')
  assert.equal(artifacts.find((artifact) => artifact.artifactType === 'table')?.name, 'Results')
})

test('buildArtifactsFromStructuredResult promotes paginated results and rich resources', () => {
  const artifacts = buildArtifactsFromStructuredResult({
    results: [
      { path: '/docs/runtime', status: 'ready' },
      { path: '/docs/mcp', status: 'stale' }
    ],
    next_cursor: 'cursor-2',
    total_count: 42,
    images: [
      {
        title: 'Workspace Architecture',
        uri: 'https://example.com/architecture.png',
        mimeType: 'image/png'
      }
    ],
    attachments: [
      {
        name: 'catalog-export.pdf',
        uri: 'https://example.com/catalog-export.pdf',
        mimeType: 'application/pdf',
        sizeBytes: 2048
      }
    ]
  })

  const paged = artifacts.find((artifact) => artifact.artifactType === 'paged_collection')
  const media = artifacts.find((artifact) => artifact.artifactType === 'media_gallery')
  const bundle = artifacts.find((artifact) => artifact.artifactType === 'file_bundle')

  assert.ok(paged)
  assert.equal(paged.payload.pagination.next_cursor, 'cursor-2')
  assert.equal(paged.payload.pagination.total_count, 42)
  assert.ok(media)
  assert.equal(media.payload.items[0].kind, 'image')
  assert.ok(bundle)
  assert.equal(bundle.payload.files[0].name, 'catalog-export.pdf')
})

test('buildArtifactsFromStructuredResult promotes directory trees, document pages, and archive bundles', () => {
  const artifacts = buildArtifactsFromStructuredResult({
    directory_tree: [
      { path: 'src/components/AgentArtifactPanel.vue', type: 'file', size_bytes: 2048 },
      { path: 'src/utils/agentArtifacts.js', type: 'file', size_bytes: 4096 },
      { path: 'tests/', type: 'directory' }
    ],
    document_pages: {
      title: 'Catalog Export',
      page_count: 2,
      pages: [
        { page: 1, text: 'Overview of the exported catalog.' },
        { page: 2, text: 'Detailed tool metadata.', thumbnail_uri: 'https://example.com/page-2.png' }
      ]
    },
    archive_bundle: {
      name: 'workspace-export.zip',
      format: 'zip',
      entries: [
        { path: 'src/components/AgentArtifactPanel.vue', size_bytes: 2048, compressed_size_bytes: 512 },
        { path: 'src/utils/agentArtifacts.js', size_bytes: 4096, compressed_size_bytes: 1024 }
      ]
    }
  })

  assert.ok(artifacts.find((artifact) => artifact.artifactType === 'directory_tree'))
  assert.ok(artifacts.find((artifact) => artifact.artifactType === 'document_pages'))
  assert.ok(artifacts.find((artifact) => artifact.artifactType === 'archive_bundle'))
  assert.equal(artifacts.find((artifact) => artifact.artifactType === 'directory_tree')?.payload?.summary?.file_count, 2)
  assert.equal(artifacts.find((artifact) => artifact.artifactType === 'document_pages')?.payload?.pages?.[1]?.page_number, 2)
  assert.equal(artifacts.find((artifact) => artifact.artifactType === 'archive_bundle')?.payload?.entry_count, 2)
})

test('summarizeArtifactFilters aggregates artifact types, child runs, and review states', () => {
  const artifacts = [
    normalizeArtifact({
      artifact_type: 'code_patch',
      name: 'Patch',
      payload: { files: [{ path: 'src/app.py', operation: 'modify', changed: true }], merge_policy: 'manual_review_required' },
      metadata: { child_run_id: 'child-1' }
    }),
    normalizeArtifact({
      artifact_type: 'review_findings',
      name: 'Findings',
      payload: { items: [{ title: 'Unsafe writeback', severity: 'high' }] },
      metadata: {}
    }),
    normalizeArtifact({
      artifact_type: 'verification_report',
      name: 'Verify',
      payload: { status: 'completed' },
      metadata: {}
    })
  ]

  const summary = summarizeArtifactFilters({ artifacts })

  assert.equal(summary.total, 3)
  assert.equal(summary.typeCounts.code_patch, 1)
  assert.equal(summary.childRunCounts['child-1'], 1)
  assert.equal(summary.childRunCounts.current_run, 2)
  assert.equal(summary.reviewCounts.needs_review, 1)
  assert.equal(summary.reviewCounts.blocked, 1)
  assert.equal(summary.reviewCounts.unreviewed, 1)
})

test('filterArtifacts filters by artifact type, child run, and review status', () => {
  const artifacts = [
    normalizeArtifact({
      artifact_type: 'code_patch',
      name: 'Patch',
      payload: { files: [{ path: 'src/a.py', operation: 'modify', changed: true }], merge_policy: 'manual_review_required' },
      metadata: { child_run_id: 'child-1' }
    }),
    normalizeArtifact({
      artifact_type: 'review_findings',
      name: 'Findings',
      payload: { items: [{ title: 'Unsafe writeback', severity: 'critical' }] },
      metadata: { child_run_id: 'child-2' }
    }),
    normalizeArtifact({
      artifact_type: 'verification_report',
      name: 'Verify',
      payload: { status: 'completed' },
      metadata: {}
    })
  ]

  assert.equal(filterArtifacts({ artifacts, artifactType: 'code_patch' }).length, 1)
  assert.equal(filterArtifacts({ artifacts, childRunId: 'child-2' }).length, 1)
  assert.equal(filterArtifacts({ artifacts, childRunId: 'current_run' }).length, 1)
  assert.equal(filterArtifacts({ artifacts, reviewStatus: 'blocked' }).length, 1)
  assert.equal(filterArtifacts({ artifacts, reviewStatus: 'needs_review' }).length, 1)
})

test('describeArtifact falls back to current run source labels', () => {
  const artifact = normalizeArtifact({
    artifact_type: 'verification_report',
    name: 'Verify',
    payload: { status: 'completed' },
    metadata: {}
  })

  const description = describeArtifact(artifact, new Map())

  assert.equal(description.typeLabel, '验证报告')
  assert.equal(description.sourceLabel, '当前 run')
  assert.equal(description.reviewStatus, 'unreviewed')
})

test('buildArtifactsFromToolResult merges structured content with code resources', () => {
  const artifacts = buildArtifactsFromToolResult({
    structured_content: {
      citations: [
        { title: 'Runtime Plan', url: 'https://example.com/runtime-plan' }
      ]
    },
    content: [
      {
        type: 'resource',
        resource: {
          name: 'agent_runtime.py',
          uri: 'file:///workspace/agent_runtime.py',
          mimeType: 'text/x-python',
          text: "print('hello')\n"
        }
      }
    ]
  }, {
    id: 'tool-call-2',
    stepId: 'step-2',
    toolName: 'inspect_workspace',
    toolKind: 'mcp'
  }, {
    includeAnswer: false
  })

  assert.ok(artifacts.find((artifact) => artifact.artifactType === 'citations'))
  const codeFiles = artifacts.find((artifact) => artifact.artifactType === 'code_files')
  assert.ok(codeFiles)
  assert.equal(codeFiles.payload.files[0].path, 'agent_runtime.py')
  assert.equal(codeFiles.payload.files[0].language, 'python')
})

test('buildArtifactsFromToolResult promotes media and file resources from MCP content', () => {
  const artifacts = buildArtifactsFromToolResult({
    content: [
      {
        type: 'image',
        mimeType: 'image/png',
        data: 'ZmFrZS1wbmc=',
        title: 'Runtime Diagram'
      },
      {
        type: 'resource',
        resource: {
          name: 'catalog-export.pdf',
          uri: 'https://example.com/catalog-export.pdf',
          mimeType: 'application/pdf'
        }
      }
    ]
  }, {
    id: 'tool-call-4',
    stepId: 'step-4',
    toolName: 'inspect_catalog',
    toolKind: 'mcp'
  }, {
    includeAnswer: false
  })

  const media = artifacts.find((artifact) => artifact.artifactType === 'media_gallery')
  const bundle = artifacts.find((artifact) => artifact.artifactType === 'file_bundle')
  assert.ok(media)
  assert.match(media.payload.items[0].uri, /^data:image\/png;base64,/)
  assert.ok(bundle)
  assert.equal(bundle.payload.files[0].uri, 'https://example.com/catalog-export.pdf')
})

test('buildArtifactsFromToolResult promotes embedded directory, document, and archive resources', () => {
  const artifacts = buildArtifactsFromToolResult({
    content: [
      {
        type: 'resource',
        resource: {
          name: 'workspace',
          children: [
            { path: 'src/agent_runtime.py', type: 'file' },
            { path: 'tests/', type: 'directory' }
          ]
        }
      },
      {
        type: 'resource',
        resource: {
          name: 'catalog-export.pdf',
          pages: [
            { page: 1, text: 'Summary page' },
            { page: 2, text: 'Tool details' }
          ]
        }
      },
      {
        type: 'resource',
        resource: {
          name: 'workspace-export.zip',
          format: 'zip',
          entries: [
            { path: 'src/agent_runtime.py', size_bytes: 1024, compressed_size_bytes: 256 }
          ]
        }
      }
    ]
  }, {
    id: 'tool-call-5',
    stepId: 'step-5',
    toolName: 'inspect_workspace',
    toolKind: 'mcp'
  }, {
    includeAnswer: false
  })

  const artifactTypes = artifacts.map((artifact) => artifact.artifactType)
  assert.ok(artifactTypes.includes('directory_tree'))
  assert.ok(artifactTypes.includes('document_pages'))
  assert.ok(artifactTypes.includes('archive_bundle'))
  assert.ok(artifacts.every((artifact) => artifact.metadata.tool_call_id === 'tool-call-5'))
})

test('buildArtifactsFromToolResult supports single MCP content object with resource link metadata', () => {
  const artifacts = buildArtifactsFromToolResult({
    content: {
      type: 'resource',
      title: 'Catalog Snapshot',
      resource_link: 'https://example.com/catalog/snapshot.json',
      mimeType: 'application/json',
      text: '{"status":"ready"}',
      annotations: { audience: ['admin'] },
      _meta: { origin: 'catalog-refresh' }
    }
  }, {
    id: 'tool-call-6',
    stepId: 'step-6',
    toolName: 'inspect_catalog',
    toolKind: 'mcp'
  }, {
    includeAnswer: false
  })

  const codeFiles = artifacts.find((artifact) => artifact.artifactType === 'code_files')
  assert.ok(codeFiles)
  assert.equal(codeFiles.payload.files[0].metadata.source, 'https://example.com/catalog/snapshot.json')
  assert.deepEqual(codeFiles.payload.files[0].metadata.annotations, { audience: ['admin'] })
  assert.deepEqual(codeFiles.payload.files[0].metadata._meta, { origin: 'catalog-refresh' })
})

test('buildArtifactsFromToolResult promotes nested structured content from MCP content entries', () => {
  const artifacts = buildArtifactsFromToolResult({
    content: [
      {
        type: 'resource',
        title: 'Preview',
        resourceLink: 'https://example.com/review/preview',
        structuredContent: {
          review_findings: [
            {
              title: 'Catalog drift',
              severity: 'medium',
              description: 'Tool output still exposes stale entries after refresh.'
            }
          ],
          task_plan: {
            summary: 'Tighten refresh path',
            steps: [
              { title: 'Invalidate stale catalog', status: 'pending' }
            ]
          }
        },
        annotations: { phase: 'post-refresh' }
      }
    ]
  }, {
    id: 'tool-call-7',
    stepId: 'step-7',
    toolName: 'review_catalog',
    toolKind: 'mcp'
  }, {
    includeAnswer: false
  })

  const findings = artifacts.find((artifact) => artifact.artifactType === 'review_findings')
  const plan = artifacts.find((artifact) => artifact.artifactType === 'task_plan')
  assert.ok(findings)
  assert.ok(plan)
  assert.deepEqual(findings.metadata.content_metadata.annotations, { phase: 'post-refresh' })
  assert.equal(findings.metadata.content_metadata.resourceLink, 'https://example.com/review/preview')
})

test('buildArtifactsFromToolResult parses JSON content items into task plan and findings artifacts', () => {
  const artifacts = buildArtifactsFromToolResult({
    content: [
      {
        type: 'text',
        text: JSON.stringify({
          review_findings: [
            {
              title: 'Missing resume reset',
              severity: 'high',
              description: 'Old tool artifacts leak into the new attempt.'
            }
          ],
          task_plan: {
            summary: 'Tighten resume behavior',
            steps: [
              { title: 'Reset execution context', status: 'completed' },
              { title: 'Add regression coverage', status: 'pending' }
            ]
          }
        })
      }
    ]
  }, {
    id: 'tool-call-3',
    stepId: 'step-3',
    toolName: 'analyze_run',
    toolKind: 'mcp'
  }, {
    includeAnswer: false
  })

  assert.ok(artifacts.find((artifact) => artifact.artifactType === 'review_findings'))
  assert.ok(artifacts.find((artifact) => artifact.artifactType === 'task_plan'))
})

test('buildRunArtifactsFromToolCalls merges promoted tool artifacts into existing run artifacts', () => {
  const artifacts = buildRunArtifactsFromToolCalls([
    {
      id: 'tool-call-1',
      stepId: 'step-1',
      toolName: 'list_pages',
      toolKind: 'mcp',
      status: 'completed',
      result: {
        structured_content: {
          rows: [
            { path: '/docs/a', title: 'A' },
            { path: '/docs/b', title: 'B' }
          ]
        }
      }
    }
  ], [
    {
      artifact_type: 'answer',
      name: 'Final Answer',
      payload: { text: 'Summarized result', format: 'markdown' }
    }
  ])

  assert.equal(artifacts[0].artifactType, 'answer')
  assert.equal(artifacts[1].artifactType, 'table')
  assert.equal(artifacts[1].name, 'list_pages - Rows')
})

test('mergeArtifacts deduplicates same payload even when names differ', () => {
  const artifacts = mergeArtifacts([
    {
      artifact_type: 'citations',
      name: 'Runtime Sources',
      payload: { items: [{ title: 'Runtime Plan', url: 'https://example.com/runtime-plan' }] }
    }
  ], [
    {
      artifact_type: 'citations',
      name: 'Citations',
      payload: { items: [{ title: 'Runtime Plan', url: 'https://example.com/runtime-plan' }] }
    }
  ])

  assert.equal(artifacts.length, 1)
  assert.equal(artifacts[0].name, 'Runtime Sources')
})
